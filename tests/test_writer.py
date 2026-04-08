"""Tests for Writer Agent (mocked LLM)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from meta_writing.agents.writer import WriterAgent, _count_chinese_chars
from meta_writing.llm import LLMClient, LLMResponse
from meta_writing.negative_examples import NEGATIVE_EXAMPLES, format_examples_for_prompt
from meta_writing.prompt_profiles import detect_prompt_profile
from meta_writing.story_bible.compressor import CompressedContext


MOCK_CHAPTER_TEXT = """\
夜色压着临海市，路灯在薄雾里散开昏黄的光。

林越站在教学楼走廊尽头，左眼又开始隐隐作痛。

"又来了。"

他按住眼尾，指缝里看见空气中的蓝色光点正慢慢聚成一团。

脚步声从背后传来。

"你在看什么？"苏晴站在三步外，语气冷淡。
"""

MOCK_REVISED_TEXT = MOCK_CHAPTER_TEXT + "\n（修改版：补上了伤口细节）"


@pytest.fixture
def mock_llm():
    client = LLMClient(api_key="test")
    client.complete = AsyncMock(
        return_value=LLMResponse(
            text=MOCK_CHAPTER_TEXT,
            usage={"input_tokens": 2000, "output_tokens": 3000},
            model="claude-sonnet-4-6",
            stop_reason="end_turn",
        )
    )
    return client


@pytest.fixture
def bible_context():
    return CompressedContext(
        text="# 故事核心\n体裁: 都市异能\n角色: 林越, 苏晴",
        estimated_tokens=100,
        compression_level="full",
    )


class TestWriterAgent:
    @pytest.mark.asyncio
    async def test_normal_write(self, mock_llm, bible_context):
        writer = WriterAgent(mock_llm)
        result = await writer.write(
            bible_context=bible_context,
            recent_chapters_text="之前章节内容",
            outline="林越深夜在学校走廊发现异常光点，苏晴出现。",
            chapter_number=4,
        )

        assert result.chapter_text == MOCK_CHAPTER_TEXT
        assert not result.is_revision

    @pytest.mark.asyncio
    async def test_revision(self, bible_context):
        client = LLMClient(api_key="test")
        client.complete = AsyncMock(
            return_value=LLMResponse(
                text=MOCK_REVISED_TEXT,
                usage={"input_tokens": 3000, "output_tokens": 3500},
                model="claude-sonnet-4-6",
                stop_reason="end_turn",
            )
        )

        writer = WriterAgent(client)
        result = await writer.revise(
            chapter_text=MOCK_CHAPTER_TEXT,
            feedback="林越在第3章受伤，但本章没有提到伤口状态。",
            bible_context=bible_context,
        )

        assert result.is_revision
        assert "修改版" in result.chapter_text

    @pytest.mark.asyncio
    async def test_pov_character_in_prompt(self, mock_llm, bible_context):
        writer = WriterAgent(mock_llm)
        await writer.write(
            bible_context=bible_context,
            recent_chapters_text="",
            outline="大纲内容",
            chapter_number=4,
            pov_character="林越",
        )

        call_args = mock_llm.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "林越" in user_msg
        assert "POV" in user_msg

    @pytest.mark.asyncio
    async def test_negative_examples_in_prompt(self, mock_llm, bible_context):
        writer = WriterAgent(mock_llm)
        await writer.write(
            bible_context=bible_context,
            recent_chapters_text="",
            outline="大纲",
            chapter_number=4,
            prompt_profile=detect_prompt_profile(
                creator_guidance="核心审美：克制美学，强调微感、留白和不解释",
                target_satisfaction_type="克制美学",
            ),
        )

        call_args = mock_llm.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "反模式" in user_msg
        assert "沙发记得" in user_msg

    @pytest.mark.asyncio
    async def test_tomato_profile_omits_literary_negative_examples(self, mock_llm, bible_context):
        writer = WriterAgent(mock_llm)
        await writer.write(
            bible_context=bible_context,
            recent_chapters_text="",
            outline="大纲",
            chapter_number=4,
            prompt_profile=detect_prompt_profile(
                creator_guidance="平台风格：番茄女频，高梗密度，快节奏，系统向",
                target_satisfaction_type="高梗密度、快节奏、强情绪",
            ),
        )

        call_args = mock_llm.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "沙发记得" not in user_msg

    @pytest.mark.asyncio
    async def test_creative_guidance_in_prompt(self, mock_llm, bible_context):
        writer = WriterAgent(mock_llm)
        creative_guidance = "TARGET_2000\nTOMATO_FAST_PACE"
        await writer.write(
            bible_context=bible_context,
            recent_chapters_text="",
            outline="大纲",
            chapter_number=4,
            creative_guidance=creative_guidance,
        )

        call_args = mock_llm.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert creative_guidance in user_msg


class TestAutoExpansion:
    @pytest.mark.asyncio
    async def test_no_expansion_when_above_minimum(self, bible_context):
        long_text = "这是一个长章节。" * 2000

        client = LLMClient(api_key="test")
        client.complete = AsyncMock(
            return_value=LLMResponse(
                text=long_text,
                usage={"input_tokens": 1000, "output_tokens": 5000},
                model="test",
                stop_reason="end_turn",
            )
        )

        writer = WriterAgent(client)
        result = await writer.write_with_expansion(
            bible_context=bible_context,
            recent_chapters_text="",
            outline="大纲",
            chapter_number=4,
        )

        assert client.complete.call_count == 1
        assert result.chapter_text == long_text

    @pytest.mark.asyncio
    async def test_expansion_triggered_when_too_short(self, bible_context):
        short_text = "这是短文。" * 500
        expanded_text = "这是扩写后的长文。" * 2000

        client = LLMClient(api_key="test")
        client.complete = AsyncMock(
            side_effect=[
                LLMResponse(
                    text=short_text,
                    usage={"input_tokens": 1000, "output_tokens": 1000},
                    model="test",
                    stop_reason="end_turn",
                ),
                LLMResponse(
                    text=expanded_text,
                    usage={"input_tokens": 2000, "output_tokens": 5000},
                    model="test",
                    stop_reason="end_turn",
                ),
            ]
        )

        writer = WriterAgent(client)
        result = await writer.write_with_expansion(
            bible_context=bible_context,
            recent_chapters_text="",
            outline="大纲",
            chapter_number=4,
        )

        assert client.complete.call_count == 2
        assert result.chapter_text == expanded_text


class TestChineseCharCount:
    def test_pure_chinese(self):
        assert _count_chinese_chars("你好世界") == 4

    def test_mixed_content(self):
        assert _count_chinese_chars("Hello世界123你好") == 4

    def test_empty_string(self):
        assert _count_chinese_chars("") == 0

    def test_no_chinese(self):
        assert _count_chinese_chars("Hello World 123!") == 0


class TestNegativeExamples:
    def test_examples_have_all_fields(self):
        for ex in NEGATIVE_EXAMPLES:
            assert ex.category
            assert ex.bad
            assert ex.good
            assert ex.why

    def test_format_examples_contains_bad_and_good(self):
        text = format_examples_for_prompt(
            profile_key="literary_microfeel",
            max_examples=3,
        )
        assert "❌" in text
        assert "✅" in text
        assert "反模式" in text

    def test_format_examples_respects_max(self):
        text = format_examples_for_prompt(
            profile_key="literary_microfeel",
            max_examples=2,
        )
        assert text.count("### 反模式") == 2
