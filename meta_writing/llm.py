"""LLM client wrappers — MiniMax (Anthropic-compatible) and DeepSeek (OpenAI-compatible).

Centralizes model selection, retry logic, and token tracking.

MiniMax endpoint: https://api.minimaxi.com/anthropic (Anthropic SDK)
DeepSeek endpoint: https://api.deepseek.com (OpenAI SDK)

Agent→model recommendations:
- Planner: Claude (best narrative planning) or DeepSeek-reasoner (strong logic)
- Writer: DeepSeek-chat (clean Chinese prose, less tics) or MiniMax (fast)
- Continuity/Style/Theme: MiniMax or DeepSeek-chat (cost-effective review)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import anthropic


MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# MiniMax models
MODEL_OPUS = "MiniMax-M2.7"            # Best reasoning, ~60 tps
MODEL_SONNET = "MiniMax-M2.7"          # Same model for writer/continuity

# DeepSeek models
MODEL_DEEPSEEK_CHAT = "deepseek-chat"          # V3 — general + Chinese prose
MODEL_DEEPSEEK_REASONER = "deepseek-reasoner"  # R1 — chain-of-thought planning

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds


@dataclass
class TokenUsage:
    """Track token usage across the pipeline."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    def add(self, usage: dict[str, int]) -> None:
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
        self.cache_read_tokens += usage.get("cache_read_input_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimated_cost_usd(self, model: str) -> float:
        """Rough cost estimate based on MiniMax pricing."""
        input_price = 1.0 / 1_000_000
        output_price = 5.0 / 1_000_000
        return self.input_tokens * input_price + self.output_tokens * output_price


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    stop_reason: str = ""


class LLMClient:
    """Async wrapper around MiniMax API (Anthropic-compatible) with retry logic."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        import httpx
        self.client = anthropic.AsyncAnthropic(
            api_key=self.api_key,
            base_url=MINIMAX_BASE_URL,
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
