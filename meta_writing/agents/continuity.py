"""Continuity Agent — validates chapter consistency against Story Bible.

The highest-value review agent. Checks:
- Character state (injuries, knowledge, emotional state, location)
- Relationship states (who knows what about whom)
- Timeline consistency (no temporal contradictions)
- World rule enforcement (magic systems, technology, geography)
- Foreshadowing audit (aging, payoff opportunities)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from ..llm import LLMClient, LLMResponse, MODEL_SONNET
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
    CRITICAL = "critical"  # Must fix before publishing
    WARNING = "warning"  # Should fix, but not a showstopper
    INFO = "info"  # Suggestion for improvement


CONTINUITY_SYSTEM_PROMPT = """\
你是一位严谨的小说连续性审查专家。你的任务是验证新章节与Story Bible的一致性。

## 检查项目

1. **角色状态矛盾**: 角色的受伤状态、知识状态、情感状态、位置是否与Story Bible记录一致？
   - 例：上一章角色受了重伤，这一章却毫无影响地战斗
   - 例：角色不应该知道某个信息，却在对话中提到了

2. **关系状态矛盾**: 角色之间的关系是否与Story Bible一致？
   - 例：两个尚未相识的角色表现得很熟悉

3. **时间线矛盾**: 事件的时间顺序是否合理？
   - 例：白天发生的事情突然变成了夜晚
   - 例：角色在不可能的时间内到达某个地方

4. **世界规则违反**: 是否违反了已建立的世界规则？
   - 例：使用了该世界观中不存在的能力
   - 例：违反了已建立的魔法体系限制

5. **伏笔审计**: 检查是否有应该回收的伏笔被忽略
   - 例：即将到期的伏笔在本章有自然的回收机会但未被利用

6. **角色动机**: 角色行为是否有合理动机？
   - 核心三角（欲望/能力/阻碍）是否被尊重？
   - 行为是否符合角色的动机类型？

7. **信息流向/知识归属**: 对话和行为中的信息来源是否合理？
   - 角色在对话中展示的知识是否有合理来源？（谁知道什么、从哪里知道的）
   - 角色是否做出了超出其当前knowledge_state的判断或动作？
   - 请求/提议的方向是否正确？（例：知道地址的人应该说"我带你去"而非"你带我去"）
   - 角色A不应该凭空知道角色B的秘密，除非有明确的信息传递场景
   - 这是最容易出错的审查项——模型（作者）知道所有角色的信息，但角色本身不知道。审查时必须严格区分"作者知道的"和"角色知道的"。

8. **微感描写文风**: 涉及微感（通过触觉/听觉感知物体残留痕迹）的描写是否遵守"纯感官、不解读"原则？
   - ❌ "X记得Y"句式（沙发记得、门框记得、铁皮记得）——物体不会"记得"，只有物理现象
   - ❌ 拟人化（"在说话"、"在等"、"在叫"）——物体没有意图，只有声音/温度/磨损
   - ❌ 读心术（"他/她在想"）——微感只读物体痕迹，不读人的想法
   - ❌ 直白情感总结（"她懂了那种孤独"、"原来不是我一个人"）——留给读者体会
   - ✅ 正确写法：只写声音的频率/质感/层次、温度的分布/变化、磨损的形状/深浅，让读者自己连线

## 输出格式

以JSON格式输出审查结果：

```json
{
  "passed": true/false,
  "issues": [
    {
      "type": "character_state/relationship/timeline/world_rule/foreshadowing/motivation/knowledge_flow/style",
      "severity": "critical/warning/info",
      "description": "问题描述",
      "location": "问题出现的位置（引用原文）",
      "suggestion": "修改建议"
    }
  ],
  "foreshadowing_notes": "伏笔相关的观察（即使没有问题也要记录）",
  "state_changes_detected": [
    {
      "character": "角色名",
      "field": "变化的字段",
      "old_value": "旧值",
      "new_value": "新值"
    }
  ]
}
```

