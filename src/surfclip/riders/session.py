"""Riders for one session: describe every ride, group, assign (the ``riders`` stage).

Appearance lives in ``appearance.parquet`` in the session folder only (constitution I). A ride's
descriptor is cached under its span and track ids, so re-runs describe only new or changed
rides; the session's colour correction is cached with it so old and new descriptors agree.
Detected rides the user deleted are described too (cheap, and needed to score grouping on the
detected rides), but only the session's current rides are grouped.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

from surfclip.config import RidersConfig
from surfclip.riders.assign import assign_confidence, queue
from surfclip.riders.cluster import Constraints, group_rides
from surfclip.riders.crops import read_frames, ride_crops, ride_moments
from surfclip.riders.describe import (
    RideDescriptor,
    colour_descriptor,
    colour_distance,
    grey_world_gains,
    hue_weight,
    ride_descriptor,
)
from surfclip.riders.stills import save_still
from surfclip.rides.evidence import Obs
from surfclip.store.schemas import (
    Ride,
    RideAssignment,
    RiderGroup,
    Riders,
    RiderStill,
    SourceInfo,
)
from surfclip.store.session import SessionStore

pa: Any = _pyarrow
pq: Any = _parquet
FloatArray = NDArray[np.float64]

APPEARANCE_FILE = "appearance.parquet"
RIDERS_FILE = "riders.json"
BACKGROUND_SAMPLES = 20


def ride_key(ride: Ride) -> str:
    """Cache key for a ride's appearance: its span and track ids."""
    tracks = ",".join(str(t) for t in sorted(ride.track_ids))
    return f"{ride.start_s:.3f}-{ride.end_s:.3f}:{tracks}"


@dataclass(frozen=True)
class Described:
    desc: RideDescriptor
    best_t: float | None  # time of the sharpest crop (for stills)


@dataclass(frozen=True)
class Appearance:
    gains: FloatArray
    rides: dict[str, Described]  # by ride_key

    @property
    def hue_weight(self) -> float:
        return hue_weight(self.gains)

    def distance(self, a: FloatArray, b: FloatArray) -> float:
        return colour_distance(a, b, self.hue_weight)


def load_appearance(store: SessionStore) -> Appearance | None:
    path = store.path(APPEARANCE_FILE)
    if not path.exists():
        return None
    table = pq.read_table(path)
    meta: dict[bytes, bytes] = table.schema.metadata or {}
    gains = np.array(json.loads(meta.get(b"gains", b"[1,1,1]")), dtype=np.float64)
    rows = table.to_pylist()
    rides: dict[str, Described] = {}
    for r in rows:
        if r["kind"] != "ride":
            continue
        rides[r["span"]] = Described(
            RideDescriptor(
                r["ride_id"],
                np.array(r["colour"], dtype=np.float64),
                int(r["crops"]),
                bool(r["low_evidence"]),
                float(r["box_height_px"]),
            ),
            r["t_s"],
        )
    return Appearance(gains, rides)


