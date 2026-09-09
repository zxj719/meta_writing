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