严格但公平：只标记真正的矛盾，不要过度挑剔创作自由的部分。
"""


@dataclass
class ContinuityIssue:
    """A single consistency issue found by the Continuity Agent."""
    type: IssueType
    severity: IssueSeverity
    description: str
    location: str
    suggestion: str


@dataclass
class StateChange:
    """A detected state change in a chapter."""
    character: str
    field: str
    old_value: str
    new_value: str


@dataclass
class ContinuityResult:
    """Result from the Continuity Agent."""
    passed: bool
    issues: list[ContinuityIssue]
    foreshadowing_notes: str
    state_changes: list[StateChange]
    raw_response: LLMResponse

    @property
    def critical_issues(self) -> list[ContinuityIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.CRITICAL]

    @property
    def has_critical(self) -> bool:
        return len(self.critical_issues) > 0

    def format_feedback(self) -> str:
        """Format issues as feedback for the Writer Agent's revision."""
        if not self.issues:
            return "无问题"

        lines = ["## 连续性审查反馈\n"]
        for i, issue in enumerate(self.issues, 1):
            severity_label = {
                IssueSeverity.CRITICAL: "🔴 严重",
                IssueSeverity.WARNING: "🟡 警告",
                IssueSeverity.INFO: "🔵 建议",
            }[issue.severity]
            lines.append(f"### 问题 {i} [{severity_label}] ({issue.type.value})")
            lines.append(f"**描述**: {issue.description}")
            if issue.location:
                lines.append(f"**位置**: {issue.location}")
            lines.append(f"**建议**: {issue.suggestion}")
            lines.append("")
        return "\n".join(lines)


class ContinuityAgent:
    """Validates chapter consistency against the Story Bible."""

    def __init__(self, llm: LLMClient, model: str = MODEL_SONNET) -> None:
        self.llm = llm
        self.model = model

    async def review(
        self,
        chapter_text: str,
        bible_context: CompressedContext,
        chapter_number: int,
    ) -> ContinuityResult:
        """Review a chapter for consistency issues.

        Args:
            chapter_text: The chapter text to review.
            bible_context: Compressed Story Bible context.
            chapter_number: The chapter number being reviewed.

        Returns:
            ContinuityResult with issues found.
        """
        user_message = (
            f"## Story Bible状态\n\n{bible_context.text}\n\n"
            f"## 第{chapter_number}章正文（待审查）\n\n{chapter_text}\n\n"
            f"请对第{chapter_number}章进行连续性审查。"
        )

        response = await self.llm.complete(
            system=CONTINUITY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=4096,
            temperature=0.3,  # Low temperature for precise analysis
        )

        return self._parse_response(response)

    def _parse_response(self, response: LLMResponse) -> ContinuityResult:
        """Parse the JSON response from the continuity review."""
        import re as _re
        text = response.text
        # Robust extraction: strip code block first, then find outermost {...}
        m = _re.search(r"```(?:json)?\s*\n?(.*?)```", text, _re.DOTALL)
        if m:
            text = m.group(1).strip()
        s = text.find("{")
        e = text.rfind("}") + 1
        if s != -1 and e > s:
            text = text[s:e]

        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError:
            # If parsing fails, treat as passed with a warning
            return ContinuityResult(
                passed=True,
                issues=[ContinuityIssue(
                    type=IssueType.CHARACTER_STATE,
                    severity=IssueSeverity.INFO,
                    description="连续性审查输出解析失败，请人工检查",
                    location="",
                    suggestion="重新运行审查",
                )],
                foreshadowing_notes="",
                state_changes=[],
                raw_response=response,
            )

        issues = []
        for i in data.get("issues", []):
            try:
                issues.append(ContinuityIssue(
                    type=IssueType(i.get("type", "character_state")),
                    severity=IssueSeverity(i.get("severity", "warning")),
                    description=i.get("description", ""),
                    location=i.get("location", ""),
                    suggestion=i.get("suggestion", ""),
                ))
            except ValueError:
                continue

        state_changes = []
        for sc in data.get("state_changes_detected", []):
            state_changes.append(StateChange(
                character=sc.get("character", ""),
                field=sc.get("field", ""),
                old_value=sc.get("old_value", ""),
                new_value=sc.get("new_value", ""),
            ))

        return ContinuityResult(
            passed=data.get("passed", len(issues) == 0),
            issues=issues,
            foreshadowing_notes=data.get("foreshadowing_notes", ""),
            state_changes=state_changes,
            raw_response=response,
        )
