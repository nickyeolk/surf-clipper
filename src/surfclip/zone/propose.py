"""Propose a zone from where riders go (FR-005, T036).

The proposal uses only the tracked people, not the picture:

1. **Riding feet**: feet of people on a board, standing or crouched, moving at least
   ``min_speed_heights`` rider heights per second.
2. **Perspective**: on a flat surface, a person's apparent height is a linear function of image
   position (it is proportional to 1/distance, which is linear in x and y for points on a
   plane). Fitting box height = a*x + b*y + c gives the pool plane's horizon; dividing image
   positions by the fitted height undoes the perspective up to an affine map, so in these
   *rectified* positions parallel walls are parallel and riders have constant size.
3. **Wave axis**: riders travel along the wave, so their main direction of motion (rectified) is
   the pool's ``u`` axis; the perpendicular is depth. The back is where riders look smaller.
4. **Side walls**: riders reach the side walls (they stall, turn and drop in there), so the 1st
   and 99th percentile of position along the wave (median over a few depth bins) mark the walls,
   perpendicular to the riding direction. A wall whose riders pile up against the frame edge is
   out of shot: the frame edge stands in for it (rides leaving there are handled as frame-edge
   exits) and confidence drops.
5. **Depth**: the 5th-95th percentile of riding depth is the wave face. It is placed at pool
   depth ``FACE_V`` (where the hand-drawn zones put it), which fixes the back wall and the front
   edge. The rides stage estimates the face band itself, so the depth scale matters little.

Walls are labelled ``a`` and ``b`` in image order; pool coordinates are mirror-invariant. The
user reviews every proposal in the zone editor (accept, adjust or redraw).
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from surfclip.rides.evidence import Obs
from surfclip.store.schemas import Zone, ZoneCorners
from surfclip.zone.geometry import GeometryError, PoolMapping

FloatArray = NDArray[np.float64]

FACE_V = (0.6, 0.9)  # pool depth of the wave face's 5th and 95th percentile (hand zones)
MIN_POINTS = 300  # fewer riding feet than this: no reliable proposal
GOOD_POINTS = 3000  # full confidence from this many
WALL_PCT = 1.0  # percentile of position along the wave that marks a wall
DEPTH_PCT = 5.0
DEPTH_BINS = 4
BORDER_FRAC = 0.02  # feet this close to the frame border (share of frame size) are cut off
FOCAL_35MM = 26.0  # assumed lens (35 mm equivalent): phones' main camera
UNRELIABLE_BELOW = 0.4


class ZoneProposal(BaseModel):
    zone: Zone
    confidence: float
    unreliable: bool
    points: int
    walls_in_frame: dict[str, bool] = Field(default_factory=dict[str, bool])
    notes: list[str] = Field(default_factory=list[str])


@dataclass(frozen=True)
class RidingFeet:
    feet: FloatArray  # (n, 2) source pixels
    prev: FloatArray  # (n, 2) the same person's feet one observation earlier
    dt: FloatArray  # (n,) seconds between the two
    heights: FloatArray  # (n,) box height, pixels

    def __len__(self) -> int:
        return len(self.feet)


def riding_feet(
    observations: Sequence[Obs], min_speed_heights: float = 0.3, max_dt: float = 1.0
) -> RidingFeet:
    """Moving people on boards: feet now and one observation earlier."""
    by: dict[int, list[Obs]] = defaultdict(list)
    for o in observations:
        by[o.track_id].append(o)
    feet: list[tuple[float, float]] = []
    prev: list[tuple[float, float]] = []
    dts: list[float] = []
    heights: list[float] = []
    for obs in by.values():
        obs.sort(key=lambda o: o.t)
        for a, b in itertools.pairwise(obs):
            dt = b.t - a.t
            if not (0 < dt <= max_dt) or not b.board or b.stance not in ("standing", "crouched"):
                continue
            speed = np.hypot(b.feet[0] - a.feet[0], b.feet[1] - a.feet[1]) / dt
            if speed / max(b.box_height, 1.0) < min_speed_heights:
                continue
            feet.append(b.feet)
            prev.append(a.feet)
            dts.append(dt)
            heights.append(b.box_height)
    return RidingFeet(
        np.array(feet, dtype=np.float64).reshape(-1, 2),
        np.array(prev, dtype=np.float64).reshape(-1, 2),
        np.array(dts, dtype=np.float64),
        np.array(heights, dtype=np.float64),
    )


def _perspective(rf: RidingFeet) -> FloatArray:
    """Homography that undoes perspective up to an affine map: [[1,0,0],[0,1,0],[a,b,c]]/c from
    box height = a*x + b*y + c (least squares, then refit without the worst 10%)."""
    # All riders: the box-shape stance label does not separate crouching from standing
    # (scripts/stance_report.py, 2026-10-15); pose differences average out over thousands of
    # positions, and the refit drops the worst outliers.
    a_mat = np.hstack([rf.feet, np.ones((len(rf), 1))])
    coef = np.linalg.lstsq(a_mat, rf.heights, rcond=None)[0]
    resid = np.abs(a_mat @ coef - rf.heights)
    keep = resid <= np.percentile(resid, 90)
    coef = np.linalg.lstsq(a_mat[keep], rf.heights[keep], rcond=None)[0]
    pred = a_mat @ coef
    if np.percentile(pred, 1) <= 0:
        return np.eye(3)  # implausible fit (heights not positive over the riding area)
    # Scaled so w = predicted height / median height: ~1 over the riding area. (The horizon may
    # well cross the frame above the pool, so the height at the image origin can be negative.)
    return np.vstack([[1.0, 0, 0], [0, 1.0, 0], coef / np.median(pred)])


def _apply(h: FloatArray, pts: FloatArray) -> FloatArray:
    homog = np.hstack([pts, np.ones((len(pts), 1))]) @ h.T
    return homog[:, :2] / homog[:, 2:3]


def _axes(
    vel: FloatArray, depth_of: FloatArray, heights: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Unit vectors along the wave (e_u) and into depth, back to front (e_d)."""
    unit = vel / np.maximum(np.linalg.norm(vel, axis=1, keepdims=True), 1e-12)
    _, vecs = np.linalg.eigh(unit.T @ unit)
    e_u = vecs[:, -1]
    if e_u[0] < 0 or (abs(e_u[0]) < 1e-12 and e_u[1] < 0):
        e_u = -e_u
    e_d = np.array([-e_u[1], e_u[0]])
    # Riders look bigger nearer the camera: the front is where heights grow.
    if np.corrcoef(depth_of @ e_d, heights)[0, 1] < 0:
        e_d = -e_d
    return e_u, e_d


