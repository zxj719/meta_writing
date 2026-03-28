"""Tests for Planner Agent (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from meta_writing.agents.planner import (
    PlannerAgent,
    PlotBranch,
    _extract_and_parse_json,
    _extract_json_block,
    _repair_json_string,
)
from meta_writing.llm import LLMClient, LLMResponse
from meta_writing.story_bible.compressor import CompressedContext


MOCK_PLANNER_RESPONSE = json.dumps({
    "branches": [
        {
            "title": "暗夜追踪",
            "outline": "林越发现学校地下室有异常能量波动，决定深夜潜入调查...",
            "characters_involved": ["林越", "苏晴"],
            "consequences": "林越发现了异能组织的秘密基地入口",
            "foreshadowing_opportunities": ["fs_001"],
            "satisfaction_type": "minor",
            "hook_type": "suspense",
            "hook_description": "地下室深处传来了一个熟悉的声音",
            "tension_impact": "tension_increase",
            "risk_level": "moderate",
        },
        {
            "title": "意外暴露",
            "outline": "林越的异能在课堂上再次失控，被全班同学目击...",
            "characters_involved": ["林越", "苏晴"],
            "consequences": "林越被迫面对异能暴露的后果",
            "foreshadowing_opportunities": [],
            "satisfaction_type": "medium",
            "hook_type": "conflict",
            "hook_description": "一个神秘组织的人出现在校门口",
            "tension_impact": "tension_increase",
            "risk_level": "bold",
        },
    ],
    "context_notes": "当前剧情处于上升期，建议增加冲突强度",
})


@pytest.fixture
def mock_llm():
    client = LLMClient(api_key="test")
    client.complete = AsyncMock(return_value=LLMResponse(
        text=MOCK_PLANNER_RESPONSE,
        usage={"input_tokens": 1000, "output_tokens": 500},
        model="claude-opus-4-6",
        stop_reason="end_turn",
    ))
    return client


@pytest.fixture
def bible_context():
    return CompressedContext(
        text="# 故事核心\n一句话: 少年觉醒异能\n当前章节: 3",
        estimated_tokens=100,
        compression_level="full",
    )


class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_normal_plan(self, mock_llm, bible_context):
        planner = PlannerAgent(mock_llm)
        result = await planner.plan(
            bible_context=bible_context,
            recent_chapters_text="最近的章节内容...",
            chapter_number=4,
        )

        assert len(result.branches) == 2
        assert result.branches[0].title == "暗夜追踪"
        assert result.branches[1].title == "意外暴露"
        assert result.context_notes != ""

    @pytest.mark.asyncio
    async def test_branches_have_consequences(self, mock_llm, bible_context):
        planner = PlannerAgent(mock_llm)
        result = await planner.plan(
            bible_context=bible_context,
            recent_chapters_text="",
            chapter_number=4,
        )

        for branch in result.branches:
            assert branch.consequences != ""
            assert branch.hook_type != ""
            assert branch.satisfaction_type in ("minor", "medium", "major")

    @pytest.mark.asyncio
    async def test_foreshadowing_opportunity_included(self, mock_llm, bible_context):
        planner = PlannerAgent(mock_llm)
        result = await planner.plan(
            bible_context=bible_context,
            recent_chapters_text="",
            chapter_number=4,
        )

        # At least one branch should include foreshadowing opportunities
        has_fs = any(b.foreshadowing_opportunities for b in result.branches)
        assert has_fs

    @pytest.mark.asyncio
    async def test_parse_failure_returns_fallback(self, bible_context):
        client = LLMClient(api_key="test")
        client.complete = AsyncMock(return_value=LLMResponse(
            text="This is not valid JSON",
            usage={"input_tokens": 100, "output_tokens": 50},
            model="claude-opus-4-6",
            stop_reason="end_turn",
        ))

        planner = PlannerAgent(client)
        result = await planner.plan(
            bible_context=bible_context,
            recent_chapters_text="",
            chapter_number=4,
        )

        # Should return a fallback branch instead of crashing
        assert len(result.branches) == 1
        assert "未能解析" in result.branches[0].title

    @pytest.mark.asyncio
    async def test_additional_guidance_included(self, mock_llm, bible_context):
        planner = PlannerAgent(mock_llm)
        await planner.plan(
            bible_context=bible_context,
            recent_chapters_text="",
            chapter_number=4,
            additional_guidance="希望这一章增加搞笑元素",
        )

        # Verify the guidance was passed in the prompt
        call_args = mock_llm.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "搞笑元素" in user_msg

    @pytest.mark.asyncio
    async def test_parse_failure_triggers_repair_retry(self, bible_context):
        """When initial parse fails, planner retries with LLM repair."""
        repaired_json = json.dumps({
            "branches": [
                {
                    "title": "修复后的分支",
                    "outline": "大纲内容",
                    "characters_involved": ["林越"],
                    "consequences": "后果",
                    "foreshadowing_opportunities": [],
                    "satisfaction_type": "minor",
                    "hook_type": "suspense",
                    "hook_description": "钩子",
                    "tension_impact": "tension_increase",
                    "risk_level": "safe",
                }
            ],
            "context_notes": "修复成功",
        })

        client = LLMClient(api_key="test")
        # First call returns broken JSON, second call (repair) returns valid JSON
        client.complete = AsyncMock(side_effect=[
            LLMResponse(
                text="这不是JSON，但我想说{broken",
                usage={"input_tokens": 100, "output_tokens": 50},
                model="test",
                stop_reason="end_turn",
            ),
            LLMResponse(
                text=repaired_json,
                usage={"input_tokens": 200, "output_tokens": 100},
                model="test",
                stop_reason="end_turn",
            ),
        ])

        planner = PlannerAgent(client)
        result = await planner.plan(
            bible_context=bible_context,
            recent_chapters_text="",
            chapter_number=4,
        )

        assert len(result.branches) == 1
        assert result.branches[0].title == "修复后的分支"
        assert client.complete.call_count == 2


class TestJsonRepair:
    """Tests for JSON extraction and repair utilities."""

    def test_extract_from_markdown_json_block(self):
        text = '好的，以下是结果：\n```json\n{"branches": []}\n```\n希望有帮助'
        result = _extract_json_block(text)
        assert result == '{"branches": []}'

    def test_extract_from_plain_code_block(self):
        text = '```\n{"branches": []}\n```'
        result = _extract_json_block(text)
        assert result == '{"branches": []}'

    def test_extract_outermost_braces(self):
        text = '分析如下：\n{"branches": [{"title": "test"}]}\n以上就是结果'
        result = _extract_json_block(text)
        assert '"branches"' in result
        data = json.loads(result)
        assert data["branches"][0]["title"] == "test"

    def test_repair_trailing_comma(self):
        broken = '{"branches": [{"title": "test",}],}'
        fixed = _repair_json_string(broken)
        data = json.loads(fixed)
        assert data["branches"][0]["title"] == "test"

    def test_extract_and_parse_valid_json(self):
        text = json.dumps({"branches": [], "context_notes": "ok"})
        result = _extract_and_parse_json(text)
        assert result is not None
        assert result["context_notes"] == "ok"

    def test_extract_and_parse_with_trailing_comma(self):
        text = '{"branches": [{"title": "A",}], "context_notes": "ok",}'
        result = _extract_and_parse_json(text)
        assert result is not None
        assert result["branches"][0]["title"] == "A"

    def test_extract_and_parse_returns_none_for_garbage(self):
        result = _extract_and_parse_json("这里没有任何JSON内容")
        assert result is None

    def test_extract_and_parse_wrapped_in_explanation(self):
        inner = json.dumps({"branches": [{"title": "T"}], "context_notes": ""})
        text = f"好的，这是我的规划：\n```json\n{inner}\n```\n希望对你有帮助！"
        result = _extract_and_parse_json(text)
        assert result is not None
        assert result["branches"][0]["title"] == "T"
