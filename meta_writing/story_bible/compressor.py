"""Context budget management for Story Bible.

Compresses Story Bible state to fit within agent context windows.
Budget: ~15K tokens for Story Bible state (from design doc).

Strategy:
- Under budget: full context for all active components
- Over budget: summarize secondary characters to 2-3 sentences
- Way over budget: minimal context (POV character + direct interactions only)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .schema import (
    Character,
    ChapterSummary,
    ForeshadowingPair,
    PacingState,
    StoryBible,
    StoryCore,
    TimelineEvent,
    WorldRule,
)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.5 Chinese chars per token, ~4 English chars per token."""
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


@dataclass
class CompressedContext:
    """Compressed Story Bible context ready for agent consumption."""
    text: str
    estimated_tokens: int
    compression_level: str  # "full" | "summarized" | "minimal"


class StoryBibleCompressor:
    """Compresses Story Bible state to fit within token budgets."""

    def __init__(self, token_budget: int = 15000) -> None:
        self.token_budget = token_budget

    def compress(
        self,
        bible: StoryBible,
        current_chapter: int,
        active_character_names: list[str] | None = None,
        pov_character: str | None = None,
    ) -> CompressedContext:
        """Compress Story Bible for agent context.

        Args:
            bible: Full Story Bible state.
            current_chapter: Current chapter being written.
            active_character_names: Characters in the current chapter outline.
                If None, inferred from recent chapter summaries.
            pov_character: POV character for the current chapter.
        """
        if active_character_names is None:
            active_character_names = self._infer_active_characters(bible, current_chapter)

        # Try full context first
        full = self._build_full_context(bible, current_chapter, active_character_names)
        tokens = _estimate_tokens(full)
        if tokens <= self.token_budget:
            return CompressedContext(text=full, estimated_tokens=tokens, compression_level="full")

        # Try summarized (compress secondary characters)
        summarized = self._build_summarized_context(
            bible, current_chapter, active_character_names, pov_character
        )
        tokens = _estimate_tokens(summarized)
        if tokens <= self.token_budget:
            return CompressedContext(text=summarized, estimated_tokens=tokens, compression_level="summarized")

        # Minimal: POV + direct interactions only
        minimal = self._build_minimal_context(
            bible, current_chapter, active_character_names, pov_character
        )
        tokens = _estimate_tokens(minimal)
        return CompressedContext(text=minimal, estimated_tokens=tokens, compression_level="minimal")

    def _infer_active_characters(self, bible: StoryBible, current_chapter: int) -> list[str]:
        """Infer active characters from recent 3 chapter summaries."""
        names: set[str] = set()
        for ch in range(max(1, current_chapter - 2), current_chapter + 1):
            summary = bible.chapter_summaries.get(ch)
            if summary:
                names.update(summary.characters_present)
        return list(names) if names else list(bible.characters.keys())[:5]

    # --- Full context ---

    def _build_full_context(
        self, bible: StoryBible, current_chapter: int, active_names: list[str]
    ) -> str:
        sections = [
            self._format_core(bible.core),
            self._format_characters_full(bible, active_names),
            self._format_timeline(bible.recent_timeline(current_chapter)),
            self._format_world_rules(bible.world_rules),
            self._format_foreshadowing(bible, current_chapter),
            self._format_pacing(bible.pacing, current_chapter),
        ]
        return "\n\n".join(s for s in sections if s)

    # --- Summarized context ---

    def _build_summarized_context(
        self,
        bible: StoryBible,
        current_chapter: int,
        active_names: list[str],
        pov_character: str | None,
    ) -> str:
        primary = {pov_character} if pov_character else set()
        primary.update(active_names[:3])  # Top 3 active characters get full profiles

        sections = [
            self._format_core(bible.core),
            self._format_characters_mixed(bible, primary, active_names),
            self._format_timeline(bible.recent_timeline(current_chapter, lookback=5)),
            self._format_foreshadowing(bible, current_chapter),
        ]
        return "\n\n".join(s for s in sections if s)

    # --- Minimal context ---

    def _build_minimal_context(
        self,
        bible: StoryBible,
        current_chapter: int,
        active_names: list[str],
        pov_character: str | None,
    ) -> str:
        primary = {pov_character} if pov_character else set()
        if not primary:
            primary.add(active_names[0] if active_names else "")
        primary.discard("")

        sections = [
            self._format_core_minimal(bible.core),
            self._format_characters_minimal(bible, primary),
            self._format_foreshadowing_urgent(bible, current_chapter),
        ]
        return "\n\n".join(s for s in sections if s)

    # --- Formatters ---

    def _format_core(self, core: StoryCore) -> str:
        lines = [
            "# 故事核心",
            f"一句话核心: {core.hook}",
            f"体裁: {core.genre.value}",
            f"核心爽点: {core.target_satisfaction_type}",
            f"当前章节: {core.current_chapter}",
        ]
        if core.world_layers:
            lines.append("\n## 世界架构")
            for layer in core.world_layers:
                revealed = f" (第{layer.revealed_in_chapter}章揭示)" if layer.revealed_in_chapter else ""
                lines.append(f"- {layer.name}: {layer.description}{revealed}")
        return "\n".join(lines)

    def _format_core_minimal(self, core: StoryCore) -> str:
        return f"# 故事核心\n一句话: {core.hook}\n体裁: {core.genre.value}\n当前章节: {core.current_chapter}"

    def _format_characters_full(self, bible: StoryBible, active_names: list[str]) -> str:
        if not active_names:
            return ""
        lines = ["# 活跃角色"]
        for name in active_names:
            char = bible.characters.get(name)
            if not char:
                continue
            lines.append(self._character_to_full_text(char))
        return "\n".join(lines)

    def _format_characters_mixed(
        self, bible: StoryBible, primary: set[str], all_active: list[str]
    ) -> str:
        lines = ["# 角色"]
        for name in all_active:
            char = bible.characters.get(name)
            if not char:
                continue
            if name in primary:
                lines.append(self._character_to_full_text(char))
            else:
                lines.append(self._character_to_summary(char))
        return "\n".join(lines)

    def _format_characters_minimal(self, bible: StoryBible, primary: set[str]) -> str:
        lines = ["# 核心角色"]
        for name in primary:
            char = bible.characters.get(name)
            if char:
                lines.append(self._character_to_full_text(char))
        return "\n".join(lines)

    def _character_to_full_text(self, char: Character) -> str:
        lines = [
            f"\n## {char.name}",
            f"外貌: {char.physical_description}" if char.physical_description else "",
            f"性格: {', '.join(char.personality_traits)}" if char.personality_traits else "",
            f"情感状态: {char.emotional_state}" if char.emotional_state else "",
            f"位置: {char.location}" if char.location else "",
            f"目标: {', '.join(char.current_goals)}" if char.current_goals else "",
            f"核心三角 — 欲望: {char.core_triangle.desire} / 能力: {char.core_triangle.ability} / 阻碍: {char.core_triangle.obstacle}",
            f"动机类型: {char.motivation_type.value}",
            f"成长阶段: {char.growth_stage.value}",
        ]
        if char.relationships:
            lines.append("关系:")
            for rel in char.relationships:
                lines.append(f"  - {rel.target} ({rel.type}): {rel.description}")
        if char.knowledge_state:
            lines.append(f"已知信息: {char.knowledge_state}")
        return "\n".join(l for l in lines if l)

    def _character_to_summary(self, char: Character) -> str:
        """Summarize a character in 2-3 sentences."""
        traits = ", ".join(char.personality_traits[:3]) if char.personality_traits else "未知"
        return (
            f"\n## {char.name} (简述)\n"
            f"{char.physical_description[:50] if char.physical_description else ''}。"
            f"性格: {traits}。"
            f"目标: {char.current_goals[0] if char.current_goals else '未明确'}。"
            f"动机: {char.motivation_type.value}。"
        )

    def _format_timeline(self, events: list[TimelineEvent]) -> str:
        if not events:
            return ""
        lines = ["# 近期事件时间线"]
        for event in events:
            lines.append(f"- [第{event.chapter}章] {event.description}")
        return "\n".join(lines)

    def _format_world_rules(self, rules: list[WorldRule]) -> str:
        if not rules:
            return ""
        lines = ["# 世界规则"]
        for rule in rules:
            lines.append(f"\n## {rule.name} ({rule.category})")
            lines.append(rule.description)
            if rule.constraints:
                lines.append("硬性约束:")
                for c in rule.constraints:
                    lines.append(f"  - {c}")
        return "\n".join(lines)

    def _format_foreshadowing(self, bible: StoryBible, current_chapter: int) -> str:
        active = bible.active_foreshadowing()
        if not active:
            return ""
        lines = ["# 活跃伏笔"]
        aging = bible.aging_foreshadowing(current_chapter)
        aging_ids = {f.id for f in aging}
        for f in active:
            age = f.age_at(current_chapter)
            urgent = " ⚠️ 即将到期!" if f.id in aging_ids else ""
            lines.append(
                f"- [{f.id}] {f.setup_description} (第{f.setup_chapter}章植入, "
                f"已过{age}章){urgent}"
            )
        return "\n".join(lines)

    def _format_foreshadowing_urgent(self, bible: StoryBible, current_chapter: int) -> str:
        aging = bible.aging_foreshadowing(current_chapter)
        if not aging:
            return ""
        lines = ["# ⚠️ 紧急伏笔 (即将到期)"]
        for f in aging:
            lines.append(f"- [{f.id}] {f.setup_description} (已过{f.age_at(current_chapter)}章)")
        return "\n".join(lines)

    def _format_pacing(self, pacing: PacingState, current_chapter: int) -> str:
        upcoming = [b for b in pacing.beats if b.chapter >= current_chapter and not b.delivered]
        if not upcoming:
            return ""
        lines = ["# 即将到来的爽点"]
        for beat in upcoming[:5]:
            lines.append(f"- 第{beat.chapter}章: {beat.beat_type.value} — {beat.description}")
        return "\n".join(lines)
