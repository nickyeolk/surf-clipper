"""T017: per-track on/off-wave state machine (FR-010, FR-011, FR-013)."""

import pytest

from surfclip.rides.evidence import classify
from surfclip.rides.state_machine import track_rides
from tests.unit.ride_synth import (
    FPS,
    ZONE,
    Seg,
    ride_segment,
    rides_cfg,
    sitting_on_wall,
    track,
)


def _rides(obs, **cfg):  # type: ignore[no-untyped-def]
    c = rides_cfg(**cfg)
    return track_rides(classify(obs, ZONE, c), c)


def test_side_wall_sitter_never_rides_even_when_overlapping_zone() -> None:
    # Feet on the wall top (just outside u=0); the box reaches well into the zone in the image.
    sitter = track(1, 0.0, Seg(300, -0.06, -0.06, v=0.3, board=True, stance="standing"))
    states, rides = _rides(sitter)
    assert rides == []
    assert set(states) == {"off"}


def test_person_in_water_without_board_stays_off() -> None:
    instructor = track(1, 0.0, Seg(120, 0.4, 0.45, board=False, stance="standing"))
    _, rides = _rides(instructor)
    assert rides == []


def test_acid_drop_from_side_wall_starts_at_the_jump() -> None:
    obs = track(1, 0.0, sitting_on_wall(3.0), ride_segment(12.0, 0.08, 0.7))
    last_wall_t = obs[round(3.0 * FPS) - 1].t
    _, rides = _rides(obs)
    assert len(rides) == 1
    r = rides[0]
    assert r.start_kind == "acid_drop"
    assert r.start_t == pytest.approx(last_wall_t)
    assert r.end_t == pytest.approx(obs[-1].t)


def test_off_frame_entry_starts_at_first_appearance() -> None:
    obs = track(1, 4.0, Seg(0.4, 0.06, 0.08, edge="left"), ride_segment(12.0, 0.08, 0.7))
    _, rides = _rides(obs)
    assert len(rides) == 1
    assert rides[0].start_kind == "off_frame"
    assert rides[0].start_t == pytest.approx(4.0)


def test_ride_is_confirmed_only_after_window_but_start_is_back_dated() -> None:
    obs = track(1, 10.0, ride_segment(12.0))
    states, rides = _rides(obs)
    assert rides[0].start_t == pytest.approx(10.0)
    assert rides[0].confirmed_t == pytest.approx(10.0 + 1.4, abs=0.21)
    assert states[0] == "on_wave"


def test_short_blip_is_not_a_ride() -> None:
    _, rides = _rides(track(1, 0.0, ride_segment(1.0)))
    assert rides == []


def test_fall_ends_ride_on_last_on_wave_frame() -> None:
    obs = track(
        1,
        0.0,
        ride_segment(12.0),
        Seg(3.0, 0.8, 0.8, board=False, stance="unknown"),
    )
    states, rides = _rides(obs)
    assert len(rides) == 1
    assert rides[0].end_t == pytest.approx(obs[round(12.0 * FPS) - 1].t)
    assert states[-1] == "off"


def test_brief_evidence_gap_does_not_split_ride() -> None:
    obs = track(
        1,
        0.0,
        ride_segment(6.0, 0.1, 0.4),
        Seg(0.4, 0.4, 0.42, board=False),  # board lost in spray for 0.4 s
        ride_segment(6.0, 0.42, 0.8),
    )
    _, rides = _rides(obs)
    assert len(rides) == 1


def test_long_gap_without_upright_evidence_splits_ride() -> None:
    obs = track(
        1,
        0.0,
        ride_segment(6.0, 0.1, 0.4),
        Seg(2.0, 0.4, 0.42, board=False, stance="unknown"),  # not seen upright: down
        ride_segment(6.0, 0.42, 0.8),
    )
    _, rides = _rides(obs)
    assert len(rides) == 2


def test_upright_bridge_has_a_limit() -> None:
    obs = track(
        1,
        0.0,
        ride_segment(6.0, 0.1, 0.4),
        Seg(5.0, 0.4, 0.42, board=False),  # upright but no board for 5 s (> 4 s bridge)
        ride_segment(6.0, 0.42, 0.8),
    )
    _, rides = _rides(obs)
    assert len(rides) == 2


def test_standing_still_on_board_is_not_riding() -> None:
    _, rides = _rides(track(1, 0.0, Seg(20.0, 0.5, 0.5)))
    assert rides == []


def test_rider_cut_off_at_frame_bottom_counts_without_visible_board() -> None:
    """Close cameras (20261012) cut off the feet and board; standing in the zone is enough."""
    obs = track(1, 0.0, ride_segment(12.0, board=False, edge="bottom"))
    _, rides = _rides(obs)
    assert len(rides) == 1


