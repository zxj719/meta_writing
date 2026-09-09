"""Tests for Orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meta_writing.agents.planner import PlannerResult, PlotBranch
from meta_writing.agents.writer import WriterResult
from meta_writing.editorial_scorecard import (
    EditorialDimension,
    EditorialDimensionScore,
    EditorialScorecard,
)
from meta_writing.llm import LLMResponse
from tests.helpers import stub_agent_client
from meta_writing.orchestrator import Orchestrator, PipelineStage
from meta_writing.story_bible.loader import StoryBibleLoader


CHAPTER_TEXT = "This is chapter four body text." * 40



def _make_response(text: str, model: str = "test-model") -> LLMResponse:
    return LLMResponse(
        text=text,
        usage={"input_tokens": 500, "output_tokens": 300},
        model=model,
        stop_reason="end_turn",
    )


def _make_branch() -> PlotBranch:
    return PlotBranch(
        title="Branch A",
        outline="A school ceremony chapter with a soft reveal and a small hook.",
        characters_involved=["Lead", "MaleLead"],
        consequences="Push the ceremony thread one beat forward.",
        foreshadowing_opportunities=[],
        satisfaction_type="medium",
        hook_type="suspense",
        hook_description="A suspicious name appears on the guest list.",
        tension_impact="tension_increase",
        risk_level="moderate",
    )


def _make_plan_result() -> PlannerResult:
    return PlannerResult(
        branches=[_make_branch()],
        context_notes="Keep momentum without detonating the whole arc yet.",
        raw_response=_make_response("planner"),
    )


def _make_scorecard(
    default_score: float = 8.2,
    overrides: dict[EditorialDimension, float] | None = None,
) -> EditorialScorecard:
    dimensions = {
        EditorialDimension.PLOT_TENSION: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.CHARACTERS: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.INFO_DESIGN: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.LANGUAGE: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.INSTRUCTION_FIT: EditorialDimensionScore(score=default_score, reason="ok"),
    }
    for dimension, score in (overrides or {}).items():
        dimensions[dimension] = EditorialDimensionScore(score=score, reason="override")
    return EditorialScorecard(dimensions=dimensions)


def _make_continuity_result(
    score: float = 8.2,
    overrides: dict[EditorialDimension, float] | None = None,
):
    result = MagicMock()
    result.passed = True
    result.has_critical = False
    result.issues = []
    result.state_changes = []
    result.scorecard = _make_scorecard(score, overrides)
    result.format_feedback.return_value = "continuity feedback"
    return result


def _make_style_result(
    score: float = 8.2,
    overrides: dict[EditorialDimension, float] | None = None,
):
    result = MagicMock()
    result.passed = True
    result.has_errors = False
    result.issues = []
    result.scorecard = _make_scorecard(score, overrides)
    result.format_feedback.return_value = "style feedback"
    return result


def _make_theme_result(
    score: float = 8.2,
    overrides: dict[EditorialDimension, float] | None = None,
):
    result = MagicMock()
    result.thematic_health = "healthy"
    result.has_critical = False
    result.issues = []
    result.scorecard = _make_scorecard(score, overrides)
    result.arc_position_notes = "middle rise"
    result.what_this_chapter_adds = "Keeps pressure on the ceremony thread."
    result.format_feedback.return_value = "theme feedback"
    return result


@pytest.mark.asyncio
class TestOrchestrator:

    async def test_happy_path_uses_three_editor_agents(self, tmp_project):
        orch = Orchestrator(tmp_project, llm=stub_agent_client())
        orch.planner.plan = AsyncMock(return_value=_make_plan_result())
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(chapter_text=CHAPTER_TEXT, raw_response=_make_response(CHAPTER_TEXT))
        )
        orch.writer.revise = AsyncMock()
        orch.continuity.review = AsyncMock(return_value=_make_continuity_result(8.4))
        orch.style_agent.review = AsyncMock(return_value=_make_style_result(8.5))
        orch.theme_agent.review_chapter = AsyncMock(return_value=_make_theme_result(8.6))
        orch.style_linter.check = MagicMock(return_value=[])
        orch._commit_chapter = AsyncMock()

        chapter = await orch.generate_chapter(
            branch_selector=AsyncMock(return_value=0),
            human_reviewer=AsyncMock(return_value=("approve", "")),
            state_confirmer=AsyncMock(return_value=True),
        )

        assert chapter == CHAPTER_TEXT
        assert orch.state.stage == PipelineStage.DONE
        assert orch.writer.revise.await_count == 0
        orch.theme_agent.review_chapter.assert_awaited_once()
        assert orch.state.editorial_score is not None
        assert orch.state.editorial_score.overall_score >= 8.0
        review_artifact = tmp_project / "editorial_reviews" / "004.md"
        assert review_artifact.exists()
        artifact_text = review_artifact.read_text(encoding="utf-8")
        assert "章节审稿记录" in artifact_text
        assert "第1轮" in artifact_text
        assert "综合分" in artifact_text

    async def test_revision_loop_continues_when_score_below_threshold(self, tmp_project):
        orch = Orchestrator(tmp_project, llm=stub_agent_client())
        orch.planner.plan = AsyncMock(return_value=_make_plan_result())
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(chapter_text=CHAPTER_TEXT, raw_response=_make_response(CHAPTER_TEXT))
        )
        orch.writer.revise = AsyncMock(
            return_value=WriterResult(
                chapter_text=CHAPTER_TEXT + " revised",
                raw_response=_make_response(CHAPTER_TEXT + " revised"),
                is_revision=True,
            )
        )
        orch.continuity.review = AsyncMock(
            side_effect=[_make_continuity_result(7.2), _make_continuity_result(8.3)]
        )
        orch.style_agent.review = AsyncMock(
            side_effect=[_make_style_result(7.4), _make_style_result(8.4)]
        )
        orch.theme_agent.review_chapter = AsyncMock(
            side_effect=[_make_theme_result(7.1), _make_theme_result(8.5)]
        )
        orch.style_linter.check = MagicMock(return_value=[])
        orch._commit_chapter = AsyncMock()

        chapter = await orch.generate_chapter(
            branch_selector=AsyncMock(return_value=0),
            human_reviewer=AsyncMock(return_value=("approve", "")),
            state_confirmer=AsyncMock(return_value=True),
        )

        assert "revised" in chapter
        assert orch.writer.revise.await_count == 1
        feedback = orch.writer.revise.call_args.kwargs["feedback"]
        assert "评分卡" in feedback
        assert orch.state.editorial_score is not None
        assert orch.state.editorial_score.overall_score >= 8.0

    async def test_revision_loop_continues_when_dimension_floor_fails(self, tmp_project):
        orch = Orchestrator(tmp_project, llm=stub_agent_client())
        orch.planner.plan = AsyncMock(return_value=_make_plan_result())
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(chapter_text=CHAPTER_TEXT, raw_response=_make_response(CHAPTER_TEXT))
        )
        orch.writer.revise = AsyncMock(
            return_value=WriterResult(
                chapter_text=CHAPTER_TEXT + " polished",
                raw_response=_make_response(CHAPTER_TEXT + " polished"),
                is_revision=True,
            )
        )
        low_language = {EditorialDimension.LANGUAGE: 6.5}
        orch.continuity.review = AsyncMock(
            side_effect=[
                _make_continuity_result(8.8, low_language),
                _make_continuity_result(8.3),
            ]
        )
        orch.style_agent.review = AsyncMock(
            side_effect=[
                _make_style_result(8.6, low_language),
                _make_style_result(8.4),
            ]
        )
        orch.theme_agent.review_chapter = AsyncMock(
            side_effect=[
                _make_theme_result(8.7, low_language),
                _make_theme_result(8.5),
            ]
        )
        orch.style_linter.check = MagicMock(return_value=[])
        orch._commit_chapter = AsyncMock()

        chapter = await orch.generate_chapter(
            branch_selector=AsyncMock(return_value=0),
            human_reviewer=AsyncMock(return_value=("approve", "")),
            state_confirmer=AsyncMock(return_value=True),
        )

        assert "polished" in chapter
        assert orch.writer.revise.await_count == 1
        feedback = orch.writer.revise.call_args.kwargs["feedback"]
        assert "语言与描写质感" in feedback
        assert orch.state.editorial_score is not None
        assert orch.state.editorial_score.dimensions[EditorialDimension.LANGUAGE] >= 7.0

    async def test_hands_off_to_human_when_editorial_progress_stalls(self, tmp_project):
        orch = Orchestrator(tmp_project, llm=stub_agent_client())
        orch.planner.plan = AsyncMock(return_value=_make_plan_result())
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(chapter_text=CHAPTER_TEXT, raw_response=_make_response(CHAPTER_TEXT))
        )
        orch.writer.revise = AsyncMock(
            side_effect=[
                WriterResult(chapter_text=CHAPTER_TEXT + " rev1", raw_response=_make_response("rev1"), is_revision=True),
                WriterResult(chapter_text=CHAPTER_TEXT + " rev2", raw_response=_make_response("rev2"), is_revision=True),
            ]
        )
        orch.continuity.review = AsyncMock(
            side_effect=[
                _make_continuity_result(7.0),
                _make_continuity_result(7.1),
                _make_continuity_result(7.15),
            ]
        )
        orch.style_agent.review = AsyncMock(
            side_effect=[
                _make_style_result(7.0),
                _make_style_result(7.1),
                _make_style_result(7.15),
            ]
        )
        orch.theme_agent.review_chapter = AsyncMock(
            side_effect=[
                _make_theme_result(7.0),
                _make_theme_result(7.1),
                _make_theme_result(7.15),
            ]
        )
        orch.style_linter.check = MagicMock(return_value=[])
        orch._commit_chapter = AsyncMock()
        human_reviewer = AsyncMock(return_value=("approve", ""))

        chapter = await orch.generate_chapter(
            branch_selector=AsyncMock(return_value=0),
            human_reviewer=human_reviewer,
            state_confirmer=AsyncMock(return_value=True),
        )

        assert "rev2" in chapter
        assert orch.writer.revise.await_count == 2
        human_reviewer.assert_awaited_once()
        orch._commit_chapter.assert_awaited_once()
        assert orch.state.editorial_score is not None
        assert orch.state.editorial_score.overall_score < 8.0
        review_artifact = tmp_project / "editorial_reviews" / "004.md"
        artifact_text = review_artifact.read_text(encoding="utf-8")
        assert "stalled_below_threshold" in artifact_text
        assert "第3轮" in artifact_text

    async def test_uses_story_core_writing_preferences_creator_guidance_and_review_guidance(
        self,
        tmp_project,
    ):
        loader = StoryBibleLoader(tmp_project / "story_data")
        bible = loader.load()
        bible.core.chapter_target_chars = 2000
        bible.core.chapter_min_chars = 1600
        loader.save(bible)

        creative_guidance = "TARGET_2000\nADULT_CEREMONY_GLOWUP"
        (tmp_project / "creator_guidance.md").write_text(creative_guidance, encoding="utf-8")

        orch = Orchestrator(tmp_project, llm=stub_agent_client())
        orch.planner.plan = AsyncMock(return_value=_make_plan_result())
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(chapter_text=CHAPTER_TEXT, raw_response=_make_response(CHAPTER_TEXT))
        )
        orch.continuity.review = AsyncMock(return_value=_make_continuity_result(8.4))
        orch.style_agent.review = AsyncMock(return_value=_make_style_result(8.4))
        orch.theme_agent.review_chapter = AsyncMock(return_value=_make_theme_result(8.4))
        orch.style_linter.check = MagicMock(return_value=[])
        orch._commit_chapter = AsyncMock()

        await orch.generate_chapter(
            branch_selector=AsyncMock(return_value=0),
            human_reviewer=AsyncMock(return_value=("approve", "")),
            state_confirmer=AsyncMock(return_value=True),
        )

        planner_guidance = orch.planner.plan.call_args.kwargs["additional_guidance"]
        writer_kwargs = orch.writer.write_with_expansion.call_args.kwargs
        assert planner_guidance == creative_guidance
        assert writer_kwargs["creative_guidance"] == creative_guidance
        assert writer_kwargs["target_chars"] == 2000
        assert writer_kwargs["min_chars"] == 1600
        assert orch.continuity.review.call_args.kwargs["creative_guidance"] == creative_guidance
        assert orch.style_agent.review.call_args.kwargs["creative_guidance"] == creative_guidance
        assert orch.theme_agent.review_chapter.call_args.kwargs["creative_guidance"] == creative_guidance

    async def test_human_rejection_raises(self, tmp_project):
        orch = Orchestrator(tmp_project, llm=stub_agent_client())
        orch.planner.plan = AsyncMock(return_value=_make_plan_result())
        orch.writer.write_with_expansion = AsyncMock(
            return_value=WriterResult(chapter_text=CHAPTER_TEXT, raw_response=_make_response(CHAPTER_TEXT))
        )
        orch.continuity.review = AsyncMock(return_value=_make_continuity_result(8.4))
        orch.style_agent.review = AsyncMock(return_value=_make_style_result(8.4))
        orch.theme_agent.review_chapter = AsyncMock(return_value=_make_theme_result(8.4))
        orch.style_linter.check = MagicMock(return_value=[])

        with pytest.raises(RuntimeError, match="rejected"):
            with patch("meta_writing.orchestrator.subprocess"):
                await orch.generate_chapter(
                    branch_selector=AsyncMock(return_value=0),
                    human_reviewer=AsyncMock(return_value=("reject", "quality bar not met")),
                    state_confirmer=AsyncMock(return_value=True),
                )
