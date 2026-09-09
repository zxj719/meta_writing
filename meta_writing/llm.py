"""LLM client wrappers — three backends for the multi-agent pipeline.

Multi-model routing (recommended):
  Planner          → ClaudeClient(claude-opus-4-6)   — narrative architecture, editorial judgment
  Writer           → DeepSeekClient(deepseek-chat)   — clean Chinese prose, low tic rate
  ThemeAgent       → ClaudeClient(claude-opus-4-6)   — best thematic coherence evaluation
  ContinuityAgent  → ClaudeClient(claude-sonnet-4-6) — strong narrative continuity
  StyleAgent       → LLMClient(MiniMax)              — fast, cheap, regex+LLM dual-check
  BibleUpdater     → DeepSeekClient(deepseek-chat)   — reliable structured JSON
  LessonExtractor  → DeepSeekClient(deepseek-chat)   — reliable structured JSON

Endpoints:
  MiniMax  → https://api.minimaxi.com/anthropic  (Anthropic SDK, MINIMAX_API_KEY)
  DeepSeek → https://api.deepseek.com            (OpenAI SDK, DEEPSEEK_API_KEY)
  Claude   → https://api.anthropic.com           (Anthropic SDK, ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import anthropic


MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

WRITER_PROVIDER_DEEPSEEK = "deepseek"
WRITER_PROVIDER_MINIMAX = "minimax"
SUPPORTED_WRITER_PROVIDERS = (
    WRITER_PROVIDER_DEEPSEEK,
    WRITER_PROVIDER_MINIMAX,
)

# MiniMax models (legacy, kept for StyleAgent)
MODEL_OPUS = "MiniMax-M2.7"
MODEL_SONNET = "MiniMax-M2.7"

# DeepSeek models
MODEL_DEEPSEEK_CHAT = "deepseek-chat"          # V3 — writer + JSON extraction
MODEL_DEEPSEEK_REASONER = "deepseek-reasoner"  # R1 — heavy reasoning tasks

# Claude models (Anthropic API — editor/reviewer roles)
MODEL_CLAUDE_OPUS = "claude-opus-4-6"          # Planner + ThemeAgent
MODEL_CLAUDE_SONNET = "claude-sonnet-4-6"      # ContinuityAgent + fast review

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds


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


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    stop_reason: str = ""


class LLMClient:
    """Async wrapper around MiniMax API (Anthropic-compatible) with retry logic."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = (
            api_key
            or os.environ.get("MINIMAX_API_KEY", "")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        )
        resolved_base_url = (
            base_url
            or os.environ.get("MINIMAX_BASE_URL", "")
            or os.environ.get("ANTHROPIC_BASE_URL", "")
            or MINIMAX_BASE_URL
        )
        import httpx
        self.client = anthropic.AsyncAnthropic(
            api_key=self.api_key,
            base_url=resolved_base_url,
            timeout=httpx.Timeout(600.0, connect=30.0),  # 10 min for long generations
        )
        self.usage = TokenUsage()

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        model: str = MODEL_SONNET,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Make a completion request with retry logic.

        Args:
            system: System prompt.
            messages: Conversation messages in Anthropic format.
            model: Model ID.
            max_tokens: Max output tokens.
            temperature: Sampling temperature (MiniMax requires (0.0, 1.0]).

        Returns:
            LLMResponse with text, usage, and metadata.

        Raises:
            anthropic.APIError: After exhausting retries.
        """
        # MiniMax requires temperature in (0.0, 1.0]
        temperature = max(0.01, min(1.0, temperature))

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                # Use streaming to keep connection alive for long generations
                text = ""
                input_tokens = 0
                output_tokens = 0
                resp_model = ""
                stop_reason = ""

                async with self.client.messages.stream(
                    model=model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ) as stream:
                    async for event in stream:
                        pass  # consume stream
                    response = await stream.get_final_message()

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                resp_model = response.model
                stop_reason = response.stop_reason or ""

                for block in response.content:
                    if block.type == "text":
                        text += block.text

                usage = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
                self.usage.add(usage)

                return LLMResponse(
                    text=text,
                    usage=usage,
                    model=resp_model,
                    stop_reason=stop_reason,
                )

            except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
                last_error = e
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                await asyncio.sleep(wait)
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    last_error = e
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error  # type: ignore[misc]


class DeepSeekClient:
    """Async wrapper around DeepSeek API (OpenAI-compatible).

    Drop-in replacement for LLMClient — same complete() interface.
    Uses openai.AsyncOpenAI under the hood.
    """

    def __init__(self, api_key: str | None = None) -> None:
        from openai import AsyncOpenAI
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=DEEPSEEK_BASE_URL,
        )
        self.usage = TokenUsage()

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        model: str = MODEL_DEEPSEEK_CHAT,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Make a completion request.

        Converts Anthropic-style messages to OpenAI format automatically.
        The system prompt is prepended as a system-role message.
        """
        openai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for msg in messages:
            openai_messages.append({"role": msg["role"], "content": msg["content"]})

        # DeepSeek hard limit is 8192 output tokens
        max_tokens = min(max_tokens, 8192)

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=openai_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False,
                )
                text = response.choices[0].message.content or ""
                usage_data = {
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                }
                self.usage.add(usage_data)
                return LLMResponse(
                    text=text,
                    usage=usage_data,
                    model=response.model,
                    stop_reason=response.choices[0].finish_reason or "",
                )
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))

        raise last_error  # type: ignore[misc]


