# 迁移到「当前智能体」后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `meta_writing` 的全部 LLM 调用从硬编码 MiniMax/DeepSeek/Anthropic 三供应商，改为子进程调用当前环境的智能体 CLI（Claude Code 或 Codex），并移除自动生成链路与 `workflow_mode` 概念。

**Architecture:** 新建单一 `AgentClient`，其 `complete()` 签名与现有 `LLMClient.complete()` 完全一致，因此五个 agent 的调用点不需改动。先加新代码（Task 2-4），再切换调用点并删除旧代码（Task 5），每个任务结束时测试套件都是绿的。

**Tech Stack:** Python 3.12+、asyncio subprocess、pytest + pytest-asyncio、click、Pydantic v2

**Spec:** [`docs/superpowers/specs/2026-09-09-agent-backend-migration-design.md`](../specs/2026-09-09-agent-backend-migration-design.md)

## Global Constraints

- 工作目录：`C:\Users\xingj\Documents\agent\novel_generator\meta_writing`，分支 `master`
- **绝不修改 wolfgame 仓库的任何文件**（Web 工作台、Worker、ECS 部署均不在范围内）
- 测试中**绝不真实 spawn 子进程**，全部 mock `asyncio.create_subprocess_exec`
- 命令中**禁止**出现 `--bare`（它会绕开 OAuth 登录态，实测返回 `Not logged in`）
- 命令中**禁止**出现 `--model`（模型由当前智能体会话决定）
- Claude Code 调用必须禁用全部工具
- `MAX_RETRIES = 3`，退避 `2 ** (attempt + 1)` 秒
- 默认超时 900 秒，可经 `META_WRITING_AGENT_TIMEOUT` 覆盖
- 每个任务最后一步都是 commit；commit message 用中文，结尾附
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- 每次跑测试用 `python -m pytest -q`（在仓库根目录）

---

### Task 1: 移除 auto_runner 与 workflow_mode

