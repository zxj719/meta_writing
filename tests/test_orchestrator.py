"""Tests for Orchestrator (mocked LLM, full pipeline)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meta_writing.agents.planner import PlannerResult, PlotBranch
from meta_writing.agents.writer import WriterResult
from meta_writing.llm import LLMResponse
from meta_writing.orchestrator import Orchestrator, PipelineStage
from meta_writing.story_bible.loader import StoryBibleLoader


PLANNER_RESPONSE = json.dumps(
    {
        "branches": [
            {
                "title": "分支A",
                "outline": "林越调查地下室。",
                "characters_involved": ["林越", "苏晴"],
                "consequences": "发现秘密基地",
                "foreshadowing_opportunities": [],
                "satisfaction_type": "minor",
                "hook_type": "suspense",
                "hook_description": "听到熟悉的声音",
                "tension_impact": "tension_increase",
                "risk_level": "moderate",
            },
            {
                "title": "分支B",
                "outline": "苏晴暴露身份。",
                "characters_involved": ["林越", "苏晴"],
                "consequences": "关系破裂",
                "foreshadowing_opportunities": ["fs_002"],
                "satisfaction_type": "medium",
                "hook_type": "reversal",
                "hook_description": "苏晴能力失控",
                "tension_impact": "tension_increase",
                "risk_level": "bold",
            },
        ],
        "context_notes": "建议增加冲突。",
    }
)

CHAPTER_TEXT = "这是第四章正文。" * 800

CLEAN_REVIEW = json.dumps(
    {
        "passed": True,
        "issues": [],
        "foreshadowing_notes": "",
        "state_changes_detected": [
            {"character": "林越", "field": "location", "old_value": "学校", "new_value": "地下室"}
        ],
    }
)

FAILED_REVIEW = json.dumps(
    {
        "passed": False,
        "issues": [
            {
                "type": "character_state",
                "severity": "critical",
                "description": "角色状态矛盾",
                "location": "第3段",
                "suggestion": "补足状态变化",
            }
        ],
        "foreshadowing_notes": "",
        "state_changes_detected": [],
    }
)


def _make_response(text: str, model: str = "claude-sonnet-4-6") -> LLMResponse:
    return LLMResponse(
        text=text,
        usage={"input_tokens": 500, "output_tokens": 300},
        model=model,
        stop_reason="end_turn",
    )


@pytest.mark.asyncio
class TestOrchestrator:
    async def test_happy_path(self, tmp_project):
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            if call_count == 2:
                return _make_response(CHAPTER_TEXT)
            if call_count == 3:
                return _make_response(CLEAN_REVIEW)
            return _make_response(CHAPTER_TEXT)

        orch.llm.complete = AsyncMock(side_effect=mock_complete)
        branch_selector = AsyncMock(return_value=0)
        human_reviewer = AsyncMock(return_value=("approve", ""))
        state_confirmer = AsyncMock(return_value=True)

        with patch("meta_writing.orchestrator.subprocess"):
            chapter = await orch.generate_chapter(
                branch_selector=branch_selector,
                human_reviewer=human_reviewer,
                state_confirmer=state_confirmer,
            )

        assert chapter == CHAPTER_TEXT
        assert orch.state.stage == PipelineStage.DONE
        assert orch.state.chapter_number == 4
        branch_selector.assert_called_once()
        human_reviewer.assert_called_once()

    async def test_revision_loop(self, tmp_project):
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            if call_count == 2:
                return _make_response(CHAPTER_TEXT)
            if call_count == 3:
                return _make_response(FAILED_REVIEW)
            if call_count == 4:
                return _make_response(CHAPTER_TEXT)
            if call_count == 5:
                return _make_response(CHAPTER_TEXT + "（已修改）")
            if call_count == 6:
                return _make_response(CLEAN_REVIEW)
            return _make_response(CHAPTER_TEXT)

        orch.llm.complete = AsyncMock(side_effect=mock_complete)

        with patch("meta_writing.orchestrator.subprocess"):
            chapter = await orch.generate_chapter(
                branch_selector=AsyncMock(return_value=0),
                human_reviewer=AsyncMock(return_value=("approve", "")),
                state_confirmer=AsyncMock(return_value=True),
            )

        assert "已修改" in chapter
        assert orch.state.revision_count >= 1

    async def test_human_rejection(self, tmp_project):
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            if call_count == 2:
                return _make_response(CHAPTER_TEXT)
            if call_count == 3:
                return _make_response(CLEAN_REVIEW)
            return _make_response(CHAPTER_TEXT)

        orch.llm.complete = AsyncMock(side_effect=mock_complete)

        with pytest.raises(RuntimeError, match="rejected"):
            with patch("meta_writing.orchestrator.subprocess"):
                await orch.generate_chapter(
                    branch_selector=AsyncMock(return_value=0),
                    human_reviewer=AsyncMock(return_value=("reject", "质量不达标")),
                    state_confirmer=AsyncMock(return_value=True),
                )

    async def test_state_extraction(self, tmp_project):
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            if call_count == 2:
                return _make_response(CHAPTER_TEXT)
            if call_count == 3:
                return _make_response(CLEAN_REVIEW)
            return _make_response(CHAPTER_TEXT)

        orch.llm.complete = AsyncMock(side_effect=mock_complete)
        state_confirmer = AsyncMock(return_value=True)

        with patch("meta_writing.orchestrator.subprocess"):
            await orch.generate_chapter(
                branch_selector=AsyncMock(return_value=0),
                human_reviewer=AsyncMock(return_value=("approve", "")),
                state_confirmer=state_confirmer,
            )

        state_confirmer.assert_called_once()
        changes = state_confirmer.call_args[0][0]
        assert len(changes) == 1
        assert changes[0]["character"] == "林越"

    async def test_no_state_changes_is_noop(self, tmp_project):
        orch = Orchestrator(tmp_project, api_key="test")

        no_changes_review = json.dumps(
            {
                "passed": True,
                "issues": [],
                "foreshadowing_notes": "",
                "state_changes_detected": [],
            }
        )

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            if call_count == 2:
                return _make_response(CHAPTER_TEXT)
            if call_count == 3:
                return _make_response(no_changes_review)
            return _make_response(CHAPTER_TEXT)

        orch.llm.complete = AsyncMock(side_effect=mock_complete)
        state_confirmer = AsyncMock(return_value=True)

        with patch("meta_writing.orchestrator.subprocess"):
            await orch.generate_chapter(
                branch_selector=AsyncMock(return_value=0),
                human_reviewer=AsyncMock(return_value=("approve", "")),
                state_confirmer=state_confirmer,
            )

        state_confirmer.assert_not_called()

    async def test_uses_story_core_writing_preferences_and_creator_guidance(self, tmp_project):
        loader = StoryBibleLoader(tmp_project / "story_data")
        bible = loader.load()
        bible.core.chapter_target_chars = 2000
        bible.core.chapter_min_chars = 1600
        bible.core.writer_provider = "minimax"
        loader.save(bible)

        creative_guidance = "TARGET_2000\nTOMATO_FAST"
        (tmp_project / "creator_guidance.md").write_text(creative_guidance, encoding="utf-8")

        orch = Orchestrator(tmp_project, api_key="test")
        orch.planner.plan = AsyncMock(
            return_value=PlannerResult(
                branches=[
                    PlotBranch(
                        title="分支A",
                        outline="第一段短大纲",
                        characters_involved=["林越"],
                        consequences="",
                        foreshadowing_opportunities=[],
                        satisfaction_type="minor",
                        hook_type="suspense",
                        hook_description="",
                        tension_impact="tension_maintain",
                        risk_level="safe",
                    )
                ],
                context_notes="",
                raw_response=_make_response(PLANNER_RESPONSE),
            )
        )
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(
                chapter_text=CHAPTER_TEXT,
                raw_response=_make_response(CHAPTER_TEXT),
            )
        )
        orch.continuity.review = AsyncMock(
            return_value=MagicMock(passed=True, has_critical=False, state_changes=[])
        )
        orch.style_agent.review = AsyncMock(
            return_value=MagicMock(has_errors=False, issues=[])
        )
        orch.style_linter.check = MagicMock(return_value=[])
        orch._commit_chapter = AsyncMock()

        await orch.generate_chapter(
            branch_selector=AsyncMock(return_value=0),
            human_reviewer=AsyncMock(return_value=("approve", "")),
            state_confirmer=AsyncMock(return_value=True),
        )

        planner_guidance = orch.planner.plan.call_args.kwargs["additional_guidance"]
        writer_kwargs = orch.writer.write_with_expansion.call_args.kwargs
        assert creative_guidance == planner_guidance
        assert writer_kwargs["creative_guidance"] == creative_guidance
        assert writer_kwargs["target_chars"] == 2000
        assert writer_kwargs["min_chars"] == 1600
