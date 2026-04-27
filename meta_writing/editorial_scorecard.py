"""Shared editorial scorecard models and aggregation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path


EDITORIAL_PASS_THRESHOLD = 8.0
EDITORIAL_DIMENSION_FLOOR = 7.0
EDITORIAL_MIN_IMPROVEMENT = 0.2
EDITORIAL_STAGNATION_PATIENCE = 2

EDITORIAL_SCORECARD_PROMPT = """\
## 章节评分卡（必须输出在 JSON 的 scorecard 字段里）

请按这五个维度分别打 0-10 分，并给一句具体理由：
- plot_tension：剧情张力与节奏（权重 30%）
- characters：人物塑造与互动（权重 25%）
- info_design：信息量与暗线设计（权重 20%）
- language：语言与描写质感（权重 15%）
- instruction_fit：指令满足与完成度（权重 10%）

打分要克制，不要虚高。6 分表示“基本可用但明显还有问题”，8 分表示“达标”，9 分以上表示“这一维真的有记忆点”。
"""


class EditorialDimension(str, Enum):
    """Five dimensions from the chapter scorecard."""

    PLOT_TENSION = "plot_tension"
    CHARACTERS = "characters"
    INFO_DESIGN = "info_design"
    LANGUAGE = "language"
    INSTRUCTION_FIT = "instruction_fit"

    @property
    def label(self) -> str:
        return {
            EditorialDimension.PLOT_TENSION: "剧情张力与节奏",
            EditorialDimension.CHARACTERS: "人物塑造与互动",
            EditorialDimension.INFO_DESIGN: "信息量与暗线设计",
            EditorialDimension.LANGUAGE: "语言与描写质感",
            EditorialDimension.INSTRUCTION_FIT: "指令满足与完成度",
        }[self]


DIMENSION_WEIGHTS: dict[EditorialDimension, float] = {
    EditorialDimension.PLOT_TENSION: 0.30,
    EditorialDimension.CHARACTERS: 0.25,
    EditorialDimension.INFO_DESIGN: 0.20,
    EditorialDimension.LANGUAGE: 0.15,
    EditorialDimension.INSTRUCTION_FIT: 0.10,
}


@dataclass(frozen=True)
class EditorialDimensionScore:
    """One dimension score plus supporting rationale."""

    score: float
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", max(0.0, min(10.0, float(self.score))))


@dataclass(frozen=True)
class EditorialScorecard:
    """One reviewer's scorecard."""

    dimensions: dict[EditorialDimension, EditorialDimensionScore] = field(default_factory=dict)

    @property
    def overall_score(self) -> float:
        weighted = 0.0
        total_weight = 0.0
        for dimension, weight in DIMENSION_WEIGHTS.items():
            score = self.dimensions.get(dimension)
            if score is None:
                continue
            weighted += score.score * weight
            total_weight += weight
        if total_weight == 0:
            return 0.0
        return weighted / total_weight

    @classmethod
    def from_json_dict(cls, data: dict[str, object] | None) -> "EditorialScorecard | None":
        if not isinstance(data, dict):
            return None

        dimensions: dict[EditorialDimension, EditorialDimensionScore] = {}
        for dimension in EditorialDimension:
            raw_entry = data.get(dimension.value)
            if not isinstance(raw_entry, dict):
                continue
            score = raw_entry.get("score")
            if score is None:
                continue
            dimensions[dimension] = EditorialDimensionScore(
                score=float(score),
                reason=str(raw_entry.get("reason", "")),
            )

        if not dimensions:
            return None
        return cls(dimensions=dimensions)


@dataclass(frozen=True)
class AggregatedEditorialScore:
    """Weighted aggregate across multiple reviewers."""

    dimensions: dict[EditorialDimension, float]
    overall_score: float
    reviewer_count: int

    def passes_threshold(
        self,
        threshold: float = EDITORIAL_PASS_THRESHOLD,
        dimension_floor: float = EDITORIAL_DIMENSION_FLOOR,
    ) -> bool:
        return self.overall_score >= threshold and not self.low_dimensions(dimension_floor)

    def low_dimensions(
        self,
        dimension_floor: float = EDITORIAL_DIMENSION_FLOOR,
    ) -> list[EditorialDimension]:
        return [dim for dim, score in self.dimensions.items() if score < dimension_floor]

    def format_feedback_for_writer(
        self,
        threshold: float = EDITORIAL_PASS_THRESHOLD,
        dimension_floor: float = EDITORIAL_DIMENSION_FLOOR,
    ) -> str:
        if self.passes_threshold(threshold, dimension_floor):
            return ""

        lines = [
            "## 章节评分卡反馈",
            f"- 当前综合分：{self.overall_score:.2f} / 10.00",
            f"- 综合达标线：{threshold:.1f}",
            f"- 单项地板分：{dimension_floor:.1f}",
            "- 先修低分项，再继续润色其他维度。",
            "",
        ]
        for dimension in self.low_dimensions(dimension_floor):
            lines.append(
                f"- {dimension.label}：{self.dimensions[dimension]:.2f}，需要优先补强这一维。"
            )
        if self.overall_score < threshold:
            lines.append("- 当前综合分也未达标，需要继续打磨整体完成度。")
        return "\n".join(lines)


