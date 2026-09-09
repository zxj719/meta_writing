"""Continuity Agent - validates chapter consistency against Story Bible."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from ..editorial_scorecard import EditorialScorecard, EDITORIAL_SCORECARD_PROMPT
from ..llm import AgentClient, LLMResponse
from ..prompt_profiles import GENERIC_PROFILE, PromptProfile
from ..story_bible.compressor import CompressedContext


class IssueType(str, Enum):
    CHARACTER_STATE = "character_state"
    RELATIONSHIP = "relationship"
    TIMELINE = "timeline"
    WORLD_RULE = "world_rule"
    FORESHADOWING = "foreshadowing"
    MOTIVATION = "motivation"
    KNOWLEDGE_FLOW = "knowledge_flow"
    STYLE = "style"


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


CONTINUITY_BASE_SYSTEM_PROMPT = """\
你是一位严谨的小说连续性审查专家，任务是验证新章节与 Story Bible 的一致性。

## 检查项目

1. 角色状态矛盾：伤势、知识状态、情绪状态、位置是否前后一致。
2. 关系状态矛盾：角色之间是否突然越级熟悉或态度跳变。
3. 时间线矛盾：时间顺序、转场和赶路是否成立。
4. 世界规则违反：是否使用了不该存在的能力或违背已建立限制。
5. 伏笔审计：即将到期的伏笔有没有自然回收机会被忽略。
6. 角色动机：行为是否尊重角色的欲望/能力/阻碍三角。
7. 信息流向：角色说出口或做出来的判断，是否真有合理的信息来源。

## 判断标准

- 只标记真正的矛盾，不要过度干预创作自由。
- “作者知道”不等于“角色知道”，严格区分。
- 问题必须写清楚是什么、出在哪里、怎么改。

""" + EDITORIAL_SCORECARD_PROMPT + """

## 输出格式

```json
{
  "passed": true,
  "issues": [
    {
      "type": "character_state/relationship/timeline/world_rule/foreshadowing/motivation/knowledge_flow/style",
      "severity": "critical/warning/info",
      "description": "问题描述",
      "location": "问题位置",
      "suggestion": "修改建议"
    }
  ],
  "foreshadowing_notes": "伏笔相关观察",
  "state_changes_detected": [
    {
      "character": "角色名",
      "field": "变更字段",
      "old_value": "旧值",
      "new_value": "新值"
    }
  ],
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


def build_continuity_system_prompt(prompt_profile: PromptProfile | None = None) -> str:
    profile = prompt_profile or GENERIC_PROFILE
    sections = [CONTINUITY_BASE_SYSTEM_PROMPT.strip()]
    if profile.continuity_notes.strip():
        sections.append(profile.continuity_notes.strip())
    return "\n\n".join(sections)


@dataclass
class ContinuityIssue:
    type: IssueType
    severity: IssueSeverity
    description: str
    location: str
    suggestion: str


@dataclass
class StateChange:
    character: str
    field: str
    old_value: str
    new_value: str


@dataclass
class ContinuityResult:
    passed: bool
    issues: list[ContinuityIssue]
    foreshadowing_notes: str
    state_changes: list[StateChange]
    raw_response: LLMResponse
    scorecard: EditorialScorecard | None = None

    @property
    def critical_issues(self) -> list[ContinuityIssue]:
        return [issue for issue in self.issues if issue.severity == IssueSeverity.CRITICAL]

    @property
    def has_critical(self) -> bool:
        return bool(self.critical_issues)

    def format_feedback(self) -> str:
        if not self.issues:
            return "无问题"

        lines = ["## 连续性审查反馈", ""]
        severity_label = {
            IssueSeverity.CRITICAL: "🔴 严重",
            IssueSeverity.WARNING: "🟡 警告",
            IssueSeverity.INFO: "🔵 建议",
        }
        for index, issue in enumerate(self.issues, start=1):
            lines.append(f"### 问题 {index} [{severity_label[issue.severity]}] ({issue.type.value})")
            lines.append(f"**描述**: {issue.description}")
            if issue.location:
                lines.append(f"**位置**: {issue.location}")
            lines.append(f"**建议**: {issue.suggestion}")
            lines.append("")
        return "\n".join(lines)


class ContinuityAgent:
    """Validates chapter consistency against the Story Bible."""

    def __init__(self, llm: AgentClient, model: str | None = None) -> None:
        self.llm = llm
        self.model = model

    async def review(
        self,
        chapter_text: str,
        bible_context: CompressedContext,
        chapter_number: int,
        prompt_profile: PromptProfile | None = None,
        creative_guidance: str = "",
    ) -> ContinuityResult:
        user_message = (
            f"## Story Bible 状态\n\n{bible_context.text}\n\n"
            f"## 第{chapter_number}章正文（待审查）\n\n{chapter_text}\n\n"
        )
        if creative_guidance.strip():
            user_message += f"## 当前创作指令与项目要求\n\n{creative_guidance.strip()}\n\n"
        user_message += f"请对第{chapter_number}章进行连续性审查。"

        response = await self.llm.complete(
            system=build_continuity_system_prompt(prompt_profile),
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=4096,
            temperature=0.3,
        )
        return self._parse_response(response)

    def _parse_response(self, response: LLMResponse) -> ContinuityResult:
        text = response.text
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError:
            return ContinuityResult(
                passed=True,
                issues=[
                    ContinuityIssue(
                        type=IssueType.CHARACTER_STATE,
                        severity=IssueSeverity.INFO,
                        description="连续性审查输出解析失败，请人工检查。",
                        location="",
                        suggestion="重新运行审查。",
                    )
                ],
                foreshadowing_notes="",
                state_changes=[],
                raw_response=response,
                scorecard=None,
            )

        issues: list[ContinuityIssue] = []
        for item in data.get("issues", []):
            try:
                issues.append(
                    ContinuityIssue(
                        type=IssueType(item.get("type", "character_state")),
                        severity=IssueSeverity(item.get("severity", "warning")),
                        description=item.get("description", ""),
                        location=item.get("location", ""),
                        suggestion=item.get("suggestion", ""),
                    )
                )
            except ValueError:
                continue

        state_changes = [
            StateChange(
                character=item.get("character", ""),
                field=item.get("field", ""),
                old_value=item.get("old_value", ""),
                new_value=item.get("new_value", ""),
            )
            for item in data.get("state_changes_detected", [])
        ]

        return ContinuityResult(
            passed=data.get("passed", len(issues) == 0),
            issues=issues,
            foreshadowing_notes=data.get("foreshadowing_notes", ""),
            state_changes=state_changes,
            raw_response=response,
            scorecard=EditorialScorecard.from_json_dict(data.get("scorecard")),
        )