def _save(store: SessionStore, app: Appearance, crop_rows: list[dict[str, Any]]) -> None:
    rows = [
        {
            "ride_id": d.desc.ride_id,
            "span": key,
            "kind": "ride",
            "t_s": d.best_t,
            "track_id": None,
            "sharpness": None,
            "box_height_px": d.desc.clarity,
            "crops": d.desc.crops,
            "low_evidence": d.desc.low_evidence,
            "colour": d.desc.vector.tolist(),
            "embedding": None,
        }
        for key, d in app.rides.items()
    ]
    table = pa.Table.from_pylist(rows + crop_rows)
    table = table.replace_schema_metadata(
        {"gains": json.dumps(app.gains.tolist()), "schema_version": "1.0.0"}
    )
    tmp = store.path(APPEARANCE_FILE + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(store.path(APPEARANCE_FILE))


def describe_rides(
    store: SessionStore, rides: Sequence[Ride], obs: Sequence[Obs], cfg: RidersConfig
) -> Appearance:
    """Descriptors for the given rides, describing only those not cached yet."""
    from surfclip.zone.editing import display_size

    cached = load_appearance(store)
    todo = [r for r in rides if cached is None or ride_key(r) not in cached.rides]
    if cached is not None and not todo:
        return cached
    info = store.read_model("probe.json", SourceInfo)
    review = store.path("review.mp4")
    by_track: dict[int, list[Obs]] = defaultdict(list)
    for o in obs:
        by_track[o.track_id].append(o)
    moments = {r.ride_id: ride_moments(r, by_track, cfg.crops_per_ride) for r in todo}
    times = [m.t_s for ms in moments.values() for m in ms]
    background: list[float] = []
    if cached is None:
        background = list(np.linspace(0, info.duration_s, BACKGROUND_SAMPLES + 2)[1:-1])
    frames = read_frames(review, times + background)
    gains = (
        cached.gains
        if cached is not None
        else grey_world_gains([frames[t] for t in background if t in frames])
    )
    width, _ = display_size(info)
    any_frame = next(iter(frames.values()), None)
    scale = any_frame.shape[1] / width if any_frame is not None else 1.0
    out = dict(cached.rides) if cached is not None else {}
    crop_rows: list[dict[str, Any]] = []
    for ride in todo:
        crops = ride_crops(
            moments[ride.ride_id], frames, scale,
            keep=cfg.keep_sharpest, min_height_px=cfg.min_crop_height_px,
        )  # fmt: skip
        vectors = [colour_descriptor(c.image, gains) for c in crops]
        desc = ride_descriptor(
            ride.ride_id, vectors, [c.box_height_px for c in crops], cfg.min_crops
        )
        out[ride_key(ride)] = Described(desc, crops[0].moment.t_s if crops else None)
        if crops:  # the sharpest crop doubles as the ride's still in the UI
            save_still(store, ride.ride_id, crops[0].moment.t_s, crops[0].image)
        crop_rows += [
            {
                "ride_id": ride.ride_id,
                "span": ride_key(ride),
                "kind": "crop",
                "t_s": c.moment.t_s,
                "track_id": c.moment.track_id,
                "sharpness": c.sharpness,
                "box_height_px": c.box_height_px,
                "crops": None,
                "low_evidence": None,
                "colour": v.tolist(),
                "embedding": None,
            }
            for c, v in zip(crops, vectors, strict=True)
        ]
    app = Appearance(gains, out)
    _save(store, app, crop_rows)
    return app


def build_riders(
    session_id: str,
    rides: Sequence[Ride],
    app: Appearance,
    cfg: RidersConfig,
    *,
    overlap_allowed_s: float,
    constraints: Constraints | None = None,
    names: dict[str, str] | None = None,  # ride id -> name: a group holding it takes the name
    ignored: set[str] | None = None,  # ride ids: a group holding one is ignored
) -> Riders:
    """Group the rides and assign confidences (pure: no files)."""
    names = names or {}
    ignored = ignored or set()
    fixed = set((constraints or Constraints()).fixed)
    # Lesson-flagged rides are grouped like any other: 001's lesson flag also fires when someone
    # stands in the pool during an ordinary ride (20240924: 24 of 79 rides), so it cannot decide
    # who rode. A merged group lesson still lands in some rider's group, tagged "lesson".
    lesson: list[Ride] = []
    described = {
        r.ride_id: app.rides[ride_key(r)]
        for r in rides
        if ride_key(r) in app.rides and app.rides[ride_key(r)].desc.crops > 0
    }
    vectors = {rid: d.desc.vector for rid, d in described.items()}
    spans = {r.ride_id: (r.start_s, r.end_s) for r in rides}
    groups = group_rides(
        vectors, spans, app.distance,
        threshold=cfg.cluster_threshold, overlap_allowed_s=overlap_allowed_s,
        constraints=constraints,
    )  # fmt: skip
    low = {rid for rid, d in described.items() if d.desc.low_evidence}
    assigned = assign_confidence(groups, vectors, app.distance, low) if groups else []

    riders: list[RiderGroup] = []
    named_groups: set[int] = set()
    for gi, group in enumerate(groups):
        name = next((names[r] for r in group if r in names), None)
        if name is not None:
            named_groups.add(gi)
        by_clarity = sorted(group, key=lambda r: described[r].desc.clarity, reverse=True)
        stills = [
            RiderStill(ride_id=r, t_s=t)
            for r in by_clarity[: cfg.stills]
            if (t := described[r].best_t) is not None
        ]
        riders.append(
            RiderGroup(
                rider_id=f"g{gi + 1:02d}",
                name=name,
                ignored=any(r in ignored for r in group),
                ride_ids=group,
                example_ride_id=by_clarity[0],
                stills=stills,
            )
        )
    if lesson:
        riders.append(
            RiderGroup(
                rider_id="lesson",
                kind="lesson",
                ride_ids=[r.ride_id for r in lesson],
                example_ride_id=lesson[0].ride_id,
            )
        )
    queued = set(queue(assigned, named_groups, cfg.queue_below, fixed))
    assignments = [
        RideAssignment(
            ride_id=a.ride_id,
            rider_id=riders[a.group].rider_id,
            confidence=a.confidence,
            confirmed=a.ride_id in fixed,
            queued=a.ride_id in queued,
            low_evidence=a.ride_id in low,
        )
        for a in assigned
    ]
    assignments += [
        RideAssignment(ride_id=r.ride_id, rider_id="lesson", confidence=1.0) for r in lesson
    ]
    assignments += [  # no usable crops of a person: no rider until the user says so
        RideAssignment(ride_id=r.ride_id, rider_id=None, confidence=0.0, low_evidence=True)
        for r in rides
        if r.ride_id not in described
    ]
    return Riders(
        session_id=session_id, descriptor="colour", riders=riders, assignments=assignments
    )