def _fallback(width: int, height: int, epoch_id: int, n: int, note: str) -> ZoneProposal:
    """A centred placeholder the user has to draw over."""
    corners = ZoneCorners(
        back_a=(0.2 * width, 0.3 * height),
        back_b=(0.8 * width, 0.3 * height),
        front_a=(0.1 * width, 0.9 * height),
        front_b=(0.9 * width, 0.9 * height),
    )
    zone = Zone(epoch_id=epoch_id, corners=corners, origin="proposed", proposal_confidence=0.0)
    return ZoneProposal(
        zone=zone,
        confidence=0.0,
        unreliable=True,
        points=n,
        walls_in_frame={"side_a": False, "side_b": False},
        notes=[note],
    )


def propose_zone(
    observations: Sequence[Obs], width: int, height: int, epoch_id: int = 0
) -> ZoneProposal:
    rf = riding_feet(observations)
    n = len(rf)
    if n < MIN_POINTS:
        return _fallback(width, height, epoch_id, n, f"only {n} riding positions: draw the zone")
    rect = _perspective(rf)
    pts = _apply(rect, rf.feet)
    vel = (pts - _apply(rect, rf.prev)) / rf.dt[:, None]
    e_u, e_d = _axes(vel, pts, rf.heights)
    s, d = pts @ e_u, pts @ e_d
    d_lo = float(np.percentile(d, DEPTH_PCT))
    d_hi = float(np.percentile(d, 100 - DEPTH_PCT))
    edges = [float(e) for e in np.linspace(d_lo, d_hi, DEPTH_BINS + 1)]
    lo: list[float] = []
    hi: list[float] = []
    for b0, b1 in itertools.pairwise(edges):
        sel: NDArray[np.bool_] = (d >= b0) & (d <= b1)
        if int(sel.sum()) < MIN_POINTS / DEPTH_BINS:
            continue
        lo.append(float(np.percentile(s[sel], WALL_PCT)))
        hi.append(float(np.percentile(s[sel], 100 - WALL_PCT)))
    if not lo:
        return _fallback(
            width, height, epoch_id, n, "riding positions too scattered: draw the zone"
        )
    s_a, s_b = float(np.median(lo)), float(np.median(hi))

    # Face quad: with a usable horizon, walls run to the vanishing point of the direction at
    # right angles to the wave; otherwise perpendicular to the riding direction (affine).
    face_img = _face_quad(rf, rect, e_u, width, height)
    if face_img is None:
        face_rect = np.array(
            [
                s_a * e_u + d_lo * e_d,
                s_b * e_u + d_lo * e_d,
                s_b * e_u + d_hi * e_d,
                s_a * e_u + d_hi * e_d,
            ]
        )
        face_img = _apply(np.linalg.inv(rect), face_rect)
        s_img = s
    else:
        s_img = _along_wave(rf.feet, face_img)

    # Is each wall in shot? Out of shot, riders' extreme feet hug the frame border.
    margin = BORDER_FRAC * max(width, height)
    x, y = rf.feet[:, 0], rf.feet[:, 1]
    at_border: NDArray[np.bool_] = (
        np.minimum(np.minimum(x, width - x), np.minimum(y, height - y)) < margin
    )
    in_frame = {
        "side_a": bool(np.mean(at_border[s_img <= np.percentile(s_img, 3)]) < 0.5),
        "side_b": bool(np.mean(at_border[s_img >= np.percentile(s_img, 97)]) < 0.5),
    }

    try:
        face_map = PoolMapping.from_corners(
            ZoneCorners(
                back_a=_pt(face_img[0]),
                back_b=_pt(face_img[1]),
                front_b=_pt(face_img[2]),
                front_a=_pt(face_img[3]),
            )
        )
    except GeometryError as exc:
        return _fallback(width, height, epoch_id, n, f"no consistent wave direction ({exc})")
    notes: list[str] = []
    zone: Zone | None = None
    for v0, v1 in (FACE_V, (0.3, 0.9), (0.0, 1.0)):  # less extrapolation if the first folds
        scale = np.array([[1.0, 0, 0], [0, v1 - v0, v0], [0, 0, 1.0]])
        to_pool = scale @ face_map.image_to_pool
        corners = _apply(np.linalg.inv(to_pool), np.array([(0.0, 0.0), (1, 0), (1, 1), (0, 1)]))
        w = np.hstack([corners, np.ones((4, 1))]) @ to_pool[2]
        if np.all(np.isfinite(corners)) and np.all(np.sign(w) == np.sign(w[0])):
            zone = Zone(
                epoch_id=epoch_id,
                corners=ZoneCorners(
                    back_a=_pt(corners[0]),
                    back_b=_pt(corners[1]),
                    front_b=_pt(corners[2]),
                    front_a=_pt(corners[3]),
                ),
                origin="proposed",
            )
            if (v0, v1) != FACE_V:
                notes.append("strong perspective: back wall placed closer than usual")
            break
    if zone is None:
        return _fallback(width, height, epoch_id, n, "perspective too strong: draw the zone")

    confidence = min(1.0, n / GOOD_POINTS)
    for wall, seen in in_frame.items():
        if not seen:
            confidence *= 0.6
            notes.append(f"{wall.replace('_', ' ')} is out of shot: set to the frame edge")
    confidence = round(confidence, 2)
    zone = zone.model_copy(update={"proposal_confidence": confidence})
    return ZoneProposal(
        zone=zone,
        confidence=confidence,
        unreliable=confidence < UNRELIABLE_BELOW,
        points=n,
        walls_in_frame=in_frame,
        notes=notes,
    )


