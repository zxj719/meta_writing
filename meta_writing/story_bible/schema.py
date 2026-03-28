"""Pydantic models for Story Bible YAML validation.

Defines the structured state that maintains novel consistency:
- StoryCore: hook, genre, world architecture, pacing config
- Character: per-character profiles with motivation triangle
- TimelineEvent: ordered events with chapter references
- WorldRule: magic systems, geography, social structures
- ForeshadowingPair: setup/payoff tracking with aging
- PacingBeat: 爽点 schedule and hook placement
- ChapterSummary: per-chapter structured summary
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class Genre(str, Enum):
    XIANXIA = "玄幻仙侠"
    URBAN_FANTASY = "都市异能"
    MYSTERY = "悬疑推理"
    SCIFI = "科幻未来"
    HORROR = "惊悚悬疑"
    INFINITE = "无限流"
    HISTORICAL = "历史军事"
    ROMANCE = "现代言情"
    ANCIENT_ROMANCE = "古代言情"
    CAMPUS = "青春校园"


class MotivationType(str, Enum):
    SURVIVAL = "survival"
    EMOTIONAL = "emotional"
    INTEREST = "interest"
    MISSION = "mission"
    CURIOSITY = "curiosity"


class GrowthStage(str, Enum):
    INITIAL = "initial"
    TRIGGERED = "triggered"
    ADAPTING = "adapting"
    CRISIS = "crisis"
    TRANSFORMED = "transformed"


class ForeshadowingStatus(str, Enum):
    PLANTED = "planted"
    REINFORCED = "reinforced"
    PAID_OFF = "paid_off"
    ABANDONED = "abandoned"


class BeatType(str, Enum):
    MINOR = "minor"  # 小爽点 — per chapter
    MEDIUM = "medium"  # 中爽点 — arc midpoint
    MAJOR = "major"  # 大爽点 — arc climax


class HookType(str, Enum):
    SUSPENSE = "suspense"  # 悬念钩子
    CONFLICT = "conflict"  # 冲突钩子
    EMOTIONAL = "emotional"  # 情感钩子
    REVERSAL = "reversal"  # 反转钩子


# --- Character ---

class CoreTriangle(BaseModel):
    """角色核心三角形: Desire × Ability × Obstacle."""
    desire: str = Field(..., description="What the character wants")
    ability: str = Field(..., description="What the character can do")
    obstacle: str = Field(..., description="What stands in the way")


class Relationship(BaseModel):
    """Relationship to another character."""
    target: str = Field(..., description="Name of the other character")
    type: str = Field(..., description="Relationship type (e.g., 师徒, 仇敌, 恋人)")
    description: str = Field(default="", description="Details about the relationship")
    knowledge: str = Field(default="", description="What this character knows about the target")


class Character(BaseModel):
    """Per-character profile with motivation system."""
    name: str
    aliases: list[str] = Field(default_factory=list, description="Other names / titles")
    physical_description: str = Field(default="")
    personality_traits: list[str] = Field(default_factory=list)
    knowledge_state: str = Field(default="", description="What this character currently knows")
    emotional_state: str = Field(default="", description="Current emotional state")
    relationships: list[Relationship] = Field(default_factory=list)
    current_goals: list[str] = Field(default_factory=list)
    location: str = Field(default="", description="Current location")

    # Methodology-driven fields
    core_triangle: CoreTriangle
    motivation_type: MotivationType
    growth_stage: GrowthStage = GrowthStage.INITIAL
    backstory: str = Field(default="", description="Hidden background (iceberg beneath surface)")

    # Tracking
    first_appearance: int = Field(default=1, description="Chapter number of first appearance")
    last_active: int = Field(default=1, description="Last chapter this character appeared in")
    is_pov: bool = Field(default=False, description="Whether this is a POV character")


# --- World ---

class WorldLayer(BaseModel):
    """One layer of the 五层世界架构."""
    name: str
    description: str
    revealed_in_chapter: Optional[int] = Field(default=None, description="Chapter where this layer is revealed")


class WorldRule(BaseModel):
    """A specific world rule (magic system, geography, social structure, etc.)."""
    name: str
    category: str = Field(..., description="e.g., magic_system, geography, social, technology")
    description: str
    constraints: list[str] = Field(default_factory=list, description="Hard constraints that cannot be violated")
    introduced_chapter: Optional[int] = Field(default=None)


# --- Timeline ---

class TimelineEvent(BaseModel):
    """An event in the story timeline."""
    chapter: int
    description: str
    characters_involved: list[str] = Field(default_factory=list)
    location: str = Field(default="")
    significance: str = Field(default="", description="Why this event matters for the plot")


# --- Foreshadowing ---

class ForeshadowingPair(BaseModel):
    """A setup/payoff pair for Chekhov's gun tracking."""
    id: str = Field(..., description="Unique identifier, e.g., 'fs_001'")
    setup_description: str = Field(..., description="What was planted")
    setup_chapter: int
    payoff_description: str = Field(default="", description="How it paid off")
    payoff_chapter: Optional[int] = None
    status: ForeshadowingStatus = ForeshadowingStatus.PLANTED
    reinforcement_chapters: list[int] = Field(default_factory=list, description="Chapters where this was reinforced")
    priority: str = Field(default="normal", description="high / normal / low")

    @property
    def age(self) -> Optional[int]:
        """How many chapters since planting (None if paid off)."""
        if self.status == ForeshadowingStatus.PAID_OFF:
            return None
        # Caller must provide current chapter to compute real age
        return None

    def age_at(self, current_chapter: int) -> int:
        """Age in chapters relative to a given chapter."""
        return current_chapter - self.setup_chapter


