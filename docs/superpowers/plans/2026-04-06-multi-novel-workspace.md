# Multi-Novel Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `meta_writing` manage multiple novel projects from one tool repo so the current novel and future novels can stay isolated.

**Architecture:** Add a lightweight workspace manager that owns a `novels/` library plus an active-project pointer. Keep backward compatibility for legacy single-project directories, but let the CLI and automation tools resolve a project by explicit path, project name, or active selection.

**Tech Stack:** Python 3.12, Click, Rich, pytest

---

### Task 1: Define workspace behavior with tests

**Files:**
- Create: `tests/test_workspace.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_create_project_creates_scaffold(tmp_path):
    ...

def test_set_current_project_persists_selection(tmp_path):
    ...

def test_resolve_project_dir_prefers_explicit_project_dir(tmp_path):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbols from the new workspace module.

- [ ] **Step 3: Write minimal implementation**

Implement a new `meta_writing/workspace.py` module with:

```python
class WorkspaceManager:
    def create_project(...)
    def list_projects(...)
    def set_current_project(...)
    def get_current_project(...)
    def resolve_project_dir(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_workspace.py meta_writing/workspace.py
git commit -m "feat: add multi-novel workspace manager"
```

### Task 2: Add CLI project management commands

**Files:**
- Modify: `meta_writing/cli.py`
- Test: `tests/test_workspace.py`

- [ ] **Step 1: Write the failing CLI tests**

```python
def test_project_create_command_creates_and_activates_project(...):
    ...

def test_project_list_marks_active_project(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL because the `project` CLI subgroup does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add:

```python
@cli.group()
def project(): ...

@project.command("create")
@project.command("list")
@project.command("use")
@project.command("current")
```

Also add `--project` and `--workspace-dir` resolution at the CLI root.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meta_writing/cli.py tests/test_workspace.py
git commit -m "feat: add CLI commands for multi-novel projects"
```

### Task 3: Isolate automation files by project

**Files:**
- Modify: `auto_runner.py`
- Modify: `scripts/editorial_pass.py`
- Test: `tests/test_workspace.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_project_runtime_files_live_under_project_dir(tmp_path):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL because runtime helper paths are still global.

- [ ] **Step 3: Write minimal implementation**

Move project-scoped files under the resolved project directory:

```python
learned_rules.md
auto_runner_log.md
editorial_report.md
```

Also add `--project-dir`, `--project`, and `--workspace-dir` arguments to automation entry points.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auto_runner.py scripts/editorial_pass.py tests/test_workspace.py
git commit -m "feat: scope automation artifacts to individual novel projects"
```

### Task 4: Verify existing behavior still works

**Files:**
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add regression coverage for legacy project directories**

```python
async def test_orchestrator_still_works_with_explicit_project_dir(...):
    ...
```

- [ ] **Step 2: Run regression tests to verify they fail or cover the new behavior**

Run: `python -m pytest tests/test_orchestrator.py tests/test_workspace.py -v`
Expected: Existing orchestrator tests stay green and the new regression test proves explicit project directories still work.

- [ ] **Step 3: Adjust fixtures or helpers only if needed**

Keep legacy explicit-directory behavior intact.

- [ ] **Step 4: Run the targeted suite**

Run: `python -m pytest tests/test_workspace.py tests/test_orchestrator.py tests/test_story_bible.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_workspace.py tests/test_orchestrator.py tests/conftest.py
git commit -m "test: cover multi-novel workspace compatibility"
```