def _cross(a: FloatArray, b: FloatArray) -> FloatArray:
    return np.asarray(np.cross(a, b), dtype=np.float64)


def _h(p: FloatArray) -> FloatArray:
    return np.array([p[0], p[1], 1.0])


def _dehom(p: FloatArray) -> FloatArray:
    return p[:2] / p[2]


def _focal(width: int, height: int) -> float:
    """Focal length in pixels for a typical phone main camera (26 mm full-frame equivalent)."""
    return float(np.hypot(width, height)) * FOCAL_35MM / 43.27  # 43.27 mm: 35 mm-frame diagonal


def _riding_vanishing_point(rf: RidingFeet, horizon: FloatArray) -> FloatArray:
    """The point on the horizon that riders' motion points towards (or away from) best.

    Searched directly: deriving it from the rectified motion amplified small horizon errors
    (synthetic oblique camera: x -4400 instead of -265)."""
    n = horizon[:2] / np.hypot(horizon[0], horizon[1])
    base = -horizon[2] / np.hypot(horizon[0], horizon[1]) * n  # closest horizon point to origin
    along = np.array([-n[1], n[0]])
    vel = (rf.feet - rf.prev) / rf.dt[:, None]
    unit = vel / np.maximum(np.linalg.norm(vel, axis=1, keepdims=True), 1e-9)
    centre = np.median(rf.feet, axis=0)
    scale = float(np.ptp(rf.feet[:, 0]) + np.ptp(rf.feet[:, 1]))

    def cost(theta: float) -> tuple[float, FloatArray]:
        if abs(np.cos(theta)) < 1e-9:  # at infinity: the horizon's own direction
            to_vp = np.broadcast_to(along, rf.feet.shape)
            vp = np.array([along[0], along[1], 0.0])
        else:
            t = np.tan(theta) * scale + (centre - base) @ along
            p = base + t * along
            to_vp = p - rf.feet
            vp = _h(p)
        to_vp = to_vp / np.maximum(np.linalg.norm(to_vp, axis=1, keepdims=True), 1e-9)
        sin = np.abs(unit[:, 0] * to_vp[:, 1] - unit[:, 1] * to_vp[:, 0])
        return float(np.median(sin)), vp

    thetas = np.linspace(-np.pi / 2, np.pi / 2, 721)
    best = min(thetas, key=lambda th: cost(float(th))[0])
    fine = np.linspace(best - np.pi / 720, best + np.pi / 720, 41)
    best = min(fine, key=lambda th: cost(float(th))[0])
    return cost(float(best))[1]


