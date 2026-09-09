"""Tests for the agent-CLI backed LLM client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

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


# --- 命令构造与温度语义化 ---

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


# --- complete(): 子进程调用、解析、重试 ---

from meta_writing.llm import AgentClient, AgentInvocationError, TokenUsage


def _fake_process(stdout: str, returncode: int = 0, stderr: str = ""):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode("utf-8"), stderr.encode("utf-8")))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# 取自一次真实的 `claude -p --output-format json` 输出。
# 这里出现的模型名是智能体**回报**给我们的运行时元数据，不是我们选择的供应商——
# 请勿把它改成占位符，它记录的是真实的响应契约。
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
