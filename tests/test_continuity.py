"""Tests for Continuity Agent (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from meta_writing.agents.continuity import (
    ContinuityAgent,
    IssueSeverity,
    IssueType,
)
from meta_writing.editorial_scorecard import EditorialDimension
from meta_writing.llm import LLMClient, LLMResponse
from meta_writing.prompt_profiles import detect_prompt_profile
from meta_writing.story_bible.compressor import CompressedContext


CLEAN_REVIEW = json.dumps(
    {
        "passed": True,
        "issues": [],
        "foreshadowing_notes": "fs_001 有自然回收机会，但本章未涉及。",
        "state_changes_detected": [
            {"character": "林越", "field": "location", "old_value": "教室", "new_value": "走廊"},
        ],
        "scorecard": {
            "plot_tension": {"score": 8.2, "reason": "推进清楚"},
            "characters": {"score": 8.0, "reason": "人物互动成立"},
            "info_design": {"score": 8.4, "reason": "暗线处理自然"},
            "language": {"score": 7.6, "reason": "语言不是主审重点"},
            "instruction_fit": {"score": 8.1, "reason": "回应了既定方向"},
        },
    }
)

CHARACTER_CONTRADICTION = json.dumps(
    {
        "passed": False,
        "issues": [
            {
                "type": "character_state",
                "severity": "critical",
                "description": "林越在第3章右臂受伤，但本章他用右手自如地撑墙。",
                "location": "第2段：林越一把抓住栏杆，右手用力一撑。",
                "suggestion": "改为左手，或补上忍痛描写。",
            }
        ],
        "foreshadowing_notes": "",
        "state_changes_detected": [],
    }
)

TIMELINE_CONTRADICTION = json.dumps(
    {
        "passed": False,
        "issues": [
            {
                "type": "timeline",
                "severity": "critical",
                "description": "场景开头是深夜，但两段后突然出现阳光。",
                "location": "第4段：阳光从窗边斜着照进来。",
                "suggestion": "改为月光或走廊灯光。",
            }
        ],
        "foreshadowing_notes": "",
        "state_changes_detected": [],
    }
)

WORLD_RULE_VIOLATION = json.dumps(
    {
        "passed": False,
        "issues": [
            {
                "type": "world_rule",
                "severity": "critical",
                "description": "林越使用了瞬移能力，但设定里他只有空间感知。",
                "location": "第10段：林越瞬间消失，出现在走廊尽头。",
                "suggestion": "改成提前感知危险后快速躲开。",
            }
        ],
        "foreshadowing_notes": "",
        "state_changes_detected": [],
    }
)

FORESHADOWING_AGING = json.dumps(
    {
        "passed": True,
        "issues": [
            {
                "type": "foreshadowing",
                "severity": "warning",
                "description": "fs_001 已埋了18章，接近回收上限。",
                "location": "",
                "suggestion": "近期安排回收或加强。",
            }
        ],
        "foreshadowing_notes": "fs_001 即将到期，建议优先处理。",
        "state_changes_detected": [],
    }
)

RELATIONSHIP_CONTRADICTION = json.dumps(
    {
        "passed": False,
        "issues": [
            {
                "type": "relationship",
                "severity": "critical",
                "description": "苏晴称呼林越为‘老朋友’，但 Story Bible 里两人只是同学。",
                "location": "对话：‘老朋友，好久不见。’",
                "suggestion": "改成更符合当前关系的称呼。",
            }
        ],
        "foreshadowing_notes": "",
        "state_changes_detected": [],
    }
)


@pytest.fixture
def bible_context() -> CompressedContext:
    return CompressedContext(
        text="# Story Bible状态\n角色：林越（空间感知异能），苏晴（火系异能B级）\n关系：同学",
        estimated_tokens=100,
        compression_level="full",
    )


def _make_agent(response_text: str) -> ContinuityAgent:
    client = LLMClient(api_key="test")
    client.complete = AsyncMock(
        return_value=LLMResponse(
            text=response_text,
            usage={"input_tokens": 1500, "output_tokens": 400},
            model="claude-sonnet-4-6",
            stop_reason="end_turn",
        )
    )
    return ContinuityAgent(client)


class TestContinuityAgent:
    @pytest.mark.asyncio
    async def test_clean_pass(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(CLEAN_REVIEW)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert result.passed
        assert len(result.issues) == 0
        assert len(result.state_changes) == 1
        assert result.state_changes[0].character == "林越"
        assert result.scorecard is not None
        assert result.scorecard.dimensions[EditorialDimension.INFO_DESIGN].score == 8.4

    @pytest.mark.asyncio
    async def test_character_state_contradiction(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(CHARACTER_CONTRADICTION)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert not result.passed
        assert len(result.critical_issues) == 1
        assert result.critical_issues[0].type == IssueType.CHARACTER_STATE

    @pytest.mark.asyncio
    async def test_timeline_contradiction(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(TIMELINE_CONTRADICTION)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert not result.passed
        assert result.issues[0].type == IssueType.TIMELINE

    @pytest.mark.asyncio
    async def test_world_rule_violation(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(WORLD_RULE_VIOLATION)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert not result.passed
        assert result.issues[0].type == IssueType.WORLD_RULE

    @pytest.mark.asyncio
    async def test_foreshadowing_aging_alert(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(FORESHADOWING_AGING)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert result.passed
        assert len(result.issues) == 1
        assert result.issues[0].type == IssueType.FORESHADOWING
        assert result.issues[0].severity == IssueSeverity.WARNING

    @pytest.mark.asyncio
    async def test_relationship_contradiction(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(RELATIONSHIP_CONTRADICTION)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert not result.passed
        assert result.issues[0].type == IssueType.RELATIONSHIP

    @pytest.mark.asyncio
    async def test_format_feedback(self, bible_context: CompressedContext) -> None:
        agent = _make_agent(CHARACTER_CONTRADICTION)
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        feedback = result.format_feedback()
        assert "严重" in feedback
        assert "右臂受伤" in feedback
        assert "建议" in feedback

    @pytest.mark.asyncio
    async def test_parse_failure_graceful(self, bible_context: CompressedContext) -> None:
        agent = _make_agent("This is not JSON at all")
        result = await agent.review("章节正文……", bible_context, chapter_number=4)

        assert result.passed
        assert len(result.issues) == 1
        assert "解析失败" in result.issues[0].description

    @pytest.mark.asyncio
    async def test_tomato_profile_omits_microfeel_style_review(
        self,
        bible_context: CompressedContext,
    ) -> None:
        agent = _make_agent(CLEAN_REVIEW)
        await agent.review(
            "章节正文……",
            bible_context,
            chapter_number=4,
            prompt_profile=detect_prompt_profile(
                creator_guidance="平台风格：番茄女频，高梗密度，快节奏，系统向",
                target_satisfaction_type="高梗密度、快节奏、强情绪",
            ),
        )

        system_prompt = agent.llm.complete.call_args.kwargs["system"]
        assert "微感描写风格" not in system_prompt
        assert "高梗密度" in system_prompt
