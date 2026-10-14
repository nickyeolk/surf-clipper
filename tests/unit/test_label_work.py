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
