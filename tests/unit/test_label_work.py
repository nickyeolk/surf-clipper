import pytest

from surfclip.eval.labels import LabelError, LabelItem, finalize, work_from_rides
from surfclip.store.schemas import Rides
from tests.unit.test_labels import EXAMPLE


def test_work_lists_rides_and_short_attempts_unvalidated() -> None:
    work = work_from_rides(Rides.model_validate(EXAMPLE), "x.mp4")
    assert [i.id for i in work.items] == ["r004512", "s006021"]
    assert work.remaining == 2
    assert work.items[0].acid_drop and work.items[1].detected_as == "short"


def test_finalize_needs_every_verdict() -> None:
    work = work_from_rides(Rides.model_validate(EXAMPLE), "x.mp4")
    with pytest.raises(LabelError, match="2 rides still need a verdict"):
        finalize(work)


def _item(id_: str, s: float, e: float, verdict: str = "ok", **kw: object) -> LabelItem:
    return LabelItem.model_validate(
        {
            "id": id_,
            "start_s": s,
            "end_s": e,
            "verdict": verdict,
            "detected_as": "acid_drop",
            "proposed_start_s": s,
            "proposed_end_s": e,
        }
        | kw
    )


def test_ride_inside_another_is_part_of_it_not_a_second_ride() -> None:
    """A wall touch split one ride; the user extended the first and also kept the second."""
    work = work_from_rides(Rides.model_validate(EXAMPLE), "x.mp4")
    work.items = [
        _item("r1", 100.0, 160.0, proposed_end_s=130.0),
        _item("r2", 132.0, 159.6),
        _item("r3", 200.0, 230.0),
    ]
    labels = finalize(work)
    assert [(r.start_s, r.end_s) for r in labels.rides] == [(100.0, 160.0), (200.0, 230.0)]


def test_changed_times_count_as_corrected_even_if_marked_ok() -> None:
    work = work_from_rides(Rides.model_validate(EXAMPLE), "x.mp4")
    work.items = [_item("r1", 100.0, 160.0, proposed_end_s=130.0), _item("r2", 200, 230)]
    origins = [r.origin for r in finalize(work).rides]
    assert origins == ["corrected", "accepted"]


def test_zero_length_ride_is_dropped() -> None:
    work = work_from_rides(Rides.model_validate(EXAMPLE), "x.mp4")
    work.items = [_item("r1", 100.0, 160.0), _item("r2", 661.4, 661.4)]
    assert len(finalize(work).rides) == 1


def test_finalize_maps_verdicts_to_origins() -> None:
    work = work_from_rides(Rides.model_validate(EXAMPLE), "x.mp4")
    work.items[0].verdict = "fix"
    work.items[0].start_s = 149.9
    work.items[1].verdict = "no"
    work.items.append(LabelItem(id="u1", start_s=300, end_s=320, verdict="add"))
    labels = finalize(work)
    assert [(r.start_s, r.origin) for r in labels.rides] == [
        (149.9, "corrected"),
        (300, "added"),
    ]
