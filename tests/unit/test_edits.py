"""T051: user edits on detected rides (FR-022, SC-007)."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from surfclip.edits.apply import apply_edits
from surfclip.store.schemas import EditOp, Edits, EditTarget, Ride, Rides, UserEdit

FPS = 30.0


def ride(rid: str, start: float, end: float) -> Ride:
    return Ride(
        ride_id=rid,
        start_s=start,
        end_s=end,
        confidence=0.8,
        start_frame=round(start * FPS),
        end_frame=round(end * FPS),
        clip_start_s=start - 1.5,
        clip_end_s=end + 2.0,
        epochs=[0],
        track_ids=[1],
    )


def detected(*rides: Ride) -> Rides:
    return Rides.model_validate(
        {
            "session_id": "abc",
            "source": {"path": "x.mp4", "fps": FPS, "hdr_format": "none"},
            "settings": {"min_length_s": 10, "pad_before_s": 1.5, "pad_after_s": 2.0},
            "rides": [r.model_dump() for r in rides],
        }
    )


def log(*edits: tuple[EditOp, EditTarget, Mapping[str, object]]) -> Edits:
    return Edits(
        edits=[
            UserEdit(
                edit_id=i, at=datetime(2026, 10, 15, tzinfo=UTC), op=op, target=t, payload=dict(p)
            )
            for i, (op, t, p) in enumerate(edits, start=1)
        ]
    )


A = ride("r003000", 100.0, 130.0)
B = ride("r004500", 150.0, 175.0)


def ids(rides: Rides) -> list[str]:
    return [r.ride_id for r in rides.rides]


def test_trim_moves_bounds_padding_and_flags() -> None:
    out = apply_edits(
        detected(A, B),
        log(("trim", EditTarget(ride_id=A.ride_id), {"start_s": 102.0, "end_s": 128.0})),
    )
    r = out.rides[0]
    assert (r.start_s, r.end_s) == (102.0, 128.0)
    assert (r.clip_start_s, r.clip_end_s) == (100.5, 130.0)
    assert r.start_frame == 3060 and r.flags.user_edited


def test_split_merge_delete_add() -> None:
    out = apply_edits(
        detected(A, B),
        log(
            ("split", EditTarget(ride_id=A.ride_id), {"at_s": 115.0}),
            ("merge", EditTarget(ride_ids=["r003000b", B.ride_id]), {}),
            ("delete", EditTarget(ride_id="r003000a"), {}),
            ("add", EditTarget(), {"start_s": 200.0, "end_s": 206.0}),
        ),
    )
    assert ids(out) == ["r003000b", "u0004"]
    assert (out.rides[0].start_s, out.rides[0].end_s) == (115.0, 175.0)
    assert out.rides[1].flags.user_added and out.rides[1].length_s == 6.0


def test_undo_and_redo() -> None:
    delete = ("delete", EditTarget(ride_id=A.ride_id), {})
    undo = ("undo", EditTarget(), {"edit_id": 1})
    assert ids(apply_edits(detected(A, B), log(delete, undo))) == [A.ride_id, B.ride_id]
    redo = ("undo", EditTarget(), {"edit_id": 2})
    assert ids(apply_edits(detected(A, B), log(delete, undo, redo))) == [B.ride_id]


def test_edits_reattach_when_rerun_changes_ride_ids() -> None:
    """After a re-run, ride A starts 0.4 s later and gets id r003012: the trim still applies."""
    edits = log(
        (
            "trim",
            EditTarget(ride_id=A.ride_id),
            {"end_s": 133.0, "spans": {A.ride_id: [100.0, 130.0]}},
        ),
        ("delete", EditTarget(ride_id=B.ride_id), {"spans": {B.ride_id: [150.0, 175.0]}}),
    )
    rerun = detected(ride("r003012", 100.4, 129.0), ride("r004530", 151.0, 175.0))
    out = apply_edits(rerun, edits)
    assert ids(out) == ["r003012"]
    assert out.rides[0].end_s == 133.0


def test_same_id_on_a_different_ride_is_not_reused() -> None:
    edits = log(("delete", EditTarget(ride_id=A.ride_id), {"spans": {A.ride_id: [100.0, 130.0]}}))
    moved = ride(A.ride_id, 100.0, 112.0)  # same start frame, but now a much shorter ride
    assert ids(apply_edits(detected(moved), edits)) == [A.ride_id]


def test_unmatched_trimmed_ride_is_kept_as_user_added() -> None:
    edits = log(
        (
            "trim",
            EditTarget(ride_id=A.ride_id),
            {"start_s": 101.0, "spans": {A.ride_id: [100.0, 130.0]}},
        )
    )
    out = apply_edits(detected(B), edits)  # re-run no longer finds ride A
    kept = next(r for r in out.rides if r.flags.user_added)
    assert (kept.ride_id, kept.start_s, kept.end_s) == ("u0001", 101.0, 130.0)


def test_unmatched_delete_is_skipped() -> None:
    edits = log(("delete", EditTarget(ride_id="r999999"), {"spans": {"r999999": [1.0, 20.0]}}))
    assert ids(apply_edits(detected(A), edits)) == [A.ride_id]


@pytest.mark.parametrize("at", [100.0, 140.0])
def test_split_outside_ride_is_ignored(at: float) -> None:
    out = apply_edits(detected(A), log(("split", EditTarget(ride_id=A.ride_id), {"at_s": at})))
    assert ids(out) == [A.ride_id]


def test_apply_is_deterministic() -> None:
    edits = log(
        ("split", EditTarget(ride_id=A.ride_id), {"at_s": 115.0}),
        ("add", EditTarget(), {"start_s": 200.0, "end_s": 230.0}),
    )
    first = apply_edits(detected(A, B), edits).model_dump_json()
    assert apply_edits(detected(A, B), edits).model_dump_json() == first
