"""Planner Agent — generates plot branch options for the next chapter.

Uses Opus for complex reasoning. Given the Story Bible state and recent chapters,
generates 2-3 plot branches with consequences for character arcs, foreshadowing
payoff opportunities, and tension curve impact.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..llm import LLMClient, LLMResponse, MODEL_OPUS
from ..story_bible.compressor import CompressedContext

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """\
你是一位资深网络小说策划大师。你的任务是为下一章生成2-3个剧情分支选项。

## 核心原则

1. **三幕式结构**: 每个分支必须推进整体叙事结构（建置→对抗→解决）
2. **爽点分布**: 确保每个分支包含至少一个爽点（小爽点、中爽点或大爽点）
3. **钩子技术**: 每个分支的结尾必须设计一个钩子（悬念/冲突/情感/反转）
4. **角色驱动**: 让角色的动机和选择驱动情节，而不是情节绑架角色
5. **伏笔管理**: 如果有即将到期的伏笔，至少一个分支必须包含回收机会

## 输出格式

你必须以JSON格式输出，结构如下：

```json
{
  "branches": [
    {
      "title": "分支标题",
      "outline": "详细的章节大纲（200-400字）",
      "characters_involved": ["角色名"],
      "consequences": "这个选择对角色弧线和整体剧情的影响",
      "foreshadowing_opportunities": ["可以回收或新植入的伏笔"],
      "satisfaction_type": "minor/medium/major",
      "hook_type": "suspense/conflict/emotional/reversal",
      "hook_description": "章末钩子的设计",
      "tension_impact": "tension_increase/tension_decrease/tension_maintain",
      "risk_level": "safe/moderate/bold"
    }
  ],
  "context_notes": "对当前剧情状态的简要分析"
}
```

