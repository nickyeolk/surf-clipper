"""Per-rider compilations with captions (003, research R1-R2).

Each of the rider's rides is re-encoded from the source once, exactly like a 001 clip, with a
caption ("me · ride 3 of 12 · 10:42") burned into its first ``caption_s`` seconds. The captioned
segments are cached by clip span + caption + settings, then joined without re-encoding.

Captions are drawn as a neutral grey at the transfer's reference-white level (HLG 75%, PQ 58%),
so on HDR footage they are as bright as paper white, not the 1000-nit peak. Neutral greys have
neutral chroma under every matrix, so the level does not depend on the YUV conversion.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from surfclip.config import CompilationConfig, ExportConfig
from surfclip.media.export import (
    clip_cache_key,
    export_clip,
    reel_file,
    rider_names,
    source_info,
)
from surfclip.store.schemas import (
    CaptionedSegment,
    Compilation,
    CompilationRide,
    Compilations,
    Ride,
    Riders,
    Rides,
    SourceInfo,
)
from surfclip.store.session import SessionStore

COMPILATIONS_FILE = "clips/compilations.json"
SEGMENT_DIR = "clips/captioned"


@dataclass(frozen=True)
class Caption:
    ride_id: str
    rider: str
    index: int  # 1-based among the rider's rides in time order
    count: int
    at_s: float

    @property
    def text(self) -> str:
        return f"{self.rider} · ride {self.index} of {self.count} · {clock(self.at_s)}"


def clock(seconds: float) -> str:
    """m:ss, or h:mm:ss from an hour."""
    s = max(0, int(seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def find_rider(riders: Riders, rider: str) -> tuple[str, list[str]]:
    """(display name, ride ids) of a rider given by id, user name or display name."""
    labels = rider_names(riders)
    for g in riders.riders:
        if rider in (g.rider_id, g.name, labels[g.rider_id]):
            return labels[g.rider_id], list(g.ride_ids)
    raise KeyError(rider)


def captions(rides: Rides, label: str, ride_ids: list[str]) -> list[Caption]:
    wanted = set(ride_ids)
    chosen = sorted((r for r in rides.rides if r.ride_id in wanted), key=lambda r: r.start_s)
    return [
        Caption(r.ride_id, label, k, len(chosen), r.start_s) for k, r in enumerate(chosen, start=1)
    ]


def _level(info: SourceInfo, cfg: CompilationConfig) -> float:
    if info.hdr_format in ("hlg", "dolby_vision"):  # Dolby Vision is exported as its HLG base
        return cfg.level_hlg
    if info.hdr_format == "hdr10":
        return cfg.level_pq
    return cfg.level_sdr


def text_colour(info: SourceInfo, cfg: CompilationConfig) -> str:
    v = round(max(0.0, min(1.0, _level(info, cfg))) * 255)
    return f"0x{v:02X}{v:02X}{v:02X}"


def _quote(value: str) -> str:
    """A filter option value in single quotes (so ``:`` ``,`` ``;`` in paths are literal)."""
    return "'" + value.replace("'", "'\\''") + "'"


def caption_filter(info: SourceInfo, cfg: CompilationConfig, text_file: Path) -> str:
    """drawtext reading the caption from a file (no escaping of names, no % expansion)."""
    short = min(info.width, info.height)  # the shorter side: same for portrait and landscape
    size = max(8, round(short * cfg.size_frac))
    border = max(1, size // 3)
    margin = round(short * cfg.margin_frac) + border
    x = str(margin) if cfg.position.endswith("left") else f"w-tw-{margin}"
    y = str(margin) if cfg.position.startswith("top") else f"h-th-{margin}"
    opts = {
        "fontfile": _quote(cfg.font),
        "textfile": _quote(str(text_file)),
        "expansion": "none",
        "fontsize": str(size),
        "fontcolor": text_colour(info, cfg),
        "box": "1",
        "boxcolor": f"black@{cfg.box_opacity:.2f}",
        "boxborderw": str(border),
        "x": x,
        "y": y,
        "enable": f"'lt(t,{cfg.caption_s:.3f})'",
    }
    return "drawtext=" + ":".join(f"{k}={v}" for k, v in opts.items())


def segment_key(
    info: SourceInfo,
    ride: Ride,
    export_cfg: ExportConfig,
    cfg: CompilationConfig,
    cpu: bool,
    caption: str,
) -> str:
    parts = [clip_cache_key(info, ride, export_cfg, cpu), caption, cfg.model_dump_json()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def read_compilations(store: SessionStore) -> Compilations:
    path = store.path(COMPILATIONS_FILE)
    return store.read_model(COMPILATIONS_FILE, Compilations) if path.exists() else Compilations()


def duration_of(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return float(out.stdout.strip())


def _use_cpu(export_cfg: ExportConfig, cpu: bool) -> bool:
    return cpu or export_cfg.encoder == "cpu"


def export_compilation(
    store: SessionStore,
    export_cfg: ExportConfig,
    cfg: CompilationConfig,
    riders: Riders,
    rider: str,
    *,
    cpu: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> Path:
    """One video of the rider's rides in time order, each captioned for its first seconds.

    Segments whose span, caption and settings are unchanged are reused (FR-007)."""
    label, ride_ids = find_rider(riders, rider)
    info = source_info(store)
    rides = store.read_model("rides.json", Rides)
    by_id = {r.ride_id: r for r in rides.rides}
    caps = captions(rides, label, ride_ids)
    if not caps:
        raise RuntimeError(f"{label} has no rides")
    use_cpu = _use_cpu(export_cfg, cpu)
    comps = read_compilations(store)
    text_dir = store.path(SEGMENT_DIR)
    text_dir.mkdir(parents=True, exist_ok=True)
    entries: list[CompilationRide] = []
    offset = 0.0
    for i, cap in enumerate(caps, start=1):
        ride = by_id[cap.ride_id]
        key = segment_key(info, ride, export_cfg, cfg, use_cpu, cap.text)
        rel = f"{SEGMENT_DIR}/{cap.ride_id}.mp4"
        seg = comps.segments.get(cap.ride_id)
        if seg is None or seg.cache_key != key or not store.path(rel).exists():
            if progress:
                progress(i, len(caps), cap.ride_id)
            text_file = text_dir / f"{cap.ride_id}.txt"
            text_file.write_text(cap.text, encoding="utf-8")
            export_clip(
                info, ride, store.path(rel), export_cfg, use_cpu,
                vf=caption_filter(info, cfg, text_file),
            )  # fmt: skip
            text_file.unlink(missing_ok=True)
            seg = CaptionedSegment(
                path=rel,
                cache_key=key,
                span=(round(ride.clip_start_s, 4), round(ride.clip_end_s, 4)),
                duration_s=duration_of(store.path(rel)),
            )
            comps.segments[cap.ride_id] = seg
            store.write_model(COMPILATIONS_FILE, comps)
        entries.append(
            CompilationRide(
                ride_id=cap.ride_id,
                offset_s=round(offset, 4),
                duration_s=seg.duration_s,
                clip_start_s=ride.clip_start_s,
                caption=cap.text,
            )
        )
        offset += seg.duration_s
    if progress:
        progress(len(caps), len(caps), "joining")
    out_rel = reel_file(label)
    _concat(store.path(out_rel), [store.path(comps.segments[e.ride_id].path) for e in entries])
    comps.compilations[label] = Compilation(
        rider=label, path=out_rel, made_at=datetime.now(UTC), rides=entries
    )
    store.write_model(COMPILATIONS_FILE, comps)
    return store.path(out_rel)


def _concat(out: Path, parts: list[Path]) -> None:
    listing = out.with_name(out.stem + ".txt")
    listing.write_text(
        "".join(f"file '{p.relative_to(out.parent).as_posix()}'\n" for p in parts),
        encoding="utf-8",
    )
    tmp = out.with_name(out.stem + ".tmp.mp4")
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(tmp)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    listing.unlink(missing_ok=True)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"joining clips failed: {result.stderr.strip()[-500:]}")
    tmp.replace(out)


def compilation_current(
    store: SessionStore,
    export_cfg: ExportConfig,
    cfg: CompilationConfig,
    riders: Riders,
    label: str,
    *,
    cpu: bool = False,
) -> bool:
    """True when the rider's compilation exists and matches their current rides and captions."""
    comps = read_compilations(store)
    comp = comps.compilations.get(label)
    if comp is None or not store.path(comp.path).exists():
        return False
    try:
        _, ride_ids = find_rider(riders, label)
    except KeyError:
        return False
    info = store.read_model("probe.json", SourceInfo)
    rides = store.read_model("rides.json", Rides)
    by_id = {r.ride_id: r for r in rides.rides}
    caps = captions(rides, label, ride_ids)
    if [c.ride_id for c in caps] != [r.ride_id for r in comp.rides]:
        return False
    use_cpu = _use_cpu(export_cfg, cpu)
    for cap in caps:
        seg = comps.segments.get(cap.ride_id)
        key = segment_key(info, by_id[cap.ride_id], export_cfg, cfg, use_cpu, cap.text)
        if seg is None or seg.cache_key != key:
            return False
    return True