**Files:**
- Delete: `auto_runner.py`
- Delete: `tests/test_auto_runner.py`
- Delete: `docs/superpowers/plans/2026-04-08-auto-runner-self-correction.md`
- Modify: `meta_writing/workspace.py`
- Modify: `meta_writing/cli.py`
- Modify: `meta_writing/orchestrator.py:35,88-94`
- Test: `tests/test_workspace.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: 无
- Produces: `WorkspaceManager.create_project(name, source_dir=None, move_source=False)`（不再有 `workflow_mode` 参数）；`ProjectMetadata(name)`；`ProjectRecord(name, path, is_active)`；`ProjectRuntimePaths(learned_rules, editorial_report, editorial_reviews_dir)`

> 这三个文件在工作区中已处于「已删除、未提交」状态。`tests/test_workspace.py:9` 的 `from auto_runner import resolve_runner_project_dir` **正是当前整个测试套件 collection error 的原因**——本任务首先修掉它。

- [ ] **Step 1: 确认当前测试套件确实是坏的**

Run: `python -m pytest -q`
Expected: `ERROR collecting tests/test_workspace.py` — `ModuleNotFoundError: No module named 'auto_runner'`

- [ ] **Step 2: 删除 test_workspace.py 里的 auto_runner 依赖与 workflow_mode 用例**

在 `tests/test_workspace.py` 中：

删除第 9 行的 import：

```python
from auto_runner import resolve_runner_project_dir
```

把 workspace import 块改为：

```python
from meta_writing.workspace import (
    ProjectRuntimePaths,
    WorkspaceManager,
    read_project_metadata,
)
```

`test_create_project_creates_scaffold` 末尾两行改为（删掉 workflow_mode 断言）：

```python
    metadata = json.loads((project_dir / ".meta-writing-project.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "book-two"
```

**整体删除**这三个测试函数：
- `test_create_project_can_set_automatic_workflow_mode`
- `test_set_project_workflow_mode_updates_metadata`
- `test_project_mode_command_updates_current_project_workflow_mode`

`test_project_runtime_files_live_under_project_dir` 删掉这一行：

```python
    assert paths.auto_runner_log == project_dir / "auto_runner_log.md"
```

`test_project_list_marks_active_project` 改为：

```python
def test_project_list_marks_active_project(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.create_project("book-one")
    manager.create_project("book-two")
    manager.set_current_project("book-two")

    runner = CliRunner()
    result = runner.invoke(cli, ["--workspace-dir", str(tmp_path), "project", "list"])

    assert result.exit_code == 0
    assert "book-one" in result.output
    assert "book-two" in result.output
    assert "(active)" in result.output
```

再全文搜索 `resolve_runner_project_dir`，删除任何仍在使用它的测试函数。

- [ ] **Step 3: 删除 test_orchestrator.py 的自动模式用例**

删除 `test_rejects_automatic_workspace_project` 整个函数（`tests/test_orchestrator.py:117-124`），以及顶部现在无人使用的 import：

```python
from meta_writing.workspace import METADATA_FILENAME
```

- [ ] **Step 4: 从 workspace.py 移除 workflow_mode**

在 `meta_writing/workspace.py` 中：

删除这四行常量：

```python
WORKFLOW_MODE_MANUAL = "manual"
WORKFLOW_MODE_AUTOMATIC = "automatic"
SUPPORTED_WORKFLOW_MODES = (WORKFLOW_MODE_MANUAL, WORKFLOW_MODE_AUTOMATIC)
```

删除整个 `_normalize_workflow_mode()` 函数。

`PROJECT_COPY_ITEMS` 删掉 `"auto_runner_log.md"`：

```python
PROJECT_COPY_ITEMS = (
    "story_data",
    "chapters",
    "learned_rules.md",
    "editorial_report.md",
    CREATOR_GUIDANCE_FILENAME,
)
```

三个 dataclass 改为：

```python
@dataclass(frozen=True)
class ProjectRecord:
    name: str
    path: Path
    is_active: bool = False


@dataclass(frozen=True)
class ProjectMetadata:
    name: str


@dataclass(frozen=True)
class ProjectRuntimePaths:
    learned_rules: Path
    editorial_report: Path
    editorial_reviews_dir: Path

    @classmethod
    def for_project(cls, project_dir: str | Path) -> "ProjectRuntimePaths":
        project_dir = Path(project_dir)
        return cls(
            learned_rules=project_dir / "learned_rules.md",
            editorial_report=project_dir / "editorial_report.md",
            editorial_reviews_dir=project_dir / "editorial_reviews",
        )
```

读写元数据改为：

```python
def read_project_metadata(project_dir: str | Path) -> ProjectMetadata | None:
    metadata_path = Path(project_dir) / METADATA_FILENAME
    if not metadata_path.exists():
        return None
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return ProjectMetadata(name=str(data.get("name") or Path(project_dir).name))


def write_project_metadata(project_dir: str | Path, metadata: ProjectMetadata) -> None:
    metadata_path = Path(project_dir) / METADATA_FILENAME
    metadata_path.write_text(
        json.dumps({"name": metadata.name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

`create_project` 去掉 `workflow_mode` 参数与相关两行：

```python
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

        write_project_metadata(project_dir, ProjectMetadata(name=slug))
        self._ensure_creator_guidance(project_dir)
        return project_dir
```

`list_projects` 里构造 `ProjectRecord` 去掉 `workflow_mode=` 一行。

**整体删除**这两个方法：`set_project_workflow_mode`、`workflow_mode_for_project_dir`。

`migrate_legacy_root_project` 去掉 `workflow_mode` 参数，调用 `create_project` 时也不再传。

- [ ] **Step 5: 从 cli.py 移除 workflow_mode**

在 `meta_writing/cli.py` 中：

workspace import 改为：

```python
from .workspace import WorkspaceManager
```

**整体删除** `_enforce_project_workflow_mode()` 函数，以及 `generate` 命令里对它的调用（第 297 行）。

`project create`：删除 `--mode` 装饰器与函数参数、`create_project` 的 `workflow_mode=` 实参。

`project migrate-root`：同上。

**整体删除** `project mode` 子命令（`@project.command("mode")` 起整个 `project_mode` 函数）。

`project list` 的输出行改为：

```python
        console.print(f"{item.name}{suffix}", markup=False)
```

- [ ] **Step 6: 从 orchestrator.py 移除模式守卫**

在 `meta_writing/orchestrator.py` 中，import 改为：

```python
from .workspace import read_project_metadata
```

删除 `__init__` 里这段（第 88-94 行附近）：

```python
        project_metadata = read_project_metadata(self.project_dir)
        if project_metadata and project_metadata.workflow_mode == WORKFLOW_MODE_AUTOMATIC:
            raise ValueError(
                "This project is configured for automatic workflow mode. "
                "Use auto_runner.py or switch the project back to manual workflow mode."
            )
```

删除后若 `read_project_metadata` 不再被使用，把它从 import 里一并去掉。

- [ ] **Step 7: 删除 auto_runner 三件套**

```bash
git rm -f auto_runner.py tests/test_auto_runner.py docs/superpowers/plans/2026-04-08-auto-runner-self-correction.md
```

（这三个文件在磁盘上已不存在，`git rm` 用于把删除登记进索引。）

- [ ] **Step 8: 跑测试**

Run: `python -m pytest -q`
Expected: PASS，无 collection error。若有 `NameError` / `ImportError`，说明还有 workflow_mode 残留，搜索 `workflow_mode` 与 `auto_runner` 补齐。

- [ ] **Step 9: 确认没有残留引用**

Run: `rg -n "workflow_mode|auto_runner|WORKFLOW_MODE" meta_writing/ scripts/ tests/`
Expected: 无输出

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: 移除自动生成链路与 workflow_mode 概念

删除 auto_runner.py 及其测试与设计文档。自动链路移除后 workflow_mode 只剩
一个合法值，成为死重量，一并移除：project mode 子命令、--mode 选项、
project list 的模式显示、orchestrator 的模式守卫。

顺带修复 tests/test_workspace.py 对 auto_runner 的 import——它此前导致整个
测试套件 collection error。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: AgentClient 骨架 — 智能体探测

**Files:**
- Modify: `meta_writing/llm.py`（**追加**，暂不删除旧 client）
- Test: `tests/test_agent_client.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `AgentSpec(kind: str, argv: tuple[str, ...])`；`detect_agent(env: Mapping[str, str] | None = None) -> AgentSpec`；`AgentNotFoundError`；`AgentInvocationError`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_agent_client.py`：

```python
"""Tests for the agent-CLI backed LLM client."""

from __future__ import annotations

import pytest

from meta_writing.llm import AgentNotFoundError, AgentSpec, detect_agent


def test_explicit_command_wins_over_everything(monkeypatch):
    monkeypatch.setattr("meta_writing.llm.shutil.which", lambda name: f"/usr/bin/{name}")
    env = {
        "META_WRITING_AGENT_CMD": "my-agent --flag",
        "META_WRITING_AGENT": "codex",
    }

    spec = detect_agent(env)

    assert spec.kind == "custom"
    assert spec.argv == ("my-agent", "--flag")


def test_named_agent_wins_over_path_order(monkeypatch):
    monkeypatch.setattr("meta_writing.llm.shutil.which", lambda name: f"/usr/bin/{name}")

    spec = detect_agent({"META_WRITING_AGENT": "codex"})

    assert spec.kind == "codex"
    assert spec.argv == ("/usr/bin/codex",)


def test_named_agent_must_be_installed(monkeypatch):
    monkeypatch.setattr("meta_writing.llm.shutil.which", lambda name: None)

    with pytest.raises(AgentNotFoundError, match="codex"):
        detect_agent({"META_WRITING_AGENT": "codex"})


def test_named_agent_rejects_unknown_value(monkeypatch):
    monkeypatch.setattr("meta_writing.llm.shutil.which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(AgentNotFoundError, match="META_WRITING_AGENT"):
        detect_agent({"META_WRITING_AGENT": "gpt"})


def test_path_detection_prefers_claude(monkeypatch):
    monkeypatch.setattr(
        "meta_writing.llm.shutil.which",
        lambda name: "/usr/bin/claude" if name == "claude" else "/usr/bin/codex",
    )

    spec = detect_agent({})

    assert spec.kind == "claude"


def test_path_detection_falls_back_to_codex(monkeypatch):
    monkeypatch.setattr(
        "meta_writing.llm.shutil.which",
        lambda name: "/usr/bin/codex" if name == "codex" else None,
    )

    spec = detect_agent({})

    assert spec.kind == "codex"


def test_no_agent_available_lists_all_three_config_options(monkeypatch):
    monkeypatch.setattr("meta_writing.llm.shutil.which", lambda name: None)

    with pytest.raises(AgentNotFoundError) as excinfo:
        detect_agent({})

    message = str(excinfo.value)
    assert "META_WRITING_AGENT_CMD" in message
    assert "META_WRITING_AGENT" in message
    assert "claude" in message and "codex" in message


def test_blank_explicit_command_is_ignored(monkeypatch):
    monkeypatch.setattr("meta_writing.llm.shutil.which", lambda name: "/usr/bin/claude")

    spec = detect_agent({"META_WRITING_AGENT_CMD": "   "})

    assert spec.kind == "claude"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_agent_client.py -q`
Expected: FAIL — `ImportError: cannot import name 'AgentNotFoundError'`

- [ ] **Step 3: 在 llm.py 顶部追加实现**

在 `meta_writing/llm.py` 的 import 区补上：

```python
import shlex
import shutil
from collections.abc import Mapping
```

然后在文件末尾追加：

```python
SUPPORTED_AGENTS = ("claude", "codex")

_AGENT_HELP = (
    "未找到可用的智能体 CLI。请任选一种方式配置：\n"
    "  1. 设置 META_WRITING_AGENT_CMD 为完整命令，例如 "
    '"claude" 或 "/path/to/codex"\n'
    "  2. 设置 META_WRITING_AGENT 为 claude 或 codex（该命令需已在 PATH 上）\n"
    "  3. 把 claude 或 codex 安装到 PATH 上"
)


class AgentNotFoundError(RuntimeError):
    """当前环境里没有可用的智能体 CLI。"""


class AgentInvocationError(RuntimeError):
    """智能体 CLI 调用失败，且重试已耗尽。"""


@dataclass(frozen=True)
class AgentSpec:
    """一个可调用的智能体 CLI。

    kind: "claude" | "codex" | "custom"
    argv: 基础命令，后续参数追加在它之后
    """

    kind: str
    argv: tuple[str, ...]


def detect_agent(env: Mapping[str, str] | None = None) -> AgentSpec:
    """按优先级探测当前环境可用的智能体 CLI。

    优先级：META_WRITING_AGENT_CMD > META_WRITING_AGENT > PATH（claude 优先）。
    """
    env = os.environ if env is None else env

    raw_cmd = (env.get("META_WRITING_AGENT_CMD") or "").strip()
    if raw_cmd:
        parts = shlex.split(raw_cmd)
        if parts:
            return AgentSpec(kind="custom", argv=tuple(parts))

    named = (env.get("META_WRITING_AGENT") or "").strip().lower()
    if named:
        if named not in SUPPORTED_AGENTS:
            raise AgentNotFoundError(
                f"META_WRITING_AGENT 只接受 {' / '.join(SUPPORTED_AGENTS)}，收到：{named}"
            )
        path = shutil.which(named)
        if not path:
            raise AgentNotFoundError(f"META_WRITING_AGENT={named}，但 PATH 上找不到该命令。")
        return AgentSpec(kind=named, argv=(path,))

    for kind in SUPPORTED_AGENTS:
        path = shutil.which(kind)
        if path:
            return AgentSpec(kind=kind, argv=(path,))

    raise AgentNotFoundError(_AGENT_HELP)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_agent_client.py -q`
Expected: PASS（8 个用例）

- [ ] **Step 5: Commit**

```bash
git add meta_writing/llm.py tests/test_agent_client.py
git commit -m "feat: 新增智能体 CLI 探测

按 META_WRITING_AGENT_CMD > META_WRITING_AGENT > PATH 的优先级探测当前
环境可用的智能体（claude / codex）。旧的供应商 client 暂时保留，下个任务
切换调用点后再删除。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: 命令构造与温度语义化

**Files:**
- Modify: `meta_writing/llm.py`
- Test: `tests/test_agent_client.py`

**Interfaces:**
- Consumes: `AgentSpec` from Task 2
- Produces: `_temperature_directive(temperature: float) -> str`；`compose_system_prompt(system: str, temperature: float) -> str`；`build_agent_command(spec: AgentSpec, system: str, prompt: str, temperature: float) -> tuple[list[str], str]`（返回 argv 与要写进 stdin 的文本）

> **适配器差异**：`claude` 有 `--system-prompt` 参数；`codex exec` 没有，system 文本必须并进 stdin。`custom` 按 codex 方式处理，因为无法预知其参数。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_agent_client.py`：

```python
from meta_writing.llm import build_agent_command, compose_system_prompt


def test_low_temperature_asks_for_stability():
    prompt = compose_system_prompt("BASE", 0.3)

    assert prompt.startswith("BASE")
    assert "稳定克制" in prompt


def test_mid_temperature_asks_for_faithful_revision():
    assert "忠实原文" in compose_system_prompt("BASE", 0.5)


def test_high_temperature_asks_for_divergence():
    assert "大胆发散" in compose_system_prompt("BASE", 0.8)


def test_temperature_boundaries_are_inclusive():
    assert "稳定克制" in compose_system_prompt("B", 0.35)
    assert "忠实原文" in compose_system_prompt("B", 0.6)
    assert "大胆发散" in compose_system_prompt("B", 0.61)


def test_claude_command_shape():
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))

    argv, stdin_text = build_agent_command(spec, "SYS", "USER", 0.7)

    assert argv[0] == "/usr/bin/claude"
    assert "-p" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "--system-prompt" in argv
    assert "SYS" in argv[argv.index("--system-prompt") + 1]
    assert stdin_text == "USER"


def test_claude_command_never_uses_bare_or_model():
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))

    argv, _ = build_agent_command(spec, "SYS", "USER", 0.7)

    assert "--bare" not in argv
    assert "--model" not in argv


def test_claude_command_disables_all_tools():
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))

    argv, _ = build_agent_command(spec, "SYS", "USER", 0.7)

    assert "--disallowed-tools" in argv
    tail = argv[argv.index("--disallowed-tools") + 1:]
    for tool in ("Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task"):
        assert tool in tail


def test_codex_command_folds_system_into_stdin():
    spec = AgentSpec(kind="codex", argv=("/usr/bin/codex",))

    argv, stdin_text = build_agent_command(spec, "SYS", "USER", 0.7)

    assert argv[:3] == ["/usr/bin/codex", "exec", "--skip-git-repo-check"]
    assert "--system-prompt" not in argv
    assert "--full-auto" not in argv
    assert "SYS" in stdin_text
    assert "USER" in stdin_text


def test_custom_command_folds_system_into_stdin():
    spec = AgentSpec(kind="custom", argv=("my-agent", "--flag"))

    argv, stdin_text = build_agent_command(spec, "SYS", "USER", 0.3)

    assert argv == ["my-agent", "--flag"]
    assert "SYS" in stdin_text
    assert "USER" in stdin_text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_agent_client.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_agent_command'`

- [ ] **Step 3: 实现**

追加到 `meta_writing/llm.py`：

```python
CLAUDE_DISALLOWED_TOOLS = (
    "Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task",
)

_TEMPERATURE_STABLE = "判断要稳定克制，同一份输入应给出一致结论，不要为了求新而改判。"
_TEMPERATURE_FAITHFUL = "在忠实原文的前提下做必要改动，不要借机重写。"
_TEMPERATURE_DIVERGENT = "允许大胆发散；若需要给出多个选项，选项之间必须有明显差异。"


def _temperature_directive(temperature: float) -> str:
    """把采样温度翻译成一句提示词指令。

    智能体 CLI 没有温度旋钮。这不等价于采样温度，只是保住
    「审稿要稳、规划要散」的分层意图。
    """
    if temperature <= 0.35:
        return _TEMPERATURE_STABLE
    if temperature <= 0.6:
        return _TEMPERATURE_FAITHFUL
    return _TEMPERATURE_DIVERGENT


def compose_system_prompt(system: str, temperature: float) -> str:
    return f"{system.strip()}\n\n## 输出稳定性\n\n{_temperature_directive(temperature)}"


def build_agent_command(
    spec: AgentSpec,
    system: str,
    prompt: str,
    temperature: float,
) -> tuple[list[str], str]:
    """构造 argv 与 stdin 文本。

    claude 支持 --system-prompt；codex 与 custom 不支持，system 并进 stdin。
    """
    system_prompt = compose_system_prompt(system, temperature)

    if spec.kind == "claude":
        argv = [
            *spec.argv,
            "-p",
            "--output-format", "json",
            "--system-prompt", system_prompt,
            "--disallowed-tools", *CLAUDE_DISALLOWED_TOOLS,
        ]
        return argv, prompt

    if spec.kind == "codex":
        argv = [*spec.argv, "exec", "--skip-git-repo-check"]
    else:
        argv = list(spec.argv)

    return argv, f"{system_prompt}\n\n---\n\n{prompt}"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_agent_client.py -q`
Expected: PASS（18 个用例）

- [ ] **Step 5: Commit**

```bash
git add meta_writing/llm.py tests/test_agent_client.py
git commit -m "feat: 智能体命令构造与温度语义化

claude 走 --system-prompt，codex/custom 把 system 并进 stdin。命令中不含
--bare（会绕开 OAuth 登录态）与 --model（由当前会话决定），并禁用全部工具。

采样温度翻译成提示词指令，保住审稿要稳、规划要散的分层意图。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: AgentClient.complete() — 子进程调用、解析、重试

**Files:**
- Modify: `meta_writing/llm.py`
- Test: `tests/test_agent_client.py`

**Interfaces:**
- Consumes: `AgentSpec`、`build_agent_command`、`AgentInvocationError` from Tasks 2-3
- Produces: `AgentClient(agent=None, timeout=None)`，方法 `async complete(system, messages, model=None, max_tokens=None, temperature=0.7) -> LLMResponse`，属性 `usage: TokenUsage`；`TokenUsage.cost_usd: float`

- [ ] **Step 1: 给 TokenUsage 加 cost_usd 的失败测试**

追加到 `tests/test_agent_client.py`：

```python
from unittest.mock import AsyncMock, MagicMock

from meta_writing.llm import AgentClient, AgentInvocationError, TokenUsage


def _fake_process(stdout: str, returncode: int = 0, stderr: str = ""):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode("utf-8"), stderr.encode("utf-8")))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


CLAUDE_OK = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "生成的正文",
    "usage": {"input_tokens": 100, "output_tokens": 50},
    "total_cost_usd": 0.25,
    "modelUsage": {"claude-opus-4-8": {}},
})


def test_token_usage_accumulates_cost():
    usage = TokenUsage()
    usage.add({"input_tokens": 10, "output_tokens": 5}, cost_usd=0.5)
    usage.add({"input_tokens": 20, "output_tokens": 5}, cost_usd=0.25)

    assert usage.input_tokens == 30
    assert usage.output_tokens == 10
    assert usage.cost_usd == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_complete_parses_claude_json(monkeypatch):
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))
    create = AsyncMock(return_value=_fake_process(CLAUDE_OK))
    monkeypatch.setattr("meta_writing.llm.asyncio.create_subprocess_exec", create)

    client = AgentClient(agent=spec)
    response = await client.complete("SYS", [{"role": "user", "content": "USER"}])

    assert response.text == "生成的正文"
    assert response.usage == {"input_tokens": 100, "output_tokens": 50}
    assert response.model == "claude-opus-4-8"
    assert client.usage.input_tokens == 100
    assert client.usage.cost_usd == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_complete_sends_prompt_on_stdin(monkeypatch):
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))
    proc = _fake_process(CLAUDE_OK)
    create = AsyncMock(return_value=proc)
    monkeypatch.setattr("meta_writing.llm.asyncio.create_subprocess_exec", create)

    client = AgentClient(agent=spec)
    await client.complete("SYS", [{"role": "user", "content": "USER-MESSAGE"}])

    sent = proc.communicate.await_args.kwargs["input"].decode("utf-8")
    assert sent == "USER-MESSAGE"


