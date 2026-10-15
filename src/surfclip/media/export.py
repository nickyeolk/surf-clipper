"""Final-quality per-ride clips (FR-020, research R13).

Frame-accurate re-encode of each ride's padded span, keeping the source's dynamic range:

* HDR (HLG, HDR10) -> HEVC Main10 with the source's colour primaries, transfer and matrix set
  explicitly (NVENC does not copy them; T001). Dolby Vision is written as its HLG base layer.
* SDR -> H.264 High, BT.709 tags kept.

Clips are exported on demand. A clip is re-encoded only when its cache key (span, source and
encoder settings) changed; records live in exports.json so pipeline re-runs keep them.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from surfclip.config import ExportConfig
from surfclip.media.probe import probe
from surfclip.store.schemas import ExportRecord, Ride, Rides, SourceInfo
from surfclip.store.session import SessionStore

log = logging.getLogger(__name__)
EXPORTS_FILE = "exports.json"


class Exports(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: dict[str, ExportRecord] = Field(default_factory=dict[str, ExportRecord])


def _codec_args(info: SourceInfo, cfg: ExportConfig, cpu: bool) -> list[str]:
    """Encoder arguments, with the bitrate capped relative to the source.

    Constant quality alone made 720p clips ~2x the source bitrate (55 MB for 57 s on 20241004):
    re-encoding cannot add detail, so the cap keeps clips near the source's size.
    """
    args = _quality_args(info, cfg, cpu)
    if info.bit_rate:
        cap = int(info.bit_rate * cfg.max_bitrate_factor)
        args += ["-maxrate", str(cap), "-bufsize", str(2 * cap)]
    return args


def _quality_args(info: SourceInfo, cfg: ExportConfig, cpu: bool) -> list[str]:
    hdr = info.hdr_format != "none"
    if hdr:
        trc = "arib-std-b67" if info.hdr_format in ("hlg", "dolby_vision") else "smpte2084"
        colour = [
            "-color_primaries",
            info.color_primaries or "bt2020",
            "-color_trc",
            trc,
            "-colorspace",
            info.color_space or "bt2020nc",
        ]
        if cpu:
            return [
                "-c:v",
                "libx265",
                "-preset",
                "medium",
                "-crf",
                str(cfg.cq),
                "-pix_fmt",
                "yuv420p10le",
                "-x265-params",
                "log-level=error",
                *colour,
            ]
        return [
            "-c:v",
            "hevc_nvenc",
            "-profile:v",
            "main10",
            "-pix_fmt",
            "p010le",
            "-preset",
            cfg.nvenc_preset,
            "-rc",
            "vbr",
            "-cq",
            str(cfg.cq),
            "-b:v",
            "0",
            *colour,
        ]
    colour = [
        "-color_primaries",
        info.color_primaries or "bt709",
        "-color_trc",
        info.color_transfer or "bt709",
        "-colorspace",
        info.color_space or "bt709",
    ]
    if cpu:
        return [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(cfg.cq),
            "-pix_fmt",
            "yuv420p",
            *colour,
        ]
    return [
        "-c:v",
        "h264_nvenc",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        cfg.nvenc_preset,
        "-rc",
        "vbr",
        "-cq",
        str(cfg.cq),
        "-b:v",
        "0",
        *colour,
    ]


def clip_cache_key(info: SourceInfo, ride: Ride, cfg: ExportConfig, cpu: bool) -> str:
    parts = [
        info.path,
        f"{ride.clip_start_s:.4f}",
        f"{ride.clip_end_s:.4f}",
        cfg.model_dump_json(),
        str(cpu),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def export_clip(info: SourceInfo, ride: Ride, out: Path, cfg: ExportConfig, cpu: bool) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-ss",
        f"{ride.clip_start_s:.6f}",
        "-i",
        info.path,
        "-t",
        f"{ride.clip_end_s - ride.clip_start_s:.6f}",
        "-map",
        "0:v:0",
        *(["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k"] if info.has_audio else []),
        *_codec_args(info, cfg, cpu),
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed for {ride.ride_id}: {result.stderr.strip()[-500:]}")
    tmp.replace(out)


def read_exports(store: SessionStore) -> Exports:
    path = store.path(EXPORTS_FILE)
    return store.read_model(EXPORTS_FILE, Exports) if path.exists() else Exports()


def attach_exports(rides: Rides, exports: Exports, store: SessionStore) -> Rides:
    """Set each ride's ``export`` from exports.json when the clip still matches the ride."""
    out: list[Ride] = []
    for r in rides.rides:
        rec = exports.records.get(r.ride_id)
        valid = (
            rec is not None
            and store.path(rec.path).exists()
            and rec.span == (round(r.clip_start_s, 4), round(r.clip_end_s, 4))
        )
        out.append(r.model_copy(update={"export": rec if valid else None}))
    return rides.model_copy(update={"rides": out})


