"""T034: zone proposal from riders' movement, on synthetic cameras with known geometry."""

import numpy as np
import pytest

from surfclip.rides.evidence import Obs
from surfclip.zone.geometry import PoolMapping
from surfclip.zone.propose import propose_zone

W, H = 1920, 1080
F = np.hypot(W, H) * 26.0 / 43.27  # the lens the proposal assumes
RIDER = 0.12  # rider height in pool units


def camera(eye: tuple[float, float, float], target: tuple[float, float, float]) -> np.ndarray:
    """3x4 projection for a camera at ``eye`` looking at ``target`` (pool u, v, up)."""
    e, t = np.array(eye), np.array(target)
    fwd = (t - e) / np.linalg.norm(t - e)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    r = np.vstack([right, down, fwd])
    k = np.array([[F, 0, W / 2], [0, F, H / 2], [0, 0, 1]])
    return k @ np.hstack([r, (-r @ e)[:, None]])


def project(p: np.ndarray, u: float, v: float, z: float = 0.0) -> tuple[float, float, float]:
    x = p @ np.array([u, v, z, 1.0])
    return x[0] / x[2], x[1] / x[2], x[2]


def riders(p: np.ndarray, n_tracks: int = 60, seed: int = 0) -> tuple[list[Obs], list[tuple]]:
    """Riders crossing the wave face (v 0.6-0.9) from wall to wall and back."""
    rng = np.random.default_rng(seed)
    obs: list[Obs] = []
    truth: list[tuple[float, float, float, float]] = []  # x, y, u, v
    for tid in range(n_tracks):
        v = rng.uniform(0.6, 0.9)
        u0, u1 = (0.02, 0.98) if tid % 2 else (0.98, 0.02)
        for i, t in enumerate(np.arange(0, 12, 0.2)):
            u = u0 + (u1 - u0) * t / 12 + rng.normal(0, 0.005)
            vv = v + 0.03 * np.sin(t) + rng.normal(0, 0.005)
            x, y, depth = project(p, u, vv)
            if not (0 <= x <= W and 0 <= y <= H):
                continue
            h = F * RIDER / depth * rng.uniform(0.95, 1.05)
            stance = "standing" if i % 4 else "crouched"
            if stance == "crouched":
                h *= 0.8
            obs.append(
                Obs(
                    t=100 * tid + t,
                    frame=0,
                    track_id=tid,
                    box=(x - 0.2 * h, y - h, x + 0.2 * h, y),
                    feet=(x, y),
                    score=0.9,
                    board=True,
                    stance=stance,
                    edge="none",
                )  # type: ignore[arg-type]
            )
            truth.append((x, y, u, vv))
    return obs, truth


CAMERAS = {
    "head-on": ((0.5, 1.6, 0.35), (0.5, 0.6, 0.0)),
    "from the left": ((-0.4, 1.4, 0.35), (0.5, 0.6, 0.0)),
    "from the right": ((1.4, 1.4, 0.35), (0.5, 0.6, 0.0)),
}


@pytest.mark.parametrize("view", list(CAMERAS))
def test_proposal_recovers_pool_coordinates(view: str) -> None:
    p = camera(*CAMERAS[view])
    obs, truth = riders(p)
    prop = propose_zone(obs, W, H)
    assert not prop.unreliable, prop.notes
    pts = np.array([(x, y) for x, y, _, _ in truth])
    uv = PoolMapping.from_corners(prop.zone.corners).to_pool(pts)
    true_u = np.array([u for *_, u, _ in truth])
    true_v = np.array([v for *_, v in truth])
    # Walls are labelled in image order: compare mirror-invariantly.
    err_u = min(np.median(np.abs(uv[:, 0] - true_u)), np.median(np.abs(1 - uv[:, 0] - true_u)))
    assert err_u < 0.05
    # Back is back: further from the camera means smaller v. Depth is the weaker estimate: the
    # horizon from rider heights is ~40 px off even on this clean data (oblique: r ~0.7).
    assert np.corrcoef(uv[:, 1], true_v)[0, 1] > 0.6


def test_too_few_riders_is_unreliable() -> None:
    obs, _ = riders(camera(*CAMERAS["head-on"]), n_tracks=2)
    prop = propose_zone(obs, W, H)
    assert prop.unreliable and prop.confidence == 0.0
    assert "draw the zone" in prop.notes[0]


def test_standing_people_who_do_not_move_are_ignored() -> None:
    p = camera(*CAMERAS["head-on"])
    obs, _ = riders(p)
    x, y, depth = project(p, 1.3, 0.2)  # someone on the deck with a board, standing still
    h = F * RIDER / depth
    still = [
        Obs(
            t=float(i),
            frame=0,
            track_id=999,
            box=(x - 0.2 * h, y - h, x + 0.2 * h, y),
            feet=(x, y),
            score=0.9,
            board=True,
            stance="standing",
            edge="none",
        )
        for i in range(2000)
    ]
    assert propose_zone(obs + still, W, H).zone == propose_zone(obs, W, H).zone
