from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from auto_runner import (
    AutoRunner,
    BibleUpdater,
    BranchSelector,
    CarryoverCorrection,
    LESSON_EXTRACTOR_PROMPT,
    build_generation_guidance,
    load_carryover_correction,
    resolve_pov_character,
    save_carryover_correction,
)
from meta_writing.agents.planner import PlannerResult, PlotBranch
from meta_writing.agents.writer import WriterResult
from meta_writing.editorial_scorecard import (
    EditorialDimension,
    EditorialDimensionScore,
    EditorialScorecard,
)
from meta_writing.workspace import METADATA_FILENAME


def _make_branch() -> PlotBranch:
    return PlotBranch(
        title="Branch A",
        outline="A chapter that settles one school beat and plants the next hook.",
        characters_involved=["Lead"],
        consequences="",
        foreshadowing_opportunities=[],
        satisfaction_type="minor",
        hook_type="suspense",
        hook_description="",
        tension_impact="tension_maintain",
        risk_level="safe",
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
    result.scorecard = _make_scorecard(score, overrides)
    result.format_feedback.return_value = "continuity feedback"
    return result


def _make_style_result(
    score: float = 8.2,
    overrides: dict[EditorialDimension, float] | None = None,
):
    result = MagicMock()
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
    result.what_this_chapter_adds = "Adds pressure to the next beat."
    result.format_feedback.return_value = "theme feedback"
    return result


def test_carryover_correction_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "carryover.json"
    correction = CarryoverCorrection(
        chapter_number=7,
        issues_summary="Do not add an unseeded new major role.",
        new_lessons=["Fix scene focus before escalating conflict."],
    )

    save_carryover_correction(path, correction)

    loaded = load_carryover_correction(path)
    assert loaded == correction


def test_build_generation_guidance_prioritizes_latest_correction() -> None:
    guidance = build_generation_guidance(
        creator_guidance="Platform style: fast tomato pacing",
        learned_rules="# Learned rules\n- Keep the strawberry milk motif",
        carryover=CarryoverCorrection(
            chapter_number=3,
            issues_summary="Do not suddenly expand the family arc.",
            new_lessons=["Do not add unseeded side characters."],
        ),
    )

    latest_idx = guidance.index("Do not suddenly expand the family arc.")
    creator_idx = guidance.index("Platform style: fast tomato pacing")
    learned_idx = guidance.index("Keep the strawberry milk motif")

    assert latest_idx < creator_idx < learned_idx
    assert "Do not add unseeded side characters." in guidance


def test_save_carryover_correction_clears_file_when_no_issues(tmp_path: Path) -> None:
    path = tmp_path / "carryover.json"
    correction = CarryoverCorrection(
        chapter_number=4,
        issues_summary="Problem",
        new_lessons=["Rule"],
    )
    save_carryover_correction(path, correction)

    save_carryover_correction(path, None)

    assert not path.exists()


def test_auto_runner_falls_back_to_minimax_for_all_roles_when_only_minimax_auth(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    runner = AutoRunner(tmp_project, api_key="test", dry_run=True)

    assert runner.planner.llm is runner._minimax_llm
    assert runner.continuity_agent.llm is runner._minimax_llm
    assert runner.theme_agent.llm is runner._minimax_llm
    assert runner._deepseek_llm is runner._minimax_llm


def test_resolve_pov_character_prefers_story_bible_pov(sample_bible) -> None:
    pov_name = next(name for name, character in sample_bible.characters.items() if character.is_pov)
    other_name = next(name for name in sample_bible.characters if name != pov_name)
    branch = PlotBranch(
        title="Branch A",
        outline="A chapter outline.",
        characters_involved=[other_name, pov_name],
        consequences="",
        foreshadowing_opportunities=[],
        satisfaction_type="minor",
        hook_type="suspense",
        hook_description="",
        tension_impact="tension_maintain",
        risk_level="safe",
    )

    assert resolve_pov_character(sample_bible, branch) == pov_name


def test_lesson_extractor_prompt_is_project_agnostic() -> None:
    assert "克制美学/微感描写" not in LESSON_EXTRACTOR_PROMPT
    assert "番茄快节奏/强情绪" in LESSON_EXTRACTOR_PROMPT


def test_auto_runner_rejects_manual_workspace_project(tmp_project: Path) -> None:
    (tmp_project / METADATA_FILENAME).write_text(
        '{"name": "book-two", "workflow_mode": "manual"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manual workflow mode"):
        AutoRunner(tmp_project, api_key="test", dry_run=True)


@pytest.mark.asyncio
async def test_branch_selector_receives_project_style_guidance() -> None:
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value=MagicMock(text='{"selected_index": 0, "reasoning": "ok"}')
    )
    selector = BranchSelector(llm)

    await selector.select(
        branches=[_make_branch()],
        context_notes="notes",
        bible_summary="summary",
        chapter_number=6,
        style_guidance="Adult ceremony looks and first photo must land.",
    )

    user_msg = llm.complete.call_args.kwargs["messages"][0]["content"]
    assert "Adult ceremony looks and first photo must land." in user_msg


@pytest.mark.asyncio
async def test_run_chapter_passes_carryover_guidance_to_planner_writer_and_reviewers(tmp_project: Path) -> None:
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    save_carryover_correction(
        runner._carryover_correction_path,
        CarryoverCorrection(
            chapter_number=3,
            issues_summary="Do not suddenly expand the family arc.",
            new_lessons=["Do not add unseeded side characters."],
        ),
    )

    runner.planner.plan = AsyncMock(
        return_value=PlannerResult(
            branches=[_make_branch()],
            context_notes="",
            raw_response=MagicMock(),
        )
    )
    runner.branch_selector.select = AsyncMock(return_value=(0, "ok"))
    runner.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(chapter_text="Draft text", raw_response=MagicMock())
    )
    runner.continuity_agent.review = AsyncMock(return_value=_make_continuity_result(8.2))
    runner.style_agent.review = AsyncMock(return_value=_make_style_result(8.2))
    runner.theme_agent.review_chapter = AsyncMock(return_value=_make_theme_result(8.2))
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()
    runner._log_result = MagicMock()

    await runner.run_chapter(4)

    planner_guidance = runner.planner.plan.call_args.kwargs["additional_guidance"]
    writer_guidance = runner.writer.write_with_expansion.call_args.kwargs["creative_guidance"]
    assert "Do not suddenly expand the family arc." in planner_guidance
    assert "Do not add unseeded side characters." in planner_guidance
    assert planner_guidance == writer_guidance
    assert runner.continuity_agent.review.call_args.kwargs["creative_guidance"] == planner_guidance
    assert runner.style_agent.review.call_args.kwargs["creative_guidance"] == planner_guidance
    assert runner.theme_agent.review_chapter.call_args.kwargs["creative_guidance"] == planner_guidance


@pytest.mark.asyncio
async def test_run_chapter_revises_when_editorial_score_below_threshold(tmp_project: Path) -> None:
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    runner.planner.plan = AsyncMock(
        return_value=PlannerResult(
            branches=[_make_branch()],
            context_notes="",
            raw_response=MagicMock(),
        )
    )
    runner.branch_selector.select = AsyncMock(return_value=(0, "ok"))
    runner.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(chapter_text="Draft text", raw_response=MagicMock())
    )
    runner.writer.revise = AsyncMock(
        return_value=WriterResult(chapter_text="Revised draft", raw_response=MagicMock(), is_revision=True)
    )
    runner.continuity_agent.review = AsyncMock(
        side_effect=[_make_continuity_result(7.1), _make_continuity_result(8.2)]
    )
    runner.style_agent.review = AsyncMock(
        side_effect=[_make_style_result(7.3), _make_style_result(8.3)]
    )
    runner.theme_agent.review_chapter = AsyncMock(
        side_effect=[_make_theme_result(7.4), _make_theme_result(8.4)]
    )
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()

    result = await runner.run_chapter(4)

    assert runner.writer.revise.await_count == 1
    assert result.editorial_score >= 8.0
    review_artifact = tmp_project / "editorial_reviews" / "004.md"
    assert review_artifact.exists()
    artifact_text = review_artifact.read_text(encoding="utf-8")
    assert "章节审稿记录" in artifact_text
    assert "第2轮" in artifact_text
    assert "综合分" in artifact_text
    log_text = (tmp_project / "auto_runner_log.md").read_text(encoding="utf-8")
    assert "评分" in log_text