确保每个分支的走向明显不同，给读者/策划者真正有意义的选择。
"""


@dataclass
class PlotBranch:
    """A single plot branch option."""
    title: str
    outline: str
    characters_involved: list[str]
    consequences: str
    foreshadowing_opportunities: list[str]
    satisfaction_type: str
    hook_type: str
    hook_description: str
    tension_impact: str
    risk_level: str


@dataclass
class PlannerResult:
    """Result from the Planner Agent."""
    branches: list[PlotBranch]
    context_notes: str
    raw_response: LLMResponse


class PlannerAgent:
    """Generates plot branch options for the next chapter."""

    def __init__(self, llm: LLMClient, model: str = MODEL_OPUS) -> None:
        self.llm = llm
        self.model = model

    async def plan(
        self,
        bible_context: CompressedContext,
        recent_chapters_text: str,
        chapter_number: int,
        additional_guidance: str = "",
    ) -> PlannerResult:
        """Generate plot branches for the next chapter.

        Args:
            bible_context: Compressed Story Bible context.
            recent_chapters_text: Text of recent 2-3 chapters for continuity.
            chapter_number: The chapter number being planned.
            additional_guidance: Optional human guidance for the planner.

        Returns:
            PlannerResult with 2-3 plot branches.
        """
        user_message = self._build_prompt(
            bible_context, recent_chapters_text, chapter_number, additional_guidance
        )

        response = await self.llm.complete(
            system=PLANNER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            model=self.model,
            max_tokens=4096,
            temperature=0.8,  # Higher creativity for diverse branches
        )

        branches, context_notes = self._parse_response(response.text)

        # If parsing failed, try LLM-based JSON repair (one retry)
        if len(branches) == 1 and branches[0].title == "未能解析的分支":
            logger.info("Planner JSON parse failed, attempting LLM repair...")
            repaired = await self._retry_json_repair(response.text)
            if repaired is not None:
                repaired_branches = _branches_from_data(repaired)
                if repaired_branches:
                    branches = repaired_branches
                    context_notes = repaired.get("context_notes", "")
                    logger.info("JSON repair succeeded, got %d branches", len(branches))

        return PlannerResult(
            branches=branches,
            context_notes=context_notes,
            raw_response=response,
        )

    def _build_prompt(
        self,
        bible_context: CompressedContext,
        recent_chapters: str,
        chapter_number: int,
        guidance: str,
    ) -> str:
        parts = [
            f"## 当前Story Bible状态\n\n{bible_context.text}",
            f"\n\n## 近期章节内容\n\n{recent_chapters}" if recent_chapters else "",
            f"\n\n## 任务\n\n请为第{chapter_number}章生成2-3个不同的剧情分支选项。",
        ]
        if guidance:
            parts.append(f"\n\n## 创作者指导\n\n{guidance}")
        return "".join(parts)

    def _parse_response(self, text: str) -> tuple[list[PlotBranch], str]:
        """Parse the JSON response from the planner with repair logic."""
        data = _extract_and_parse_json(text)
        if data is None:
            return self._fallback_branch(text), "JSON解析失败，返回原始文本"

        branches = _branches_from_data(data)
        if not branches:
            return self._fallback_branch(text), "JSON中未找到branches，返回原始文本"

        return branches, data.get("context_notes", "")

    async def _retry_json_repair(self, broken_text: str) -> dict | None:
        """Ask the LLM to fix broken JSON output (one retry)."""
        repair_prompt = (
            "以下是你之前输出的JSON，但解析失败。请只输出修复后的合法JSON，"
            "不要加任何解释或markdown代码块。\n\n"
            f"{broken_text}"
        )
        try:
            response = await self.llm.complete(
                system="你是一个JSON修复工具。只输出合法JSON，不加任何其他内容。",
                messages=[{"role": "user", "content": repair_prompt}],
                model=self.model,
                max_tokens=4096,
                temperature=0.1,
            )
            return _extract_and_parse_json(response.text)
        except Exception:
            logger.warning("JSON repair retry failed")
            return None

    @staticmethod
    def _fallback_branch(text: str) -> list[PlotBranch]:
        return [
            PlotBranch(
                title="未能解析的分支",
                outline=text,
                characters_involved=[],
                consequences="",
                foreshadowing_opportunities=[],
                satisfaction_type="minor",
                hook_type="suspense",
                hook_description="",
                tension_impact="tension_maintain",
                risk_level="safe",
            )
        ]


def _extract_json_block(text: str) -> str:
    """Extract JSON from markdown code blocks or raw text."""
    # Try ```json ... ``` first
    m = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try ``` ... ```
    m = re.search(r"```\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try to find the outermost { ... }
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return text.strip()


def _repair_json_string(text: str) -> str:
    """Fix common JSON issues from LLM output."""
    s = text
    # Remove trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # Fix unescaped newlines inside string values
    # (naive: replace literal newlines between quotes)
    s = re.sub(r'(?<=": ")(.*?)(?="[,\s}\]])', lambda m: m.group(0).replace("\n", "\\n"), s)
    return s


def _extract_and_parse_json(text: str) -> dict | None:
    """Try multiple strategies to extract valid JSON from LLM output."""
    json_text = _extract_json_block(text)

    # Attempt 1: direct parse
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: repair common issues
    try:
        return json.loads(_repair_json_string(json_text))
    except json.JSONDecodeError:
        pass

    # Attempt 3: repair on the full text (in case extraction was wrong)
    try:
        return json.loads(_repair_json_string(text))
    except json.JSONDecodeError:
        pass

    logger.warning("All JSON parse attempts failed")
    return None


def _branches_from_data(data: dict) -> list[PlotBranch]:
    """Build PlotBranch list from parsed JSON data."""
    branches = []
    for b in data.get("branches", []):
        branches.append(PlotBranch(
            title=b.get("title", ""),
            outline=b.get("outline", ""),
            characters_involved=b.get("characters_involved", []),
            consequences=b.get("consequences", ""),
            foreshadowing_opportunities=b.get("foreshadowing_opportunities", []),
            satisfaction_type=b.get("satisfaction_type", "minor"),
            hook_type=b.get("hook_type", "suspense"),
            hook_description=b.get("hook_description", ""),
            tension_impact=b.get("tension_impact", "tension_maintain"),
            risk_level=b.get("risk_level", "safe"),
        ))
    return branches
