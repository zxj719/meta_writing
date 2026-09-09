"""Pipeline controller for manual chapter generation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from .agents.continuity import ContinuityAgent, ContinuityResult
from .agents.planner import PlannerAgent, PlannerResult, PlotBranch
from .agents.style import StyleAgent, StyleAgentResult
from .agents.theme import ThemeAgent, ThemeAgentResult
from .agents.writer import (
    MIN_CHAPTER_CHARS,
    TARGET_CHAPTER_CHARS,
    WriterAgent,
    WriterResult,
)
from .editorial_scorecard import (
    EDITORIAL_PASS_THRESHOLD,
    AggregatedEditorialScore,
    EditorialReviewRound,
    EditorialReviewTrace,
    aggregate_editorial_scorecards,
    editorial_progress_stalled,
)
from .llm import LLMClient, MODEL_OPUS, MODEL_SONNET, build_writer_backend
from .prompt_profiles import detect_prompt_profile
from .story_bible.compressor import StoryBibleCompressor
from .story_bible.loader import StoryBibleLoader
from .story_bible.schema import ChapterSummary, StoryBible
from .style_linter import Severity, StyleLinter


MAX_REVISION_ITERATIONS = 5


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
    stage: PipelineStage = PipelineStage.INIT
    chapter_number: int = 0
    planner_result: PlannerResult | None = None
    selected_branch: PlotBranch | None = None
    writer_result: WriterResult | None = None
    continuity_result: ContinuityResult | None = None
    style_agent_result: StyleAgentResult | None = None
    theme_agent_result: ThemeAgentResult | None = None
    editorial_score: AggregatedEditorialScore | None = None
    editorial_score_history: list[float] = field(default_factory=list)
    editorial_review_rounds: list[EditorialReviewRound] = field(default_factory=list)
    revision_count: int = 0
    error: str | None = None


BranchSelector = Callable[[list[PlotBranch]], Awaitable[int]]
HumanReviewer = Callable[[str, ContinuityResult | None], Awaitable[tuple[str, str]]]
StateChangeConfirmer = Callable[[list[dict[str, Any]]], Awaitable[bool]]


class Orchestrator:
    """Manages the full manual chapter generation pipeline."""

    def __init__(
        self,
        project_dir: str | Path,
        api_key: str | None = None,
        planner_model: str = MODEL_OPUS,
        writer_model: str | None = None,
        continuity_model: str = MODEL_SONNET,
        writer_provider: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.story_data_dir = self.project_dir / "story_data"
        self.chapters_dir = self.project_dir / "chapters"
        self.creator_guidance_path = self.project_dir / "creator_guidance.md"
        self.editorial_reviews_dir = self.project_dir / "editorial_reviews"
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

        self.llm = LLMClient(api_key=api_key)
        self.loader = StoryBibleLoader(self.story_data_dir)
        self.compressor = StoryBibleCompressor()
        core = self.loader.load_core()

        resolved_writer_provider = writer_provider or (core.writer_provider if core else "minimax")
        writer_llm, auto_writer_model = build_writer_backend(
            resolved_writer_provider,
            minimax_api_key=api_key,
        )
        if resolved_writer_provider == "minimax":
            writer_llm = self.llm
        resolved_writer_model = writer_model or auto_writer_model

        self.planner = PlannerAgent(self.llm, model=planner_model)
        self.writer = WriterAgent(writer_llm, model=resolved_writer_model)
        self.continuity = ContinuityAgent(self.llm, model=continuity_model)
        self.style_agent = StyleAgent(self.llm, model=continuity_model)
        self.theme_agent = ThemeAgent(self.llm, model=continuity_model)
        self.style_linter = StyleLinter()

        self.state = PipelineState()

    def load_bible(self) -> StoryBible:
        return self.loader.load()

    def get_recent_chapters_text(self, current_chapter: int, lookback: int = 3) -> str:
        texts = []
        for chapter in range(max(1, current_chapter - lookback + 1), current_chapter):
            path = self.chapters_dir / f"{chapter:03d}.md"
            if path.exists():
                texts.append(f"--- 第{chapter}章 ---\n{path.read_text(encoding='utf-8')}")
        return "\n\n".join(texts)

    def _load_creator_guidance(self) -> str:
        if not self.creator_guidance_path.exists():
            return ""
        return self.creator_guidance_path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _merge_guidance(file_guidance: str, inline_guidance: str) -> str:
        parts = [part.strip() for part in (file_guidance, inline_guidance) if part and part.strip()]
        return "\n\n".join(parts)

    async def generate_chapter(
        self,
        branch_selector: BranchSelector,
        human_reviewer: HumanReviewer,
        state_confirmer: StateChangeConfirmer,
        guidance: str = "",
    ) -> str:
        self.state.stage = PipelineStage.INIT
        self.state.editorial_score_history.clear()
        self.state.editorial_review_rounds.clear()
        bible = self.load_bible()
        chapter_number = bible.core.current_chapter + 1
        self.state.chapter_number = chapter_number

        creator_guidance = self._load_creator_guidance()
        merged_guidance = self._merge_guidance(creator_guidance, guidance)
        prompt_profile = detect_prompt_profile(
            creator_guidance=merged_guidance,
            target_satisfaction_type=bible.core.target_satisfaction_type,
        )

        recent_text = self.get_recent_chapters_text(chapter_number)
        bible_context = self.compressor.compress(bible, chapter_number, pov_character=None)

        self.state.stage = PipelineStage.PLANNING
        planner_result = await self.planner.plan(
            bible_context=bible_context,
            recent_chapters_text=recent_text,
            chapter_number=chapter_number,
            additional_guidance=merged_guidance,
            prompt_profile=prompt_profile,
        )
        self.state.planner_result = planner_result

        self.state.stage = PipelineStage.BRANCH_SELECTION
        branch_index = await branch_selector(planner_result.branches)
        selected_branch = planner_result.branches[branch_index]
        self.state.selected_branch = selected_branch

        bible_context = self.compressor.compress(
            bible,
            chapter_number,
            active_character_names=selected_branch.characters_involved,
        )

        self.state.stage = PipelineStage.WRITING
        writer_result = await self.writer.write_with_expansion(
            bible_context=bible_context,
            recent_chapters_text=recent_text,
            outline=selected_branch.outline,
            chapter_number=chapter_number,
            min_chars=bible.core.chapter_min_chars or MIN_CHAPTER_CHARS,
            target_chars=bible.core.chapter_target_chars or TARGET_CHAPTER_CHARS,
            creative_guidance=merged_guidance,
            prompt_profile=prompt_profile,
        )
        self.state.writer_result = writer_result
        chapter_text = writer_result.chapter_text

        for iteration in range(MAX_REVISION_ITERATIONS):
            self.state.stage = PipelineStage.REVIEWING
            self.state.revision_count = iteration

            style_issues = self.style_linter.check(chapter_text)
            style_feedback = self.style_linter.format_feedback_for_writer(style_issues)

            continuity_result = await self.continuity.review(
                chapter_text=chapter_text,
                bible_context=bible_context,
                chapter_number=chapter_number,
                prompt_profile=prompt_profile,
                creative_guidance=merged_guidance,
            )
            self.state.continuity_result = continuity_result

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
                creative_guidance=merged_guidance,
                prompt_profile=prompt_profile,
            )
            self.state.style_agent_result = style_agent_result

            previous_summary = ""
            if chapter_number > 1 and (chapter_number - 1) in bible.chapter_summaries:
                previous_summary = bible.chapter_summaries[chapter_number - 1].summary

            theme_agent_result = await self.theme_agent.review_chapter(
                chapter_text=chapter_text,
                chapter_number=chapter_number,
                previous_chapter_summary=previous_summary,
                arc_context=bible_context.text[:800],
                creative_guidance=merged_guidance,
                prompt_profile=prompt_profile,
            )
            self.state.theme_agent_result = theme_agent_result

            editorial_score = aggregate_editorial_scorecards(
                [
                    continuity_result.scorecard,
                    style_agent_result.scorecard,
                    theme_agent_result.scorecard,
                ]
            )
            self.state.editorial_score = editorial_score
            self.state.editorial_score_history.append(editorial_score.overall_score)

            has_style_errors = any(issue.severity == Severity.ERROR for issue in style_issues)
            blockers: list[str] = []
            if continuity_result.has_critical or not continuity_result.passed:
                blockers.append("continuity")
            if has_style_errors or style_agent_result.has_errors:
                blockers.append("style")
            if theme_agent_result.has_critical:
                blockers.append("third_editor")
            if not editorial_score.passes_threshold(EDITORIAL_PASS_THRESHOLD):
                blockers.append("scorecard")
            review_passed = (
                continuity_result.passed
                and not continuity_result.has_critical
                and not has_style_errors
                and not style_agent_result.has_errors
                and not theme_agent_result.has_critical
                and editorial_score.passes_threshold(EDITORIAL_PASS_THRESHOLD)
            )
            self.state.editorial_review_rounds.append(
                EditorialReviewRound(
                    iteration=iteration + 1,
                    overall_score=editorial_score.overall_score,
                    dimensions=dict(editorial_score.dimensions),
                    passed=review_passed,
                    blockers=blockers,
                )
            )
            if review_passed:
                review_trace_decision = "passed"
                break

            if editorial_progress_stalled(self.state.editorial_score_history):
                review_trace_decision = "stalled_below_threshold"
                break

            if iteration == MAX_REVISION_ITERATIONS - 1:
                review_trace_decision = "max_revisions_reached"
                break

            self.state.stage = PipelineStage.REVISING
            feedback_parts: list[str] = []
            if continuity_result.has_critical or not continuity_result.passed:
                feedback_parts.append(continuity_result.format_feedback())
            if style_feedback:
                feedback_parts.append(style_feedback)
            if style_agent_result.issues:
                feedback_parts.append(style_agent_result.format_feedback())
            if theme_agent_result.issues:
                feedback_parts.append(theme_agent_result.format_feedback())
            score_feedback = editorial_score.format_feedback_for_writer(EDITORIAL_PASS_THRESHOLD)
            if score_feedback:
                feedback_parts.append(score_feedback)
            feedback = "\n\n".join(part for part in feedback_parts if part.strip())

            revised = await self.writer.revise(
                chapter_text=chapter_text,
                feedback=feedback,
                bible_context=bible_context,
                creative_guidance=merged_guidance,
                prompt_profile=prompt_profile,
            )
            chapter_text = revised.chapter_text
            self.state.writer_result = revised
        else:
            review_trace_decision = "max_revisions_reached"

        self._write_editorial_review_trace(
            chapter_number=chapter_number,
            final_decision=review_trace_decision,
        )

        self.state.stage = PipelineStage.HUMAN_REVIEW
        action, notes = await human_reviewer(chapter_text, self.state.continuity_result)

        if action == "reject":
            self.state.stage = PipelineStage.ERROR
            self.state.error = f"Human rejected: {notes}"
            raise RuntimeError(f"Chapter rejected by human: {notes}")

        if action == "edit":
            chapter_text = notes

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

    def _write_editorial_review_trace(self, chapter_number: int, final_decision: str) -> None:
        trace = EditorialReviewTrace(
            chapter_number=chapter_number,
            final_decision=final_decision,
            rounds=list(self.state.editorial_review_rounds),
        )
        trace.write(self.editorial_reviews_dir)

    async def _commit_chapter(
        self,
        bible: StoryBible,
        chapter_number: int,
        chapter_text: str,
        selected_branch: PlotBranch,
        continuity_result: ContinuityResult | None,
        state_confirmer: StateChangeConfirmer,
    ) -> None:
        chapter_path = self.chapters_dir / f"{chapter_number:03d}.md"
        chapter_path.write_text(chapter_text, encoding="utf-8")

        state_changes: list[dict[str, Any]] = []
        if continuity_result and continuity_result.state_changes:
            state_changes = [
                {
                    "character": change.character,
                    "field": change.field,
                    "old_value": change.old_value,
                    "new_value": change.new_value,
                }
                for change in continuity_result.state_changes
            ]

        if state_changes:
            confirmed = await state_confirmer(state_changes)
            if confirmed:
                self._apply_state_changes(bible, state_changes)

        bible.core.current_chapter = chapter_number
        bible.chapter_summaries[chapter_number] = ChapterSummary(
            chapter_number=chapter_number,
            summary=selected_branch.outline[:200],
            characters_present=selected_branch.characters_involved,
            word_count=len(chapter_text),
        )

        self.loader.save(bible)
        self._git_commit(chapter_number)

    def _apply_state_changes(self, bible: StoryBible, changes: list[dict[str, Any]]) -> None:
        for change in changes:
            character = bible.characters.get(change["character"])
            if character is None:
                continue
            field_name = change["field"]
            if hasattr(character, field_name):
                setattr(character, field_name, change["new_value"])

    def _git_commit(self, chapter_number: int) -> None:
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
            pass
