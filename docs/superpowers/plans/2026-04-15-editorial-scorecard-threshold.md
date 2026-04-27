# Editorial Scorecard Threshold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared five-dimension chapter scorecard to the three editorial agents, aggregate their scores into a weighted overall score, and keep revising until the chapter reaches at least `8.0` or the revision cap is hit.

**Architecture:** Introduce a shared `editorial_scorecard` module that owns rubric definitions, score parsing, aggregation, and revision feedback formatting. Extend `continuity`, `style`, and `theme` reviews to emit structured scorecard data, then update `orchestrator.py` and `auto_runner.py` to gate acceptance on the aggregated score instead of pass/fail flags alone.

**Tech Stack:** Python 3.13, asyncio, pytest, dataclasses, existing LLM review agents

---

### Task 1: Add shared editorial scorecard model and aggregator

**Files:**
- Create: `meta_writing/meta_writing/editorial_scorecard.py`
- Test: `meta_writing/tests/test_editorial_scorecard.py`

- [ ] **Step 1: Write the failing tests**

```python
from meta_writing.editorial_scorecard import (
    EditorialDimension,
    EditorialDimensionScore,
    EditorialScorecard,
    aggregate_editorial_scorecards,
)


def make_scorecard(score: float) -> EditorialScorecard:
    return EditorialScorecard(
        dimensions={
            EditorialDimension.PLOT_TENSION: EditorialDimensionScore(score=score, reason="ok"),
            EditorialDimension.CHARACTERS: EditorialDimensionScore(score=score, reason="ok"),
            EditorialDimension.INFO_DESIGN: EditorialDimensionScore(score=score, reason="ok"),
            EditorialDimension.LANGUAGE: EditorialDimensionScore(score=score, reason="ok"),
            EditorialDimension.INSTRUCTION_FIT: EditorialDimensionScore(score=score, reason="ok"),
        }
    )


def test_aggregate_editorial_scorecards_uses_weighted_average() -> None:
    aggregate = aggregate_editorial_scorecards([make_scorecard(8.0), make_scorecard(9.0)])

    assert round(aggregate.overall_score, 2) == 8.5
    assert aggregate.passes_threshold(8.0) is True


def test_aggregate_editorial_scorecards_reports_low_dimensions() -> None:
    aggregate = aggregate_editorial_scorecards([make_scorecard(7.0)])

    assert aggregate.passes_threshold(8.0) is False
    assert EditorialDimension.PLOT_TENSION in aggregate.low_dimensions(8.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_editorial_scorecard.py -q`
Expected: FAIL because `meta_writing.editorial_scorecard` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from enum import Enum


class EditorialDimension(str, Enum):
    PLOT_TENSION = "plot_tension"
    CHARACTERS = "characters"
    INFO_DESIGN = "info_design"
    LANGUAGE = "language"
    INSTRUCTION_FIT = "instruction_fit"


DIMENSION_WEIGHTS = {
    EditorialDimension.PLOT_TENSION: 0.30,
    EditorialDimension.CHARACTERS: 0.25,
    EditorialDimension.INFO_DESIGN: 0.20,
    EditorialDimension.LANGUAGE: 0.15,
    EditorialDimension.INSTRUCTION_FIT: 0.10,
}


@dataclass(frozen=True)
class EditorialDimensionScore:
    score: float
    reason: str = ""


@dataclass(frozen=True)
class EditorialScorecard:
    dimensions: dict[EditorialDimension, EditorialDimensionScore]


@dataclass(frozen=True)
class AggregatedEditorialScore:
    dimensions: dict[EditorialDimension, float]
    overall_score: float

    def passes_threshold(self, threshold: float) -> bool:
        return self.overall_score >= threshold

    def low_dimensions(self, threshold: float) -> list[EditorialDimension]:
        return [dim for dim, score in self.dimensions.items() if score < threshold]


