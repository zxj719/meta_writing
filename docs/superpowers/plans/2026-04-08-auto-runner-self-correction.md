# AutoRunner Self-Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `auto_runner.py` carry forward the previous round's drift and review failures as explicit hard constraints before planning and writing the next chapter.

**Architecture:** Add a small structured carryover-correction state that `AutoRunner` writes after each chapter and loads before the next one. Merge that state ahead of `creator_guidance.md` and `learned_rules.md` so the next planner and writer both see a “fix these first” block instead of only a long accumulated rules file.

**Tech Stack:** Python, pytest, existing `meta_writing` runtime and `auto_runner.py`

---

### Task 1: Add failing tests for carryover correction state and guidance composition

**Files:**
- Create: `tests/test_auto_runner.py`
- Modify: `auto_runner.py`
- Test: `tests/test_auto_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from auto_runner import (
    CarryoverCorrection,
    build_generation_guidance,
    load_carryover_correction,
    save_carryover_correction,
)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auto_runner.py -q`
Expected: FAIL with import errors because carryover helpers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(eq=True)
class CarryoverCorrection:
    chapter_number: int
    issues_summary: str = ""
    new_lessons: list[str] = field(default_factory=list)


def load_carryover_correction(path: Path) -> CarryoverCorrection | None:
    ...


def save_carryover_correction(path: Path, correction: CarryoverCorrection | None) -> None:
    ...


def build_generation_guidance(
    creator_guidance: str,
    learned_rules: str,
    carryover: CarryoverCorrection | None,
) -> str:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auto_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_auto_runner.py auto_runner.py
git commit -m "test: add auto runner carryover correction coverage"
```

### Task 2: Thread carryover correction into AutoRunner planning and writing

**Files:**
- Modify: `auto_runner.py`
- Test: `tests/test_auto_runner.py`

- [ ] **Step 1: Write the failing integration-style test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from auto_runner import AutoRunner, CarryoverCorrection, save_carryover_correction
from meta_writing.agents.planner import PlannerResult, PlotBranch
from meta_writing.agents.writer import WriterResult


@pytest.mark.asyncio
async def test_run_chapter_passes_carryover_guidance_to_planner_and_writer(tmp_project):
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
    runner.continuity_agent.review = AsyncMock(return_value=MagicMock(passed=True, has_critical=False, issues=[]))
    runner.style_agent.review = AsyncMock(return_value=MagicMock(has_errors=False, issues=[]))
    runner.theme_agent.review_chapter = AsyncMock(return_value=MagicMock(thematic_health="healthy", has_critical=False, issues=[]))
    runner.style_linter.check = MagicMock(return_value=[])
    runner.lessons.extract_and_append = AsyncMock(return_value=[])
    runner.bible_updater.update = AsyncMock(side_effect=lambda **kwargs: kwargs["bible"])
    runner._git_commit = MagicMock()
    runner._log_result = MagicMock()

    await runner.run_chapter(4)

    planner_guidance = runner.planner.plan.call_args.kwargs["additional_guidance"]
    writer_guidance = runner.writer.write_with_expansion.call_args.kwargs["creative_guidance"]
    assert "不要突然扩大家庭线" in planner_guidance
    assert "不要新增没铺垫的新角色" in planner_guidance
    assert planner_guidance == writer_guidance
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auto_runner.py::test_run_chapter_passes_carryover_guidance_to_planner_and_writer -q`
Expected: FAIL because `AutoRunner` does not yet load or pass carryover correction state.

- [ ] **Step 3: Write minimal implementation**

```python
class AutoRunner:
    def __init__(...):
        ...
        self._carryover_correction_path = self.project_dir / ".auto_runner_correction.json"

    def _build_guidance(self, learned_rules: str) -> str:
        carryover = load_carryover_correction(self._carryover_correction_path)
        return build_generation_guidance(
            creator_guidance=self.creator_guidance,
            learned_rules=learned_rules,
            carryover=carryover,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auto_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auto_runner.py tests/test_auto_runner.py
git commit -m "feat: inject auto runner carryover correction guidance"
```

### Task 3: Persist the latest drift summary after each chapter and verify targeted tests

**Files:**
- Modify: `auto_runner.py`
- Test: `tests/test_auto_runner.py`

- [ ] **Step 1: Write the failing persistence test**

```python
def test_save_carryover_correction_clears_file_when_no_issues(tmp_path: Path) -> None:
    path = tmp_path / "carryover.json"
    correction = CarryoverCorrection(chapter_number=4, issues_summary="问题", new_lessons=["规则"])
    save_carryover_correction(path, correction)

    save_carryover_correction(path, None)

    assert not path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auto_runner.py::test_save_carryover_correction_clears_file_when_no_issues -q`
Expected: FAIL because clearing behavior does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
if issues_summary or new_lessons:
    save_carryover_correction(
        self._carryover_correction_path,
        CarryoverCorrection(
            chapter_number=chapter_number,
            issues_summary=issues_summary,
            new_lessons=new_lessons,
        ),
    )
else:
    save_carryover_correction(self._carryover_correction_path, None)
```

- [ ] **Step 4: Run targeted tests and the existing regression suite**

Run: `python -m pytest tests/test_auto_runner.py tests/test_workspace.py tests/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auto_runner.py tests/test_auto_runner.py
git commit -m "feat: persist auto runner carryover corrections"
```
