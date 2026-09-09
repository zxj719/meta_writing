"""Shared test helpers."""

from __future__ import annotations

from meta_writing.llm import AgentClient, AgentSpec


def stub_agent_client() -> AgentClient:
    """An AgentClient that skips CLI detection.

    Tests always replace `complete` with a mock, so the command is never run.
    Passing an explicit AgentSpec keeps the tests from depending on whether
    the machine happens to have claude or codex installed.
    """
    return AgentClient(agent=AgentSpec(kind="claude", argv=("claude",)), timeout=1.0)