def aggregate_editorial_scorecards(
    scorecards: list[EditorialScorecard],
) -> AggregatedEditorialScore:
    dimension_scores = {}
    for dim in EditorialDimension:
        scores = [card.dimensions[dim].score for card in scorecards if dim in card.dimensions]
        dimension_scores[dim] = sum(scores) / len(scores)
    overall_score = sum(dimension_scores[dim] * weight for dim, weight in DIMENSION_WEIGHTS.items())
    return AggregatedEditorialScore(dimensions=dimension_scores, overall_score=overall_score)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_editorial_scorecard.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meta_writing/meta_writing/editorial_scorecard.py meta_writing/tests/test_editorial_scorecard.py
git commit -m "feat: add shared editorial scorecard model"
```

### Task 2: Extend the three editorial agents to emit scorecards

**Files:**
- Modify: `meta_writing/meta_writing/agents/continuity.py`
- Modify: `meta_writing/meta_writing/agents/style.py`
- Modify: `meta_writing/meta_writing/agents/theme.py`
- Modify: `meta_writing/meta_writing/prompt_profiles.py`
- Test: `meta_writing/tests/test_continuity.py`
- Test: `meta_writing/tests/test_prompt_profiles.py`
- Test: `meta_writing/tests/test_theme.py`

- [ ] **Step 1: Write the failing tests**

```python
from meta_writing.agents.style import StyleAgent
from meta_writing.llm import LLMResponse


def test_style_agent_parses_scorecard() -> None:
    agent = StyleAgent(llm=None)  # type: ignore[arg-type]
    response = LLMResponse(
        text='{"passed": true, "issues": [], "rhythm_notes": "ok", "scorecard": {"plot_tension": {"score": 8.0, "reason": "ok"}, "characters": {"score": 8.0, "reason": "ok"}, "info_design": {"score": 8.0, "reason": "ok"}, "language": {"score": 9.0, "reason": "ok"}, "instruction_fit": {"score": 8.0, "reason": "ok"}}}',
        usage={"input_tokens": 1, "output_tokens": 1},
        model="test",
        stop_reason="end_turn",
    )

    result = agent._parse_response(response)

    assert result.scorecard is not None
    assert result.scorecard.dimensions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_continuity.py tests/test_prompt_profiles.py tests/test_theme.py -q`
Expected: FAIL because scorecard fields and generic third-editor behavior are missing

- [ ] **Step 3: Write minimal implementation**

```python
# each agent result dataclass gains:
scorecard: EditorialScorecard | None = None

# each agent prompt gains a scorecard JSON requirement:
"scorecard": {
  "plot_tension": {"score": 0-10, "reason": "..."},
  "characters": {"score": 0-10, "reason": "..."},
  "info_design": {"score": 0-10, "reason": "..."},
  "language": {"score": 0-10, "reason": "..."},
  "instruction_fit": {"score": 0-10, "reason": "..."}
}

# theme/profile layer:
# tomato and generic projects should use the third editor too,
# but with a general story-editor prompt instead of literary-microfeel-only criteria.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_continuity.py tests/test_prompt_profiles.py tests/test_theme.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meta_writing/meta_writing/agents/continuity.py meta_writing/meta_writing/agents/style.py meta_writing/meta_writing/agents/theme.py meta_writing/meta_writing/prompt_profiles.py meta_writing/tests/test_continuity.py meta_writing/tests/test_prompt_profiles.py meta_writing/tests/test_theme.py
git commit -m "feat: add editorial scorecards to review agents"
```

### Task 3: Gate orchestrator revisions on aggregated score >= 8.0

**Files:**
- Modify: `meta_writing/meta_writing/orchestrator.py`
- Test: `meta_writing/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_revision_loop_continues_when_score_below_threshold(tmp_project):
    orch = Orchestrator(tmp_project, api_key="test")
    low_score = MagicMock(
        passed=True,
        has_critical=False,
        issues=[],
        scorecard=make_scorecard(7.2),
    )
    high_score = MagicMock(
        passed=True,
        has_critical=False,
        issues=[],
        scorecard=make_scorecard(8.4),
    )
    orch.planner.plan = AsyncMock(return_value=...)
    orch.writer.write_with_expansion = AsyncMock(return_value=WriterResult(chapter_text="first", raw_response=_make_response("first")))
    orch.writer.revise = AsyncMock(return_value=WriterResult(chapter_text="second", raw_response=_make_response("second"), is_revision=True))
    orch.continuity.review = AsyncMock(side_effect=[low_score, high_score])
    orch.style_agent.review = AsyncMock(side_effect=[low_score, high_score])
    orch.theme_agent.review_chapter = AsyncMock(side_effect=[low_score, high_score])
    orch.style_linter.check = MagicMock(return_value=[])
    orch._commit_chapter = AsyncMock()

    await orch.generate_chapter(...)

    assert orch.writer.revise.await_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py -q`
Expected: FAIL because orchestrator still breaks on issue flags only

- [ ] **Step 3: Write minimal implementation**

```python
EDITORIAL_PASS_THRESHOLD = 8.0

