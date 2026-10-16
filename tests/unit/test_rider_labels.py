"""T010/T013: rider labels proposed from groups, finalized, and scored."""

import pytest

from surfclip.eval.labels import LabelError, SessionLabels
from surfclip.eval.metrics import LabelRide
from surfclip.eval.riders import (
    LabelledRide,
    RiderLabels,
    evaluate_riders,
    finalize,
    propose_work,
)
from surfclip.store.schemas import Ride, RiderGroup, Riders, Rides


def ride(rid: str, s: float, e: float) -> Ride:
    return Ride(ride_id=rid, start_s=s, end_s=e, confidence=0.9, start_frame=0, end_frame=0,
                clip_start_s=s, clip_end_s=e, epochs=[0], track_ids=[1])  # fmt: skip


DETECTED = Rides.model_validate(
    {
        "session_id": "s",
        "source": {"path": "x.mp4", "fps": 30.0, "hdr_format": "none"},
        "settings": {"min_length_s": 1, "pad_before_s": 1.5, "pad_after_s": 2.0},
        "rides": [ride(f"r{k}", 100.0 * k, 100.0 * k + 30).model_dump() for k in range(6)],
    }
)
# The tool's groups: r0 r2 r4 together (correct: "me"), r1 r3 (correct: "pat"), r5 alone
# (truly "me": the grouping got it wrong).
RIDERS = Riders(
    session_id="s",
    descriptor="colour",
    riders=[
        RiderGroup(rider_id="g01", ride_ids=["r0", "r2", "r4"]),
        RiderGroup(rider_id="g02", ride_ids=["r1", "r3"]),
        RiderGroup(rider_id="g03", ride_ids=["r5"]),
    ],
    assignments=[],
)
TRUTH = {0: "me", 1: "pat", 2: "me", 3: "pat", 4: "me", 5: "me"}


def test_proposals_come_from_the_detected_groups() -> None:
    labels = SessionLabels(
        source="x.mp4",
        rides=[LabelRide(start_s=100.0 * k + 1, end_s=100.0 * k + 30) for k in range(6)]
        + [LabelRide(start_s=900.0, end_s=920.0)],  # a ride the tool missed
    )
    work = propose_work(labels, DETECTED, RIDERS, "x.mp4")
    assert [i.proposed for i in work.items] == [
        "Rider 1", "Rider 2", "Rider 1", "Rider 2", "Rider 1", "Rider 3", None,
    ]  # fmt: skip
    assert work.items[0].detected_ride == "r0" and work.items[6].detected_ride is None
    with pytest.raises(LabelError):
        finalize(work)
    for item in work.items:
        item.rider = "me"
    work.named = ["me"]
    assert len(finalize(work).rides) == 7


def test_grouping_accuracy_uses_one_group_per_rider() -> None:
    labels = RiderLabels(
        source="x.mp4",
        named=["me"],
        rides=[
            LabelledRide(start_s=100.0 * k, end_s=100.0 * k + 30, rider=TRUTH[k]) for k in range(6)
        ],
    )
    m = evaluate_riders(labels, DETECTED, RIDERS)
    assert (m.labelled, m.correct, m.true_riders, m.groups) == (6, 5, 2, 3)
    assert m.accuracy == pytest.approx(5 / 6)
    assert m.corrections == 1  # "me" needs one same-as (r5's card holds only "me")