def aggregate_editorial_scorecards(
    scorecards: list[EditorialScorecard | None],
) -> AggregatedEditorialScore:
    """Aggregate reviewer scorecards by averaging each dimension, then weighting."""

    usable = [scorecard for scorecard in scorecards if scorecard is not None]
    if not usable:
        return AggregatedEditorialScore(
            dimensions={dimension: 0.0 for dimension in EditorialDimension},
            overall_score=0.0,
            reviewer_count=0,
        )

    dimension_scores: dict[EditorialDimension, float] = {}
    for dimension in EditorialDimension:
        values = [
            scorecard.dimensions[dimension].score
            for scorecard in usable
            if dimension in scorecard.dimensions
        ]
        if not values:
            dimension_scores[dimension] = 0.0
            continue
        dimension_scores[dimension] = sum(values) / len(values)

    overall_score = sum(
        dimension_scores[dimension] * weight
        for dimension, weight in DIMENSION_WEIGHTS.items()
    )
    return AggregatedEditorialScore(
        dimensions=dimension_scores,
        overall_score=overall_score,
        reviewer_count=len(usable),
    )


def editorial_progress_stalled(
    score_history: list[float],
    min_improvement: float = EDITORIAL_MIN_IMPROVEMENT,
    patience: int = EDITORIAL_STAGNATION_PATIENCE,
) -> bool:
    """Return True when recent review rounds barely improve overall score."""

    if patience <= 0 or len(score_history) < patience + 1:
        return False

    recent_scores = score_history[-(patience + 1):]
    improvements = [
        recent_scores[index + 1] - recent_scores[index]
        for index in range(len(recent_scores) - 1)
    ]
    return all(delta < min_improvement for delta in improvements)


@dataclass(frozen=True)
class EditorialReviewRound:
    """One review loop pass for a chapter."""

    iteration: int
    overall_score: float
    dimensions: dict[EditorialDimension, float]
    passed: bool
    blockers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EditorialReviewTrace:
    """Persistable review trace for one chapter."""

    chapter_number: int
    final_decision: str
    rounds: list[EditorialReviewRound] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# 章节审稿记录 ch{self.chapter_number:03d}",
            "",
            f"- final_decision: {self.final_decision}",
            f"- rounds: {len(self.rounds)}",
            "",
        ]
        for round_data in self.rounds:
            lines.append(f"## 第{round_data.iteration}轮")
            lines.append(f"- 综合分: {round_data.overall_score:.2f}")
            lines.append(f"- 是否达标: {'yes' if round_data.passed else 'no'}")
            if round_data.blockers:
                lines.append("- 阻塞项:")
                lines.extend(f"  - {blocker}" for blocker in round_data.blockers)
            lines.append("- 维度分:")
            for dimension in EditorialDimension:
                lines.append(
                    f"  - {dimension.label}: {round_data.dimensions.get(dimension, 0.0):.2f}"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def to_json_dict(self) -> dict[str, object]:
        return {
            "chapter_number": self.chapter_number,
            "final_decision": self.final_decision,
            "rounds": [
                {
                    "iteration": round_data.iteration,
                    "overall_score": round_data.overall_score,
                    "passed": round_data.passed,
                    "blockers": round_data.blockers,
                    "dimensions": {
                        dimension.value: round_data.dimensions.get(dimension, 0.0)
                        for dimension in EditorialDimension
                    },
                }
                for round_data in self.rounds
            ],
        }

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / f"{self.chapter_number:03d}.md"
        json_path = output_dir / f"{self.chapter_number:03d}.json"
        markdown_path.write_text(self.to_markdown(), encoding="utf-8")
        json_path.write_text(
            json.dumps(self.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