@pytest.mark.asyncio
async def test_complete_retries_on_is_error_then_succeeds(monkeypatch):
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))
    failing = json.dumps({"is_error": True, "result": "rate limited"})
    create = AsyncMock(side_effect=[_fake_process(failing), _fake_process(CLAUDE_OK)])
    monkeypatch.setattr("meta_writing.llm.asyncio.create_subprocess_exec", create)
    monkeypatch.setattr("meta_writing.llm.asyncio.sleep", AsyncMock())

    client = AgentClient(agent=spec)
    response = await client.complete("SYS", [{"role": "user", "content": "U"}])

    assert response.text == "生成的正文"
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_complete_retries_on_invalid_json(monkeypatch):
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))
    create = AsyncMock(side_effect=[_fake_process("not json"), _fake_process(CLAUDE_OK)])
    monkeypatch.setattr("meta_writing.llm.asyncio.create_subprocess_exec", create)
    monkeypatch.setattr("meta_writing.llm.asyncio.sleep", AsyncMock())

    client = AgentClient(agent=spec)
    response = await client.complete("SYS", [{"role": "user", "content": "U"}])

    assert response.text == "生成的正文"


@pytest.mark.asyncio
async def test_complete_raises_after_retries_exhausted(monkeypatch):
    spec = AgentSpec(kind="claude", argv=("/usr/bin/claude",))
    create = AsyncMock(return_value=_fake_process("", returncode=1, stderr="boom"))
    monkeypatch.setattr("meta_writing.llm.asyncio.create_subprocess_exec", create)
    monkeypatch.setattr("meta_writing.llm.asyncio.sleep", AsyncMock())

    client = AgentClient(agent=spec)
    with pytest.raises(AgentInvocationError, match="boom"):
        await client.complete("SYS", [{"role": "user", "content": "U"}])

    assert create.await_count == 3


