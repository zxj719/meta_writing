"""Workspace management for multiple novel projects."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


PROJECTS_DIRNAME = "novels"
STATE_DIRNAME = ".meta-writing"
STATE_FILENAME = "workspace.json"
METADATA_FILENAME = ".meta-writing-project.json"
CREATOR_GUIDANCE_FILENAME = "creator_guidance.md"

PROJECT_COPY_ITEMS = (
    "story_data",
    "chapters",
    "learned_rules.md",
    "auto_runner_log.md",
    "editorial_report.md",
    CREATOR_GUIDANCE_FILENAME,
)

DEFAULT_CREATOR_GUIDANCE_TEMPLATE = """# Creator Guidance

## 小说基本信息
- 书名：
- 题材：
- 平台风格：

## 已写章节摘要
- 第1章：
- 第2章：
- 第3章：

## 当前人物状态
- 主角：
- 核心配角：
- 反派/阻力：

## 阶段大纲
- 第一阶段：
- 第二阶段：
- 第三阶段：

## 写作要求
- 目标单章字数：2000
- 每章至少一个笑点/爽点：
- 每章结尾保留钩子：
- 禁止出现的套路句式：
"""


def _sanitize_project_name(name: str) -> str:
    slug = name.strip()
    if not slug:
        raise ValueError("Project name cannot be empty")
    slug = slug.replace("\\", "-").replace("/", "-")
    return slug


@dataclass(frozen=True)
class ProjectRecord:
    name: str
    path: Path
    is_active: bool = False


@dataclass(frozen=True)
class ProjectRuntimePaths:
    learned_rules: Path
    auto_runner_log: Path
    editorial_report: Path

    @classmethod
    def for_project(cls, project_dir: str | Path) -> "ProjectRuntimePaths":
        project_dir = Path(project_dir)
        return cls(
            learned_rules=project_dir / "learned_rules.md",
            auto_runner_log=project_dir / "auto_runner_log.md",
            editorial_report=project_dir / "editorial_report.md",
        )


def resolve_workspace_project_dir(
    workspace_dir: str | Path,
    project: str | None = None,
    project_dir: str | Path | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Resolve a novel project directory from workspace-level inputs."""
    manager = WorkspaceManager(Path(workspace_dir).resolve())
    return manager.resolve_project_dir(
        project=project,
        project_dir=project_dir,
        cwd=cwd or Path.cwd(),
    )


class WorkspaceManager:
    """Manages a library of novel projects under a shared workspace root."""

    def __init__(self, root_dir: str | Path, projects_dirname: str = PROJECTS_DIRNAME) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.projects_dir = self.root_dir / projects_dirname
        self.state_dir = self.root_dir / STATE_DIRNAME
        self.state_path = self.state_dir / STATE_FILENAME

    def project_dir(self, name: str) -> Path:
        return self.projects_dir / _sanitize_project_name(name)

    def create_project(
        self,
        name: str,
        source_dir: str | Path | None = None,
        move_source: bool = False,
    ) -> Path:
        slug = _sanitize_project_name(name)
        project_dir = self.projects_dir / slug
        if project_dir.exists():
            raise FileExistsError(f"Project already exists: {slug}")

        self.projects_dir.mkdir(parents=True, exist_ok=True)
        project_dir.mkdir(parents=True)
        (project_dir / "story_data").mkdir()
        (project_dir / "chapters").mkdir()

        if source_dir is not None:
            source_path = Path(source_dir).resolve()
            self._copy_project_contents(source_path, project_dir)
            if move_source:
                self._remove_project_contents(source_path)

        metadata = {"name": slug}
        (project_dir / METADATA_FILENAME).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._ensure_creator_guidance(project_dir)
        return project_dir

    def list_projects(self) -> list[ProjectRecord]:
        if not self.projects_dir.exists():
            return []

        active = self.get_current_project()
        projects: list[ProjectRecord] = []
        for path in sorted(p for p in self.projects_dir.iterdir() if p.is_dir()):
            metadata_path = path / METADATA_FILENAME
            name = path.name
            if metadata_path.exists():
                try:
                    name = json.loads(metadata_path.read_text(encoding="utf-8")).get("name", path.name)
                except json.JSONDecodeError:
                    name = path.name
            projects.append(ProjectRecord(name=name, path=path, is_active=name == active))
        return projects

    def set_current_project(self, name: str) -> None:
        slug = _sanitize_project_name(name)
        self._require_project_dir(slug)

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"current_project": slug}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_current_project(self) -> str | None:
        if not self.state_path.exists():
            return None
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        current = data.get("current_project")
        return _sanitize_project_name(current) if current else None

    def resolve_project_dir(
        self,
        project: str | None = None,
        project_dir: str | Path | None = None,
        cwd: str | Path | None = None,
    ) -> Path:
        if project_dir is not None:
            return Path(project_dir).resolve()

        if project:
            return self._require_project_dir(_sanitize_project_name(project)).resolve()

        current_cwd = Path(cwd).resolve() if cwd is not None else self.root_dir
        current_project = self.get_current_project()
        if current_project and current_cwd == self.root_dir:
            return self._require_project_dir(current_project, label="Active project").resolve()

        current_project_dir = self._find_project_ancestor(current_cwd)
        if current_project_dir is not None:
            return current_project_dir

        if current_project:
            return self._require_project_dir(current_project, label="Active project").resolve()

        return current_cwd

    @staticmethod
    def _looks_like_project_dir(path: Path) -> bool:
        return (path / "story_data").exists() or (path / "chapters").exists()

    def _find_project_ancestor(self, path: Path) -> Path | None:
        for candidate in (path, *path.parents):
            if self._looks_like_project_dir(candidate):
                return candidate
            if candidate == self.root_dir:
                break
        return None

    def _require_project_dir(self, slug: str, label: str = "Project") -> Path:
        project_dir = self.project_dir(slug)
        if not project_dir.exists():
            raise FileNotFoundError(f"{label} does not exist: {slug}")
        return project_dir

    def _copy_project_contents(self, source_dir: Path, dest_dir: Path) -> None:
        for item_name in PROJECT_COPY_ITEMS:
            source_path = source_dir / item_name
            dest_path = dest_dir / item_name
            if not source_path.exists():
                continue
            if source_path.is_dir():
                shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, dest_path)

    def _remove_project_contents(self, source_dir: Path) -> None:
        for item_name in PROJECT_COPY_ITEMS:
            source_path = source_dir / item_name
            if not source_path.exists():
                continue
            if source_path.is_dir():
                shutil.rmtree(source_path)
            else:
                source_path.unlink()

    def _ensure_creator_guidance(self, project_dir: Path) -> None:
        guidance_path = project_dir / CREATOR_GUIDANCE_FILENAME
        if guidance_path.exists():
            return
        guidance_path.write_text(DEFAULT_CREATOR_GUIDANCE_TEMPLATE, encoding="utf-8")
