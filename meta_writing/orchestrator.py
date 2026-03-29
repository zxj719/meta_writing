"""Orchestrator — pipeline controller for the chapter generation workflow.

Manages the full per-chapter workflow:
1. Load Story Bible state
2. Planner generates 2-3 plot branches
3. Human selects a branch
4. Writer drafts chapter
5. Continuity Agent reviews
6. Writer revises (up to 3 iterations)
7. Human reviews final draft
8. Commit: chapter text + Story Bible updates + foreshadowing updates + chapter summary
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

from .agents.continuity import ContinuityAgent, ContinuityResult
from .agents.planner import PlannerAgent, PlannerResult, PlotBranch
from .agents.style import StyleAgent, StyleAgentResult
from .agents.writer import WriterAgent, WriterResult
from .llm import LLMClient, MODEL_OPUS, MODEL_SONNET
from .story_bible.compressor import CompressedContext, StoryBibleCompressor
from .story_bible.loader import StoryBibleLoader
from .story_bible.schema import ChapterSummary, StoryBible
from .style_linter import StyleLinter, Severity


MAX_REVISION_ITERATIONS = 3


class PipelineStage(str, Enum):
    INIT = "init"
    PLANNING = "planning"
    BRANCH_SELECTION = "branch_selection"
    WRITING = "writing"
    REVIEWING = "reviewing"
    REVISING = "revising"
    HUMAN_REVIEW = "human_review"
    COMMITTING = "committing"
    DONE = "done"
    ERROR = "error"


@dataclass
class PipelineState:
    """Current state of the chapter generation pipeline."""
    stage: PipelineStage = PipelineStage.INIT
    chapter_number: int = 0
    planner_result: PlannerResult | None = None
    selected_branch: PlotBranch | None = None
    writer_result: WriterResult | None = None
    continuity_result: ContinuityResult | None = None
    style_agent_result: StyleAgentResult | None = None
    revision_count: int = 0
    error: str | None = None


# Callback types for human-in-the-loop
BranchSelector = Callable[[list[PlotBranch]], Awaitable[int]]
HumanReviewer = Callable[[str, ContinuityResult | None], Awaitable[tuple[str, str]]]
# Returns (action, notes) where action is "approve"/"reject"/"edit"
StateChangeConfirmer = Callable[[list[dict[str, Any]]], Awaitable[bool]]


class Orchestrator:
    """Manages the full chapter generation pipeline."""

    def __init__(
        self,
        project_dir: str | Path,
        api_key: str | None = None,
        planner_model: str = MODEL_OPUS,
        writer_model: str = MODEL_SONNET,
        continuity_model: str = MODEL_SONNET,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.story_data_dir = self.project_dir / "story_data"
        self.chapters_dir = self.project_dir / "chapters"
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.llm = LLMClient(api_key=api_key)
        self.loader = StoryBibleLoader(self.story_data_dir)
        self.compressor = StoryBibleCompressor()

        self.planner = PlannerAgent(self.llm, model=planner_model)
        self.writer = WriterAgent(self.llm, model=writer_model)
        self.continuity = ContinuityAgent(self.llm, model=continuity_model)
        self.style_agent = StyleAgent(self.llm, model=continuity_model)
        self.style_linter = StyleLinter()

        self.state = PipelineState()

    def load_bible(self) -> StoryBible:
        """Load the current Story Bible."""
        return self.loader.load()

    def get_recent_chapters_text(self, current_chapter: int, lookback: int = 3) -> str:
        """Read the text of recent chapters for context."""
        texts = []
        for ch in range(max(1, current_chapter - lookback + 1), current_chapter):
            path = self.chapters_dir / f"{ch:03d}.md"
            if path.exists():
                texts.append(f"--- 第{ch}章 ---\n{path.read_text(encoding='utf-8')}")
        return "\n\n".join(texts)

    async def generate_chapter(
        self,
        branch_selector: BranchSelector,
        human_reviewer: HumanReviewer,
        state_confirmer: StateChangeConfirmer,
        guidance: str = "",
    ) -> str:
        """Run the full chapter generation pipeline.

        Args:
            branch_selector: Async callback that selects a branch (returns index).
            human_reviewer: Async callback for human review of final draft.
            state_confirmer: Async callback to confirm Story Bible state changes.
            guidance: Optional guidance for the planner.

        Returns:
            The final chapter text.
        """
        # 1. Load state
        self.state.stage = PipelineStage.INIT
        bible = self.load_bible()
        chapter_number = bible.core.current_chapter + 1
        self.state.chapter_number = chapter_number

        recent_text = self.get_recent_chapters_text(chapter_number)
        bible_context = self.compressor.compress(
            bible, chapter_number, pov_character=None
        )

        # 2. Plan
        self.state.stage = PipelineStage.PLANNING
        planner_result = await self.planner.plan(
            bible_context=bible_context,
            recent_chapters_text=recent_text,
            chapter_number=chapter_number,
            additional_guidance=guidance,
        )
        self.state.planner_result = planner_result

        # 3. Human selects branch
        self.state.stage = PipelineStage.BRANCH_SELECTION
        branch_index = await branch_selector(planner_result.branches)
        selected_branch = planner_result.branches[branch_index]
        self.state.selected_branch = selected_branch

        # Recompress with known active characters
        bible_context = self.compressor.compress(
            bible,
            chapter_number,
            active_character_names=selected_branch.characters_involved,
        )

        # 4. Write (with auto-expansion if too short)
        self.state.stage = PipelineStage.WRITING
        writer_result = await self.writer.write_with_expansion(
            bible_context=bible_context,
            recent_chapters_text=recent_text,
            outline=selected_branch.outline,
            chapter_number=chapter_number,
        )
        self.state.writer_result = writer_result
        chapter_text = writer_result.chapter_text

        # 5-6. Review + Revise loop
        for iteration in range(MAX_REVISION_ITERATIONS):
            self.state.stage = PipelineStage.REVIEWING
            self.state.revision_count = iteration

            # 5a. Fast style lint (regex, zero-cost)
            style_issues = self.style_linter.check(chapter_text)
            style_feedback = self.style_linter.format_feedback_for_writer(style_issues)

            # 5b. LLM continuity review
            continuity_result = await self.continuity.review(
                chapter_text=chapter_text,
                bible_context=bible_context,
                chapter_number=chapter_number,
            )
            self.state.continuity_result = continuity_result

            # 5c. LLM style review (pacing, tics, echoes)
            prev_ending = ""
            if chapter_number > 1:
                prev_path = self.chapters_dir / f"{chapter_number - 1:03d}.md"
                if prev_path.exists():
                    prev_text = prev_path.read_text(encoding="utf-8")
                    prev_ending = prev_text[-400:] if len(prev_text) > 400 else prev_text

            style_agent_result = await self.style_agent.review(
                chapter_text=chapter_text,
                previous_chapter_ending=prev_ending,
                chapter_number=chapter_number,
            )
            self.state.style_agent_result = style_agent_result

            has_style_errors = any(
                i.severity == Severity.ERROR for i in style_issues
            )

            if (continuity_result.passed and not continuity_result.has_critical
                    and not has_style_errors
                    and not style_agent_result.has_errors):
                break

            # Revise — combine continuity + style feedback
            self.state.stage = PipelineStage.REVISING
            feedback_parts = []
            if continuity_result.has_critical or not continuity_result.passed:
                feedback_parts.append(continuity_result.format_feedback())
            if style_feedback:
                feedback_parts.append(style_feedback)
            if style_agent_result.issues:
                feedback_parts.append(style_agent_result.format_feedback())
            feedback = "\n\n".join(feedback_parts)

            revised = await self.writer.revise(
                chapter_text=chapter_text,
                feedback=feedback,
                bible_context=bible_context,
            )
            chapter_text = revised.chapter_text
            self.state.writer_result = revised

        # 7. Human review
        self.state.stage = PipelineStage.HUMAN_REVIEW
        action, notes = await human_reviewer(chapter_text, self.state.continuity_result)

        if action == "reject":
            self.state.stage = PipelineStage.ERROR
            self.state.error = f"Human rejected: {notes}"
            raise RuntimeError(f"Chapter rejected by human: {notes}")

        if action == "edit":
            # Human provided edited text in notes
            chapter_text = notes

        # 8. Commit
        self.state.stage = PipelineStage.COMMITTING
        await self._commit_chapter(
            bible=bible,
            chapter_number=chapter_number,
            chapter_text=chapter_text,
            selected_branch=selected_branch,
            continuity_result=self.state.continuity_result,
            state_confirmer=state_confirmer,
        )

        self.state.stage = PipelineStage.DONE
        return chapter_text

    async def _commit_chapter(
        self,
        bible: StoryBible,
        chapter_number: int,
        chapter_text: str,
        selected_branch: PlotBranch,
        continuity_result: ContinuityResult | None,
        state_confirmer: StateChangeConfirmer,
    ) -> None:
        """Atomic commit: save chapter + update Story Bible + git commit."""
        # Save chapter text
        chapter_path = self.chapters_dir / f"{chapter_number:03d}.md"
        chapter_path.write_text(chapter_text, encoding="utf-8")

        # Extract state changes from continuity review
        state_changes: list[dict[str, Any]] = []
        if continuity_result and continuity_result.state_changes:
            state_changes = [
                {
                    "character": sc.character,
                    "field": sc.field,
                    "old_value": sc.old_value,
                    "new_value": sc.new_value,
                }
                for sc in continuity_result.state_changes
            ]

        # Human confirms state changes before writing to Story Bible
        if state_changes:
            confirmed = await state_confirmer(state_changes)
            if confirmed:
                self._apply_state_changes(bible, state_changes)

        # Update chapter counter
        bible.core.current_chapter = chapter_number

        # Create chapter summary (minimal — full extraction is a future enhancement)
        summary = ChapterSummary(
            chapter_number=chapter_number,
            summary=selected_branch.outline[:200],
            characters_present=selected_branch.characters_involved,
            word_count=len(chapter_text),
        )
        bible.chapter_summaries[chapter_number] = summary

        # Save everything
        self.loader.save(bible)

        # Git commit (atomic)
        self._git_commit(chapter_number)

    def _apply_state_changes(
        self, bible: StoryBible, changes: list[dict[str, Any]]
    ) -> None:
        """Apply confirmed state changes to the Story Bible."""
        for change in changes:
            char_name = change["character"]
            char = bible.characters.get(char_name)
            if not char:
                continue
            field_name = change["field"]
            new_value = change["new_value"]
            if hasattr(char, field_name):
                setattr(char, field_name, new_value)

    def _git_commit(self, chapter_number: int) -> None:
        """Create an atomic git commit for the chapter + Story Bible updates."""
        try:
            subprocess.run(
                ["git", "add", "story_data/", "chapters/"],
                cwd=str(self.project_dir),
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"chapter {chapter_number:03d}: generate and commit"],
                cwd=str(self.project_dir),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # Non-fatal: log but don't crash the pipeline
            pass
