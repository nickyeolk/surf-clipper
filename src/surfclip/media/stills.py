"""Stills: one source frame at full resolution, saved as an SDR JPEG (003 FR-004, research R4).

The requested time is snapped to the source's frame grid and the still is named by ride and
frame, so saving the same frame twice returns the existing file. HDR sources are tone-mapped
exactly like the review copy, so the still looks like what the user picked in the player.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime

from PIL import Image

from surfclip.config import CompilationConfig
from surfclip.media.export import rider_names
from surfclip.media.review import TONEMAP
from surfclip.store.schemas import Riders, Rides, SourceInfo, Still, Stills
from surfclip.store.session import SessionStore

STILLS_FILE = "clips/stills.json"
STILL_DIR = "clips/stills"
_NAME = re.compile(r"^[A-Za-z0-9_]+\.jpg$")


class StillError(ValueError):
    pass


def snap(t_s: float, fps: float) -> tuple[int, float]:
    """(frame number, its time) of the frame shown at t_s."""
    frame = max(0, round(t_s * fps))
    return frame, frame / fps


def read_stills(store: SessionStore) -> Stills:
    path = store.path(STILLS_FILE)
    return store.read_model(STILLS_FILE, Stills) if path.exists() else Stills()


def _ride_at(store: SessionStore, t: float) -> tuple[str | None, str | None]:
    """The ride (and its rider's label) shown at t: within the ride, else within its clip."""
    if not store.path("rides.json").exists():
        return None, None
    rides = store.read_model("rides.json", Rides).rides
    hit = next((r for r in rides if r.start_s <= t <= r.end_s), None) or next(
        (r for r in rides if r.clip_start_s <= t <= r.clip_end_s), None
    )
    if hit is None:
        return None, None
    rider = None
    if store.path("riders.json").exists():
        riders = store.read_model("riders.json", Riders)
        labels = rider_names(riders)
        rider = next((labels[g.rider_id] for g in riders.riders if hit.ride_id in g.ride_ids), None)
    return hit.ride_id, rider


def save_still(store: SessionStore, cfg: CompilationConfig, t_s: float) -> tuple[Still, bool]:
    """Save the frame at t_s. Returns (still, created)."""
    info = store.read_model("probe.json", SourceInfo)
    frame, t = snap(t_s, info.avg_fps)
    if t_s < 0 or t >= info.duration_s:
        raise StillError(f"{t_s:.2f} s is outside the video (0-{info.duration_s:.1f} s)")
    ride_id, rider = _ride_at(store, t)
    name = f"{ride_id or 't'}_f{frame:06d}.jpg"
    stills = read_stills(store)
    existing = next((s for s in stills.stills if s.name == name), None)
    if existing is not None and store.path(existing.path).exists():
        return existing, False
    rel = f"{STILL_DIR}/{name}"
    out = store.path(rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.jpg")
    vf = [TONEMAP] if info.hdr_format != "none" else []
    # JPEG viewers read BT.601 full range: convert from the frame's own matrix (BT.709 after
    # tone-mapping), or colours shift.
    vf.append("scale=in_color_matrix=auto:out_color_matrix=bt601:out_range=pc,format=yuvj420p")
    # Seek half a frame early: the first frame at or after that time is exactly `frame`.
    seek = max(0.0, (frame - 0.5) / info.avg_fps)
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{seek:.6f}", "-i", info.path,
         "-frames:v", "1", "-vf", ",".join(vf), "-q:v", str(cfg.still_quality), str(tmp)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if result.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"could not save the still: {result.stderr.strip()[-300:]}")
    tmp.replace(out)
    with Image.open(out) as img:
        width, height = img.size
    still = Still(
        name=name, path=rel, t_s=round(t, 6), frame=frame, ride_id=ride_id, rider=rider,
        width=width, height=height, saved_at=datetime.now(UTC),
    )  # fmt: skip
    stills.stills = [s for s in stills.stills if s.name != name] + [still]
    store.write_model(STILLS_FILE, stills)
    return still, True


def delete_still(store: SessionStore, name: str) -> bool:
    if not _NAME.match(name):
        raise StillError(f"not a still: {name}")
    stills = read_stills(store)
    keep = [s for s in stills.stills if s.name != name]
    store.path(f"{STILL_DIR}/{name}").unlink(missing_ok=True)
    if len(keep) == len(stills.stills):
        return False
    stills.stills = keep
    store.write_model(STILLS_FILE, stills)
    return True