@pytest.mark.asyncio
async def test_codex_uses_raw_stdout_as_text(monkeypatch):
    spec = AgentSpec(kind="codex", argv=("/usr/bin/codex",))
    create = AsyncMock(return_value=_fake_process("codex 写的正文\n"))
    monkeypatch.setattr("meta_writing.llm.asyncio.create_subprocess_exec", create)

    client = AgentClient(agent=spec)
    response = await client.complete("SYS", [{"role": "user", "content": "U"}])

    assert response.text == "codex 写的正文"
    assert client.usage.input_tokens == 0
```

在 `tests/test_agent_client.py` 顶部补 `import json`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_agent_client.py -q`
Expected: FAIL — `ImportError: cannot import name 'AgentClient'`

- [ ] **Step 3: 修改 TokenUsage 并实现 AgentClient**

把 `meta_writing/llm.py` 里现有的 `TokenUsage.add` 与成本方法改为：

```python
@dataclass
class TokenUsage:
    """Track token usage and real cost across the pipeline."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, usage: dict[str, int], cost_usd: float = 0.0) -> None:
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
        self.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
        self.cost_usd += cost_usd

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
```

**删除** `estimated_cost_usd()` 方法（它硬编码 MiniMax 定价）。

追加 `AgentClient`：

```python
DEFAULT_AGENT_TIMEOUT_SECONDS = 900.0


def _resolve_timeout(env: Mapping[str, str] | None = None) -> float:
    env = os.environ if env is None else env
    raw = (env.get("META_WRITING_AGENT_TIMEOUT") or "").strip()
    if not raw:
        return DEFAULT_AGENT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_AGENT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_AGENT_TIMEOUT_SECONDS


class AgentClient:
    """通过当前环境的智能体 CLI 完成生成与审稿。

    complete() 的签名与旧的供应商 client 保持一致，因此 agent 层无需改动。
    model 与 max_tokens 被忽略——模型由当前智能体会话决定，这正是
    「使用当前智能体」的含义。temperature 被翻译成提示词指令。
    """

    def __init__(self, agent: AgentSpec | None = None, timeout: float | None = None) -> None:
        self.agent = agent or detect_agent()
        self.timeout = timeout if timeout is not None else _resolve_timeout()
        self.usage = TokenUsage()

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        model: str | None = None,      # ignored: decided by the current agent
        max_tokens: int | None = None, # ignored: decided by the current agent
        temperature: float = 0.7,
    ) -> LLMResponse:
        prompt = "\n\n".join(
            str(message.get("content", "")) for message in messages
        ).strip()
        argv, stdin_text = build_agent_command(self.agent, system, prompt, temperature)

        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._invoke_once(argv, stdin_text)
            except AgentInvocationError as exc:
                last_error = str(exc)
            else:
                return response

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))

        raise AgentInvocationError(
            f"智能体调用连续失败 {MAX_RETRIES} 次：{last_error}"
        )

    async def _invoke_once(self, argv: list[str], stdin_text: str) -> LLMResponse:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin_text.encode("utf-8")),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            raise AgentInvocationError(f"智能体调用超时（{self.timeout}s）") from exc

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            raise AgentInvocationError(
                f"智能体退出码 {process.returncode}：{stderr[:500] or '(无 stderr)'}"
            )

        if self.agent.kind == "claude":
            return self._parse_claude_output(stdout, stderr)
        return self._parse_plain_output(stdout, stderr)

    def _parse_claude_output(self, stdout: str, stderr: str) -> LLMResponse:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AgentInvocationError(
                f"智能体输出不是合法 JSON：{stdout[:300]}"
            ) from exc

        if payload.get("is_error"):
            raise AgentInvocationError(f"智能体报错：{payload.get('result', '')[:500]}")

        text = str(payload.get("result") or "").strip()
        if not text:
            raise AgentInvocationError("智能体返回空结果")

        usage = payload.get("usage") or {}
        cost = float(payload.get("total_cost_usd") or 0.0)
        self.usage.add(usage, cost_usd=cost)

        model_usage = payload.get("modelUsage") or {}
        model_name = next(iter(model_usage), "")

        return LLMResponse(
            text=text,
            usage={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
            model=model_name,
            stop_reason=str(payload.get("stop_reason") or ""),
        )

    def _parse_plain_output(self, stdout: str, stderr: str) -> LLMResponse:
        text = stdout.strip()
        if not text:
            raise AgentInvocationError(f"智能体返回空结果：{stderr[:300]}")
        return LLMResponse(text=text, usage={}, model=self.agent.kind, stop_reason="")
```

