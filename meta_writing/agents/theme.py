"""Theme Agent — cross-chapter thematic coherence review.

Tracks:
- Thematic progression (each chapter should advance, not repeat)
- Restraint aesthetic (克制美学) violations
- Character arc position consistency
- Core motif consistency (glass, keys, demolition, notebooks)
- Concept drift across chapters
- Pattern repetition without escalation

Uses MiniMax-M2.7 via the existing LLMClient.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum

from ..llm import LLMClient, LLMResponse, MODEL_SONNET

logger = logging.getLogger(__name__)


THEME_SYSTEM_PROMPT = """\
你是一位专注于文学主题连贯性的资深编辑。你审查的是一部以"克制美学"为核心的中文文学小说。

## 故事核心

**主题**: 物体记录时间，微感者能感知这些记录——但感知到的只是影子，不是那件事本身。
**美学原则**: 不说出来的 > 说出来的。留白是技艺，不是省略。
**人物**: 夏浮（声音微感）、温野（温度/热量微感）、梁书（书店主，现实压力锚点）
**弧线节奏**: 孤独→相遇→互补感知→命名声音博物馆→找到呈现方式

## 你的审查重点

### 单章审查
1. **主题推进**: 本章比上一章在主题理解上前进了多少？如果没有前进（只是重复了同样的感悟），标记为问题
2. **克制性违反**: 是否有地方"说穿了"本应留给读者的内容？是否有不必要的解释或总结？
3. **人物弧线位置**: 夏浮/温野的状态是否与其所处弧线阶段一致？（比如"已经信任"的状态不应出现在信任建立之前的章节）
4. **意象使用**: 核心意象（玻璃、钥匙、拆迁中的建筑、笔记本）的使用是否有新的层次，还是在重复?

### 跨章审查（仅在提供多章时）
5. **概念漂移**: 某个关键概念（如"刻度"、"微感"、"密度"）的定义是否在不同章节间有不一致？
6. **情节模式重复**: 是否有某个场景结构（如：进入空间→感知→过载→撤退→台阶上聊天）在不加递进的情况下重复出现？

## 判断标准

- 只标记真正影响故事质量的问题
- "重复"只是问题，如果重复带来了新的层次或反转则不是问题
- 不要对感知描写的技术细节提意见（那是Style Agent的工作）
- 主题审查关注"这一章的存在是否有必要，它给读者提供了什么新的理解"

## 输出格式