class ClaudeClient:
    """Async wrapper around the real Anthropic API (claude-opus-4-6 / claude-sonnet-4-6).

    Drop-in replacement for LLMClient — same complete() interface.
    Used for editor/reviewer roles: Planner, ThemeAgent, ContinuityAgent.
    Reads ANTHROPIC_API_KEY from environment.
    """

    def __init__(self, api_key: str | None = None) -> None:
        import httpx
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = anthropic.AsyncAnthropic(
            api_key=self.api_key,
            timeout=httpx.Timeout(600.0, connect=30.0),
        )
        self.usage = TokenUsage()

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        model: str = MODEL_CLAUDE_SONNET,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Make a completion request using the real Anthropic API."""
        temperature = max(0.0, min(1.0, temperature))
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                text = ""
                async with self.client.messages.stream(
                    model=model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ) as stream:
                    async for _ in stream:
                        pass
                    response = await stream.get_final_message()

                for block in response.content:
                    if block.type == "text":
                        text += block.text

                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
                self.usage.add(usage)
                return LLMResponse(
                    text=text,
                    usage=usage,
                    model=response.model,
                    stop_reason=response.stop_reason or "",
                )
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
                last_error = e
                await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    last_error = e
                    await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
                else:
                    raise

        raise last_error  # type: ignore[misc]


def normalize_writer_provider(provider: str | None, fallback: str = WRITER_PROVIDER_DEEPSEEK) -> str:
    """Normalize a writer provider string with a safe fallback."""
    normalized = (provider or "").strip().lower()
    if normalized in SUPPORTED_WRITER_PROVIDERS:
        return normalized
    return fallback


def build_writer_backend(
    provider: str | None,
    minimax_api_key: str | None = None,
):
    """Return the writer client and model for the requested provider."""
    resolved = normalize_writer_provider(provider)
    if resolved == WRITER_PROVIDER_MINIMAX:
        return LLMClient(api_key=minimax_api_key), MODEL_SONNET
    return DeepSeekClient(), MODEL_DEEPSEEK_CHAT


# ===========================================================================
# Agent backend — 通过当前环境的智能体 CLI 完成生成与审稿
# ===========================================================================

SUPPORTED_AGENTS = ("claude", "codex")

_AGENT_HELP = (
    "未找到可用的智能体 CLI。请任选一种方式配置：\n"
    '  1. 设置 META_WRITING_AGENT_CMD 为完整命令，例如 "claude" 或 "/path/to/codex"\n'
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
    命令中不含 --bare（会绕开 OAuth 登录态）与 --model（由当前会话决定）。
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
        model: str | None = None,       # ignored: decided by the current agent
        max_tokens: int | None = None,  # ignored: decided by the current agent
        temperature: float = 0.7,
    ) -> LLMResponse:
        prompt = "\n\n".join(
            str(message.get("content", "")) for message in messages
        ).strip()
        argv, stdin_text = build_agent_command(self.agent, system, prompt, temperature)

        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                return await self._invoke_once(argv, stdin_text)
            except AgentInvocationError as exc:
                last_error = str(exc)

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))

        raise AgentInvocationError(f"智能体调用连续失败 {MAX_RETRIES} 次：{last_error}")

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
            return self._parse_claude_output(stdout)
        return self._parse_plain_output(stdout, stderr)

    def _parse_claude_output(self, stdout: str) -> LLMResponse:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AgentInvocationError(f"智能体输出不是合法 JSON：{stdout[:300]}") from exc

        if payload.get("is_error"):
            raise AgentInvocationError(f"智能体报错：{str(payload.get('result', ''))[:500]}")

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
