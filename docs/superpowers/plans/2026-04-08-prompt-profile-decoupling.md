# Prompt Profile Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple project-specific aesthetics from shared agents so `meta_writing` can switch between tomato web-novel projects and restrained literary projects without prompt leakage.

**Architecture:** Introduce a prompt-profile module that classifies a project from its creator guidance and target satisfaction type, then feed profile-specific notes into `PlannerAgent`, `WriterAgent`, and `ContinuityAgent`. Shared agents keep generic base prompts; project-specific constraints move into explicit profile addenda.

**Tech Stack:** Python, pytest, shared agent classes, project guidance text.

---

### Task 1: Add Prompt Profile Abstraction

**Files:**
- Create: `meta_writing/prompt_profiles.py`
- Test: `tests/test_prompt_profiles.py`

- [ ] Add a `PromptProfile` dataclass with profile key, planner notes, writer notes, continuity notes, and whether writer anti-pattern examples should be enabled.
- [ ] Add `detect_prompt_profile(creator_guidance, target_satisfaction_type)` with at least `generic`, `tomato_romance`, and `literary_microfeel`.
- [ ] Write tests proving tomato guidance resolves to the tomato profile and microfeel guidance resolves to the literary profile.

### Task 2: Make Shared Agents Profile-Aware

**Files:**
- Modify: `meta_writing/agents/planner.py`
- Modify: `meta_writing/agents/writer.py`
- Modify: `meta_writing/agents/continuity.py`
- Test: `tests/test_writer.py`
- Test: `tests/test_auto_runner.py`

- [ ] Add optional prompt profile support to `PlannerAgent`, `WriterAgent`, and `ContinuityAgent`.
- [ ] Keep generic base system prompts in the agent files; append profile notes at request time instead of hard-coding literary rules into the base prompt.
- [ ] Make writer negative examples conditional on the active profile so tomato projects do not inherit literary anti-pattern examples.
- [ ] Write failing tests first for:
  - tomato writer prompts should not include literary anti-pattern examples like `沙发记得`
  - tomato branch selection/planning should include tomato style guidance, not fixed microfeel rules
  - lesson extraction prompt stays project-agnostic

### Task 3: Wire Profiles Into Orchestrator and AutoRunner

**Files:**
- Modify: `meta_writing/orchestrator.py`
- Modify: `auto_runner.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_auto_runner.py`

- [ ] Detect the project prompt profile from `creator_guidance.md` and `story_core.target_satisfaction_type`.
- [ ] Pass the resolved profile into shared agents.
- [ ] Preserve current `ThemeAgent` gating so restrained literary review only runs for the literary profile.
- [ ] Add tests that a tomato project instantiates shared agents with the tomato profile.

### Task 4: Verify No Shared-Agent Literary Leakage Remains

**Files:**
- Inspect: `meta_writing/agents/planner.py`
- Inspect: `meta_writing/agents/writer.py`
- Inspect: `meta_writing/agents/continuity.py`

- [ ] Run focused tests for prompt profiles and shared agents.
- [ ] Run the existing `tests/test_auto_runner.py`, `tests/test_orchestrator.py`, and `tests/test_writer.py`.
- [ ] If the profile system is stable, summarize remaining leakage sources still outside the shared prompt path, such as `ThemeAgent` and editorial scripts.
