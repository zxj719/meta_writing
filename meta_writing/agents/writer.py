"""Writer Agent — generates full chapter prose from an outline.

Uses Sonnet for fast, good-quality Chinese web novel prose.
Context window budget: ~15K Story Bible + ~30K recent chapters + ~3K outline + ~10K output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ..llm import LLMClient, LLMResponse, MODEL_SONNET
from ..negative_examples import format_examples_for_prompt
from ..prompt_profiles import GENERIC_PROFILE, PromptProfile
from ..story_bible.compressor import CompressedContext

logger = logging.getLogger(__name__)

# Chinese character count thresholds
MIN_CHAPTER_CHARS = 7000   # Below this, auto-expand
TARGET_CHAPTER_CHARS = 10000  # Expansion target


WRITER_BASE_SYSTEM_PROMPT = """\
你是一位顶尖的中文网络小说写手。你的任务是根据大纲和Story Bible上下文，生成高质量的章节正文。

## 核心写作要求

1. **文风一致**: 保持与前几章一致的叙事风格、用词习惯和POV
2. **五感描写**: 充分运用视觉、听觉、嗅觉、触觉描写，营造沉浸式阅读体验
3. **对话设计**: 每句对话必须同时完成至少两个功能：推进情节/展现性格/建立关系/营造氛围
4. **节奏把控**: 遵循「紧张→短暂缓解→更大紧张→高潮→余韵」的节奏公式
5. **长短句交替**: 长句营造氛围，短句制造紧张感，独句段强调重点
6. **角色动机**: 每个角色的行为必须有可理解的动机，能回答"为什么？"

## 禁止事项（AI味检测）

- ❌ 重复性句首（"他不禁……"、"一股……涌上心头"）
- ❌ 过度使用四字成语作为填充
- ❌ 角色用相同的情感反应面对不同情境（每次都"震惊/不可思议"）
- ❌ 泛泛的"金手指"能力描写
- ❌ 配角对主角的谄媚式崇拜
- ❌ 过度解释已经展示过的内容（show don't tell）
- ❌ 在正文中留下规划标记（"**节点一**"、"**节点二**"等结构标记）——只输出正文
- ❌ 复制上一章的结尾句式或意象——每章结尾必须有本章独有的最终画面
- ❌ "她不知道"在全文中出现超过3次——其余改为具体的犹豫动作或沉默
- ❌ 排比式内心独白（"她应该……？她应该……？她应该……？"这类三连问）
- ❌ 直白情感陈述替代场景推进
- ❌ 把台词写成连续宣言，而不是人物在现场的真实反应

## 输出要求

- 输出纯正文，不要加章节标题或元数据
- 字数目标：8000-12000字（中文字符）
- 使用简体中文
- 段落之间用空行分隔
"""

EXPANSION_BASE_SYSTEM_PROMPT = """\
你是一位顶尖的中文网络小说写手。你需要对一篇已完成的章节进行扩写——保留现有的所有好的内容，在合适的位置插入新的段落和细节。

## 核心写作要求

1. **文风一致**: 与原文完全一致，沿用现有叙事视角、节奏和人物说话方式。
2. **五感描写**: 每一段新增描写都要有具体、独特、服务场景的细节。
3. **扩写要有功能**: 新增内容必须补足推进、互动、信息或氛围，不能只是堆字数。
4. **无缝衔接**: 扩写的内容必须与前后文自然衔接，读起来像原文本来就有这些段落。

## 严格禁止

- ❌ "她不知道"在全文中出现超过3次——其余改为具体的犹豫动作或沉默
- ❌ 排比式内心独白（"她应该……？她应该……？"这类三连问）
- ❌ 直白情感陈述替代人物动作和情境
- ❌ 把原文已有信息换一种说法重复一遍
- ❌ 同一个比喻在相邻500字内出现两次
- ❌ 新增内容与原文重复或矛盾
- ❌ 无来由地切换到另一种项目风格

## 输出要求

