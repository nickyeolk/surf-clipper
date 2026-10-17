"""The analysis stage (004 T006): keypoints and measures for the rides of named riders.

Only rides of riders the user named are analysed (FR-010); keypoints of rides that are no
longer named are deleted. Keypoints are cached per ride by span and pose settings, measures by
span, rider and all analysis settings, so tuning a threshold never re-runs pose.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable

from surfclip.analysis.pose import (
    Keypoints,
    PoseModel,
    read_keypoints,
    ride_keypoints,
    write_keypoints,
)
from surfclip.config import Config
from surfclip.rides.evidence import Obs
from surfclip.store.schemas import (
    AnalysisFile,
    Ride,
    RideAnalysis,
    Riders,
    Rides,
    RideSummary,
    SourceInfo,
)
from surfclip.store.session import SessionStore

log = logging.getLogger(__name__)
ANALYSIS_FILE = "analysis.json"
KEYPOINT_DIR = "analysis"


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]


def code_version() -> str:
    from surfclip.stages import source_version

    return source_version("analysis/*.py")


def pose_version() -> str:
    from surfclip.stages import source_version

    return source_version("analysis/pose.py")


def named_riders(riders: Riders | None) -> dict[str, str]:
    """ride id -> the user-given name of its rider (named, not ignored riders only)."""
    if riders is None:
        return {}
    return {r: g.name for g in riders.riders if g.name and not g.ignored for r in g.ride_ids}


def keypoints_key(ride: Ride, cfg: Config) -> str:
    p = cfg.analysis_pose
    return _hash(
        round(ride.start_s, 3), round(ride.end_s, 3), p.fps, p.model, p.imgsz, p.crop_margin,
        pose_version(),
    )  # fmt: skip


def read_analysis(store: SessionStore) -> AnalysisFile | None:
    path = store.path(ANALYSIS_FILE)
    return store.read_model(ANALYSIS_FILE, AnalysisFile) if path.exists() else None


def measure(
    store: SessionStore, ride: Ride, kp: Keypoints, cfg: Config, rider: str, keys: tuple[str, str]
) -> RideAnalysis:
    """Signals and events of one ride (filled in by signals.py / events.py)."""
    from surfclip.analysis.events import analyse_ride

    return analyse_ride(store, ride, kp, cfg, rider=rider, cache_key=keys[0], keypoints_key=keys[1])


def analyse_session(
    store: SessionStore,
    cfg: Config,
    *,
    cpu: bool = False,
    only_rider: str | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> AnalysisFile:
    from surfclip.stages import session_observations

    rides = store.read_model("rides.json", Rides)
    riders = store.read_model("riders.json", Riders) if store.path("riders.json").exists() else None
    names = named_riders(riders)
    if only_rider is not None:
        names = {r: n for r, n in names.items() if n.lower() == only_rider.lower()}
    todo = sorted((r for r in rides.rides if r.ride_id in names), key=lambda r: r.start_s)
    old = read_analysis(store)
    previous = {a.ride_id: a for a in old.rides} if old else {}
    info = store.read_model("probe.json", SourceInfo)
    obs: list[Obs] | None = None
    model: PoseModel | None = None
    version = code_version()
    out: list[RideAnalysis] = []
    for i, ride in enumerate(todo):
        rider = names[ride.ride_id]
        kkey = keypoints_key(ride, cfg)
        key = _hash(
            kkey, rider, cfg.section_hash("analysis_pose"), cfg.section_hash("zone"), version
        )
        prev = previous.get(ride.ride_id)
        if prev is not None and prev.cache_key == key:
            out.append(prev)
            continue
        path = store.path(f"{KEYPOINT_DIR}/{ride.ride_id}.parquet")
        if prev is not None and prev.keypoints_key == kkey and path.exists():
            kp = read_keypoints(path)
        else:
            if obs is None:
                obs = session_observations(store)
            if model is None:
                model = PoseModel(cfg.analysis_pose, cpu=cpu)
            track = [
                o
                for o in obs
                if o.track_id in ride.track_ids and ride.start_s - 1 <= o.t <= ride.end_s + 1
            ]
            others = [
                o
                for o in obs
                if o.track_id not in ride.track_ids and ride.start_s <= o.t <= ride.end_s
            ]

            def step(f: float, i: int = i) -> None:
                if progress:
                    progress((i + f) / len(todo), f"pose: ride {i + 1} of {len(todo)}")

            kp = ride_keypoints(info, ride, track, others, model, progress=step)
            write_keypoints(path, kp)
        out.append(measure(store, ride, kp, cfg, rider, (key, kkey)))
        if progress:
            progress((i + 1) / len(todo), f"analysed ride {i + 1} of {len(todo)}")
    keep = {r.ride_id for r in todo} if only_rider is None else None
    kp_dir = store.path(KEYPOINT_DIR)
    if keep is not None and kp_dir.exists():  # body data only for named riders' rides (FR-010)
        for f in list(kp_dir.glob("*.parquet")):
            if f.stem not in keep:
                f.unlink()
    if keep is None and old is not None:  # one rider re-analysed: keep the others' results
        done = {a.ride_id for a in out}
        out += [a for a in old.rides if a.ride_id not in done]
    result = AnalysisFile(
        session_id=store.session.session_id,
        settings=cfg.analysis_pose.model_dump(mode="json"),
        rides=sorted(out, key=lambda a: a.span[0]),
    )
    store.write_model(ANALYSIS_FILE, result)
    return result


def empty_summary(ride: Ride) -> RideSummary:
    return RideSummary(length_s=round(ride.length_s, 3))


def with_user_edits(store: SessionStore, result: AnalysisFile) -> AnalysisFile:
    """Stars and trick tags from edits.json applied to the stage output (they are edits, so
    they follow rides by span like every user correction; the latest star edit wins)."""
    from surfclip.edits.apply import edit_spans, resolve_ride, undone_ids
    from surfclip.edits.log import read_edits
    from surfclip.store.schemas import AnalysisEvent

    rides = {r.ride_id: r for r in store.read_model("rides.json", Rides).rides}
    edits = read_edits(store)
    undone = undone_ids(edits)
    starred: dict[str, bool] = {}
    tricks: dict[str, list[AnalysisEvent]] = {}
    for e in edits.edits:
        if e.op not in ("ride_star", "trick_tag") or e.edit_id in undone or not e.target.ride_id:
            continue
        rid = resolve_ride(e.target.ride_id, edit_spans(e).get(e.target.ride_id), rides)
        if rid is None:
            continue
        if e.op == "ride_star":
            starred[rid] = bool(e.payload.get("starred", True))
        else:
            t, name = e.payload.get("t"), e.payload.get("name")
            if isinstance(t, int | float) and isinstance(name, str):
                tricks.setdefault(rid, []).append(
                    AnalysisEvent(t=float(t), name=name, by="user", edit_id=e.edit_id)
                )
    out = [
        a.model_copy(
            update={
                "starred": starred.get(a.ride_id, False),
                "tricks": sorted(tricks.get(a.ride_id, []), key=lambda ev: ev.t),
            }
        )
        for a in result.rides
    ]
    return result.model_copy(update={"rides": out})
