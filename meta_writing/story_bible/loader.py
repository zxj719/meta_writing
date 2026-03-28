"""Load and save Story Bible YAML files.

Directory layout on disk:
    story_data/
    ├── story_core.yaml
    ├── characters/
    │   ├── lin_yue.yaml
    │   └── ...
    ├── timeline.yaml
    ├── world_rules.yaml
    ├── foreshadowing.yaml
    ├── pacing.yaml
    └── chapter_summaries/
        ├── 001.yaml
        └── ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

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


class StoryBibleLoader:
    """Loads and saves Story Bible state from/to YAML files."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create directory structure if it doesn't exist."""
        (self.data_dir / "characters").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "chapter_summaries").mkdir(parents=True, exist_ok=True)

    # --- Paths ---

    @property
    def core_path(self) -> Path:
        return self.data_dir / "story_core.yaml"

    @property
    def timeline_path(self) -> Path:
        return self.data_dir / "timeline.yaml"

    @property
    def world_rules_path(self) -> Path:
        return self.data_dir / "world_rules.yaml"

    @property
    def foreshadowing_path(self) -> Path:
        return self.data_dir / "foreshadowing.yaml"

    @property
    def pacing_path(self) -> Path:
        return self.data_dir / "pacing.yaml"

    def character_path(self, name: str) -> Path:
        safe_name = name.replace(" ", "_").lower()
        return self.data_dir / "characters" / f"{safe_name}.yaml"

    def chapter_summary_path(self, chapter_number: int) -> Path:
        return self.data_dir / "chapter_summaries" / f"{chapter_number:03d}.yaml"

    # --- Read helpers ---

    def _read_yaml(self, path: Path) -> Any:
        """Read a YAML file, return None if it doesn't exist."""
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _write_yaml(self, path: Path, data: Any) -> None:
        """Write data to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                width=120,
            )

    # --- Load individual components ---

    def load_core(self) -> StoryCore | None:
        data = self._read_yaml(self.core_path)
        if data is None:
            return None
        return StoryCore.model_validate(data)

    def load_character(self, name: str) -> Character | None:
        data = self._read_yaml(self.character_path(name))
        if data is None:
            return None
        return Character.model_validate(data)

    def load_all_characters(self) -> dict[str, Character]:
        characters: dict[str, Character] = {}
        chars_dir = self.data_dir / "characters"
        if not chars_dir.exists():
            return characters
        for path in sorted(chars_dir.glob("*.yaml")):
            data = self._read_yaml(path)
            if data:
                char = Character.model_validate(data)
                characters[char.name] = char
        return characters

    def load_timeline(self) -> list[TimelineEvent]:
        data = self._read_yaml(self.timeline_path)
        if not data:
            return []
        return [TimelineEvent.model_validate(e) for e in data]

    def load_world_rules(self) -> list[WorldRule]:
        data = self._read_yaml(self.world_rules_path)
        if not data:
            return []
        return [WorldRule.model_validate(r) for r in data]

    def load_foreshadowing(self) -> list[ForeshadowingPair]:
        data = self._read_yaml(self.foreshadowing_path)
        if not data:
            return []
        return [ForeshadowingPair.model_validate(f) for f in data]

    def load_pacing(self) -> PacingState:
        data = self._read_yaml(self.pacing_path)
        if not data:
            return PacingState()
        return PacingState.model_validate(data)

    def load_chapter_summary(self, chapter_number: int) -> ChapterSummary | None:
        data = self._read_yaml(self.chapter_summary_path(chapter_number))
        if data is None:
            return None
        return ChapterSummary.model_validate(data)

    def load_all_chapter_summaries(self) -> dict[int, ChapterSummary]:
        summaries: dict[int, ChapterSummary] = {}
        sums_dir = self.data_dir / "chapter_summaries"
        if not sums_dir.exists():
            return summaries
        for path in sorted(sums_dir.glob("*.yaml")):
            data = self._read_yaml(path)
            if data:
                summary = ChapterSummary.model_validate(data)
                summaries[summary.chapter_number] = summary
        return summaries

    # --- Load full bible ---

    def load(self) -> StoryBible:
        """Load the entire Story Bible from disk.

        Raises ValidationError if story_core.yaml is missing or invalid.
        """
        core = self.load_core()
        if core is None:
            raise ValidationError.from_exception_data(
                title="StoryCore",
                line_errors=[],
            )
        return StoryBible(
            core=core,
            characters=self.load_all_characters(),
            timeline=self.load_timeline(),
            world_rules=self.load_world_rules(),
            foreshadowing=self.load_foreshadowing(),
            pacing=self.load_pacing(),
            chapter_summaries=self.load_all_chapter_summaries(),
        )

    # --- Save individual components ---

    def save_core(self, core: StoryCore) -> None:
        self._write_yaml(self.core_path, core.model_dump(mode="json"))

    def save_character(self, character: Character) -> None:
        self._write_yaml(
            self.character_path(character.name),
            character.model_dump(mode="json"),
        )

    def save_timeline(self, timeline: list[TimelineEvent]) -> None:
        self._write_yaml(
            self.timeline_path,
            [e.model_dump(mode="json") for e in timeline],
        )

    def save_world_rules(self, rules: list[WorldRule]) -> None:
        self._write_yaml(
            self.world_rules_path,
            [r.model_dump(mode="json") for r in rules],
        )

    def save_foreshadowing(self, pairs: list[ForeshadowingPair]) -> None:
        self._write_yaml(
            self.foreshadowing_path,
            [f.model_dump(mode="json") for f in pairs],
        )

    def save_pacing(self, pacing: PacingState) -> None:
        self._write_yaml(self.pacing_path, pacing.model_dump(mode="json"))

    def save_chapter_summary(self, summary: ChapterSummary) -> None:
        self._write_yaml(
            self.chapter_summary_path(summary.chapter_number),
            summary.model_dump(mode="json"),
        )

    # --- Save full bible ---

    def save(self, bible: StoryBible) -> None:
        """Save the entire Story Bible to disk."""
        self.save_core(bible.core)
        for character in bible.characters.values():
            self.save_character(character)
        self.save_timeline(bible.timeline)
        self.save_world_rules(bible.world_rules)
        self.save_foreshadowing(bible.foreshadowing)
        self.save_pacing(bible.pacing)
        for summary in bible.chapter_summaries.values():
            self.save_chapter_summary(summary)