- 输出扩写后的完整章节正文
- 使用简体中文
- 段落之间用空行分隔
"""


REVISION_BASE_SYSTEM_PROMPT = """\
你是一位顶尖的中文网络小说写手。你需要根据审查反馈修改章节内容。

## 修改原则

1. **精准修改**: 只修改审查意见指出的问题，不要大幅重写无关段落
2. **保持风格**: 修改后的文字必须与原文风格一致
3. **逻辑自洽**: 修改必须确保前后文逻辑一致
4. **最小侵入**: 用最小的改动解决问题

## 输出要求

输出修改后的完整章节正文（不是只输出修改部分）。
"""


def build_writer_system_prompt(prompt_profile: PromptProfile | None = None) -> str:
    profile = prompt_profile or GENERIC_PROFILE
    sections = [WRITER_BASE_SYSTEM_PROMPT.strip()]
    if profile.writer_notes.strip():
        sections.append(profile.writer_notes.strip())
    return "\n\n".join(sections)


def build_expansion_system_prompt(prompt_profile: PromptProfile | None = None) -> str:
    profile = prompt_profile or GENERIC_PROFILE
    sections = [EXPANSION_BASE_SYSTEM_PROMPT.strip()]
    if profile.expansion_notes.strip():
        sections.append(profile.expansion_notes.strip())
    return "\n\n".join(sections)


def build_revision_system_prompt(prompt_profile: PromptProfile | None = None) -> str:
    profile = prompt_profile or GENERIC_PROFILE
    sections = [REVISION_BASE_SYSTEM_PROMPT.strip()]
    if profile.revision_notes.strip():
        sections.append(profile.revision_notes.strip())
    return "\n\n".join(sections)


@dataclass
class WriterResult:
    """Result from the Writer Agent."""
    chapter_text: str
    raw_response: LLMResponse
    is_revision: bool = False


class WriterAgent:
    """Generates full chapter prose from outline + Story Bible context."""

    def __init__(self, llm: LLMClient, model: str = MODEL_SONNET) -> None:
        self.llm = llm
        self.model = model

    async def write(
        self,
        bible_context: CompressedContext,
        recent_chapters_text: str,
        outline: str,
        chapter_number: int,
        pov_character: str = "",
        creative_guidance: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> WriterResult:
        """Generate a full chapter from an outline.

        Args:
            bible_context: Compressed Story Bible context.
            recent_chapters_text: Text of recent 2-3 chapters for style reference.
            outline: Selected plot branch outline.
            chapter_number: The chapter number being written.
            pov_character: POV character name.

        Returns:
            WriterResult with the chapter text.
        """
        user_message = self._build_write_prompt(
            bible_context,
            recent_chapters_text,
            outline,
            chapter_number,
            pov_character,
            creative_guidance,
            prompt_profile,
        )
        if creative_guidance:
            user_message += f"\n\n## 创作指导\n\n{creative_guidance}"

        response = await self.llm.complete(
            system=build_writer_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=16384,  # ~10K Chinese characters
            temperature=0.7,
        )

        return WriterResult(chapter_text=response.text, raw_response=response)

    async def revise(
        self,
        chapter_text: str,
        feedback: str,
        bible_context: CompressedContext,
        creative_guidance: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> WriterResult:
        """Revise a chapter based on review feedback.

        Args:
            chapter_text: Current chapter text.
            feedback: Issues found by review agents.
            bible_context: Compressed Story Bible context.

        Returns:
            WriterResult with the revised chapter text.
        """
        user_message = (
            f"## Story Bible上下文\n\n{bible_context.text}\n\n"
            f"## 当前章节正文\n\n{chapter_text}\n\n"
            f"## 审查反馈（需修改的问题）\n\n{feedback}\n\n"
            f"请根据以上反馈修改章节正文，输出修改后的完整正文。"
        )

        response = await self.llm.complete(
            system=build_revision_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=16384,
            temperature=0.5,  # Lower for more faithful revisions
        )

        return WriterResult(chapter_text=response.text, raw_response=response, is_revision=True)

    async def write_with_expansion(
        self,
        bible_context: CompressedContext,
        recent_chapters_text: str,
        outline: str,
        chapter_number: int,
        pov_character: str = "",
        min_chars: int = MIN_CHAPTER_CHARS,
        target_chars: int = TARGET_CHAPTER_CHARS,
        creative_guidance: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> WriterResult:
        """Write a chapter, auto-expanding if below minimum char count.

        Two-stage process:
        1. Generate initial draft
        2. If Chinese char count < min_chars, auto-expand with targeted instructions

        Returns the final WriterResult (may have gone through expansion).
        """
        result = await self.write(
            bible_context=bible_context,
            recent_chapters_text=recent_chapters_text,
            outline=outline,
            chapter_number=chapter_number,
            pov_character=pov_character,
            creative_guidance=creative_guidance,
            prompt_profile=prompt_profile,
        )

        cn_count = _count_chinese_chars(result.chapter_text)
        logger.info("Initial draft: %d Chinese chars (min=%d)", cn_count, min_chars)

        if cn_count >= min_chars:
            return result

        # Auto-expand
        logger.info("Below minimum, auto-expanding to ~%d chars...", target_chars)
        expanded = await self.expand(
            chapter_text=result.chapter_text,
            outline=outline,
            bible_context=bible_context,
            target_chars=target_chars,
            creative_guidance=creative_guidance,
            prompt_profile=prompt_profile,
        )

        final_count = _count_chinese_chars(expanded.chapter_text)
        logger.info("After expansion: %d Chinese chars", final_count)
        return expanded

    async def expand(
        self,
        chapter_text: str,
        outline: str,
        bible_context: CompressedContext,
        target_chars: int = TARGET_CHAPTER_CHARS,
        creative_guidance: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> WriterResult:
        """Expand a chapter that is too short.

        Identifies thin sections and asks the LLM to add depth while
        preserving all existing content.
        """
        cn_count = _count_chinese_chars(chapter_text)
        deficit = target_chars - cn_count

        user_message = (
            f"## Story Bible上下文\n\n{bible_context.text}\n\n"
            f"## 章节大纲\n\n{outline}\n\n"
            f"## 当前章节正文（需扩写）\n\n{chapter_text}\n\n"
            f"## 扩写要求\n\n"
            f"当前字数约{cn_count}字，目标{target_chars}字，需增加约{deficit}字。\n\n"
            f"请分析原文，找出可以加深的段落（场景描写、感官细节、角色互动、环境氛围），"
            f"在这些位置插入新内容。要求：\n"
            f"1. 保留原文所有好的段落，不删改\n"
            f"2. 新增内容与前后文无缝衔接\n"
            f"3. 每个新增段落都带有独特的感官细节\n"
            f"4. 不重复已有的比喻或描写\n\n"
            f"输出扩写后的完整章节正文。"
        )

        response = await self.llm.complete(
            system=build_expansion_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=16384,
            temperature=0.7,
        )

        return WriterResult(chapter_text=response.text, raw_response=response)

    def _build_write_prompt(
        self,
        bible_context: CompressedContext,
        recent_chapters: str,
        outline: str,
        chapter_number: int,
        pov_character: str,
        creative_guidance: str,
        prompt_profile: PromptProfile | None,
    ) -> str:
        parts = [f"## Story Bible上下文\n\n{bible_context.text}"]

        if recent_chapters:
            parts.append(f"\n\n## 近期章节（风格参考）\n\n{recent_chapters}")

        parts.append(f"\n\n## 第{chapter_number}章大纲\n\n{outline}")

        if pov_character:
            parts.append(f"\n\n## POV角色: {pov_character}")

        # Inject negative examples to prevent known anti-patterns
        examples = format_examples_for_prompt(
            profile_key=(prompt_profile or GENERIC_PROFILE).negative_examples_profile
        )
        if examples:
            parts.append(f"\n\n{examples}")

        parts.append(f"\n\n请根据以上信息，撰写第{chapter_number}章的完整正文。")

        return "".join(parts)


def _count_chinese_chars(text: str) -> int:
    """Count Chinese characters in text (CJK Unified Ideographs)."""
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
