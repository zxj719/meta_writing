"""auto_runner.py — Autonomous chapter generation loop.

Self-improving pipeline per chapter:
  Plan → AutoSelect → Write → Review(StyleLint+Continuity+Theme) → Revise(×3)
  → ExtractLessons → UpdateBible → Commit → pass lessons forward

Usage:
  python auto_runner.py                  # current_chapter+1 → ch20
  python auto_runner.py --to 15         # stop at ch15
  python auto_runner.py --from 13       # start from ch13 (override)
  python auto_runner.py --push          # git push after each chapter
  python auto_runner.py --dry-run       # plan+select only, no write/commit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: activate venv if running outside it
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent

sys.path.insert(0, str(PROJECT_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("auto_runner")

# ---------------------------------------------------------------------------
# Imports (after path setup)
# ---------------------------------------------------------------------------
from meta_writing.llm import LLMClient, MODEL_SONNET, MODEL_OPUS
from meta_writing.agents.planner import PlannerAgent, PlotBranch
from meta_writing.agents.writer import WriterAgent
from meta_writing.agents.continuity import ContinuityAgent
from meta_writing.agents.style import StyleAgent
from meta_writing.agents.theme import ThemeAgent
from meta_writing.story_bible.loader import StoryBibleLoader
from meta_writing.story_bible.compressor import StoryBibleCompressor
from meta_writing.story_bible.schema import (
    ChapterSummary, CharacterStateChange, TimelineEvent,
    PacingBeat, HookPlacement, ForeshadowingPair, ForeshadowingStatus,
    BeatType, HookType, StoryBible,
)
from meta_writing.style_linter import StyleLinter, Severity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_REVISIONS = 3
LEARNED_RULES_FILE = PROJECT_DIR / "learned_rules.md"
RUN_LOG_FILE = PROJECT_DIR / "auto_runner_log.md"


# ===========================================================================
# 1. BranchSelector — LLM picks the best branch for arc position
# ===========================================================================

BRANCH_SELECTOR_PROMPT = """\
你是一位经验丰富的中文文学小说策划。你需要从若干剧情分支中选出最适合当前弧线位置的那一个。

## 选择标准（按优先级）

1. **弧线推进**: 选择让故事在当前阶段自然向前走一步的分支，而不是跳太快或原地踏步
2. **克制美学**: 优先选择通过具体事件、感知场景、沉默时刻推进关系的分支，而不是情感剖白
3. **张力节奏**: 根据前几章的张力水平决定是升温还是降温——不要连续多章都是高张力
4. **伏笔管理**: 如果有即将到期的伏笔，优先选择能自然回收的分支
5. **新鲜感**: 避免重复上一章的场景结构或意象

## 输出格式

```json
{
  "selected_index": 0,
  "reasoning": "选择这个分支的理由（2-3句）",
  "arc_assessment": "当前弧线位置的简要判断"
}
```

只输出JSON，不要其他内容。
"""


class BranchSelector:
    """LLM-based automatic branch selection."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def select(
        self,
        branches: list[PlotBranch],
        context_notes: str,
        bible_summary: str,
        chapter_number: int,
    ) -> tuple[int, str]:
        """Select the best branch. Returns (index, reasoning)."""
        branches_text = "\n\n".join(
            f"### 分支 {i+1}: {b.title}\n"
            f"钩子类型: {b.hook_type} | 张力: {b.tension_impact} | 风险: {b.risk_level}\n"
            f"{b.outline}\n"
            f"伏笔机会: {', '.join(b.foreshadowing_opportunities)}"
            for i, b in enumerate(branches)
        )

        user_msg = (
            f"## 第{chapter_number}章分支选择\n\n"
            f"**策划分析**: {context_notes}\n\n"
            f"**当前弧线状态**:\n{bible_summary}\n\n"
            f"## 候选分支\n\n{branches_text}\n\n"
            f"请选择最适合第{chapter_number}章的分支。"
        )

        resp = await self.llm.complete(
            system=BRANCH_SELECTOR_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            model=MODEL_SONNET,
            max_tokens=2048,
            temperature=0.3,
        )

        try:
            text = resp.text
            # Strip markdown code block if present
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            json_text = m.group(1).strip() if m else text
            # Find outermost { ... }
            start = json_text.find("{")
            end = json_text.rfind("}") + 1
            if start != -1 and end > start:
                json_text = json_text[start:end]
            data = json.loads(json_text)
            idx = int(data.get("selected_index", 0))
            idx = max(0, min(idx, len(branches) - 1))
            return idx, data.get("reasoning", "")
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        logger.warning("Branch selector parse failed, defaulting to branch 0")
        return 0, "自动选择失败，使用分支1"