def test_rider_cut_off_at_a_side_edge_counts_without_visible_board() -> None:
    """20261012 14:47: the rider carves past the left frame edge; the board is out of shot."""
    obs = track(
        1,
        0.0,
        ride_segment(8.0, 0.9, 0.6),
        Seg(5.0, 0.6, 0.55, board=False, edge="left"),
        ride_segment(6.0, 0.55, 0.8),
    )
    _, rides = _rides(obs)
    assert len(rides) == 1
    assert rides[0].end_t == pytest.approx(obs[-1].t)


def test_standing_at_a_side_edge_does_not_start_a_ride() -> None:
    obs = track(1, 0.0, Seg(20.0, 0.3, 0.7, board=False, edge="left"))
    _, rides = _rides(obs)
    assert rides == []


def test_rider_carving_next_to_a_side_wall_stays_riding() -> None:
    obs = track(1, 0.0, ride_segment(6.0, 0.5, 0.98), ride_segment(6.0, 0.98, 0.5))
    _, rides = _rides(obs)
    assert len(rides) == 1


def test_hand_on_the_wall_while_upright_stays_one_ride() -> None:
    """20240924: a rider crouches against a side wall, board hidden, then rides on."""
    obs = track(
        1,
        0.0,
        ride_segment(8.0, 0.3, 0.97),
        Seg(1.6, 0.97, 0.99, board=False, stance="crouched"),
        Seg(0.2, 1.01, 1.01, board=True),  # one frame on the wall band
        Seg(0.4, 0.99, 0.99, board=False),
        ride_segment(8.0, 0.98, 0.3),
    )
    _, rides = _rides(obs)
    assert len(rides) == 1
    assert rides[0].end_t == pytest.approx(obs[-1].t)


def test_deep_crouch_read_as_sitting_stays_one_ride() -> None:
    """20240924 39:19: a low carve makes the box wide; it reads as sitting for under a second."""
    obs = track(
        1,
        0.0,
        ride_segment(8.0, 0.3, 0.6),
        Seg(0.2, 0.6, 0.6, board=False, stance="sitting"),
        Seg(0.6, 0.6, 0.62, board=True, stance="sitting"),
        Seg(0.6, 0.62, 0.6, board=False, stance="standing"),
        ride_segment(8.0, 0.6, 0.2),
    )
    _, rides = _rides(obs)
    assert len(rides) == 1


def test_stall_against_the_wall_stays_one_ride() -> None:
    """20240924 57:24: sits low against the side wall for ~2 s, then rides on."""
    obs = track(
        1,
        0.0,
        ride_segment(8.0, 0.3, 0.95),
        Seg(2.2, 0.97, 0.99, board=False, stance="sitting"),
        ride_segment(8.0, 0.98, 0.2),
    )
    _, rides = _rides(obs)
    assert len(rides) == 1


def test_fall_with_a_gap_still_splits() -> None:
    obs = track(
        1,
        0.0,
        ride_segment(8.0, 0.2, 0.5),
        Seg(2.5, 0.5, 0.5, board=False, stance="sitting"),  # down in the water, mid-wave
        ride_segment(8.0, 0.5, 0.2),
    )
    _, rides = _rides(obs)
    assert len(rides) == 2


FACE = (0.3, 0.6)


def test_washed_over_the_back_ends_ride_even_if_upright() -> None:
    """FR-015: still standing on the board in the whitewater behind the wave is not riding."""
    obs = track(1, 0.0, ride_segment(12.0, v=0.45), Seg(5.0, 0.8, 0.85, v=0.85, board=True))
    c = rides_cfg()
    _, rides = track_rides(classify(obs, ZONE, c, face=FACE), c)
    assert len(rides) == 1
    assert rides[0].end_t == pytest.approx(obs[round(12.0 * FPS) - 1].t)


def test_landed_air_stays_one_ride() -> None:
    """An ollie lifts the feet off the face for under a second; the ride continues."""
    obs = track(
        1,
        0.0,
        ride_segment(6.0, 0.1, 0.4, v=0.45),
        Seg(0.6, 0.4, 0.45, v=0.15, board=True),  # in the air: feet project towards the back
        ride_segment(6.0, 0.45, 0.8, v=0.45),
    )
    c = rides_cfg()
    _, rides = track_rides(classify(obs, ZONE, c, face=FACE), c)
    assert len(rides) == 1


def test_mirrored_scene_gives_same_rides() -> None:
    obs = track(1, 0.0, sitting_on_wall(3.0, u=1.05), ride_segment(12.0, 0.92, 0.3))
    _, rides = _rides(obs)
    assert len(rides) == 1 and rides[0].start_kind == "acid_drop"