确认 `meta_writing/llm.py` 顶部已 `import json`（若无则补上）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_agent_client.py -q`
Expected: PASS

- [ ] **Step 5: 跑全量测试**

Run: `python -m pytest -q`
Expected: PASS。若 `test_llm.py` 因 `estimated_cost_usd` 被删而失败，先不管——Task 5 会整体删除该文件。若失败的是别的文件，先修好再继续。

- [ ] **Step 6: Commit**

```bash
git add meta_writing/llm.py tests/test_agent_client.py
git commit -m "feat: AgentClient 子进程调用、响应解析与重试

complete() 签名与旧供应商 client 一致，agent 层无需改动。claude 走 JSON
输出并采集真实 usage 与 total_cost_usd；codex/custom 取 stdout 纯文本。

重试条件：非零退出、非法 JSON、is_error、空结果、超时。TokenUsage 改为
累加真实成本，删除硬编码 MiniMax 定价的 estimated_cost_usd。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: 切换全部调用点并删除旧供应商代码

**Files:**
- Modify: `meta_writing/llm.py`（删除旧 client）
- Modify: `meta_writing/agents/{planner,writer,continuity,style,theme}.py`
- Modify: `meta_writing/orchestrator.py`
- Modify: `meta_writing/cli.py`
- Modify: `meta_writing/story_bible/schema.py`
- Modify: `meta_writing/style_linter.py`
- Modify: `scripts/editorial_pass.py`
- Delete: `tests/test_llm.py`
- Test: `tests/test_orchestrator.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `AgentClient` from Task 4
- Produces: `Orchestrator(project_dir, llm: AgentClient | None = None)`（不再有 `api_key` / `writer_provider` 参数）；五个 agent 的 `__init__(self, llm: AgentClient, model: str | None = None)`

> **为什么 `Orchestrator` 要接收可选的 `llm`**：`AgentClient()` 在构造时就会调 `detect_agent()`，若机器上没有 agent CLI 会直接抛 `AgentNotFoundError`。`tests/test_orchestrator.py` 有 7 处构造 `Orchestrator`，若不做依赖注入，测试就会依赖运行机器上装没装 claude——这是不可接受的。注入口同时也让测试不必 monkeypatch 模块内部。

- [ ] **Step 1: 删除旧供应商代码**

从 `meta_writing/llm.py` **整体删除**：`LLMClient`、`DeepSeekClient`、`ClaudeClient`、`build_writer_backend`、`normalize_writer_provider`、`SUPPORTED_WRITER_PROVIDERS`、`WRITER_PROVIDER_DEEPSEEK`、`WRITER_PROVIDER_MINIMAX`、`MODEL_OPUS`、`MODEL_SONNET`、`MODEL_DEEPSEEK_CHAT`、`MODEL_DEEPSEEK_REASONER`、`MODEL_CLAUDE_OPUS`、`MODEL_CLAUDE_SONNET`、`MINIMAX_BASE_URL`、`DEEPSEEK_BASE_URL`，以及 `import anthropic`。

把模块 docstring 换成：

```python
"""智能体后端 —— 全部生成与审稿都通过当前环境的智能体 CLI 完成。

不需要任何模型供应商的 API key。模型由当前智能体会话决定。

探测优先级：META_WRITING_AGENT_CMD > META_WRITING_AGENT > PATH（claude 优先）。
"""
```

同时删除 `tests/test_llm.py`（它整份都在测已删除的供应商路由，替代品是 `tests/test_agent_client.py`）：

```bash
git rm -f tests/test_llm.py
```

- [ ] **Step 2: 改五个 agent 的构造函数**

对 `planner.py`、`writer.py`、`continuity.py`、`style.py`、`theme.py` 各做两处改动。

import 行（`planner.py` 原为 `MODEL_OPUS`，其余四个为 `MODEL_SONNET`）统一改为：

```python
from ..llm import AgentClient, LLMResponse
```

构造函数统一改为：

```python
    def __init__(self, llm: AgentClient, model: str | None = None) -> None:
        self.llm = llm
        self.model = model