# during review loop:
aggregate = aggregate_editorial_scorecards(
    [
        continuity_result.scorecard,
        style_agent_result.scorecard,
        theme_agent_result.scorecard,
    ]
)
score_feedback = aggregate.format_feedback_for_writer(threshold=EDITORIAL_PASS_THRESHOLD)
needs_revision = (
    existing_issue_flags
    or not aggregate.passes_threshold(EDITORIAL_PASS_THRESHOLD)
)
if score_feedback:
    feedback_parts.append(score_feedback)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meta_writing/meta_writing/orchestrator.py meta_writing/tests/test_orchestrator.py
git commit -m "feat: gate manual revisions on editorial score threshold"
```

### Task 4: Gate auto-runner revisions on the same score threshold

**Files:**
- Modify: `meta_writing/auto_runner.py`
- Modify: `meta_writing/tests/test_auto_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_run_chapter_revises_when_editorial_score_below_threshold(tmp_project):
    runner = AutoRunner(tmp_project, api_key="test", dry_run=False)
    low = MagicMock(scorecard=make_scorecard(7.4), passed=True, has_critical=False, issues=[], has_errors=False, thematic_health="healthy")
    high = MagicMock(scorecard=make_scorecard(8.3), passed=True, has_critical=False, issues=[], has_errors=False, thematic_health="healthy")
    runner.continuity_agent.review = AsyncMock(side_effect=[low, high])
    runner.style_agent.review = AsyncMock(side_effect=[low, high])
    runner.theme_agent.review_chapter = AsyncMock(side_effect=[low, high])
    runner.writer.revise = AsyncMock(return_value=WriterResult(chapter_text="修订后", raw_response=MagicMock(), is_revision=True))

    await runner.run_chapter(4)

    assert runner.writer.revise.await_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auto_runner.py -q`
Expected: FAIL because auto-runner does not consider aggregated score yet

- [ ] **Step 3: Write minimal implementation**

```python
# after continuity/style/theme review:
aggregate = aggregate_editorial_scorecards([...])
needs_revision = existing_issue_flags or not aggregate.passes_threshold(8.0)
feedback_parts.append(aggregate.format_feedback_for_writer(threshold=8.0))

# log the score in result/log output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auto_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meta_writing/auto_runner.py meta_writing/tests/test_auto_runner.py
git commit -m "feat: add score-threshold revision loop to auto runner"
```

### Task 5: Run focused and full verification

**Files:**
- No code changes expected unless failures surface

- [ ] **Step 1: Run focused verification**

Run: `python -m pytest tests/test_editorial_scorecard.py tests/test_continuity.py tests/test_theme.py tests/test_orchestrator.py tests/test_auto_runner.py -q`
Expected: PASS

- [ ] **Step 2: Run full verification**

Run: `python -m pytest tests -q`
Expected: PASS

- [ ] **Step 3: Review requirements against implementation**

Checklist:
- Three editorial agents each emit a scorecard
- Weighted overall score is computed in code, not trusted to the model
- Threshold is `8.0`
- Revision loop continues when score is below threshold
- Writer receives score-driven revision feedback
- Tomato/manual projects keep a sane third-editor prompt instead of literary-theme contamination

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: enforce editorial scorecard thresholds across review loops"
```
