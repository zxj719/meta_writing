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
    should_enable_theme_review,
)
from meta_writing.agents.planner import PlannerResult, PlotBranch
from meta_writing.agents.writer import WriterResult
from meta_writing.workspace import METADATA_FILENAME


def test_carryover_correction_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "carryover.json"
    correction = CarryoverCorrection(
        chapter_number=7,
        issues_summary="不要新增没铺垫的新角色",
        new_lessons=["跑偏时先收束场景再推进剧情"],
    )

    save_carryover_correction(path, correction)

    loaded = load_carryover_correction(path)
    assert loaded == correction


def test_build_generation_guidance_prioritizes_latest_correction() -> None:
    guidance = build_generation_guidance(
        creator_guidance="平台风格：高梗密度",
        learned_rules="# 累积规则\n- 保留草莓牛奶意象",
        carryover=CarryoverCorrection(
            chapter_number=3,
            issues_summary="不要突然扩大家庭线",
            new_lessons=["不要新增没铺垫的新角色"],
        ),
    )

    latest_idx = guidance.index("上一轮必须纠偏的问题")
    creator_idx = guidance.index("平台风格：高梗密度")
    learned_idx = guidance.index("累积写作规则")

    assert latest_idx < creator_idx < learned_idx
    assert "不要突然扩大家庭线" in guidance
    assert "不要新增没铺垫的新角色" in guidance


