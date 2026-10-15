"""Zone support for the zone editor (US2): stills, rider-feet hints, the proposed zone, save +
re-run.

Library code called by the API, so the backend stays a thin layer (constitution X).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from surfclip.config import DEFAULT_CONFIG_PATH, load_config
from surfclip.edits.log import append_edit
from surfclip.media.decode import output_size
from surfclip.rides.evidence import to_source_pixels
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import EditTarget, Point, Rides, SourceInfo, Zone
from surfclip.store.session import SessionStore
from surfclip.zone.geometry import PoolMapping
from surfclip.zone.propose import ZoneProposal, propose_zone

_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


def display_size(info: SourceInfo) -> tuple[int, int]:
    """Full-resolution size after rotation: the pixel space zones are drawn in."""
    return output_size(info, max(info.width, info.height))


def keyframe(store: SessionStore, t: float) -> Path:
    """A full-resolution still at time t (cached), tone-mapped if the source is HDR."""
    info = store.read_model("probe.json", SourceInfo)
    t = max(0.0, min(info.duration_s - 0.5, t))
    out = store.path(f"keyframes/t{int(t)}.jpg")
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = [_TONEMAP] if info.hdr_format != "none" else []
    vf.append("format=yuvj420p")
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            info.path,
            "-frames:v",
            "1",
            "-vf",
            ",".join(vf),
            "-q:v",
            "3",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def rider_feet(store: SessionStore, limit: int = 4000) -> list[Point]:
    """Feet of people standing on boards, in source pixels: where riding happens."""
    tf = store.path("tracks.parquet")
    if not tf.exists():
        return []
    info = store.read_model("probe.json", SourceInfo)
    meta = read_meta(tf)
    w, h = display_size(info)
    obs = [
        o
        for o in to_source_pixels(read_observations(tf), w / meta.width, h / meta.height)
        if o.board and o.stance in ("standing", "crouched")
    ]
    if len(obs) > limit:
        keep: list[int] = sorted(
            int(i) for i in np.random.default_rng(0).choice(len(obs), limit, replace=False)
        )
        obs = [obs[i] for i in keep]
    return [(round(o.feet[0], 1), round(o.feet[1], 1)) for o in obs]


PROPOSAL_FILE = "zone_proposal.json"


def zone_proposal(store: SessionStore) -> ZoneProposal | None:
    """The zone proposed from riders' movement (cached until tracks.parquet changes)."""
    from surfclip.stages import session_observations  # stages import heavy media modules

    tf = store.path("tracks.parquet")
    if not tf.exists():
        return None
    key = f"{tf.stat().st_mtime_ns}:{tf.stat().st_size}"
    cached = store.path(PROPOSAL_FILE)
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        if data.get("tracks") == key:
            return ZoneProposal.model_validate(data["proposal"])
    w, h = display_size(store.read_model("probe.json", SourceInfo))
    proposal = propose_zone(session_observations(store), w, h)
    cached.write_text(
        json.dumps({"tracks": key, "proposal": proposal.model_dump(mode="json")}, indent=2),
        encoding="utf-8",
    )
    return proposal


def confirm_zone(store: SessionStore, zone: Zone, config_path: Path = DEFAULT_CONFIG_PATH) -> Rides:
    """Validate and confirm a zone, then re-run the (cached) pipeline up to rides."""
    from surfclip.stages import default_pipeline  # stages import heavy media modules

    PoolMapping.from_corners(zone.corners)  # raises GeometryError for crossed/collinear corners
    proposal = zone_proposal(store)
    accepted = proposal is not None and proposal.zone.corners == zone.corners
    zone = zone.model_copy(update={"origin": "user"})
    append_edit(
        store,
        "confirm_zone",
        EditTarget(epoch_id=zone.epoch_id),
        {"zone": zone.model_dump(mode="json"), "how": "accepted" if accepted else "edited"},
    )
    cfg = load_config(config_path, store.session.config_overrides)
    default_pipeline().run(store, cfg, until="rides")
    return store.read_model("rides.json", Rides)
