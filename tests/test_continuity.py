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
from meta_writing.llm import LLMClient, LLMResponse
from meta_writing.story_bible.compressor import CompressedContext


CLEAN_REVIEW = json.dumps({
    "passed": True,
    "issues": [],
    "foreshadowing_notes": "fs_001 有自然回收机会但本章未涉及",
    "state_changes_detected": [
        {"character": "林越", "field": "location", "old_value": "教室", "new_value": "走廊"},
    ],
})

CHARACTER_CONTRADICTION = json.dumps({
    "passed": False,
    "issues": [
        {
            "type": "character_state",
            "severity": "critical",
            "description": "林越在第3章右臂受伤，但本章他用右手自如地攀爬",
            "location": "第4段：林越一把抓住栏杆，右手用力一撑",
            "suggestion": "改为用左手，或添加忍痛的描写",
        }
    ],
    "foreshadowing_notes": "",
    "state_changes_detected": [],
})

TIMELINE_CONTRADICTION = json.dumps({
    "passed": False,
    "issues": [
        {
            "type": "timeline",
            "severity": "critical",
            "description": "场景开始时是深夜，但两段后描写了阳光",
            "location": "第6段：阳光从窗户洒进来",
            "suggestion": "改为月光或灯光",
        }
    ],
    "foreshadowing_notes": "",
    "state_changes_detected": [],
})

WORLD_RULE_VIOLATION = json.dumps({
    "passed": False,
    "issues": [
        {
            "type": "world_rule",
            "severity": "critical",
            "description": "林越使用了传送能力，但他的异能是空间感知，不包含传送",
            "location": "第10段：林越瞬间消失，出现在走廊另一端",
            "suggestion": "改为感知到危险后快速躲避",
        }
    ],
    "foreshadowing_notes": "",
    "state_changes_detected": [],
})

FORESHADOWING_AGING = json.dumps({
    "passed": True,
    "issues": [
        {
            "type": "foreshadowing",
            "severity": "warning",
            "description": "fs_001（林越左眼疤痕发光）已植入18章，接近20章的到期阈值",
            "location": "",
            "suggestion": "在近期章节安排回收或强化",
        }
    ],
    "foreshadowing_notes": "fs_001 即将到期，建议优先处理",
    "state_changes_detected": [],
})

RELATIONSHIP_CONTRADICTION = json.dumps({
    "passed": False,
    "issues": [
        {
            "type": "relationship",
            "severity": "critical",
            "description": "苏晴称呼林越为'老朋友'，但根据Story Bible他们只是同学关系",
            "location": "对话：'老朋友，好久不见'",
            "suggestion": "改为'同学'或更符合当前关系的称呼",
        }
    ],
    "foreshadowing_notes": "",
    "state_changes_detected": [],
})


@pytest.fixture
def bible_context():
    return CompressedContext(
        text="# Story Bible状态\n角色: 林越(空间感知异能), 苏晴(火系异能B级)\n关系: 同学",
        estimated_tokens=100,
        compression_level="full",
    )


def _make_agent(response_text: str) -> ContinuityAgent:
    client = LLMClient(api_key="test")
    client.complete = AsyncMock(return_value=LLMResponse(
        text=response_text,
        usage={"input_tokens": 1500, "output_tokens": 400},
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
    ))
    return ContinuityAgent(client)


class TestContinuityAgent:
    @pytest.mark.asyncio
    async def test_clean_pass(self, bible_context):
        agent = _make_agent(CLEAN_REVIEW)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        assert result.passed
        assert len(result.issues) == 0
        assert len(result.state_changes) == 1
        assert result.state_changes[0].character == "林越"

    @pytest.mark.asyncio
    async def test_character_state_contradiction(self, bible_context):
        agent = _make_agent(CHARACTER_CONTRADICTION)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        assert not result.passed
        assert len(result.critical_issues) == 1
        assert result.critical_issues[0].type == IssueType.CHARACTER_STATE

    @pytest.mark.asyncio
    async def test_timeline_contradiction(self, bible_context):
        agent = _make_agent(TIMELINE_CONTRADICTION)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        assert not result.passed
        assert result.issues[0].type == IssueType.TIMELINE

    @pytest.mark.asyncio
    async def test_world_rule_violation(self, bible_context):
        agent = _make_agent(WORLD_RULE_VIOLATION)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        assert not result.passed
        assert result.issues[0].type == IssueType.WORLD_RULE

    @pytest.mark.asyncio
    async def test_foreshadowing_aging_alert(self, bible_context):
        agent = _make_agent(FORESHADOWING_AGING)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        assert result.passed  # aging is a warning, not a failure
        assert len(result.issues) == 1
        assert result.issues[0].type == IssueType.FORESHADOWING
        assert result.issues[0].severity == IssueSeverity.WARNING

    @pytest.mark.asyncio
    async def test_relationship_contradiction(self, bible_context):
        agent = _make_agent(RELATIONSHIP_CONTRADICTION)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        assert not result.passed
        assert result.issues[0].type == IssueType.RELATIONSHIP

    @pytest.mark.asyncio
    async def test_format_feedback(self, bible_context):
        agent = _make_agent(CHARACTER_CONTRADICTION)
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        feedback = result.format_feedback()
        assert "严重" in feedback
        assert "右臂受伤" in feedback
        assert "建议" in feedback

    @pytest.mark.asyncio
    async def test_parse_failure_graceful(self, bible_context):
        agent = _make_agent("This is not JSON at all")
        result = await agent.review("章节正文...", bible_context, chapter_number=4)

        # Should not crash, returns a parse failure info issue
        assert result.passed
        assert len(result.issues) == 1
        assert "解析失败" in result.issues[0].description