# ===========================================================================
# 2. LessonAccumulator — extracts rules from review issues, feeds forward
# ===========================================================================

LESSON_EXTRACTOR_PROMPT = """\
你是一位严格的文学编辑。你刚刚审查了一章小说，发现了一些问题。
你需要从这些问题中提炼出1-3条简洁的"下次不要犯的规则"。

## 要求

- 每条规则必须具体，不能是泛泛的"要注意X"，要说清楚具体是什么情况触发了什么问题
- 规则要直接针对这篇小说的风格特点（克制美学/微感描写）
- 如果本章没有发现新问题（已有规则覆盖），可以只输出一条加强版的总结

## 输出格式

```json
{
  "new_rules": [
    "规则1：...",
    "规则2：...",
    "规则3：..."
  ],
  "chapter_verdict": "本章最主要的一个问题或值得保留的一个优点（一句话）"
}
```

只输出JSON。
"""


class LessonAccumulator:
    """Accumulates writing lessons across chapters for self-improvement."""

    def __init__(self, llm: LLMClient, rules_file: Path = LEARNED_RULES_FILE) -> None:
        self.llm = llm
        self.rules_file = rules_file

    def load(self) -> str:
        """Load all accumulated rules as a block of text."""
        if not self.rules_file.exists():
            return ""
        return self.rules_file.read_text(encoding="utf-8")

    async def extract_and_append(
        self,
        chapter_number: int,
        issues_summary: str,
        chapter_verdict: str = "",
    ) -> list[str]:
        """Extract new rules from this chapter's issues and append to file."""
        if not issues_summary.strip():
            return []

        resp = await self.llm.complete(
            system=LESSON_EXTRACTOR_PROMPT,
            messages=[{"role": "user", "content": f"## 第{chapter_number}章审查问题摘要\n\n{issues_summary}"}],
            model=MODEL_SONNET,
            max_tokens=1024,
            temperature=0.2,
        )

        new_rules: list[str] = []
        verdict = chapter_verdict
        try:
            text = resp.text
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            json_text = m.group(1).strip() if m else text
            s = json_text.find("{"); e = json_text.rfind("}") + 1
            if s != -1 and e > s:
                json_text = json_text[s:e]
            data = json.loads(json_text)
            new_rules = data.get("new_rules", [])
            verdict = data.get("chapter_verdict", chapter_verdict)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Lesson extractor parse failed for ch%d", chapter_number)
            return []

        if new_rules:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            block = f"\n## 第{chapter_number}章学到的规则（{timestamp}）\n\n"
            block += f"> 本章判断：{verdict}\n\n"
            for rule in new_rules:
                block += f"- {rule}\n"

            with open(self.rules_file, "a", encoding="utf-8") as f:
                f.write(block)

            logger.info("ch%d: extracted %d new lessons", chapter_number, len(new_rules))

        return new_rules


# ===========================================================================
# 3. BibleUpdater — LLM-guided Story Bible update after each chapter
# ===========================================================================

BIBLE_UPDATER_PROMPT = """\
你是一位精准的Story Bible编辑。你刚刚读完了一章小说。
你需要从中提取结构化信息，用于更新Story Bible。

## 输出格式

```json
{
  "chapter_title": "章节标题（4-8个字）",
  "summary": "2-3句话的情节摘要",
  "events": ["事件1", "事件2", "事件3"],
  "characters_present": ["角色名1", "角色名2"],
  "character_updates": [
    {
      "name": "角色名",
      "knowledge_state": "更新后的知识状态（如无变化，原样输出）",
      "emotional_state": "更新后的情感状态（如无变化，原样输出）",
      "last_active": 章节号
    }
  ],
  "timeline_entry": {
    "description": "本章主要事件的一句话描述",
    "characters_involved": ["角色名"],
    "location": "地点",
    "significance": "为什么这个事件在故事中重要"
  },
  "pacing_beat": {
    "beat_type": "minor",
    "description": "本章爽点描述"
  },
  "pacing_hook": {
    "hook_type": "suspense",
    "description": "章末钩子描述"
  },
  "tension_score": 5.5,
  "foreshadowing_reinforced": ["fs_002", "fs_003"],
  "foreshadowing_paid_off": []
}
```

beat_type: minor / medium / major
hook_type: suspense / conflict / emotional / reversal
tension_score: 0-10的浮点数，根据全章紧张程度判断

只输出JSON，不要其他内容。
"""