```

方法体一律不动。

- [ ] **Step 3: 改 orchestrator.py**

import 改为：

```python
from .llm import AgentClient
```

`__init__` 签名改为（删除 `api_key`、`planner_model`、`writer_model`、`continuity_model`、`writer_provider` 五个参数，新增可选的 `llm` 注入口）：

```python
    def __init__(self, project_dir: str | Path, llm: AgentClient | None = None) -> None:
        self.project_dir = Path(project_dir)
```

删除 writer backend 那整段（`resolved_writer_provider` / `build_writer_backend` / `resolved_writer_model`），agent 构造改为：

```python
        self.llm = llm or AgentClient()
        self.planner = PlannerAgent(self.llm)
        self.writer = WriterAgent(self.llm)
        self.continuity = ContinuityAgent(self.llm)
        self.style_agent = StyleAgent(self.llm)
        self.theme_agent = ThemeAgent(self.llm)
        self.style_linter = StyleLinter()
```

若 `core = self.loader.load_core()` 在删除 writer 路由后不再被使用，一并删除该行。

- [ ] **Step 4: 改 cli.py**

删除这行 import：

```python
from .llm import MODEL_SONNET, SUPPORTED_WRITER_PROVIDERS
```

`init` 命令删除这三行（Writer provider 提问）：

```python
    writer_provider = Prompt.ask(
        "Writer provider",
        choices=list(SUPPORTED_WRITER_PROVIDERS),
        default="minimax",
    )
```

并从 `StoryCore(...)` 构造里删除 `writer_provider=writer_provider,`。

`generate` 的成本输出两行改为：

```python
            console.print(f"Token用量: {orch.llm.usage.total_tokens:,} tokens")
            console.print(f"实际成本: ${orch.llm.usage.cost_usd:.4f}")