@pytest.mark.asyncio
async def test_run_chapter_revises_when_dimension_floor_fails(tmp_project: Path) -> None:
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    runner.planner.plan = AsyncMock(
        return_value=PlannerResult(
            branches=[_make_branch()],
            context_notes="",
            raw_response=MagicMock(),
        )
    )
    runner.branch_selector.select = AsyncMock(return_value=(0, "ok"))
    runner.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(chapter_text="Draft text", raw_response=MagicMock())
    )
    runner.writer.revise = AsyncMock(
        return_value=WriterResult(chapter_text="Polished draft", raw_response=MagicMock(), is_revision=True)
    )
    low_language = {EditorialDimension.LANGUAGE: 6.6}
    runner.continuity_agent.review = AsyncMock(
        side_effect=[
            _make_continuity_result(8.7, low_language),
            _make_continuity_result(8.2),
        ]
    )
    runner.style_agent.review = AsyncMock(
        side_effect=[
            _make_style_result(8.7, low_language),
            _make_style_result(8.3),
        ]
    )
    runner.theme_agent.review_chapter = AsyncMock(
        side_effect=[
            _make_theme_result(8.7, low_language),
            _make_theme_result(8.4),
        ]
    )
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()
    runner._log_result = MagicMock()

    result = await runner.run_chapter(4)

    assert runner.writer.revise.await_count == 1
    assert result.editorial_score >= 8.0


