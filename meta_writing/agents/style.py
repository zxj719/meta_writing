"""Style Agent — LLM-based prose quality review.

Catches what regex cannot:
- AI verbal tics and rhythm monotony across a chapter
- Structural echoes with previous chapters (ending copy, opening copy)
- Over-explanation of the sensing process
- Dialogue meta-commentary patterns
- Consecutive paragraph structural monotony

Uses MiniMax-M2.7 (fast tier) for cost-efficient style review.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum

from ..llm import LLMClient, LLMResponse, MODEL_SONNET

logger = logging.getLogger(__name__)


STYLE_SYSTEM_PROMPT = """\
你是一位专注于中文网络小说文风的审稿编辑。你的任务是审查章节正文，找出影响阅读体验的文风问题。

## 你的审查重点

1. **AI节拍感**：重复性短句口头禅（"可以。"/"稳的。"/"嗯。"出现超过合理次数）、刻度汇报超过2次、感知流程变成系统日志

2. **说话方式元注释**：描述角色"说话方式"而不是直接展示（"他说话的方式是...慢一点，因为..."——这是作者注释，不是叙事）

3. **结构回声**：与前一章的结尾或开头句式过于相似，给读者似曾相识的疲惫感

4. **过度解释感知过程**：描写微感时走向"步骤说明书"（"第一步...第二步..."/"有三个层次..."），而不是流动的感知体验

5. **段落节奏单一**：连续5段以上都以相同的句式开头（都是"她..."/"都是"然后..."），缺乏节奏变化

6. **比喻密度过高**：500字内出现3个以上比喻，造成密度感过重

## 判断标准

- 只标记真正影响阅读体验的问题，不过度挑剔
- 偶尔一次的确认短句不算问题——是频率问题
- 有意识的重复（排比、强调）不算节奏单一
- 不要对微感描写的内容本身提意见（只看文风，不看世界观逻辑）

## 输出格式

```json
{
  "passed": true/false,
  "issues": [
    {
      "type": "ai_tic/meta_commentary/structural_echo/over_explanation/rhythm_monotony/simile_density",
      "severity": "error/warning/info",
      "description": "问题描述（具体、可操作）",
      "location": "问题位置（引用原文片段，20字以内）",
      "suggestion": "修改建议"
    }
  ],
  "rhythm_notes": "章节节奏的整体观察（即使没有问题也要写一行）"
}
```
"""


@dataclass
class StyleIssue:
    """A style issue found by the Style Agent."""
    type: str
    severity: str
    description: str
    location: str
    suggestion: str


@dataclass
class StyleAgentResult:
    """Result from the Style Agent."""
    passed: bool
    issues: list[StyleIssue]
    rhythm_notes: str
    raw_response: LLMResponse

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def format_feedback(self) -> str:
        if not self.issues:
            return ""
        lines = ["## 文风审查反馈\n"]
        severity_icons = {"error": "🔴", "warning": "🟡", "info": "🔵"}
        for issue in self.issues:
            icon = severity_icons.get(issue.severity, "🔵")
            lines.append(f"{icon} **{issue.type}**: {issue.description}")
            if issue.location:
                lines.append(f"   位置: 「{issue.location}」")
            lines.append(f"   建议: {issue.suggestion}")
            lines.append("")
        return "\n".join(lines)


class StyleAgent:
    """LLM-based prose style reviewer."""

    def __init__(self, llm: LLMClient, model: str = MODEL_SONNET) -> None:
        self.llm = llm
        self.model = model

    async def review(
        self,
        chapter_text: str,
        previous_chapter_ending: str = "",
        chapter_number: int = 0,
    ) -> StyleAgentResult:
        """Review a chapter for style issues.

        Args:
            chapter_text: The chapter text to review.
            previous_chapter_ending: Last ~300 chars of the previous chapter (for echo detection).
            chapter_number: Chapter number for context.

        Returns:
            StyleAgentResult with issues found.
        """
        user_message = self._build_prompt(chapter_text, previous_chapter_ending, chapter_number)

        response = await self.llm.complete(
            system=STYLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=4096,
            temperature=0.3,
        )

        return self._parse_response(response)

    def _build_prompt(
        self, chapter_text: str, prev_ending: str, chapter_number: int
    ) -> str:
        parts = []
        if chapter_number:
            parts.append(f"## 第{chapter_number}章正文\n\n{chapter_text}")
        else:
            parts.append(f"## 章节正文\n\n{chapter_text}")

        if prev_ending:
            parts.append(f"\n\n## 前一章结尾（用于结构回声检测）\n\n{prev_ending}")

        parts.append("\n\n请对以上章节进行文风审查，输出JSON格式结果。")
        return "".join(parts)

    def _parse_response(self, response: LLMResponse) -> StyleAgentResult:
        text = response.text
        # Extract JSON from possible markdown
        m = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        else:
            m = re.search(r"```\s*\n?(.*?)```", text, re.DOTALL)
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
            logger.warning("Style Agent JSON parse failed")
            return StyleAgentResult(
                passed=True,
                issues=[],
                rhythm_notes="文风审查输出解析失败",
                raw_response=response,
            )

        issues = [
            StyleIssue(
                type=i.get("type", ""),
                severity=i.get("severity", "info"),
                description=i.get("description", ""),
                location=i.get("location", ""),
                suggestion=i.get("suggestion", ""),
            )
            for i in data.get("issues", [])
        ]

        return StyleAgentResult(
            passed=data.get("passed", True),
            issues=issues,
            rhythm_notes=data.get("rhythm_notes", ""),
            raw_response=response,
        )
