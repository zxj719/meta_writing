# Novel Quality Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chapter-level quality gates that catch mechanical AI phrasing and missing appearance/expression/environment coverage, then feed actionable revision guidance back into the writing pipeline.

**Architecture:** Reuse the existing review loop instead of adding a new pipeline stage. Strengthen the zero-cost `StyleLinter` for mechanical pattern detection, expand the LLM-based `StyleAgent` prompt to audit description coverage and narrative monotony, and update the writer prompts so generation and revision both target the same quality bar.

**Tech Stack:** Python, pytest, existing `StyleLinter`, `StyleAgent`, `WriterAgent`, `Orchestrator`, `AutoRunner`

---

### Task 1: Lock the expected linter behavior with tests

**Files:**
- Modify: `meta_writing/tests/test_style_linter.py`

- [ ] Add failing tests for mechanical contrast-pattern overuse.
- [ ] Add failing tests for short sentence tic overuse.
- [ ] Run: `python -m pytest meta_writing/tests/test_style_linter.py -q`
- [ ] Confirm the new tests fail before implementation.

### Task 2: Lock the writer prompt changes with tests

**Files:**
- Modify: `meta_writing/tests/test_writer.py`

- [ ] Add failing assertions that writer prompts now require appearance, expression, environment coverage, and avoidance of mechanical sentence scaffolds.
- [ ] Run: `python -m pytest meta_writing/tests/test_writer.py -q`
- [ ] Confirm the new assertions fail before implementation.

### Task 3: Implement the mechanical-pattern detector

**Files:**
- Modify: `meta_writing/meta_writing/style_linter.py`

- [ ] Add global linter rules for repeated “X，但Y” scaffolds and repetitive short-sentence tics.
- [ ] Keep thresholds conservative so only clearly repetitive output is flagged.
- [ ] Ensure `format_feedback_for_writer()` emits actionable rewrite instructions for new error-level rules.

### Task 4: Upgrade generation and review prompts

**Files:**
- Modify: `meta_writing/meta_writing/agents/writer.py`
- Modify: `meta_writing/meta_writing/agents/style.py`
- Modify: `meta_writing/meta_writing/prompt_profiles.py`

- [ ] Add explicit writer requirements for appearance anchors, micro-expression detail, environment coverage, and mixed narrative techniques.
- [ ] Add style-review checks for mechanical language patterns, missing appearance/expression/environment, and purely linear “plot-only” narration.
- [ ] Keep prompt language project-aware and avoid reintroducing cross-project aesthetic pollution.

### Task 5: Verify pipeline integration

**Files:**
- Modify if needed: `meta_writing/meta_writing/orchestrator.py`
- Modify if needed: `meta_writing/auto_runner.py`

- [ ] Reuse the strengthened linter and style agent in the existing review loops.
- [ ] Only change orchestration code if the new checks need extra inputs or feedback handling.
- [ ] Keep both manual and automatic workflows on the same quality gate where practical.

### Task 6: Run verification

**Files:**
- No code changes expected

- [ ] Run targeted tests:
  - `python -m pytest meta_writing/tests/test_style_linter.py -q`
  - `python -m pytest meta_writing/tests/test_writer.py -q`
  - `python -m pytest meta_writing/tests/test_orchestrator.py -q`
  - `python -m pytest meta_writing/tests/test_auto_runner.py -q`
- [ ] If orchestration code changed, run the full suite:
  - `python -m pytest meta_writing/tests -q`
- [ ] Review output and only then report status.