@pytest.mark.asyncio
async def test_run_chapter_raises_when_editorial_progress_stalls(tmp_project: Path) -> None:
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    runner.planner.plan = AsyncMock(
        return_value=PlannerResult(
            branches=[_make_branch()],
            context_notes="",
            raw_response=MagicMock(),
        )
    )
    runner.branch_selector.select = AsyncMock(return_value=(0, "ok"))
    runner.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(chapter_text="Draft text", raw_response=MagicMock())
    )
    runner.writer.revise = AsyncMock(
        side_effect=[
            WriterResult(chapter_text="Revision one", raw_response=MagicMock(), is_revision=True),
            WriterResult(chapter_text="Revision two", raw_response=MagicMock(), is_revision=True),
        ]
    )
    runner.continuity_agent.review = AsyncMock(
        side_effect=[
            _make_continuity_result(7.0),
            _make_continuity_result(7.1),
            _make_continuity_result(7.15),
        ]
    )
    runner.style_agent.review = AsyncMock(
        side_effect=[
            _make_style_result(7.0),
            _make_style_result(7.1),
            _make_style_result(7.15),
        ]
    )
    runner.theme_agent.review_chapter = AsyncMock(
        side_effect=[
            _make_theme_result(7.0),
            _make_theme_result(7.1),
            _make_theme_result(7.15),
        ]
    )
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()

    with pytest.raises(RuntimeError, match="stalled below threshold"):
        await runner.run_chapter(4)

    assert runner.writer.revise.await_count == 2
    runner._git_commit.assert_not_called()
    review_artifact = tmp_project / "editorial_reviews" / "004.md"
    assert review_artifact.exists()
    artifact_text = review_artifact.read_text(encoding="utf-8")
    assert "stalled_below_threshold" in artifact_text
    assert "第3轮" in artifact_text


def test_bible_updater_uses_resolved_pov_character_for_summary(sample_bible, tmp_project: Path) -> None:
    updater = BibleUpdater(MagicMock(), MagicMock())
    pov_name = next(name for name, character in sample_bible.characters.items() if character.is_pov)
    other_name = next(name for name in sample_bible.characters if name != pov_name)
    branch = PlotBranch(
        title="Branch A",
        outline="A chapter outline.",
        characters_involved=[pov_name, other_name],
        consequences="",
        foreshadowing_opportunities=[],
        satisfaction_type="minor",
        hook_type="suspense",
        hook_description="",
        tension_impact="tension_maintain",
        risk_level="safe",
    )

    updater._apply_update(
        sample_bible,
        chapter_number=4,
        chapter_text="Body text",
        branch=branch,
        data={
            "chapter_title": "Title",
            "summary": "Summary",
            "events": [],
            "characters_present": [pov_name, other_name],
            "character_updates": [],
            "timeline_entry": {},
        },
    )

    assert sample_bible.chapter_summaries[4].pov_character == pov_name
