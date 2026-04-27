"""Style Agent - LLM-based prose quality review."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..editorial_scorecard import EditorialScorecard, EDITORIAL_SCORECARD_PROMPT
from ..llm import LLMClient, LLMResponse, MODEL_SONNET
from ..prompt_profiles import GENERIC_PROFILE, PromptProfile

logger = logging.getLogger(__name__)


STYLE_BASE_SYSTEM_PROMPT = """\
你是一位专注于中文网络小说文风的审稿编辑。你的任务是审查章节正文，找出影响阅读体验的文风问题。

## 你的审查重点

1. 机械语言模式：重复脚手架、公式化断句、固定句式回潮、AI 腔总结句。
2. 说话方式元注释：不要把“他说话的方式是……”这种作者说明当成有效描写。
3. 描写缺口：主角外貌、神态、身体反应、环境画面是否明显偏薄。
4. 结构回声：与前一章结尾或本章内部段落结构是否过度相似。
5. 节奏单一：整章是否只剩逻辑推进，没有动作、环境、心理和对话的交替。
6. 比喻老套或堆叠：不是禁止比喻，而是防止套话和过密。

## 判断标准

- 只标记真正影响阅读体验的问题，不要过度挑刺。
- 偶发一次不算问题，频率过高才算。
- 如果外貌、神态、环境三项里至少两项明显缺失，应至少提出 warning。
- 问题描述必须具体指出“缺了什么”和“适合补在哪里”。

""" + EDITORIAL_SCORECARD_PROMPT + """

## 输出格式

```json
{
  "passed": true,
  "issues": [
    {
      "type": "mechanical_pattern/meta_commentary/description_gap/structural_echo/over_explanation/rhythm_monotony/simile_density",
      "severity": "error/warning/info",
      "description": "具体问题描述",
      "location": "问题位置或短引文",
      "suggestion": "修改建议"
    }
  ],
  "rhythm_notes": "对整体节奏的一句判断",
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


def build_style_system_prompt(prompt_profile: PromptProfile | None = None) -> str:
    profile = prompt_profile or GENERIC_PROFILE
    sections = [STYLE_BASE_SYSTEM_PROMPT.strip()]
    if profile.revision_notes.strip():
        sections.append("## 当前项目修订约束\n" + profile.revision_notes.strip())
    return "\n\n".join(sections)


@dataclass
class StyleIssue:
    type: str
    severity: str
    description: str
    location: str
    suggestion: str


@dataclass
class StyleAgentResult:
    passed: bool
    issues: list[StyleIssue]
    rhythm_notes: str
    raw_response: LLMResponse
    scorecard: EditorialScorecard | None = None

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def format_feedback(self) -> str:
        if not self.issues:
            return ""
        lines = ["## 文风审查反馈", ""]
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
        creative_guidance: str = "",
        prompt_profile: PromptProfile | None = None,
    ) -> StyleAgentResult:
        user_message = self._build_prompt(
            chapter_text=chapter_text,
            prev_ending=previous_chapter_ending,
            chapter_number=chapter_number,
            creative_guidance=creative_guidance,
        )

        response = await self.llm.complete(
            system=build_style_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=4096,
            temperature=0.3,
        )
        return self._parse_response(response)

    def _build_prompt(
        self,
        chapter_text: str,
        prev_ending: str,
        chapter_number: int,
        creative_guidance: str,
    ) -> str:
        parts = []
        if chapter_number:
            parts.append(f"## 第{chapter_number}章正文\n\n{chapter_text}")
        else:
            parts.append(f"## 章节正文\n\n{chapter_text}")

        if prev_ending:
            parts.append(f"\n\n## 前一章结尾（用于结构回声检测）\n\n{prev_ending}")
        if creative_guidance.strip():
            parts.append(f"\n\n## 当前创作指令与项目要求\n\n{creative_guidance.strip()}")

        parts.append("\n\n请对以上章节进行文风审查，并严格输出 JSON。")
        return "".join(parts)

    def _parse_response(self, response: LLMResponse) -> StyleAgentResult:
        text = response.text
        match = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            match = re.search(r"```\s*\n?(.*?)```", text, re.DOTALL)
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
            logger.warning("Style Agent JSON parse failed")
            return StyleAgentResult(
                passed=True,
                issues=[],
                rhythm_notes="文风审查输出解析失败",
                raw_response=response,
                scorecard=None,
            )

        issues = [
            StyleIssue(
                type=item.get("type", ""),
                severity=item.get("severity", "info"),
                description=item.get("description", ""),
                location=item.get("location", ""),
                suggestion=item.get("suggestion", ""),
            )
            for item in data.get("issues", [])
        ]

        return StyleAgentResult(
            passed=data.get("passed", True),
            issues=issues,
            rhythm_notes=data.get("rhythm_notes", ""),
            raw_response=response,
            scorecard=EditorialScorecard.from_json_dict(data.get("scorecard")),
        )
