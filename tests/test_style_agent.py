from __future__ import annotations

from meta_writing.agents.style import StyleAgent
from meta_writing.editorial_scorecard import EditorialDimension
from meta_writing.llm import LLMClient, LLMResponse


def test_style_agent_parses_scorecard() -> None:
    agent = StyleAgent(LLMClient(api_key="test"))
    response = LLMResponse(
        text="""
{
  "passed": true,
  "issues": [],
  "rhythm_notes": "节奏稳定",
  "scorecard": {
    "plot_tension": {"score": 8.0, "reason": "节奏在线"},
    "characters": {"score": 7.8, "reason": "互动够味"},
    "info_design": {"score": 7.5, "reason": "有暗线但略直给"},
    "language": {"score": 8.9, "reason": "描写有记忆点"},
    "instruction_fit": {"score": 8.1, "reason": "基本回应要求"}
  }
}
""",
        usage={"input_tokens": 1, "output_tokens": 1},
        model="test",
        stop_reason="end_turn",
    )

    result = agent._parse_response(response)

    assert result.scorecard is not None
    assert result.scorecard.dimensions[EditorialDimension.LANGUAGE].score == 8.9
