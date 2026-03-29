"""Tests for Orchestrator (mocked LLM, full pipeline)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from meta_writing.orchestrator import Orchestrator, PipelineStage, MAX_REVISION_ITERATIONS
from meta_writing.llm import LLMResponse


PLANNER_RESPONSE = json.dumps({
    "branches": [
        {
            "title": "分支A",
            "outline": "林越调查地下室",
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
            "outline": "苏晴暴露身份",
            "characters_involved": ["林越", "苏晴"],
            "consequences": "关系破裂",
            "foreshadowing_opportunities": ["fs_002"],
            "satisfaction_type": "medium",
            "hook_type": "reversal",
            "hook_description": "苏晴的火焰异能暴露",
            "tension_impact": "tension_increase",
            "risk_level": "bold",
        },
    ],
    "context_notes": "建议增加冲突",
})

CHAPTER_TEXT = "这是第四章的正文内容。" * 800  # ~8000 Chinese chars, above auto-expansion threshold

CLEAN_REVIEW = json.dumps({
    "passed": True,
    "issues": [],
    "foreshadowing_notes": "",
    "state_changes_detected": [
        {"character": "林越", "field": "location", "old_value": "学校", "new_value": "地下室"},
    ],
})

FAILED_REVIEW = json.dumps({
    "passed": False,
    "issues": [
        {
            "type": "character_state",
            "severity": "critical",
            "description": "角色状态矛盾",
            "location": "第5段",
            "suggestion": "修改描述",
        }
    ],
    "foreshadowing_notes": "",
    "state_changes_detected": [],
})


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
        """Full pipeline: plan → select → write → review (pass) → commit."""
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Planner
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            elif call_count == 2:  # Writer
                return _make_response(CHAPTER_TEXT)
            elif call_count == 3:  # Continuity
                return _make_response(CLEAN_REVIEW)
            return _make_response(CHAPTER_TEXT)

        orch.llm.complete = AsyncMock(side_effect=mock_complete)

        # Callbacks
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
        """Continuity finds issues → writer revises → passes on retry."""
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Planner
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            elif call_count == 2:  # Writer (initial)
                return _make_response(CHAPTER_TEXT)
            elif call_count == 3:  # Continuity iter-0 (fails)
                return _make_response(FAILED_REVIEW)
            elif call_count == 4:  # Style Agent iter-0 (JSON parse fails → passes)
                return _make_response(CHAPTER_TEXT)
            elif call_count == 5:  # Writer (revision)
                return _make_response(CHAPTER_TEXT + "（已修改）")
            elif call_count == 6:  # Continuity iter-1 (passes)
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
        """Human rejects → pipeline raises error."""
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            elif call_count == 2:
                return _make_response(CHAPTER_TEXT)
            elif call_count == 3:
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
        """State changes from continuity review are confirmed and applied."""
        orch = Orchestrator(tmp_project, api_key="test")

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            elif call_count == 2:
                return _make_response(CHAPTER_TEXT)
            elif call_count == 3:
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

        # State confirmer should have been called with the detected changes
        state_confirmer.assert_called_once()
        changes = state_confirmer.call_args[0][0]
        assert len(changes) == 1
        assert changes[0]["character"] == "林越"

    async def test_no_state_changes_is_noop(self, tmp_project):
        """No state changes → confirmer not called."""
        orch = Orchestrator(tmp_project, api_key="test")

        no_changes_review = json.dumps({
            "passed": True, "issues": [],
            "foreshadowing_notes": "", "state_changes_detected": [],
        })

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_response(PLANNER_RESPONSE, "claude-opus-4-6")
            elif call_count == 2:
                return _make_response(CHAPTER_TEXT)
            elif call_count == 3:
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
