from __future__ import annotations

from meta_writing.editorial_scorecard import (
    EditorialDimension,
    EditorialDimensionScore,
    EditorialScorecard,
    aggregate_editorial_scorecards,
    editorial_progress_stalled,
)


def _make_scorecard(
    default_score: float = 8.0,
    overrides: dict[EditorialDimension, float] | None = None,
) -> EditorialScorecard:
    dimensions = {
        EditorialDimension.PLOT_TENSION: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.CHARACTERS: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.INFO_DESIGN: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.LANGUAGE: EditorialDimensionScore(score=default_score, reason="ok"),
        EditorialDimension.INSTRUCTION_FIT: EditorialDimensionScore(score=default_score, reason="ok"),
    }
    for dimension, score in (overrides or {}).items():
        dimensions[dimension] = EditorialDimensionScore(score=score, reason="override")
    return EditorialScorecard(dimensions=dimensions)


def test_aggregate_editorial_scorecards_uses_weighted_average() -> None:
    aggregate = aggregate_editorial_scorecards([_make_scorecard(8.0), _make_scorecard(9.0)])

    assert round(aggregate.overall_score, 2) == 8.5
    assert aggregate.passes_threshold(8.0, 7.0) is True


def test_aggregate_editorial_scorecards_reports_low_dimensions_by_floor() -> None:
    aggregate = aggregate_editorial_scorecards(
        [
            _make_scorecard(
                8.8,
                overrides={EditorialDimension.LANGUAGE: 6.7},
            )
        ]
    )

    assert aggregate.overall_score > 8.0
    assert aggregate.passes_threshold(8.0, 7.0) is False
    assert aggregate.low_dimensions(7.0) == [EditorialDimension.LANGUAGE]


def test_editorial_progress_stalled_when_recent_rounds_barely_improve() -> None:
    assert editorial_progress_stalled([7.1, 7.22, 7.33], min_improvement=0.2, patience=2) is True
    assert editorial_progress_stalled([7.1, 7.35, 7.6], min_improvement=0.2, patience=2) is False
