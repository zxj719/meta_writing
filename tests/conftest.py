"""Shared test fixtures."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from meta_writing.story_bible.schema import (
    Character,
    ChapterSummary,
    CoreTriangle,
    ForeshadowingPair,
    ForeshadowingStatus,
    Genre,
    GrowthStage,
    HookPlacement,
    HookType,
    MotivationType,
    PacingBeat,
    PacingState,
    BeatType,
    Relationship,
    StoryBible,
    StoryCore,
    TimelineEvent,
    WorldLayer,
    WorldRule,
)


@pytest.fixture
def sample_core() -> StoryCore:
    return StoryCore(
        hook="少年觉醒异能，踏上揭开世界真相的旅途",
        genre=Genre.URBAN_FANTASY,
        target_satisfaction_type="能力觉醒、逆袭打脸",
        world_layers=[
            WorldLayer(name="表层世界", description="现代都市，科技发达"),
            WorldLayer(name="规则层", description="异能者隐藏在普通人中"),
            WorldLayer(name="禁忌层", description="S级异能者不得干涉普通人世界"),
            WorldLayer(name="真相层", description="异能来源于远古文明遗迹"),
            WorldLayer(name="本质层", description="力量与责任的平衡"),
        ],
        foreshadowing_max_age_chapters=20,
        total_planned_chapters=100,
        current_chapter=3,
    )


@pytest.fixture
def sample_characters() -> dict[str, Character]:
    return {
        "林越": Character(
            name="林越",
            aliases=["小林"],
            physical_description="身材瘦高，黑发，左眼有一道淡淡的疤痕",
            personality_traits=["冷静", "好奇心强", "正义感"],
            knowledge_state="知道异能存在，但不了解完整体系",
            emotional_state="对自身异能感到困惑和兴奋",
            relationships=[
                Relationship(target="苏晴", type="同学", description="高中同班同学"),
            ],
            current_goals=["控制自己的异能", "找到父亲失踪的真相"],
            location="临海市第一中学",
            core_triangle=CoreTriangle(
                desire="找到失踪的父亲",
                ability="空间感知异能（刚觉醒）",
                obstacle="对异能世界一无所知",
            ),
            motivation_type=MotivationType.CURIOSITY,
            growth_stage=GrowthStage.TRIGGERED,
            first_appearance=1,
            last_active=3,
            is_pov=True,
        ),
        "苏晴": Character(
            name="苏晴",
            physical_description="短发，眼神锐利，总穿运动装",
            personality_traits=["果断", "暴躁", "重情义"],
            emotional_state="担心林越的异常表现",
            relationships=[
                Relationship(target="林越", type="同学", description="暗中保护林越"),
            ],
            current_goals=["监视林越的异能觉醒"],
            location="临海市第一中学",
            core_triangle=CoreTriangle(
                desire="完成组织交给的任务",
                ability="火系异能（B级）",
                obstacle="对林越产生了感情",
            ),
            motivation_type=MotivationType.MISSION,
            growth_stage=GrowthStage.ADAPTING,
            first_appearance=1,
            last_active=3,
            is_pov=False,
        ),
    }


@pytest.fixture
def sample_foreshadowing() -> list[ForeshadowingPair]:
    return [
        ForeshadowingPair(
            id="fs_001",
            setup_description="林越左眼疤痕在异能觉醒时发光",
            setup_chapter=1,
            status=ForeshadowingStatus.PLANTED,
            priority="high",
        ),
        ForeshadowingPair(
            id="fs_002",
            setup_description="苏晴在第2章偷偷给组织打电话汇报",
            setup_chapter=2,
            status=ForeshadowingStatus.REINFORCED,
            reinforcement_chapters=[3],
            priority="normal",
        ),
    ]


@pytest.fixture
def sample_bible(sample_core, sample_characters, sample_foreshadowing) -> StoryBible:
    return StoryBible(
        core=sample_core,
        characters=sample_characters,
        timeline=[
            TimelineEvent(chapter=1, description="林越在放学路上异能觉醒", characters_involved=["林越"]),
            TimelineEvent(chapter=2, description="苏晴暗中观察林越", characters_involved=["苏晴", "林越"]),
            TimelineEvent(chapter=3, description="林越在体育课上失控使用异能", characters_involved=["林越", "苏晴"]),
        ],
        world_rules=[
            WorldRule(
                name="异能等级体系",
                category="magic_system",
                description="异能分为S/A/B/C/D五个等级",
                constraints=["D级不能对抗C级以上", "S级异能者全球不超过10人"],
            ),
        ],
        foreshadowing=sample_foreshadowing,
        pacing=PacingState(
            beats=[
                PacingBeat(chapter=1, beat_type=BeatType.MINOR, description="异能觉醒", delivered=True),
                PacingBeat(chapter=5, beat_type=BeatType.MEDIUM, description="第一次正式战斗"),
                PacingBeat(chapter=10, beat_type=BeatType.MAJOR, description="真相揭示"),
            ],
            hooks=[
                HookPlacement(chapter=1, hook_type=HookType.SUSPENSE, description="苏晴的神秘电话"),
            ],
        ),
        chapter_summaries={
            1: ChapterSummary(
                chapter_number=1,
                summary="林越在放学路上遭遇异变，左眼疤痕发光，觉醒了空间感知异能。",
                characters_present=["林越"],
                word_count=8500,
            ),
            2: ChapterSummary(
                chapter_number=2,
                summary="苏晴开始暗中监视林越，并向组织汇报他的异能觉醒。",
                characters_present=["林越", "苏晴"],
                word_count=9200,
            ),
            3: ChapterSummary(
                chapter_number=3,
                summary="体育课上林越失控使用异能，苏晴及时掩护，两人关系开始变化。",
                characters_present=["林越", "苏晴"],
                word_count=10100,
            ),
        },
    )


@pytest.fixture
def tmp_project(sample_bible) -> Path:
    """Create a temporary project directory with a populated Story Bible."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        from meta_writing.story_bible.loader import StoryBibleLoader
        loader = StoryBibleLoader(project_dir / "story_data")
        loader.save(sample_bible)
        (project_dir / "chapters").mkdir(exist_ok=True)
        yield project_dir