def _param(points: FloatArray, vp: FloatArray, ref: FloatArray) -> FloatArray:
    """Where the line from vanishing point ``vp`` through each point meets line ``ref``,
    as a coordinate along ``ref``."""
    hp = np.hstack([points, np.ones((len(points), 1))])
    lines = _cross(np.broadcast_to(vp, hp.shape), hp)
    meet = _cross(lines, np.broadcast_to(ref, lines.shape))
    xy = meet[:, :2] / meet[:, 2:3]
    direction = np.array([ref[1], -ref[0]]) / np.hypot(ref[0], ref[1])
    return xy @ direction


def _face_quad(
    rf: RidingFeet, rect: FloatArray, e_u: FloatArray, width: int, height: int
) -> FloatArray | None:
    """Image corners (back_a, back_b, front_b, front_a) of the riding area bounded by the side
    walls and the wave face's depth percentiles, using two vanishing points:

    * ``vp_u``, where lines along the wave meet: the riding direction, rectified, at infinity;
    * ``vp_d``, where the side walls meet: on the horizon, at right angles to ``vp_u`` for a
      camera with the principal point at the centre and focal length ``_focal``.
    """
    if np.allclose(rect, np.eye(3)):
        return None
    horizon = rect[2]
    vp_u = _riding_vanishing_point(rf, horizon)
    f = _focal(width, height)
    k = np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1.0]])
    k_inv = np.linalg.inv(k)
    omega = k_inv.T @ k_inv  # image of the absolute conic
    vp_d = _cross(omega @ vp_u, horizon)
    if np.allclose(vp_d, 0):
        return None
    mid = _h(np.median(rf.feet, axis=0))
    ref_u = _cross(vp_u, mid)  # a line along the wave through the riding area
    ref_d = _cross(vp_d, mid)  # a line in depth through it
    t_u = _param(rf.feet, vp_d, ref_u)
    t_d = _param(rf.feet, vp_u, ref_d)
    if not (np.all(np.isfinite(t_u)) and np.all(np.isfinite(t_d))):
        return None
    dir_u = np.array([ref_u[1], -ref_u[0]]) / np.hypot(ref_u[0], ref_u[1])
    dir_d = np.array([ref_d[1], -ref_d[0]]) / np.hypot(ref_d[0], ref_d[1])

    def on(ref: FloatArray, direction: FloatArray, t: float) -> FloatArray:
        # the point of line ``ref`` at coordinate t (closest point to the origin + t*direction)
        n = ref[:2] / np.hypot(ref[0], ref[1])
        base = -ref[2] / np.hypot(ref[0], ref[1]) * n
        return _h(base + (t - base @ direction) * direction)

    ua, ub = np.percentile(t_u, [WALL_PCT, 100 - WALL_PCT])
    d0, d1 = np.percentile(t_d, [DEPTH_PCT, 100 - DEPTH_PCT])
    wall_a = _cross(vp_d, on(ref_u, dir_u, float(ua)))
    wall_b = _cross(vp_d, on(ref_u, dir_u, float(ub)))
    edge0 = _cross(vp_u, on(ref_d, dir_d, float(d0)))
    edge1 = _cross(vp_u, on(ref_d, dir_d, float(d1)))
    # The back edge is where riders look smaller (lower predicted height).
    p0, p1 = _dehom(_cross(edge0, ref_d)), _dehom(_cross(edge1, ref_d))
    if horizon @ _h(p0) > horizon @ _h(p1):
        edge0, edge1 = edge1, edge0
    corners = [
        _cross(wall_a, edge0),
        _cross(wall_b, edge0),
        _cross(wall_b, edge1),
        _cross(wall_a, edge1),
    ]
    if any(abs(c[2]) < 1e-12 for c in corners):
        return None
    quad = np.array([_dehom(c) for c in corners])
    # Plausibility: the side walls converge towards the back (or are parallel), and the riding
    # area is wider along the wave than deep. Otherwise the height fit was misleading.
    if abs(vp_d[2]) > 1e-12:
        vd = _dehom(vp_d)
        for back, front in ((quad[0], quad[3]), (quad[1], quad[2])):
            if np.hypot(*(back - vd)) > np.hypot(*(front - vd)):
                return None
    if np.hypot(*(quad[1] - quad[0])) < np.hypot(*(quad[3] - quad[0])):
        return None
    return quad


def _along_wave(feet: FloatArray, face: FloatArray) -> FloatArray:
    """Position along the wave (pool u in the face quad's mapping) for each foot point."""
    mapping = PoolMapping.from_corners(
        ZoneCorners(
            back_a=_pt(face[0]), back_b=_pt(face[1]), front_b=_pt(face[2]), front_a=_pt(face[3])
        )
    )
    return mapping.to_pool(feet)[:, 0]


def _pt(p: FloatArray) -> tuple[float, float]:
    return (round(float(p[0]), 1), round(float(p[1]), 1))
