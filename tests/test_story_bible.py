"""Tests for Story Bible schema, loader, and compressor."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from meta_writing.story_bible.schema import (
    Character,
    ChapterSummary,
    CoreTriangle,
    ForeshadowingPair,
    ForeshadowingStatus,
    Genre,
    GrowthStage,
    MotivationType,
    StoryBible,
    StoryCore,
    WorldLayer,
)
from meta_writing.story_bible.loader import StoryBibleLoader
from meta_writing.story_bible.compressor import StoryBibleCompressor, _estimate_tokens


# --- Schema tests ---


class TestCharacterSchema:
    def test_valid_character(self, sample_characters):
        char = sample_characters["林越"]
        assert char.name == "林越"
        assert char.core_triangle.desire == "找到失踪的父亲"
        assert char.motivation_type == MotivationType.CURIOSITY
        assert char.growth_stage == GrowthStage.TRIGGERED

    def test_missing_required_fields_rejected(self):
        with pytest.raises(Exception):
            Character(name="test")  # missing core_triangle and motivation_type

    def test_invalid_enum_rejected(self):
        with pytest.raises(Exception):
            Character(
                name="test",
                core_triangle=CoreTriangle(desire="x", ability="y", obstacle="z"),
                motivation_type="invalid_type",  # type: ignore
            )


class TestStoryCoreSchema:
    def test_valid_core(self, sample_core):
        assert sample_core.hook == "少年觉醒异能，踏上揭开世界真相的旅途"
        assert sample_core.genre == Genre.URBAN_FANTASY
        assert sample_core.foreshadowing_max_age_chapters == 20

    def test_missing_hook_rejected(self):
        with pytest.raises(Exception):
            StoryCore(genre=Genre.XIANXIA)  # missing hook


class TestForeshadowingSchema:
    def test_valid_pair(self, sample_foreshadowing):
        fs = sample_foreshadowing[0]
        assert fs.id == "fs_001"
        assert fs.status == ForeshadowingStatus.PLANTED
        assert fs.age_at(10) == 9

    def test_invalid_status_rejected(self):
        with pytest.raises(Exception):
            ForeshadowingPair(
                id="test",
                setup_description="test",
                setup_chapter=1,
                status="invalid",  # type: ignore
            )


class TestStoryBible:
    def test_active_foreshadowing(self, sample_bible):
        active = sample_bible.active_foreshadowing()
        assert len(active) == 2

    def test_aging_foreshadowing(self, sample_bible):
        # At chapter 3, foreshadowing from chapter 1 is only 2 chapters old
        # Threshold is 20, alert at 15 — should not trigger
        aging = sample_bible.aging_foreshadowing(3)
        assert len(aging) == 0

        # At chapter 18, it should trigger (age 17, threshold-5 = 15)
        aging = sample_bible.aging_foreshadowing(18)
        assert len(aging) >= 1

    def test_recent_timeline(self, sample_bible):
        events = sample_bible.recent_timeline(3, lookback=2)
        # lookback=2 from ch3: cutoff = max(1, 3-2) = 1, so ch1,2,3 all included
        assert len(events) == 3


# --- Loader tests ---


class TestLoader:
    def test_round_trip(self, sample_bible):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = StoryBibleLoader(tmpdir)
            loader.save(sample_bible)
            loaded = loader.load()

            assert loaded.core.hook == sample_bible.core.hook
            assert loaded.core.genre == sample_bible.core.genre
            assert len(loaded.characters) == len(sample_bible.characters)
            assert "林越" in loaded.characters
            assert loaded.characters["林越"].name == "林越"
            assert len(loaded.timeline) == len(sample_bible.timeline)
            assert len(loaded.foreshadowing) == len(sample_bible.foreshadowing)
            assert len(loaded.chapter_summaries) == len(sample_bible.chapter_summaries)

    def test_load_nonexistent_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = StoryBibleLoader(tmpdir)
            assert loader.load_core() is None
            assert loader.load_character("nobody") is None
            assert loader.load_timeline() == []

    def test_save_and_load_single_character(self, sample_characters):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = StoryBibleLoader(tmpdir)
            char = sample_characters["林越"]
            loader.save_character(char)
            loaded = loader.load_character("林越")
            assert loaded is not None
            assert loaded.name == "林越"
            assert loaded.core_triangle.desire == char.core_triangle.desire

    def test_yaml_files_are_readable(self, sample_bible):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = StoryBibleLoader(tmpdir)
            loader.save(sample_bible)

            # Verify YAML is human-readable
            core_data = yaml.safe_load(loader.core_path.read_text(encoding="utf-8"))
            assert core_data["hook"] == sample_bible.core.hook


# --- Compressor tests ---


class TestCompressor:
    def test_full_context_under_budget(self, sample_bible):
        compressor = StoryBibleCompressor(token_budget=50000)  # generous budget
        result = compressor.compress(sample_bible, current_chapter=4)
        assert result.compression_level == "full"
        assert "林越" in result.text
        assert "故事核心" in result.text

    def test_summarized_context_over_budget(self, sample_bible):
        compressor = StoryBibleCompressor(token_budget=200)  # tight budget
        result = compressor.compress(sample_bible, current_chapter=4)
        assert result.compression_level in ("summarized", "minimal")

    def test_minimal_context_way_over_budget(self, sample_bible):
        compressor = StoryBibleCompressor(token_budget=100)  # extremely tight
        result = compressor.compress(sample_bible, current_chapter=4)
        assert result.compression_level == "minimal"

    def test_token_estimation(self):
        chinese = "这是一段中文测试文本" * 10  # 90 Chinese chars
        tokens = _estimate_tokens(chinese)
        assert 40 < tokens < 80  # ~60 tokens for 90 Chinese chars

        english = "This is a test" * 10  # 140 chars
        tokens = _estimate_tokens(english)
        assert 25 < tokens < 50  # ~35 tokens

    def test_active_characters_inferred(self, sample_bible):
        compressor = StoryBibleCompressor()
        result = compressor.compress(sample_bible, current_chapter=4)
        # Should contain characters from recent chapters
        assert "林越" in result.text
