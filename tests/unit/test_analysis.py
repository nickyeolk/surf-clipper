"""004 T007/T008: signals are body-relative; events and endings on synthetic riders."""

import numpy as np
import pytest

from surfclip.analysis.events import ending, find_events, shares
from surfclip.analysis.pose import Keypoints, crop_box, interpolate_boxes, pick_rider
from surfclip.analysis.signals import compression, raw_compression, rotation
from surfclip.config import load_config
from surfclip.rides.evidence import Obs

CFG = load_config().analysis_pose
FPS = CFG.fps


def _skeleton(crouch: float, facing: float = 1.0, x: float = 0.0, scale: float = 1.0) -> np.ndarray:
    """17 COCO keypoints of a side-ish standing rider; crouch 0 = straight, 1 = deep."""
    kp = np.zeros((17, 3))
    kp[:, 2] = 0.9
    leg = 1.0 - 0.45 * crouch  # hip-ankle distance shrinks as the knees bend
    pts = {
        5: (-0.2 * facing, 0.0), 6: (0.2 * facing, 0.0),  # shoulders
        11: (-0.12, 0.6), 12: (0.12, 0.6),  # hips
        13: (-0.15 - 0.3 * crouch, 0.6 + leg / 2), 14: (0.15 + 0.3 * crouch, 0.6 + leg / 2),
        15: (-0.15, 0.6 + leg), 16: (0.15, 0.6 + leg),
    }  # fmt: skip
    for k, (px, py) in pts.items():
        kp[k, :2] = (100 + x + px * 100 * scale, 100 + py * 100 * scale)
    return kp


def _keypoints(crouches: list[float], **kw: float) -> Keypoints:
    n = len(crouches)
    return Keypoints(
        t=np.arange(n) / FPS,
        box=np.zeros((n, 4)),
        kp=np.stack([_skeleton(c, **kw) for c in crouches]),
        other_iou=np.zeros(n),
    )


@pytest.mark.parametrize("signal", ["leg_torso", "leg_straightness"])
def test_compression_ignores_zoom_and_mirroring(signal: str) -> None:
    near = _keypoints([0.0, 0.5, 1.0], scale=3.0)
    far = _keypoints([0.0, 0.5, 1.0], scale=0.5)
    mirrored = _keypoints([0.0, 0.5, 1.0], facing=-1.0)
    a, b, c = (raw_compression(k, signal) for k in (near, far, mirrored))
    assert np.allclose(a, b) and np.allclose(a, c)
    assert a[0] > a[1] > a[2]  # deeper crouch = lower


def test_unclear_frames_are_left_out_and_short_gaps_bridged() -> None:
    crouch = [0.2 + 0.3 * np.sin(i / 4) for i in range(60)]
    kp = _keypoints(crouch)
    kp.kp[10, 15, 2] = 0.05  # ankle not seen for one frame
    kp.other_iou[40:60] = 0.8  # someone else in the crop for the last 20 frames
    comp = compression(kp, CFG)
    assert np.isfinite(comp[10])  # 1-frame gap bridged
    assert np.isnan(comp[45:]).all()
    assert np.nanmedian(comp) == pytest.approx(1.0, abs=0.02)


def test_turns_need_a_direction_change_pumps_do_not() -> None:
    n = int(12 * FPS)
    t = np.arange(n) / FPS
    comp = 1.0 - 0.35 * np.exp(-((t - 3) ** 2) / 0.05) - 0.35 * np.exp(-((t - 8) ** 2) / 0.05)
    lat = np.where(t < 3, 0.3 + 0.1 * t, 0.6 - 0.1 * (t - 3))  # reverses at 3 s only
    lat = np.where(t > 6, lat[int(6 * FPS)] - 0.0 * (t - 6), lat)
    rot = np.zeros(n)
    turns, pumps = find_events(comp, lat, rot, CFG, t0=100.0)
    assert [round(e.t) for e in turns] == [103]
    assert [round(e.t) for e in pumps] == [108]
    s = shares(n, np.zeros(n, dtype=bool), turns, pumps, FPS, 100.0)
    assert s.turning > 0 and s.pumping > 0
    assert s.turning + s.pumping + s.trimming + s.unclear == pytest.approx(1.0, abs=0.01)


def test_rotation_flip_counts_as_a_turn_without_pool_position() -> None:
    n = int(6 * FPS)
    t = np.arange(n) / FPS
    comp = 1.0 - 0.35 * np.exp(-((t - 3) ** 2) / 0.05)
    rot = np.tanh((t - 3) * 3)  # shoulders swing from one side to the other
    turns, pumps = find_events(comp, np.full(n, np.nan), rot, CFG, t0=0.0)
    assert len(turns) == 1 and not pumps


def test_endings() -> None:
    k = int(CFG.fall_window_s * FPS)
    upright = np.ones(k)
    clear = np.zeros(k, dtype=bool)
    assert ending(upright * 0.5, np.full(k, np.nan), np.full(k, 10.0), clear, CFG) == "fall"
    assert ending(upright, np.full(k, np.nan), np.full(k, 70.0), clear, CFG) == "fall"
    assert ending(upright, np.full(k, np.nan), np.full(k, 10.0), clear, CFG) == "exit"
    assert ending(upright * 0.8, np.full(k, 0.98), np.full(k, 35.0), clear, CFG) == "exit"
    assert ending(upright, np.full(k, np.nan), np.full(k, 10.0), ~clear, CFG) == "unclear"


def test_rotation_sign_follows_facing() -> None:
    assert (
        rotation(_keypoints([0.0], facing=1.0))[0] < 0 < rotation(_keypoints([0.0], facing=-1.0))[0]
    )


def test_crop_and_rider_picking() -> None:
    track = [
        Obs(t=0.0, frame=0, track_id=1, box=(0, 0, 10, 20), feet=(5, 20), score=0.9,
            board=True, stance="standing", edge=None),  # type: ignore[arg-type]
        Obs(t=1.0, frame=5, track_id=1, box=(10, 0, 20, 20), feet=(15, 20), score=0.9,
            board=True, stance="standing", edge=None),  # type: ignore[arg-type]
    ]  # fmt: skip
    boxes = interpolate_boxes(track, np.array([0.5, 2.0]))
    assert boxes[0].tolist() == [5, 0, 15, 20] and boxes[1].tolist() == [10, 0, 20, 20]
    assert crop_box(np.array([100.0, 100, 150, 200]), 0.3, (160, 400)) == (70, 70, 160, 230)
    assert pick_rider(np.array([[10.0, 10], [50, 60]]), (100, 120)) == 1
    assert pick_rider(np.zeros((0, 2)), (100, 120)) is None
