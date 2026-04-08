# Workflow Modes And Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit per-project `manual` vs `automatic` workflow modes and stop workspace-level cross-novel contamination from legacy root content.

**Architecture:** Store workflow mode in per-project metadata so `meta-writing generate` and `auto_runner.py` can enforce different execution paths without touching story content. Tighten workspace resolution so implicit root-level legacy novels are no longer selected inside a multi-project workspace, and add a first-class migration command to move legacy root content into `novels/<project>/`.

**Tech Stack:** Python, Click, pytest, existing `meta_writing` workspace manager and automation entry points

---

### Task 1: Cover workflow-mode metadata in workspace tests

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_workspace.py`
- Test: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_workspace.py`

- [ ] Add tests for default project workflow mode, explicit mode on create, and mode updates through metadata helpers.
- [ ] Add tests that implicit workspace resolution no longer falls back to root-level legacy story files once the workspace has named projects.
- [ ] Add a test for migrating root legacy project content into `novels/<name>/`.

### Task 2: Cover mode guards in manual and automatic entry points

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_orchestrator.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_auto_runner.py`
- Test: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_orchestrator.py`
- Test: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_auto_runner.py`

- [ ] Add a test that `Orchestrator` rejects projects marked `automatic`.
- [ ] Add a test that `AutoRunner` rejects projects marked `manual`.
- [ ] Keep existing bare-directory fixtures working when no project metadata exists.

### Task 3: Implement project metadata and workspace isolation

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\workspace.py`

- [ ] Add typed project metadata with a `workflow_mode` field and helpers to read, write, and update it.
- [ ] Set new projects to `manual` by default, with support for explicit `automatic`.
- [ ] Make implicit workspace resolution refuse legacy root project fallback inside a multi-project workspace.
- [ ] Add a workspace helper to migrate legacy root content into a named project.

### Task 4: Wire mode guards into CLI and automation entry points

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\cli.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\meta_writing\orchestrator.py`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\auto_runner.py`

- [ ] Add project create/mode/migrate-root CLI flows on top of workspace metadata helpers.
- [ ] Enforce `manual` mode in the interactive `generate` path.
- [ ] Enforce `automatic` mode in `auto_runner.py`.
- [ ] Keep explicit `--project-dir` behavior available for legacy standalone project directories.

### Task 5: Update docs and migrate the current legacy root novel

**Files:**
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\docs\multi-project-workspace.md`
- Modify: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\docs\new-novel-quickstart.md`
- Modify: workspace files under `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\`

- [ ] Document the difference between `manual` and `automatic` project modes.
- [ ] Document how to migrate root-level legacy novel files into a project.
- [ ] Move the current root-level legacy novel into its own project directory so the workspace matches the new rules.

### Task 6: Verify behavior end to end

**Files:**
- Test: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_workspace.py`
- Test: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_orchestrator.py`
- Test: `c:\Users\xingj\Documents\agent\novel_generator\meta_writing\tests\test_auto_runner.py`

- [ ] Run the targeted workspace/mode test subset.
- [ ] Run the full `tests` suite if the targeted subset passes.
- [ ] Inspect git diff to confirm only intended project files were migrated.