```

- [ ] **Step 5: 改 schema.py 与 style_linter.py**

`meta_writing/story_bible/schema.py`：从 `StoryCore` 删除整个 `writer_provider` 字段定义。

`meta_writing/style_linter.py`：两条规则的 message 里把 `MiniMax最高频散文口头禅` 改为 `高频散文口头禅`（`na_zhong_na_zhong` 与 `na_zhong_na_zhong_heavy` 各一处）。

- [ ] **Step 6: 改 editorial_pass.py**

import 改为 `from meta_writing.llm import AgentClient`。

删除 api_key 读取那四行，改为：

```python
    llm = AgentClient()
```

成本报告那行改为：

```python
    report_sections.append(f"- 实际费用: ${usage.cost_usd:.4f}\n")
```

若 `os` / `sys` 在删除后不再被使用，清理无用 import。

- [ ] **Step 7: 改测试**

`tests/conftest.py`：从 `sample_core` 的 `StoryCore(...)` 删除 `writer_provider="minimax",`。

`tests/test_orchestrator.py`：在 helper 区加一个不触发探测的桩 client：

```python
from meta_writing.llm import AgentClient, AgentSpec


def _stub_llm() -> AgentClient:
    """不做探测的 AgentClient，避免测试依赖机器上是否装了 agent CLI。"""
    return AgentClient(agent=AgentSpec(kind="claude", argv=("claude",)), timeout=1.0)
```

把 7 处 `Orchestrator(tmp_project, api_key="test")` 全部改为 `Orchestrator(tmp_project, llm=_stub_llm())`。

（这些测试都直接 mock 了 agent 的方法，桩 client 不会真的被调用。）

Run: `rg -n 'api_key="test"' tests/`
Expected: 无输出

- [ ] **Step 8: 跑全量测试**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 9: 验收扫描**

Run: `rg -in "minimax|deepseek|anthropic|claude-opus|claude-sonnet|writer_provider|build_writer_backend" meta_writing/ scripts/ tests/`
Expected: 无输出

Run: `rg -n "\bclaude\b|\bcodex\b" meta_writing/`
Expected: 只在 `llm.py` 的 `SUPPORTED_AGENTS`、`detect_agent`、`build_agent_command`、docstring 与帮助文本中出现（这些是 CLI 命令名，不是供应商选择）

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: 全部 LLM 调用切换到当前智能体后端

删除 LLMClient/DeepSeekClient/ClaudeClient 与全部供应商路由、模型常量、
端点常量。五个 agent 改为共用一个 AgentClient，Orchestrator 不再接收
api_key 与 writer_provider。

StoryCore.writer_provider 一并删除——Pydantic 默认忽略未知字段，现存
story_core.yaml 里的残留值不会报错，下次 save 时自然清除。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: 真实冒烟验证

**Files:**
- 不修改任何文件（若发现问题则回到对应任务修复）

**Interfaces:**
- Consumes: Task 5 的成品
- Produces: 无

> 这是唯一一次真实调用智能体 CLI。会产生真实成本（每次调用约 11.7K input token）。

- [ ] **Step 1: 确认探测可用**

```powershell
python -X utf8 -c "from meta_writing.llm import detect_agent; s=detect_agent(); print(s.kind, s.argv)"
```

Expected: 打印 `claude ('C:\\...\\claude',)` 或类似。若抛 `AgentNotFoundError`，按错误信息配置后重试。

- [ ] **Step 2: 单次真实调用**

```powershell
@'
import asyncio
from meta_writing.llm import AgentClient

async def main():
    client = AgentClient()
    r = await client.complete(
        system="你是一个JSON生成器。只输出合法JSON，不加解释、不加代码块。",
        messages=[{"role": "user", "content": '只输出：{"ok": true}'}],
        temperature=0.3,
    )
    print("text  :", r.text)
    print("model :", r.model)
    print("tokens:", client.usage.total_tokens)
    print("cost  :", client.usage.cost_usd)

asyncio.run(main())
'@ | python -X utf8 -
```

Expected: `text` 为 `{"ok": true}`，`tokens` > 0，`cost` > 0。

- [ ] **Step 3: 跑通规划阶段**

对一个**临时**项目（不要用 `rescue-male-lead`）跑 `meta-writing generate`，在分支选择界面出现后按 Ctrl+C 中断。

```powershell
meta-writing --workspace-dir . project create smoke-test --activate
meta-writing --workspace-dir . --project smoke-test init
meta-writing --workspace-dir . --project smoke-test generate --guidance "第一章：随便写点什么。"
```

Expected: Planner 返回 2-3 条分支并渲染成表格。看到表格即验证成功，Ctrl+C 退出。

- [ ] **Step 4: 清理冒烟项目**

```powershell
Remove-Item -Recurse -Force novels/smoke-test
Remove-Item -Force .meta-writing/workspace.json
```

- [ ] **Step 5: 确认工作区干净**

Run: `git status --short`
Expected: 无输出（冒烟不应留下任何文件）

---

### Task 7: 文档同步

**Files:**
- Rename: `docs/architecture/model-routing.md` → `docs/architecture/agent-backend.md`（重写内容）
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture/{overview,pipelines,agents}.md`
- Modify: `docs/reference/{configuration,cli,story-bible-schema,style-rules}.md`
- Modify: `docs/guides/{getting-started,multi-project-workspace,new-novel-quickstart}.md`
- Modify: `docs/operations/editorial-scorecard-maintenance.md`
- Modify: `docs/decisions/README.md`

**Interfaces:**
- Consumes: Task 5 的成品
- Produces: 无

- [ ] **Step 1: 重写模型路由文档**

```bash
git mv docs/architecture/model-routing.md docs/architecture/agent-backend.md
```

整体重写为「智能体后端」，必须覆盖：探测优先级三档、claude 与 codex 的命令构造差异（codex 无 `--system-prompt`）、为什么禁止 `--bare`（会绕开 OAuth 登录态）、为什么不传 `--model`、工具全部禁用的理由、温度语义化及其**不等价于采样温度**的说明、重试与超时、每次调用约 11.7K token 的固定开销、codex 适配器未经验证的标注。

- [ ] **Step 2: 改架构文档**