def test_save_carryover_correction_clears_file_when_no_issues(tmp_path: Path) -> None:
    path = tmp_path / "carryover.json"
    correction = CarryoverCorrection(
        chapter_number=4,
        issues_summary="问题",
        new_lessons=["规则"],
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


def test_should_enable_theme_review_only_for_restrained_microfeel_projects() -> None:
    assert should_enable_theme_review(
        creator_guidance="平台风格：番茄女频，高梗密度，快节奏，系统向",
        target_satisfaction_type="高梗密度、快节奏、强情绪",
    ) is False
    assert should_enable_theme_review(
        creator_guidance="核心审美：克制美学，强调微感、留白和主题递进",
        target_satisfaction_type="克制美学",
    ) is True


def test_resolve_pov_character_prefers_story_bible_pov(sample_bible) -> None:
    branch = PlotBranch(
        title="分支A",
        outline="写一个收束校园线的章节",
        characters_involved=["林越", "苏晴"],
        consequences="",
        foreshadowing_opportunities=[],
        satisfaction_type="minor",
        hook_type="suspense",
        hook_description="",
        tension_impact="tension_maintain",
        risk_level="safe",
    )

    assert resolve_pov_character(sample_bible, branch) == "林越"


def test_lesson_extractor_prompt_is_project_agnostic() -> None:
    assert "克制美学/微感描写" not in LESSON_EXTRACTOR_PROMPT
    assert "例如番茄快节奏/强情绪，或克制微感/留白" in LESSON_EXTRACTOR_PROMPT


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
    branch = PlotBranch(
        title="鍒嗘敮A",
        outline="鍐欎竴涓暀瀹ら噷鐨勫揩鑺傚鎷夋壇鍦烘櫙",
        characters_involved=["鏋楄秺", "鑻忔櫞"],
        consequences="",
        foreshadowing_opportunities=[],
        satisfaction_type="minor",
        hook_type="suspense",
        hook_description="",
        tension_impact="tension_maintain",
        risk_level="safe",
    )

    await selector.select(
        branches=[branch],
        context_notes="notes",
        bible_summary="summary",
        chapter_number=6,
        style_guidance="骞冲彴椋庢牸锛氱暘鑼勫コ棰戯紝楂樻瀵嗗害锛屽揩鑺傚",
    )

    user_msg = llm.complete.call_args.kwargs["messages"][0]["content"]
    assert "骞冲彴椋庢牸锛氱暘鑼勫コ棰戯紝楂樻瀵嗗害锛屽揩鑺傚" in user_msg
    assert "鍏嬪埗缇庡" not in user_msg


@pytest.mark.asyncio
async def test_run_chapter_passes_carryover_guidance_to_planner_and_writer(tmp_project: Path) -> None:
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    save_carryover_correction(
        runner._carryover_correction_path,
        CarryoverCorrection(
            chapter_number=3,
            issues_summary="不要突然扩大家庭线",
            new_lessons=["不要新增没铺垫的新角色"],
        ),
    )

    runner.planner.plan = AsyncMock(
        return_value=PlannerResult(
            branches=[
                PlotBranch(
                    title="分支A",
                    outline="写一个收束校园线的章节",
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
            raw_response=MagicMock(),
        )
    )
    runner.branch_selector.select = AsyncMock(return_value=(0, "ok"))
    runner.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(chapter_text="正文", raw_response=MagicMock())
    )
    runner.continuity_agent.review = AsyncMock(
        return_value=MagicMock(passed=True, has_critical=False, issues=[])
    )
    runner.style_agent.review = AsyncMock(
        return_value=MagicMock(has_errors=False, issues=[])
    )
    runner.theme_agent.review_chapter = AsyncMock(
        return_value=MagicMock(thematic_health="healthy", has_critical=False, issues=[])
    )
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()
    runner._log_result = MagicMock()

    await runner.run_chapter(4)

    planner_guidance = runner.planner.plan.call_args.kwargs["additional_guidance"]
    planner_profile = runner.planner.plan.call_args.kwargs["prompt_profile"]
    writer_guidance = runner.writer.write_with_expansion.call_args.kwargs["creative_guidance"]
    assert "不要突然扩大家庭线" in planner_guidance
    assert "不要新增没铺垫的新角色" in planner_guidance
    assert planner_guidance == writer_guidance
    assert runner.writer.write_with_expansion.call_args.kwargs["pov_character"] == "林越"
    assert planner_profile.key == "tomato_romance"
    assert runner.writer.write_with_expansion.call_args.kwargs["prompt_profile"].key == "tomato_romance"
    assert runner.continuity_agent.review.call_args.kwargs["prompt_profile"].key == "tomato_romance"


@pytest.mark.asyncio
async def test_run_chapter_skips_theme_review_when_theme_review_disabled(tmp_project: Path) -> None:
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    runner.enable_theme_review = False

    runner.planner.plan = AsyncMock(
        return_value=PlannerResult(
            branches=[
                PlotBranch(
                    title="分支A",
                    outline="写一个收束校园线的章节",
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
            raw_response=MagicMock(),
        )
    )
    runner.branch_selector.select = AsyncMock(return_value=(0, "ok"))
    runner.writer.write_with_expansion = AsyncMock(
        return_value=WriterResult(chapter_text="正文", raw_response=MagicMock())
    )
    runner.continuity_agent.review = AsyncMock(
        return_value=MagicMock(passed=True, has_critical=False, issues=[])
    )
    runner.style_agent.review = AsyncMock(
        return_value=MagicMock(has_errors=False, issues=[])
    )
    runner.theme_agent.review_chapter = AsyncMock(
        return_value=MagicMock(thematic_health="healthy", has_critical=False, issues=[])
    )
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()
    runner._log_result = MagicMock()

    await runner.run_chapter(4)

    runner.theme_agent.review_chapter.assert_not_called()


def test_bible_updater_uses_resolved_pov_character_for_summary(sample_bible, tmp_project: Path) -> None:
    loader_project = tmp_project / "story_data"
    updater = BibleUpdater(MagicMock(), MagicMock())
    branch = PlotBranch(
        title="分支A",
        outline="写一个收束校园线的章节",
        characters_involved=["林越", "苏晴"],
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
        chapter_text="正文",
        branch=branch,
        data={
            "chapter_title": "标题",
            "summary": "摘要",
            "events": [],
            "characters_present": ["林越", "苏晴"],
            "character_updates": [],
            "timeline_entry": {},
        },
    )

    assert sample_bible.chapter_summaries[4].pov_character == "林越"
