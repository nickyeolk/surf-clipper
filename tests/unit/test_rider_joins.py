"""T028: rides split at the frame edge are joined when they are one rider (FR-011)."""

from surfclip.config import load_config
from surfclip.edits.apply import apply_joins
from surfclip.riders.joins import find_joins
from surfclip.store.schemas import RideAssignment, RiderGroup, Riders, Rides

CFG = load_config().riders  # join_gap_s 6, join_confidence 0.4


def rides(*spec: tuple[str, float, float, bool, str]) -> Rides:
    return Rides.model_validate(
        {
            "session_id": "s",
            "source": {"path": "x.mp4", "fps": 30.0, "hdr_format": "none"},
            "settings": {"min_length_s": 1, "pad_before_s": 1.5, "pad_after_s": 2.0},
            "rides": [
                {"ride_id": rid, "start_s": s, "end_s": e, "confidence": 0.9, "start_frame": 0,
                 "end_frame": 0, "clip_start_s": s, "clip_end_s": e, "epochs": [0],
                 "track_ids": [k], "start_kind": kind, "flags": {"truncated": trunc}}
                for k, (rid, s, e, trunc, kind) in enumerate(spec)
            ],
        }
    )  # fmt: skip


def riders(cards: dict[str, list[str]], conf: float = 0.6) -> Riders:
    return Riders(
        session_id="s",
        descriptor="embedding",
        riders=[RiderGroup(rider_id=c, ride_ids=ids) for c, ids in cards.items()],
        assignments=[
            RideAssignment(ride_id=r, rider_id=c, confidence=conf)
            for c, ids in cards.items()
            for r in ids
        ],
    )


SPLIT = rides(("a", 0, 20, True, "unknown"), ("b", 23, 40, True, "off_frame"),
              ("c", 100, 130, False, "unknown"))  # fmt: skip


def test_same_rider_short_gap_at_the_edge_is_joined() -> None:
    auto, suggest = find_joins(SPLIT.rides, riders({"g1": ["a", "b"], "g2": ["c"]}), CFG)
    assert [(p[0][0], p[1][0]) for p in auto] == [("a", "b")] and not suggest
    joined = apply_joins(SPLIT, auto, [])
    first = joined.rides[0]
    assert (first.ride_id, first.start_s, first.end_s, first.flags.joined) == ("a", 0, 40, True)
    assert len(joined.rides) == 2


def test_different_riders_or_long_gap_are_not_joined() -> None:
    auto, suggest = find_joins(SPLIT.rides, riders({"g1": ["a"], "g2": ["b", "c"]}), CFG)
    assert not auto and not suggest
    far = rides(("a", 0, 20, True, "unknown"), ("b", 30, 40, True, "off_frame"))
    assert find_joins(far.rides, riders({"g1": ["a", "b"]}), CFG) == ([], [])


def test_low_confidence_is_only_suggested() -> None:
    auto, suggest = find_joins(SPLIT.rides, riders({"g1": ["a", "b"], "g2": ["c"]}, 0.2), CFG)
    assert not auto and [(s.first, s.second) for s in suggest] == [("a", "b")]


def test_unjoined_pair_stays_apart() -> None:
    auto, _ = find_joins(SPLIT.rides, riders({"g1": ["a", "b"], "g2": ["c"]}), CFG)
    assert len(apply_joins(SPLIT, auto, auto).rides) == 3  # the user unjoined it
    again, _ = find_joins(SPLIT.rides, riders({"g1": ["a", "b"], "g2": ["c"]}), CFG, auto)
    assert again == []