# --- Pacing ---

class PacingBeat(BaseModel):
    """A scheduled 爽点 or hook placement."""
    chapter: int
    beat_type: BeatType
    description: str = Field(default="")
    delivered: bool = False


class HookPlacement(BaseModel):
    """A hook placed at a chapter boundary."""
    chapter: int
    hook_type: HookType
    description: str
    position: str = Field(default="end", description="end / mid / start")


class PacingState(BaseModel):
    """Overall pacing schedule and tracking."""
    beats: list[PacingBeat] = Field(default_factory=list)
    hooks: list[HookPlacement] = Field(default_factory=list)
    tension_curve: list[float] = Field(default_factory=list, description="Tension level per chapter (0-10)")


# --- Chapter Summary ---

class CharacterStateChange(BaseModel):
    """A change to a character's state in a chapter."""
    character: str
    field: str = Field(..., description="Which field changed (e.g., emotional_state, location)")
    old_value: str = Field(default="")
    new_value: str


class ChapterSummary(BaseModel):
    """Structured summary of a single chapter."""
    chapter_number: int
    title: str = Field(default="")
    summary: str = Field(..., description="2-3 sentence plot summary")
    events: list[str] = Field(default_factory=list, description="Key events in order")
    characters_present: list[str] = Field(default_factory=list)
    state_changes: list[CharacterStateChange] = Field(default_factory=list)
    new_information_revealed: list[str] = Field(default_factory=list)
    foreshadowing_planted: list[str] = Field(default_factory=list, description="IDs of new foreshadowing")
    foreshadowing_paid_off: list[str] = Field(default_factory=list, description="IDs of paid-off foreshadowing")
    pov_character: str = Field(default="", description="POV character for this chapter")
    word_count: int = Field(default=0)


# --- Story Core (top-level) ---

class StoryCore(BaseModel):
    """Top-level story configuration."""
    hook: str = Field(..., description="一句话核心 — one-line hook")
    genre: Genre
    target_satisfaction_type: str = Field(default="", description="核心爽点 type for this genre")

    # 五层世界架构
    world_layers: list[WorldLayer] = Field(
        default_factory=list,
        description="5-layer world architecture (surface → essence)",
    )

    # Foreshadowing aging config (per genre)
    foreshadowing_max_age_chapters: int = Field(
        default=20,
        description="Max chapters before a planted foreshadowing triggers an alert. "
                    "Defaults: 玄幻 30, 言情 15, 悬疑 20",
    )

    # Metadata
    total_planned_chapters: Optional[int] = None
    current_chapter: int = Field(default=0, description="Last completed chapter number")


# --- Full Story Bible (in-memory aggregate) ---

class StoryBible(BaseModel):
    """Complete in-memory representation of the Story Bible.

    Individual components are stored as separate YAML files on disk.
    This model represents the loaded aggregate for agent context.
    """
    core: StoryCore
    characters: dict[str, Character] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    world_rules: list[WorldRule] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingPair] = Field(default_factory=list)
    pacing: PacingState = Field(default_factory=PacingState)
    chapter_summaries: dict[int, ChapterSummary] = Field(default_factory=dict)

    def active_foreshadowing(self) -> list[ForeshadowingPair]:
        """Return foreshadowing pairs that are still active (planted or reinforced)."""
        return [
            f for f in self.foreshadowing
            if f.status in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.REINFORCED)
        ]

    def aging_foreshadowing(self, current_chapter: int) -> list[ForeshadowingPair]:
        """Return foreshadowing pairs that are approaching or past the max age threshold."""
        threshold = self.core.foreshadowing_max_age_chapters
        return [
            f for f in self.active_foreshadowing()
            if f.age_at(current_chapter) >= threshold - 5  # alert 5 chapters before deadline
        ]

    def characters_in_chapter(self, chapter_number: int) -> list[Character]:
        """Get characters that appeared in a specific chapter."""
        summary = self.chapter_summaries.get(chapter_number)
        if not summary:
            return []
        return [
            self.characters[name]
            for name in summary.characters_present
            if name in self.characters
        ]

    def recent_timeline(self, current_chapter: int, lookback: int = 10) -> list[TimelineEvent]:
        """Get timeline events from the last N chapters."""
        cutoff = max(1, current_chapter - lookback)
        return [e for e in self.timeline if e.chapter >= cutoff]