def export_rides(
    store: SessionStore,
    cfg: ExportConfig,
    *,
    ride_ids: list[str] | None = None,
    cpu: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[str], list[str]]:
    """Export new or changed clips. Returns (exported ride ids, skipped up-to-date ride ids)."""
    info = store.read_model("probe.json", SourceInfo)
    if info.bit_rate is None:  # probe.json from before bit_rate was recorded; re-probing is cheap
        info = probe(Path(info.path))
    rides = store.read_model("rides.json", Rides)
    exports = read_exports(store)
    todo = [r for r in rides.rides if ride_ids is None or r.ride_id in ride_ids]
    use_cpu = cpu or cfg.encoder == "cpu"
    done: list[str] = []
    skipped: list[str] = []
    for i, ride in enumerate(todo, start=1):
        key = clip_cache_key(info, ride, cfg, use_cpu)
        rel = f"clips/{ride.ride_id}.mp4"
        rec = exports.records.get(ride.ride_id)
        if rec is not None and rec.cache_key == key and store.path(rel).exists():
            skipped.append(ride.ride_id)
            continue
        if progress:
            progress(i, len(todo), ride.ride_id)
        export_clip(info, ride, store.path(rel), cfg, use_cpu)
        exports.records[ride.ride_id] = ExportRecord(
            path=rel,
            cache_key=key,
            exported_at=datetime.now(UTC),
            span=(round(ride.clip_start_s, 4), round(ride.clip_end_s, 4)),
        )
        store.write_model(EXPORTS_FILE, exports)
        done.append(ride.ride_id)
    if progress:
        progress(len(todo), len(todo), "done")
    # Re-read: the user may have edited rides while clips were encoding.
    latest = store.read_model("rides.json", Rides)
    store.write_model("rides.json", attach_exports(latest, exports, store))
    return done, skipped


REEL_FILE = "clips/reel.mp4"


def export_reel(
    store: SessionStore,
    cfg: ExportConfig,
    *,
    ride_ids: list[str] | None = None,
    cpu: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> Path:
    """All (or the given) rides as one video, in time order: the per-ride clips (exported first
    when new or changed) joined without re-encoding. They share codec settings, so the concat
    demuxer can copy the streams."""
    export_rides(store, cfg, ride_ids=ride_ids, cpu=cpu, progress=progress)
    rides = store.read_model("rides.json", Rides)
    chosen = sorted(
        (r for r in rides.rides if r.export and (ride_ids is None or r.ride_id in ride_ids)),
        key=lambda r: r.start_s,
    )
    if not chosen:
        raise RuntimeError("no rides to put in the reel")
    out = store.path(REEL_FILE)
    listing = out.with_name("reel.txt")
    listing.write_text(
        "".join(f"file '{Path(r.export.path).name}'\n" for r in chosen if r.export),
        encoding="utf-8",
    )
    tmp = out.with_name("reel.tmp.mp4")
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
    return out