`docs/architecture/overview.md`：四层架构图去掉 `auto_runner.py`；**整节删除** §4「两条链路」；§3 生命周期图保留；§7 稳健性表格增加智能体调用的重试策略；§8 相关文档表里 `model-routing.md` 改为 `agent-backend.md`。

`docs/architecture/pipelines.md`：**大幅重写**为单链路。删除全部对比表、工作流模式互斥、自动链路章节。保留 §2 的三个回调、流水线状态机、审稿-修订循环、落盘。§4 已知缺口里删除「两条链路重复实现」与「auto_runner 待决」两条，保留章节摘要失真与审稿未并发。

`docs/architecture/agents.md`：**整节删除** §4「自动链路专属 agent」；§5「扩展一个新 agent」改为单链路（去掉「两条链路都要改」的说明）；表格里的温度列增加脚注说明现在是语义化而非采样温度。

- [ ] **Step 3: 改参考文档**

`docs/reference/configuration.md`：§1 凭据表整体替换为智能体探测变量表（`META_WRITING_AGENT_CMD`、`META_WRITING_AGENT`、`META_WRITING_AGENT_TIMEOUT`）；删除端点覆盖、写手供应商、三级回退；§3 常量表删除 `MAX_REVISIONS`（auto_runner 已删）与向量存储之外的供应商项，增加 `DEFAULT_AGENT_TIMEOUT_SECONDS`；§5「已知陷阱」删除全部供应商相关条目，改为智能体相关（未登录、codex 未验证、嵌套调用）。

`docs/reference/cli.md`：`project create` / `project migrate-root` 删除 `--mode`；**整节删除** `project mode`；`project list` 输出格式更新；`init` 删除 Writer provider 提问行；§7 删除 `auto_runner.py` 一节。

`docs/reference/story-bible-schema.md`：`StoryCore` 表格与 YAML 示例删除 `writer_provider`；删除 §「项目元数据」里的 `workflow_mode` 说明。

`docs/reference/style-rules.md`：把 `na_zhong_na_zhong` 两条规则的描述从「MiniMax最高频散文口头禅」改为「高频散文口头禅」，与代码一致。

- [ ] **Step 4: 改指南与运维文档**

`docs/guides/getting-started.md`：§3「配置密钥」整节替换为「准备智能体」——确认 `claude` 在 PATH 上且已登录（`claude -p` 能跑通），并给出 `detect_agent()` 验证片段；删除 `MINIMAX_API_KEY` 全部内容；§11 相关文档表更新链接。

`docs/guides/multi-project-workspace.md`：**整节删除**「Workflow modes」；删除 `--mode` 与 `auto_runner.py` 的命令示例。

`docs/guides/new-novel-quickstart.md`：**整节删除**「MiniMax auth」；`project create` 示例去掉 `--mode`。

`docs/guides/manual-chapter-workflow.md`：§1「为什么手动」整节删除（已无自动链路可对比），改为一句话说明这是唯一链路；其余保留。

`docs/operations/editorial-scorecard-maintenance.md`：§2 系统总览的「两条链路」改为一条；§9「自动链路如何工作」整节删除；§3 代码地图删除 `auto_runner.py` 与 `test_auto_runner.py` 两条（**它们现在是死链**）；§12 修订轮次只留 orchestrator 一处。

`docs/operations/testing-and-verification.md`：删除「两条链路都要改、都要测」的提醒；测试文件表把 `test_llm.py` 换成 `test_agent_client.py`。

`docs/decisions/README.md`：把 auto-runner-self-correction 一行从「工作区中处于删除状态」改为「已随自动链路一并移除」；演进脉络末尾补一句当前状态。

- [ ] **Step 5: 改索引与 README**

`docs/README.md`：architecture 表格 `model-routing.md` → `agent-backend.md` 并更新描述。

`README.md`：**整节替换**「模型供应商」为「运行前提」——需要一个已登录的智能体 CLI（Claude Code 或 Codex），无需任何模型 API key；**整节删除**「两种工作流」；快速开始去掉 `$env:MINIMAX_API_KEY` 与 `--mode manual`；系统构成图去掉 auto_runner。

- [ ] **Step 6: 校验全部内部链接**

```powershell
@'
import re, pathlib
root = pathlib.Path(".")
bad = []
for md in list(root.glob("*.md")) + list(root.glob("docs/**/*.md")):
    for m in re.finditer(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)", md.read_text(encoding="utf-8")):
        t = m.group(1).strip()
        if t.startswith(("http", "mailto")):
            continue
        if not (md.parent / t).resolve().exists():
            bad.append(f"{md} -> {t}")
print("broken:", len(bad))
for b in bad:
    print("  ", b)
'@ | python -X utf8 -
```

Expected: `broken: 0`

（上一轮遗留的 8 条 `auto_runner.py` 死链，应在本任务后全部消失。）

- [ ] **Step 7: 确认文档里不再有供应商内容**

Run: `rg -in "minimax|deepseek|anthropic|workflow_mode|auto_runner|writer_provider" README.md docs/ --glob '!docs/superpowers/**'`
Expected: 无输出（`docs/superpowers/` 下的历史计划与设计文档保留原样，它们是归档）

- [ ] **Step 8: 跑最后一次全量测试**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "docs: 同步智能体后端迁移

model-routing.md 重写为 agent-backend.md（保留 git 历史）。删除全部供应商、
API key、两条链路、workflow_mode 相关内容。修复此前指向 auto_runner.py 的
8 条死链。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 10: 推送**

```bash
git push origin master
git log --oneline -8
git ls-remote origin master
```

Expected: 远端 HEAD 与本地一致。

---

## 完成标准

1. `python -m pytest -q` 全绿，无 collection error
2. `rg -in "minimax|deepseek|anthropic|writer_provider|workflow_mode|auto_runner" meta_writing/ scripts/ tests/` 无输出
3. `rg -in "minimax|deepseek|anthropic|workflow_mode|auto_runner|writer_provider" README.md docs/ --glob '!docs/superpowers/**'` 无输出
4. 文档内部链接检查 `broken: 0`
5. 真实冒烟通过：`meta-writing generate` 能走到分支选择界面
6. 运行时不需要任何模型供应商 API key
7. wolfgame 仓库零改动