```json
{
  "chapter_evaluated": "章节号或范围",
  "thematic_health": "healthy/needs_work/critical",
  "issues": [
    {
      "type": "no_progression/restraint_violation/arc_mismatch/motif_repetition/concept_drift/pattern_repetition",
      "severity": "critical/warning/info",
      "description": "问题描述",
      "location": "章节内位置或具体章节",
      "suggestion": "修改方向"
    }
  ],
  "arc_position_notes": "本章在整体弧线中的位置评估",
  "what_this_chapter_adds": "本章对读者理解的独特贡献（即使有问题也要写）"
}
```
"""


@dataclass
class ThemeIssue:
    type: str
    severity: str
    description: str
    location: str
    suggestion: str


@dataclass
class ThemeAgentResult:
    chapter_evaluated: str
    thematic_health: str
    issues: list[ThemeIssue]
    arc_position_notes: str
    what_this_chapter_adds: str
    raw_response: LLMResponse

    @property
    def has_critical(self) -> bool:
        return any(i.severity == "critical" for i in self.issues)

    def format_feedback(self) -> str:
        if not self.issues:
            return ""
        lines = ["## 主题审查反馈\n"]
        severity_icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        for issue in self.issues:
            icon = severity_icons.get(issue.severity, "🔵")
            lines.append(f"{icon} **{issue.type}**: {issue.description}")
            if issue.location:
                lines.append(f"   位置: {issue.location}")
            lines.append(f"   建议: {issue.suggestion}")
            lines.append("")
        if self.arc_position_notes:
            lines.append(f"**弧线位置**: {self.arc_position_notes}")
        if self.what_this_chapter_adds:
            lines.append(f"**本章贡献**: {self.what_this_chapter_adds}")
        return "\n".join(lines)


class ThemeAgent:
    """Cross-chapter thematic coherence reviewer."""

    def __init__(self, llm: LLMClient, model: str = MODEL_SONNET) -> None:
        self.llm = llm
        self.model = model

    async def review_chapter(
        self,
        chapter_text: str,
        chapter_number: int,
        previous_chapter_summary: str = "",
        arc_context: str = "",
    ) -> ThemeAgentResult:
        """Review a single chapter for thematic coherence.

        Args:
            chapter_text: The chapter text.
            chapter_number: Chapter number.
            previous_chapter_summary: Summary of previous chapter for progression check.
            arc_context: Overall arc position context.

        Returns:
            ThemeAgentResult.
        """
        parts = [f"## 第{chapter_number}章正文\n\n{chapter_text}"]
        if previous_chapter_summary:
            parts.append(f"\n\n## 上一章摘要（用于主题推进检查）\n\n{previous_chapter_summary}")
        if arc_context:
            parts.append(f"\n\n## 整体弧线背景\n\n{arc_context}")
        parts.append(f"\n\n请对第{chapter_number}章进行主题连贯性审查，输出JSON结果。")

        response = await self.llm.complete(
            system=THEME_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "".join(parts)}],
            model=self.model,
            max_tokens=2048,
            temperature=0.3,
        )
        return self._parse_response(response, str(chapter_number))

    async def review_arc(
        self,
        chapters: list[tuple[int, str]],  # [(chapter_number, text), ...]
        arc_context: str = "",
    ) -> ThemeAgentResult:
        """Review multiple chapters for cross-chapter thematic issues.

        Args:
            chapters: List of (chapter_number, text) tuples.
            arc_context: Overall story arc context.

        Returns:
            ThemeAgentResult covering all chapters.
        """
        chapter_range = f"{chapters[0][0]}-{chapters[-1][0]}"
        # Use summaries for multi-chapter review to stay within context
        summaries = []
        for num, text in chapters:
            # Take first 500 chars as representative sample
            sample = text[:500].replace('\n', ' ')
            summaries.append(f"第{num}章开头: {sample}...")

        user_message = (
            f"## 章节范围：第{chapter_range}章\n\n"
            + "\n\n".join(summaries)
        )
        if arc_context:
            user_message += f"\n\n## 整体弧线背景\n\n{arc_context}"
        user_message += f"\n\n请对第{chapter_range}章进行跨章主题审查，重点检查概念漂移和情节模式重复。"

        response = await self.llm.complete(
            system=THEME_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=3000,
            temperature=0.3,
        )
        return self._parse_response(response, chapter_range)

    def _parse_response(self, response: LLMResponse, chapter_label: str) -> ThemeAgentResult:
        text = response.text
        m = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Theme Agent JSON parse failed for chapter %s", chapter_label)
            return ThemeAgentResult(
                chapter_evaluated=chapter_label,
                thematic_health="unknown",
                issues=[],
                arc_position_notes="主题审查输出解析失败",
                what_this_chapter_adds="",
                raw_response=response,
            )

        issues = [
            ThemeIssue(
                type=i.get("type", ""),
                severity=i.get("severity", "info"),
                description=i.get("description", ""),
                location=i.get("location", ""),
                suggestion=i.get("suggestion", ""),
            )
            for i in data.get("issues", [])
        ]

        return ThemeAgentResult(
            chapter_evaluated=data.get("chapter_evaluated", chapter_label),
            thematic_health=data.get("thematic_health", "healthy"),
            issues=issues,
            arc_position_notes=data.get("arc_position_notes", ""),
            what_this_chapter_adds=data.get("what_this_chapter_adds", ""),
            raw_response=response,
        )
