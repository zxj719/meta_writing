"""Tests for LLM client configuration and writer backend selection."""

from __future__ import annotations

from types import SimpleNamespace

from meta_writing.llm import (
    LLMClient,
    MODEL_DEEPSEEK_CHAT,
    MODEL_SONNET,
    build_writer_backend,
)


def test_llm_client_uses_anthropic_compatible_env_aliases(monkeypatch):
    captured: dict[str, object] = {}

    def fake_async_anthropic(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(stream=None))

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-auth-token")
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setattr("meta_writing.llm.anthropic.AsyncAnthropic", fake_async_anthropic)

    client = LLMClient()

    assert client.api_key == "test-auth-token"
    assert captured["api_key"] == "test-auth-token"
    assert captured["base_url"] == "https://api.minimaxi.com/anthropic"


def test_build_writer_backend_returns_minimax_client(monkeypatch):
    fake_client = object()

    def fake_llm_client(api_key=None):
        assert api_key == "test-key"
        return fake_client

    monkeypatch.setattr("meta_writing.llm.LLMClient", fake_llm_client)

    client, model = build_writer_backend("minimax", minimax_api_key="test-key")

    assert client is fake_client
    assert model == MODEL_SONNET


def test_build_writer_backend_returns_deepseek_client(monkeypatch):
    fake_client = object()

    def fake_deepseek_client():
        return fake_client

    monkeypatch.setattr("meta_writing.llm.DeepSeekClient", fake_deepseek_client)

    client, model = build_writer_backend("deepseek")

    assert client is fake_client
    assert model == MODEL_DEEPSEEK_CHAT
