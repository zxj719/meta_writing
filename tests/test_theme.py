from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from meta_writing.agents.theme import ThemeAgent, build_theme_system_prompt
from meta_writing.editorial_scorecard import EditorialDimension
from meta_writing.llm import LLMClient, LLMResponse
from meta_writing.prompt_profiles import detect_prompt_profile


THEME_RESPONSE = """
{
  "chapter_evaluated": "4",
  "thematic_health": "healthy",
  "issues": [],
  "arc_position_notes": "本章位于中段升温位。",
  "what_this_chapter_adds": "让人物关系和暗线同时推进。",
  "scorecard": {
    "plot_tension": {"score": 8.5, "reason": "有推进"},
    "characters": {"score": 8.3, "reason": "互动成立"},
    "info_design": {"score": 8.0, "reason": "暗线埋得住"},
    "language": {"score": 7.7, "reason": "语言不是主审重点"},
    "instruction_fit": {"score": 8.4, "reason": "回应了要求"}
  }
}
"""


def _make_agent(response_text: str) -> ThemeAgent:
    client = LLMClient(api_key="test")
    client.complete = AsyncMock(
        return_value=LLMResponse(
            text=response_text,
            usage={"input_tokens": 1200, "output_tokens": 300},
            model="claude-opus-4-6",
            stop_reason="end_turn",
        )
    )
    return ThemeAgent(client)


def test_theme_agent_parses_scorecard() -> None:
    agent = _make_agent(THEME_RESPONSE)
    result = agent._parse_response(agent.llm.complete.return_value, "4")

    assert result.scorecard is not None
    assert result.scorecard.dimensions[EditorialDimension.PLOT_TENSION].score == 8.5


def test_tomato_profile_uses_story_editor_prompt() -> None:
    prompt = build_theme_system_prompt(
        detect_prompt_profile(
            creator_guidance="平台风格：番茄女频，高梗密度，快节奏，系统向",
            target_satisfaction_type="打脸、反转、关系推进",
        )
    )

    assert "剧情张力与节奏" in prompt
    assert "克制美学" not in prompt


def test_literary_profile_uses_literary_theme_prompt() -> None:
    prompt = build_theme_system_prompt(
        detect_prompt_profile(
            creator_guidance="核心审美：克制美学，强调微感、留白和不解释",
            target_satisfaction_type="克制美学",
        )
    )

    assert "克制美学" in prompt
    assert "剧情张力与节奏" in prompt
