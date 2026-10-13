"""T019: evaluation metrics against hand labels (SC-001..SC-003)."""

import pytest

from surfclip.eval.metrics import LabelRide, Span, evaluate


def test_perfect_detection() -> None:
    labels = [LabelRide(start_s=10, end_s=30), LabelRide(start_s=50, end_s=70)]
    m = evaluate([Span(10, 30), Span(50, 70)], labels)
    assert (m.recall, m.precision) == (1.0, 1.0)
    assert m.start_err_median == 0 and m.end_err_p95 == 0


def test_iou_threshold_decides_match() -> None:
    labels = [LabelRide(start_s=10, end_s=30)]
    assert evaluate([Span(15, 30)], labels).recall == 1.0  # IoU 0.75
    assert evaluate([Span(25, 40)], labels).recall == 0.0  # IoU 0.17


def test_miss_and_false_ride() -> None:
    labels = [LabelRide(start_s=10, end_s=30), LabelRide(start_s=50, end_s=70)]
    m = evaluate([Span(10, 30), Span(100, 120)], labels)
    assert m.recall == 0.5 and m.precision == 0.5
    assert m.missed == [1] and m.false_rides == [1]


def test_each_label_matches_at_most_one_detection() -> None:
    labels = [LabelRide(start_s=10, end_s=30)]
    m = evaluate([Span(10, 30), Span(11, 30)], labels)
    assert m.recall == 1.0 and m.precision == 0.5


def test_short_labels_are_excluded_from_recall() -> None:
    labels = [LabelRide(start_s=10, end_s=30), LabelRide(start_s=50, end_s=55)]
    m = evaluate([Span(10, 30)], labels, min_length_s=10)
    assert m.recall == 1.0 and m.n_labels == 1


def test_boundary_errors_and_acid_drops_reported_separately() -> None:
    labels = [
        LabelRide(start_s=10, end_s=30),
        LabelRide(start_s=50, end_s=70, acid_drop=True),
    ]
    m = evaluate([Span(10.4, 30.2), Span(51.0, 70.0)], labels)
    assert m.start_err_median == pytest.approx(0.4)
    assert m.acid_start_errs == [pytest.approx(1.0)]
    assert m.end_err_p95 == pytest.approx(0.2, abs=1e-9)


def test_no_detections_and_no_labels() -> None:
    m = evaluate([], [])
    assert m.recall == 1.0 and m.precision == 1.0
