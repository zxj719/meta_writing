"""Theme/Story Agent - cross-chapter editorial review."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..editorial_scorecard import EditorialScorecard, EDITORIAL_SCORECARD_PROMPT
from ..llm import LLMClient, LLMResponse, MODEL_SONNET
from ..prompt_profiles import GENERIC_PROFILE, PromptProfile

logger = logging.getLogger(__name__)


STORY_EDITOR_PROMPT = """\
你是一位负责“剧情、人物、暗线和完成度”的章节编辑。你不是纯连续性检查器，也不是纯文风编辑，你要判断这一章作为“小说章节”是否成立。

## 你的审查重点

1. 这一章是否真的在推进故事，而不是空转。
2. 主角和配角是否像活人，而不是嘴替或工具人。
3. 信息与暗线是否藏在动作、环境、选择和对话缝隙里，而不是靠直说。
4. 这一章是否回应了当前创作指令和上一轮要求。
5. 如果本章是过渡章，是否仍然留下可读性、高光、关系推进或后续钩子。

## 判断标准

- 不要要求每章都必须爆大雷，但不能允许松散空转。
- 普通生活章可以松，但松弛不等于无事发生。
- 要特别警惕“为了满足要求，硬插一段”的痕迹。

""" + EDITORIAL_SCORECARD_PROMPT + """

## 输出格式

```json
{
  "chapter_evaluated": "章节号",
  "thematic_health": "healthy/needs_work/critical",
  "issues": [
    {
      "type": "no_progression/character_flatness/info_too_direct/instruction_miss/pattern_repetition",
      "severity": "critical/warning/info",
      "description": "问题描述",
      "location": "位置或段落说明",
      "suggestion": "修改方向"
    }
  ],
  "arc_position_notes": "本章在整体故事弧线中的位置判断",
  "what_this_chapter_adds": "本章给读者的独特贡献",
  "scorecard": {
    "plot_tension": {"score": 0-10, "reason": "一句理由"},
    "characters": {"score": 0-10, "reason": "一句理由"},
    "info_design": {"score": 0-10, "reason": "一句理由"},
    "language": {"score": 0-10, "reason": "一句理由"},
    "instruction_fit": {"score": 0-10, "reason": "一句理由"}
  }
}
```
"""


LITERARY_THEME_PROMPT = """\
你是一位专注于文学主题连贯性的资深编辑。你审查的是一部以“克制美学”为核心的中文小说。

## 审查重点

1. 主题推进：本章是否比上一章多走了一步，而不是重复同一种感悟。
2. 克制性：是否说穿了本该交给读者自己感受到的内容。
3. 人物弧线位置：人物状态是否与整体弧线一致。
4. 意象使用：核心意象有没有新层次，而不是只在重复。
5. 跨章模式：是否机械重复了同一种场景结构或感知路径。

""" + EDITORIAL_SCORECARD_PROMPT + """

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
      "location": "章节内位置或章节编号",
      "suggestion": "修改方向"
    }
  ],
  "arc_position_notes": "本章在整体弧线中的位置判断",
  "what_this_chapter_adds": "本章给读者的新理解",
  "scorecard": {
    "plot_tension": {"score": 0-10, "reason": "一句理由"},
    "characters": {"score": 0-10, "reason": "一句理由"},
    "info_design": {"score": 0-10, "reason": "一句理由"},
    "language": {"score": 0-10, "reason": "一句理由"},
    "instruction_fit": {"score": 0-10, "reason": "一句理由"}
  }
}
```
"""


def build_theme_system_prompt(prompt_profile: PromptProfile | None = None) -> str:
    profile = prompt_profile or GENERIC_PROFILE
    if profile.third_editor_mode == "literary_theme":
        return LITERARY_THEME_PROMPT
    return STORY_EDITOR_PROMPT


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
    scorecard: EditorialScorecard | None = None

    @property
    def has_critical(self) -> bool:
        return any(issue.severity == "critical" for issue in self.issues)

    def format_feedback(self) -> str:
        if not self.issues:
            return ""
        lines = ["## 第三编辑审查反馈", ""]
        severity_icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        for issue in self.issues:
            lines.append(f"{severity_icons.get(issue.severity, '🔵')} **{issue.type}**: {issue.description}")
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
    """Cross-chapter thematic or story-editor reviewer."""

    def __init__(self, llm: LLMClient, model: str = MODEL_SONNET) -> None:
        self.llm = llm
        self.model = model

    async def review_chapter(
        self,
        chapter_text: str,
        chapter_number: int,
        previous_chapter_summary: str = "",
        arc_context: str = "",
        creative_guidance: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> ThemeAgentResult:
        parts = [f"## 第{chapter_number}章正文\n\n{chapter_text}"]
        if previous_chapter_summary:
            parts.append(f"\n\n## 上一章摘要\n\n{previous_chapter_summary}")
        if arc_context:
            parts.append(f"\n\n## 整体弧线背景\n\n{arc_context}")
        if creative_guidance.strip():
            parts.append(f"\n\n## 当前创作指令与项目要求\n\n{creative_guidance.strip()}")
        parts.append(f"\n\n请对第{chapter_number}章进行第三编辑审查，并输出 JSON 结果。")

        response = await self.llm.complete(
            system=build_theme_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": "".join(parts)}],
            model=self.model,
            max_tokens=4096,
            temperature=0.3,
        )
        return self._parse_response(response, str(chapter_number))

    async def review_arc(
        self,
        chapters: list[tuple[int, str]],
        arc_context: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> ThemeAgentResult:
        chapter_range = f"{chapters[0][0]}-{chapters[-1][0]}"
        summaries = [
            f"第{number}章开头：{text[:500].replace(chr(10), ' ')}..."
            for number, text in chapters
        ]

        user_message = f"## 章节范围：第{chapter_range}章\n\n" + "\n\n".join(summaries)
        if arc_context:
            user_message += f"\n\n## 整体弧线背景\n\n{arc_context}"
        user_message += f"\n\n请对第{chapter_range}章进行跨章第三编辑审查。"

        response = await self.llm.complete(
            system=build_theme_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=4096,
            temperature=0.3,
        )
        return self._parse_response(response, chapter_range)

    def _parse_response(self, response: LLMResponse, chapter_label: str) -> ThemeAgentResult:
        text = response.text
        match = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
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
                arc_position_notes="第三编辑输出解析失败",
                what_this_chapter_adds="",
                raw_response=response,
                scorecard=None,
            )

        issues = [
            ThemeIssue(
                type=item.get("type", ""),
                severity=item.get("severity", "info"),
                description=item.get("description", ""),
                location=item.get("location", ""),
                suggestion=item.get("suggestion", ""),
            )
            for item in data.get("issues", [])
        ]

        return ThemeAgentResult(
            chapter_evaluated=data.get("chapter_evaluated", chapter_label),
            thematic_health=data.get("thematic_health", "healthy"),
            issues=issues,
            arc_position_notes=data.get("arc_position_notes", ""),
            what_this_chapter_adds=data.get("what_this_chapter_adds", ""),
            raw_response=response,
            scorecard=EditorialScorecard.from_json_dict(data.get("scorecard")),
        )
