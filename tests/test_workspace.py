from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_runner import resolve_runner_project_dir
from meta_writing.cli import cli
from meta_writing.workspace import (
    ProjectRuntimePaths,
    WORKFLOW_MODE_AUTOMATIC,
    WORKFLOW_MODE_MANUAL,
    WorkspaceManager,
    read_project_metadata,
)
from scripts.editorial_pass import resolve_editorial_project_dir


def test_create_project_creates_scaffold(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)

    project_dir = manager.create_project("book-two")

    assert project_dir == tmp_path / "novels" / "book-two"
    assert (project_dir / "story_data").is_dir()
    assert (project_dir / "chapters").is_dir()
    assert (project_dir / ".meta-writing-project.json").is_file()
    assert (project_dir / "creator_guidance.md").is_file()

    metadata = json.loads((project_dir / ".meta-writing-project.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "book-two"
    assert metadata["workflow_mode"] == WORKFLOW_MODE_MANUAL


def test_create_project_can_set_automatic_workflow_mode(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)

    project_dir = manager.create_project("book-two", workflow_mode=WORKFLOW_MODE_AUTOMATIC)

    metadata = read_project_metadata(project_dir)
    assert metadata is not None
    assert metadata.workflow_mode == WORKFLOW_MODE_AUTOMATIC


def test_set_project_workflow_mode_updates_metadata(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    project_dir = manager.create_project("book-two")

    manager.set_project_workflow_mode("book-two", WORKFLOW_MODE_AUTOMATIC)

    metadata = read_project_metadata(project_dir)
    assert metadata is not None
    assert metadata.workflow_mode == WORKFLOW_MODE_AUTOMATIC


def test_create_project_writes_creator_guidance_template(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)

    project_dir = manager.create_project("book-two")
    guidance_text = (project_dir / "creator_guidance.md").read_text(encoding="utf-8")

    assert "小说基本信息" in guidance_text
    assert "已写章节摘要" in guidance_text
    assert "写作要求" in guidance_text


def test_set_current_project_persists_selection(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create_project("book-one")
    manager.create_project("book-two")

    manager.set_current_project("book-two")

    reloaded = WorkspaceManager(tmp_path)
    assert reloaded.get_current_project() == "book-two"


def test_create_project_can_copy_existing_project_data(tmp_path: Path) -> None:
    source_dir = tmp_path / "legacy-project"
    (source_dir / "story_data").mkdir(parents=True)
    (source_dir / "chapters").mkdir()
    (source_dir / "story_data" / "story_core.yaml").write_text("hook: test\n", encoding="utf-8")
    (source_dir / "chapters" / "001.md").write_text("chapter one", encoding="utf-8")
    (source_dir / "learned_rules.md").write_text("rules", encoding="utf-8")

    manager = WorkspaceManager(tmp_path)
    project_dir = manager.create_project("book-copy", source_dir=source_dir)

    assert (project_dir / "story_data" / "story_core.yaml").read_text(encoding="utf-8") == "hook: test\n"
    assert (project_dir / "chapters" / "001.md").read_text(encoding="utf-8") == "chapter one"
    assert (project_dir / "learned_rules.md").read_text(encoding="utf-8") == "rules"


def test_create_project_can_move_existing_project_data(tmp_path: Path) -> None:
    source_dir = tmp_path / "legacy-project"
    (source_dir / "story_data").mkdir(parents=True)
    (source_dir / "chapters").mkdir()
    (source_dir / "story_data" / "story_core.yaml").write_text("hook: test\n", encoding="utf-8")
    (source_dir / "chapters" / "001.md").write_text("chapter one", encoding="utf-8")
    (source_dir / "learned_rules.md").write_text("rules", encoding="utf-8")
    (source_dir / "notes.md").write_text("keep me", encoding="utf-8")

    manager = WorkspaceManager(tmp_path)
    project_dir = manager.create_project("book-move", source_dir=source_dir, move_source=True)

    assert (project_dir / "story_data" / "story_core.yaml").read_text(encoding="utf-8") == "hook: test\n"
    assert (project_dir / "chapters" / "001.md").read_text(encoding="utf-8") == "chapter one"
    assert (project_dir / "learned_rules.md").read_text(encoding="utf-8") == "rules"
    assert not (source_dir / "story_data").exists()
    assert not (source_dir / "chapters").exists()
    assert not (source_dir / "learned_rules.md").exists()
    assert (source_dir / "notes.md").read_text(encoding="utf-8") == "keep me"


def test_resolve_project_dir_prefers_explicit_project_dir(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create_project("active-book")
    manager.set_current_project("active-book")

    explicit_project_dir = tmp_path / "manual-project"
    explicit_project_dir.mkdir()
    (explicit_project_dir / "story_data").mkdir()
    (explicit_project_dir / "chapters").mkdir()

    resolved = manager.resolve_project_dir(project_dir=explicit_project_dir)

    assert resolved == explicit_project_dir.resolve()


def test_resolve_project_dir_rejects_unknown_named_project(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)

    with pytest.raises(FileNotFoundError, match="missing-book"):
        manager.resolve_project_dir(project="missing-book")


def test_resolve_project_dir_uses_active_project_from_workspace_root(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    active_project = manager.create_project("active-book")
    manager.set_current_project("active-book")

    resolved = manager.resolve_project_dir(cwd=tmp_path)

    assert resolved == active_project.resolve()


def test_resolve_project_dir_prefers_active_project_over_legacy_root_files(tmp_path: Path) -> None:
    (tmp_path / "story_data").mkdir()
    (tmp_path / "chapters").mkdir()
    manager = WorkspaceManager(tmp_path)
    active_project = manager.create_project("active-book")
    manager.set_current_project("active-book")

    resolved = manager.resolve_project_dir(cwd=tmp_path)

    assert resolved == active_project.resolve()


def test_resolve_project_dir_rejects_implicit_legacy_root_project_in_workspace(tmp_path: Path) -> None:
    (tmp_path / "story_data").mkdir()
    (tmp_path / "chapters").mkdir()
    manager = WorkspaceManager(tmp_path)
    manager.create_project("active-book")

    with pytest.raises(FileNotFoundError, match="legacy novel files"):
        manager.resolve_project_dir(cwd=tmp_path)


def test_resolve_project_dir_uses_project_ancestor_for_nested_paths(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    project_dir = manager.create_project("active-book")

    resolved = manager.resolve_project_dir(cwd=project_dir / "chapters")

    assert resolved == project_dir.resolve()


def test_project_runtime_files_live_under_project_dir(tmp_path: Path) -> None:
    project_dir = tmp_path / "novels" / "book-two"
    project_dir.mkdir(parents=True)

    paths = ProjectRuntimePaths.for_project(project_dir)

    assert paths.learned_rules == project_dir / "learned_rules.md"
    assert paths.auto_runner_log == project_dir / "auto_runner_log.md"
    assert paths.editorial_report == project_dir / "editorial_report.md"


def test_migrate_legacy_root_project_moves_files_into_named_project(tmp_path: Path) -> None:
    (tmp_path / "story_data").mkdir()
    (tmp_path / "chapters").mkdir()
    (tmp_path / "story_data" / "story_core.yaml").write_text("hook: migrated\n", encoding="utf-8")
    (tmp_path / "chapters" / "001.md").write_text("chapter one", encoding="utf-8")
    (tmp_path / "learned_rules.md").write_text("rules", encoding="utf-8")
    manager = WorkspaceManager(tmp_path)

    project_dir = manager.migrate_legacy_root_project("legacy-book")

    assert project_dir == tmp_path / "novels" / "legacy-book"
    assert not (tmp_path / "story_data").exists()
    assert not (tmp_path / "chapters").exists()
    assert not (tmp_path / "learned_rules.md").exists()
    assert (project_dir / "story_data" / "story_core.yaml").read_text(encoding="utf-8") == "hook: migrated\n"
    assert (project_dir / "chapters" / "001.md").read_text(encoding="utf-8") == "chapter one"


def test_resolve_runner_project_dir_uses_active_workspace_project(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    active_project = manager.create_project("book-two")
    manager.set_current_project("book-two")

    resolved = resolve_runner_project_dir(
        workspace_dir=tmp_path,
        project=None,
        project_dir=None,
        cwd=tmp_path,
    )

    assert resolved == active_project.resolve()


def test_resolve_runner_project_dir_prefers_explicit_project_dir(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create_project("book-two")
    manager.set_current_project("book-two")
    explicit_project_dir = tmp_path / "manual-project"
    explicit_project_dir.mkdir()
    (explicit_project_dir / "story_data").mkdir()
    (explicit_project_dir / "chapters").mkdir()

    resolved = resolve_runner_project_dir(
        workspace_dir=tmp_path,
        project=None,
        project_dir=explicit_project_dir,
        cwd=tmp_path,
    )

    assert resolved == explicit_project_dir.resolve()


def test_resolve_runner_project_dir_rejects_unknown_project(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing-book"):
        resolve_runner_project_dir(
            workspace_dir=tmp_path,
            project="missing-book",
            project_dir=None,
            cwd=tmp_path,
        )


def test_resolve_editorial_project_dir_rejects_unknown_project(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing-book"):
        resolve_editorial_project_dir(
            workspace_dir=tmp_path,
            project="missing-book",
            project_dir=None,
            cwd=tmp_path,
        )


def test_project_create_command_creates_and_activates_project(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--workspace-dir", str(tmp_path), "project", "create", "book-two", "--activate"],
    )

    assert result.exit_code == 0
    manager = WorkspaceManager(tmp_path)
    assert (tmp_path / "novels" / "book-two").is_dir()
    assert manager.get_current_project() == "book-two"


def test_project_create_command_can_move_legacy_source_files(tmp_path: Path) -> None:
    (tmp_path / "story_data").mkdir()
    (tmp_path / "chapters").mkdir()
    (tmp_path / "story_data" / "story_core.yaml").write_text("hook: migrated\n", encoding="utf-8")
    (tmp_path / "chapters" / "001.md").write_text("chapter one", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--workspace-dir",
            str(tmp_path),
            "project",
            "create",
            "current-book",
            "--from-project-dir",
            str(tmp_path),
            "--move-source",
            "--activate",
        ],
    )

    assert result.exit_code == 0
    assert not (tmp_path / "story_data").exists()
    assert not (tmp_path / "chapters").exists()
    assert (tmp_path / "novels" / "current-book" / "story_data" / "story_core.yaml").read_text(
        encoding="utf-8"
    ) == "hook: migrated\n"


def test_project_list_marks_active_project(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create_project("book-one")
    manager.create_project("book-two", workflow_mode=WORKFLOW_MODE_AUTOMATIC)
    manager.set_current_project("book-two")

    runner = CliRunner()
    result = runner.invoke(cli, ["--workspace-dir", str(tmp_path), "project", "list"])

    assert result.exit_code == 0
    assert "book-one" in result.output
    assert "book-two" in result.output
    assert "(active)" in result.output
    assert "[manual]" in result.output
    assert "[automatic]" in result.output


def test_cli_rejects_unknown_project_option(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--workspace-dir", str(tmp_path), "--project", "missing-book", "status"],
    )

    assert result.exit_code != 0
    assert "Project does not exist: missing-book" in result.output


def test_project_migrate_root_command_moves_legacy_files(tmp_path: Path) -> None:
    (tmp_path / "story_data").mkdir()
    (tmp_path / "chapters").mkdir()
    (tmp_path / "story_data" / "story_core.yaml").write_text("hook: migrated\n", encoding="utf-8")
    (tmp_path / "chapters" / "001.md").write_text("chapter one", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--workspace-dir", str(tmp_path), "project", "migrate-root", "legacy-book", "--no-activate"],
    )

    assert result.exit_code == 0
    assert not (tmp_path / "story_data").exists()
    assert not (tmp_path / "chapters").exists()
    assert (tmp_path / "novels" / "legacy-book" / "chapters" / "001.md").read_text(encoding="utf-8") == "chapter one"


def test_project_mode_command_updates_current_project_workflow_mode(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create_project("book-two")
    manager.set_current_project("book-two")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--workspace-dir", str(tmp_path), "project", "mode", WORKFLOW_MODE_AUTOMATIC],
    )

    assert result.exit_code == 0
    metadata = read_project_metadata(tmp_path / "novels" / "book-two")
    assert metadata is not None
    assert metadata.workflow_mode == WORKFLOW_MODE_AUTOMATIC
