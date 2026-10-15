"""T018: assembling track rides into session rides (FR-012, FR-014, FR-015, FR-018)."""

import pytest

from surfclip.rides.assemble import assemble
from surfclip.rides.evidence import Obs, classify
from surfclip.rides.state_machine import track_rides
from tests.unit.ride_synth import (
    SOURCE_FPS,
    ZONE,
    Seg,
    ride_segment,
    rides_cfg,
    sitting_on_wall,
    track,
)


def _assemble(*tracks: list[Obs], duration_s: float = 600.0, **cfg: float):  # type: ignore[no-untyped-def]
    c = rides_cfg(**cfg)
    evidence = {t[0].track_id: classify(t, ZONE, c) for t in tracks}
    trs = [r for evs in evidence.values() for r in track_rides(evs, c)[1]]
    return assemble(trs, evidence, cfg=c, fps=SOURCE_FPS, duration_s=duration_s)


def test_acid_drop_links_side_wall_track_to_new_on_wave_track() -> None:
    sitter = track(1, 0.0, sitting_on_wall(5.0))
    rider = track(2, sitter[-1].t + 0.4, ride_segment(12.0, 0.06, 0.7, v=0.32))
    rides, short = _assemble(sitter, rider)
    assert len(rides) == 1 and not short
    r = rides[0]
    assert r.start_kind == "acid_drop"
    assert r.start_s == pytest.approx(sitter[-1].t)
    assert r.track_ids == [1, 2]


def test_no_link_when_new_track_appears_far_away() -> None:
    sitter = track(1, 0.0, sitting_on_wall(5.0))
    rider = track(2, sitter[-1].t + 0.4, ride_segment(12.0, 0.4, 0.9, v=0.8))
    rides, _ = _assemble(sitter, rider)
    assert rides[0].start_kind != "acid_drop"
    assert rides[0].track_ids == [2]


def test_frame_edge_exit_and_return_within_grace_is_one_ride() -> None:
    a = track(3, 0.0, ride_segment(8.0, 0.3, 0.9), Seg(0.4, 0.9, 0.92, edge="right"))
    b = track(4, a[-1].t + 1.5, Seg(0.4, 0.92, 0.9, edge="right"), ride_segment(6.0, 0.9, 0.4))
    rides, _ = _assemble(a, b)
    assert len(rides) == 1
    assert rides[0].track_ids == [3, 4]
    assert rides[0].flags.truncated


def test_frame_edge_return_after_grace_is_two_rides() -> None:
    a = track(3, 0.0, ride_segment(11.0, 0.3, 0.9), Seg(0.4, 0.9, 0.92, edge="right"))
    b = track(4, a[-1].t + 2.5, Seg(0.4, 0.92, 0.9, edge="right"), ride_segment(11.0, 0.9, 0.4))
    rides, _ = _assemble(a, b)
    assert len(rides) == 2


def test_identity_switch_mid_ride_is_one_ride() -> None:
    """20240924 28:04: the tracker hands the rider to another track id at the same spot."""
    a = track(5, 0.0, ride_segment(7.0, 0.7, 0.06))
    b = track(6, a[-1].t + 0.2, ride_segment(12.0, 0.08, 0.8))
    rides, short = _assemble(a, b)
    assert len(rides) == 1 and not short
    assert rides[0].start_s == pytest.approx(0.0)
    assert rides[0].track_ids == [5, 6]


def test_turn_at_side_wall_with_new_track_is_one_ride() -> None:
    """20240924 28:47: the rider turns at wall b, the tracker loses them and picks them up again."""
    a = track(5, 0.0, ride_segment(12.0, 0.3, 0.95))
    b = track(6, a[-1].t + 2.0, ride_segment(6.0, 0.96, 0.4))
    rides, short = _assemble(a, b)
    assert len(rides) == 1 and not short
    assert rides[0].end_s == pytest.approx(b[-1].t)
    assert rides[0].track_ids == [5, 6]


def test_next_rider_from_same_wall_later_is_a_new_ride() -> None:
    a = track(5, 0.0, ride_segment(12.0, 0.3, 0.95))
    b = track(6, a[-1].t + 6.0, ride_segment(12.0, 0.96, 0.4))
    rides, _ = _assemble(a, b)
    assert len(rides) == 2


def test_new_ride_far_away_is_not_a_continuation() -> None:
    a = track(5, 0.0, ride_segment(12.0, 0.7, 0.1))
    b = track(6, a[-1].t + 0.2, ride_segment(12.0, 0.8, 0.3, v=0.9))
    rides, _ = _assemble(a, b)
    assert len(rides) == 2


def test_ride_shorter_than_minimum_is_a_short_attempt() -> None:
    rides, short = _assemble(track(1, 0.0, ride_segment(6.0)))
    assert rides == []
    assert len(short) == 1


def test_minimum_length_is_configurable() -> None:
    rides, short = _assemble(track(1, 0.0, ride_segment(6.0)), min_length_s=5.0)
    assert len(rides) == 1 and not short


def test_lesson_flag_when_instructor_stands_in_zone() -> None:
    beginner = track(1, 0.0, ride_segment(15.0, 0.3, 0.8))
    instructor = track(2, 0.0, Seg(15.0, 0.35, 0.8, v=0.45, board=False))
    rides, _ = _assemble(beginner, instructor)
    assert len(rides) == 1
    assert rides[0].track_ids == [1]
    assert rides[0].flags.lesson


def test_group_lesson_is_one_ride() -> None:
    """User decision 2026-10-15: a lesson (beginners overlapping on the wave) is one ride."""
    first = track(1, 0.0, ride_segment(15.0, 0.2, 0.7))
    second = track(2, 5.0, ride_segment(20.0, 0.1, 0.9, v=0.5))
    third = track(3, 19.0, ride_segment(12.0, 0.3, 0.8, v=0.55))
    rides, _ = _assemble(first, second, third)
    assert len(rides) == 1
    r = rides[0]
    assert r.flags.lesson
    assert r.start_s == pytest.approx(0.0)
    assert r.end_s == pytest.approx(third[-1].t)
    assert sorted(r.track_ids) == [1, 2, 3]


def test_changeover_overlap_gives_two_rides() -> None:
    first = track(1, 0.0, ride_segment(20.0, 0.2, 0.8))
    second = track(2, 19.0, ride_segment(15.0, 0.1, 0.6))
    rides, _ = _assemble(first, second)
    assert len(rides) == 2
    assert rides[0].end_s > rides[1].start_s
    assert not any(r.flags.lesson for r in rides)  # a 1 s overlap is a changeover, not a lesson


def test_padding_frames_and_ids() -> None:
    rides, _ = _assemble(track(1, 100.0, ride_segment(12.0)))
    r = rides[0]
    assert r.clip_start_s == pytest.approx(r.start_s - 1.5)
    assert r.clip_end_s == pytest.approx(r.end_s + 2.0)
    assert r.start_frame == round(r.start_s * SOURCE_FPS)
    assert r.ride_id == f"r{r.start_frame:06d}"
    assert 0 < r.confidence <= 1
    assert r.state_timeline[0][1] == "on_wave"


def test_padding_is_clamped_to_video() -> None:
    rides, _ = _assemble(track(1, 0.4, ride_segment(12.0)), duration_s=13.0)
    assert rides[0].clip_start_s == 0.0
    assert rides[0].clip_end_s == 13.0