class BibleUpdater:
    """Updates Story Bible YAML files based on a completed chapter."""

    def __init__(self, llm: LLMClient, loader: StoryBibleLoader) -> None:
        self.llm = llm
        self.loader = loader

    async def update(
        self,
        bible: StoryBible,
        chapter_text: str,
        chapter_number: int,
        branch: PlotBranch,
    ) -> StoryBible:
        """Extract chapter data and update the Story Bible in-place."""
        # Provide context about the characters so LLM can write accurate updates
        char_context = "\n".join(
            f"- {name}: knowledge={c.knowledge_state[:100]}... emotional={c.emotional_state[:80]}..."
            for name, c in bible.characters.items()
        )
        user_msg = (
            f"## 第{chapter_number}章正文（前3000字）\n\n{chapter_text[:3000]}\n\n"
            f"## 当前角色状态（供参考）\n{char_context}\n\n"
            f"## 分支大纲（供参考）\n{branch.outline[:300]}\n\n"
            f"请提取第{chapter_number}章的Story Bible更新数据。"
        )

        resp = await self.llm.complete(
            system=BIBLE_UPDATER_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            model=MODEL_SONNET,
            max_tokens=4096,
            temperature=0.2,
        )

        try:
            text = resp.text
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            json_text = m.group(1).strip() if m else text
            s = json_text.find("{"); e2 = json_text.rfind("}") + 1
            if s != -1 and e2 > s:
                json_text = json_text[s:e2]
            data = json.loads(json_text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("BibleUpdater parse failed for ch%d: %s", chapter_number, e)
            # Minimal update: just chapter counter and word count
            self._minimal_update(bible, chapter_number, chapter_text, branch)
            return bible

        self._apply_update(bible, chapter_number, chapter_text, branch, data)
        return bible

    def _apply_update(
        self,
        bible: StoryBible,
        chapter_number: int,
        chapter_text: str,
        branch: PlotBranch,
        data: dict,
    ) -> None:
        # 1. Chapter summary
        state_changes = []
        for cu in data.get("character_updates", []):
            name = cu.get("name", "")
            if name and name in bible.characters:
                char = bible.characters[name]
                old_ks = char.knowledge_state
                old_es = char.emotional_state
                new_ks = cu.get("knowledge_state", old_ks)
                new_es = cu.get("emotional_state", old_es)
                if new_ks != old_ks:
                    state_changes.append(CharacterStateChange(
                        character=name, field="knowledge_state",
                        old_value=old_ks, new_value=new_ks,
                    ))
                    char.knowledge_state = new_ks
                if new_es != old_es:
                    state_changes.append(CharacterStateChange(
                        character=name, field="emotional_state",
                        old_value=old_es, new_value=new_es,
                    ))
                    char.emotional_state = new_es
                char.last_active = chapter_number

        summary = ChapterSummary(
            chapter_number=chapter_number,
            title=data.get("chapter_title", ""),
            summary=data.get("summary", branch.outline[:150]),
            events=data.get("events", []),
            characters_present=data.get("characters_present", branch.characters_involved),
            state_changes=state_changes,
            foreshadowing_paid_off=data.get("foreshadowing_paid_off", []),
            pov_character="夏浮",
            word_count=len(chapter_text),
        )
        bible.chapter_summaries[chapter_number] = summary

        # 2. Timeline
        tl = data.get("timeline_entry", {})
        if tl:
            bible.timeline.append(TimelineEvent(
                chapter=chapter_number,
                description=tl.get("description", ""),
                characters_involved=tl.get("characters_involved", []),
                location=tl.get("location", ""),
                significance=tl.get("significance", ""),
            ))

        # 3. Pacing
        beat_data = data.get("pacing_beat", {})
        if beat_data:
            try:
                bible.pacing.beats.append(PacingBeat(
                    chapter=chapter_number,
                    beat_type=BeatType(beat_data.get("beat_type", "minor")),
                    description=beat_data.get("description", ""),
                    delivered=True,
                ))
            except ValueError:
                pass  # invalid beat_type, skip

        hook_data = data.get("pacing_hook", {})
        if hook_data:
            try:
                bible.pacing.hooks.append(HookPlacement(
                    chapter=chapter_number,
                    hook_type=HookType(hook_data.get("hook_type", "suspense")),
                    description=hook_data.get("description", ""),
                    position="end",
                ))
            except ValueError:
                pass

        tension = data.get("tension_score")
        if tension is not None:
            bible.pacing.tension_curve.append(float(tension))

        # 4. Foreshadowing status updates
        reinforced = data.get("foreshadowing_reinforced", [])
        paid_off = data.get("foreshadowing_paid_off", [])
        for fs in bible.foreshadowing:
            if fs.id in reinforced and fs.status != ForeshadowingStatus.PAID_OFF:
                fs.status = ForeshadowingStatus.REINFORCED
                if chapter_number not in fs.reinforcement_chapters:
                    fs.reinforcement_chapters.append(chapter_number)
            if fs.id in paid_off:
                fs.status = ForeshadowingStatus.PAID_OFF
                fs.payoff_chapter = chapter_number

        # 5. Update chapter counter
        bible.core.current_chapter = chapter_number

    def _minimal_update(
        self,
        bible: StoryBible,
        chapter_number: int,
        chapter_text: str,
        branch: PlotBranch,
    ) -> None:
        bible.chapter_summaries[chapter_number] = ChapterSummary(
            chapter_number=chapter_number,
            summary=branch.outline[:150],
            characters_present=branch.characters_involved,
            word_count=len(chapter_text),
        )
        bible.core.current_chapter = chapter_number


# ===========================================================================
# 4. AutoRunner — main loop
# ===========================================================================

@dataclass
class ChapterRunResult:
    chapter_number: int
    word_count: int
    branch_title: str
    branch_reasoning: str
    revision_count: int
    issues_summary: str
    theme_health: str
    new_lessons: list[str]
    bible_title: str


class AutoRunner:
    """Autonomous loop: generate chapters from start to end."""

    def __init__(
        self,
        project_dir: Path,
        api_key: str,
        push: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.project_dir = project_dir
        self.push = push
        self.dry_run = dry_run

        self.llm = LLMClient(api_key=api_key)
        self.loader = StoryBibleLoader(project_dir / "story_data")
        self.compressor = StoryBibleCompressor()
        self.chapters_dir = project_dir / "chapters"

        self.planner = PlannerAgent(self.llm, model=MODEL_OPUS)
        self.writer = WriterAgent(self.llm, model=MODEL_SONNET)
        self.continuity_agent = ContinuityAgent(self.llm, model=MODEL_SONNET)
        self.style_agent = StyleAgent(self.llm, model=MODEL_SONNET)
        self.theme_agent = ThemeAgent(self.llm, model=MODEL_SONNET)
        self.style_linter = StyleLinter()

        self.branch_selector = BranchSelector(self.llm)
        self.lessons = LessonAccumulator(self.llm)
        self.bible_updater = BibleUpdater(self.llm, self.loader)

    def _get_recent_text(self, chapter_number: int, lookback: int = 3) -> str:
        texts = []
        for ch in range(max(1, chapter_number - lookback), chapter_number):
            path = self.chapters_dir / f"{ch:03d}.md"
            if path.exists():
                texts.append(f"=== 第{ch}章 ===\n{path.read_text(encoding='utf-8')[-4000:]}")
        return "\n\n".join(texts)

    def _summarize_issues(
        self, linter_issues, continuity_result, theme_result, style_result
    ) -> str:
        parts = []

        # StyleLinter
        errors = [i for i in linter_issues if i.severity == Severity.ERROR]
        warnings = [i for i in linter_issues if i.severity == Severity.WARNING]
        if errors:
            parts.append(f"StyleLinter错误({len(errors)}条):\n" +
                         "\n".join(f"  - [{i.pattern_name}] {i.message}" for i in errors))
        if warnings:
            parts.append(f"StyleLinter警告({len(warnings)}条):\n" +
                         "\n".join(f"  - [{i.pattern_name}] {i.message}" for i in warnings[:3]))

        # Continuity
        if continuity_result and not continuity_result.passed:
            crit = [i for i in continuity_result.issues
                    if hasattr(i, 'severity') and str(i.severity).lower() == 'critical']
            if crit:
                parts.append("Continuity严重问题:\n" +
                             "\n".join(f"  - {i.description}" for i in crit[:3]))

        # Theme
        if theme_result and theme_result.thematic_health != "healthy":
            if theme_result.issues:
                parts.append(f"主题问题({theme_result.thematic_health}):\n" +
                             "\n".join(f"  - {i.description}" for i in theme_result.issues[:2]))

        # Style Agent
        if style_result and style_result.issues:
            parts.append("StyleAgent问题:\n" +
                         "\n".join(f"  - {i.description}" for i in style_result.issues[:2]))

        return "\n\n".join(parts)

    async def run_chapter(self, chapter_number: int) -> ChapterRunResult:
        logger.info("=" * 60)
        logger.info("Starting ch%d", chapter_number)

        bible = self.loader.load()
        learned_rules = self.lessons.load()
        recent_text = self._get_recent_text(chapter_number)

        # --- 1. Plan ---
        bible_ctx = self.compressor.compress(bible, chapter_number)
        guidance = ""
        if learned_rules:
            guidance = f"## 从前几章学到的写作规则\n\n{learned_rules}\n\n请特别注意避免以上问题。"

        logger.info("ch%d: planning...", chapter_number)
        plan_result = await self.planner.plan(
            bible_context=bible_ctx,
            recent_chapters_text=recent_text[-6000:],
            chapter_number=chapter_number,
            additional_guidance=guidance,
        )

        # --- 2. Auto-select branch ---
        arc_summary = f"当前弧线：ch{chapter_number}，前情：{bible_ctx.text[:500]}"
        branch_idx, branch_reasoning = await self.branch_selector.select(
            branches=plan_result.branches,
            context_notes=plan_result.context_notes,
            bible_summary=arc_summary,
            chapter_number=chapter_number,
        )
        selected_branch = plan_result.branches[branch_idx]
        logger.info(
            "ch%d: selected branch %d/%d — %s",
            chapter_number, branch_idx + 1, len(plan_result.branches), selected_branch.title,
        )
        logger.info("ch%d: reasoning: %s", chapter_number, branch_reasoning)

        if self.dry_run:
            logger.info("ch%d: dry-run mode, stopping after branch selection", chapter_number)
            return ChapterRunResult(
                chapter_number=chapter_number, word_count=0,
                branch_title=selected_branch.title, branch_reasoning=branch_reasoning,
                revision_count=0, issues_summary="(dry-run)", theme_health="n/a",
                new_lessons=[], bible_title="(dry-run)",
            )

        # Recompress with active characters
        bible_ctx = self.compressor.compress(
            bible, chapter_number,
            active_character_names=selected_branch.characters_involved,
        )

        # --- 3. Write (retry up to 3 times if empty response) ---
        logger.info("ch%d: writing...", chapter_number)
        chapter_text = ""
        for write_attempt in range(3):
            writer_result = await self.writer.write(
                bible_context=bible_ctx,
                recent_chapters_text=recent_text,
                outline=selected_branch.outline,
                chapter_number=chapter_number,
                pov_character="夏浮",
            )
            chapter_text = writer_result.chapter_text
            if chapter_text.strip():
                break
            logger.warning("ch%d: write attempt %d returned empty, retrying...", chapter_number, write_attempt + 1)
            await asyncio.sleep(5)
        logger.info("ch%d: wrote %d chars", chapter_number, len(chapter_text))
        if not chapter_text.strip():
            raise RuntimeError(f"ch{chapter_number}: writer returned empty text after 3 attempts")

        # --- 4. Review + Revise loop ---
        revision_count = 0
        issues_summary = ""
        theme_health = "healthy"
        theme_result = None
        style_result = None
        continuity_result = None
        linter_issues = []

        # Previous chapter ending — used by StyleAgent (echo detection) and ThemeAgent (hook contradiction)
        prev_ending = ""
        prev_path = self.chapters_dir / f"{chapter_number - 1:03d}.md"
        if prev_path.exists():
            prev_text = prev_path.read_text(encoding="utf-8")
            prev_ending = prev_text[-600:]  # longer window for better echo detection

        for iteration in range(MAX_REVISIONS):
            logger.info("ch%d: review iteration %d...", chapter_number, iteration + 1)

            linter_issues = self.style_linter.check(chapter_text)
            continuity_result = await self.continuity_agent.review(
                chapter_text, bible_ctx, chapter_number
            )
            style_result = await self.style_agent.review(
                chapter_text=chapter_text,
                previous_chapter_ending=prev_ending,
                chapter_number=chapter_number,
            )
            # ThemeAgent: run once per chapter (expensive), but drives revisions if critical
            if iteration == 0:
                prev_summary = ""
                if chapter_number > 1 and (chapter_number - 1) in bible.chapter_summaries:
                    prev_summary = bible.chapter_summaries[chapter_number - 1].summary
                # Include prev chapter's ending hook to catch hook contradictions
                prev_hook_ctx = ""
                if prev_ending:
                    prev_hook_ctx = f"\n\n## 上一章结尾（检查本章开头是否与之矛盾）\n{prev_ending}"
                theme_result = await self.theme_agent.review_chapter(
                    chapter_text=chapter_text,
                    chapter_number=chapter_number,
                    previous_chapter_summary=prev_summary,
                    arc_context=bible_ctx.text[:800] + prev_hook_ctx,
                )
                theme_health = theme_result.thematic_health

            has_errors = any(i.severity == Severity.ERROR for i in linter_issues)
            needs_revision = (
                has_errors
                or (continuity_result and (not continuity_result.passed or continuity_result.has_critical))
                or (style_result and style_result.has_errors)
                or (theme_result and theme_result.has_critical)
            )

            if not needs_revision:
                logger.info("ch%d: review passed on iteration %d", chapter_number, iteration + 1)
                break

            revision_count = iteration + 1
            if revision_count >= MAX_REVISIONS:
                logger.warning("ch%d: max revisions reached, proceeding with issues", chapter_number)
                break

            # Build feedback
            feedback_parts = []
            linter_feedback = self.style_linter.format_feedback_for_writer(linter_issues)
            if linter_feedback:
                feedback_parts.append(linter_feedback)
            if continuity_result and (not continuity_result.passed or continuity_result.has_critical):
                feedback_parts.append(continuity_result.format_feedback())
            if style_result and style_result.issues:
                feedback_parts.append(style_result.format_feedback())
            if theme_result and theme_result.has_critical:
                feedback_parts.append(theme_result.format_feedback())
            feedback = "\n\n".join(feedback_parts)

            logger.info("ch%d: revising (pass %d)...", chapter_number, revision_count)
            revised = await self.writer.revise(
                chapter_text=chapter_text,
                feedback=feedback,
                bible_context=bible_ctx,
            )
            chapter_text = revised.chapter_text

        # --- 5. Extract lessons ---
        issues_summary = self._summarize_issues(
            linter_issues, continuity_result, theme_result, style_result,
        )
        new_lessons = await self.lessons.extract_and_append(
            chapter_number=chapter_number,
            issues_summary=issues_summary,
        )

        # --- 6. Save chapter text ---
        chapter_path = self.chapters_dir / f"{chapter_number:03d}.md"
        chapter_path.write_text(chapter_text, encoding="utf-8")
        logger.info("ch%d: saved to %s", chapter_number, chapter_path.name)

        # --- 7. Update Story Bible ---
        logger.info("ch%d: updating Story Bible...", chapter_number)
        bible = await self.bible_updater.update(
            bible=bible,
            chapter_text=chapter_text,
            chapter_number=chapter_number,
            branch=selected_branch,
        )
        self.loader.save(bible)
        bible_title = bible.chapter_summaries.get(chapter_number, type("", (), {"title": ""})()).title or selected_branch.title

        # --- 8. Git commit ---
        self._git_commit(chapter_number)
        if self.push:
            self._git_push()

        result = ChapterRunResult(
            chapter_number=chapter_number,
            word_count=len(chapter_text),
            branch_title=selected_branch.title,
            branch_reasoning=branch_reasoning,
            revision_count=revision_count,
            issues_summary=issues_summary,
            theme_health=theme_health,
            new_lessons=new_lessons,
            bible_title=bible_title,
        )
        self._log_result(result, theme_result)
        return result

    def _git_commit(self, chapter_number: int) -> None:
        try:
            subprocess.run(
                ["git", "add", "story_data/", "chapters/", "learned_rules.md"],
                cwd=str(self.project_dir), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m",
                 f"feat: 第{chapter_number}章——自动生成\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"],
                cwd=str(self.project_dir), check=True, capture_output=True,
            )
            logger.info("ch%d: git commit done", chapter_number)
        except subprocess.CalledProcessError as e:
            logger.warning("ch%d: git commit failed: %s", chapter_number, e)

    def _git_push(self) -> None:
        try:
            subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=str(self.project_dir), check=True, capture_output=True,
            )
            logger.info("git push done")
        except subprocess.CalledProcessError as e:
            logger.warning("git push failed: %s", e)

    def _log_result(self, r: ChapterRunResult, theme_result) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"\n## ch{r.chapter_number:02d} — {r.bible_title} ({timestamp})\n",
            f"- 分支: {r.branch_title}",
            f"- 字数: {r.word_count}",
            f"- 修改轮次: {r.revision_count}",
            f"- 主题健康: {r.theme_health}",
        ]
        if theme_result and theme_result.what_this_chapter_adds:
            lines.append(f"- 本章贡献: {theme_result.what_this_chapter_adds}")
        if r.issues_summary:
            lines.append(f"- 问题摘要:\n```\n{r.issues_summary}\n```")
        if r.new_lessons:
            lines.append("- 新学规则:\n" + "\n".join(f"  - {l}" for l in r.new_lessons))

        with open(RUN_LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    async def run(self, start: int, end: int) -> None:
        """Run the generation loop from start to end (inclusive)."""
        logger.info("AutoRunner: ch%d → ch%d", start, end)
        if not LEARNED_RULES_FILE.exists():
            LEARNED_RULES_FILE.write_text(
                "# 自动生成学习规则\n\n写作过程中发现的需要避免的模式。\n",
                encoding="utf-8",
            )
        if not RUN_LOG_FILE.exists():
            RUN_LOG_FILE.write_text("# AutoRunner 运行日志\n", encoding="utf-8")

        for ch in range(start, end + 1):
            try:
                result = await self.run_chapter(ch)
                logger.info(
                    "ch%d done: %d chars, %d revisions, %d new lessons",
                    ch, result.word_count, result.revision_count, len(result.new_lessons),
                )
            except Exception as e:
                logger.error("ch%d FAILED: %s", ch, e, exc_info=True)
                with open(RUN_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"\n## ch{ch:02d} — FAILED ({datetime.now().strftime('%H:%M')})\n\n```\n{e}\n```\n")
                raise  # stop the loop on failure

        logger.info("AutoRunner: all done ✓")


# ===========================================================================
# 5. CLI entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous chapter generation loop")
    parser.add_argument("--from", dest="start", type=int, default=None,
                        help="Start chapter (default: current_chapter+1)")
    parser.add_argument("--to", dest="end", type=int, default=20,
                        help="End chapter inclusive (default: 20)")
    parser.add_argument("--push", action="store_true",
                        help="Git push after each chapter")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan and select branch only, do not write or commit")
    args = parser.parse_args()

    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        # Try .env file
        env_path = PROJECT_DIR / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("MINIMAX_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        logger.error("MINIMAX_API_KEY not set")
        sys.exit(1)

    runner = AutoRunner(PROJECT_DIR, api_key, push=args.push, dry_run=args.dry_run)

    # Determine start chapter
    start = args.start
    if start is None:
        bible = runner.loader.load()
        start = bible.core.current_chapter + 1

    if start > args.end:
        logger.info("Nothing to do: start=%d end=%d", start, args.end)
        return

    asyncio.run(runner.run(start, args.end))


if __name__ == "__main__":
    main()
