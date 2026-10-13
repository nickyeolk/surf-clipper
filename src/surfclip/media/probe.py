"""ffprobe wrapper: SourceInfo for a session video, plus input validation (FR-001, FR-002).

Metadata is used as a hint only: missing colour tags fall back to SDR, missing frame counts
are estimated. Location tags are never copied (constitution I).
"""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, cast

from surfclip.store.schemas import SourceInfo

MAX_DURATION_S = 1.5 * 3600
SUPPORTED_CODECS = {"h264", "hevc"}
_HINT_TAGS = {"handler_name", "encoder", "com.apple.quicktime.make", "com.apple.quicktime.model"}

HdrFormat = Literal["none", "hlg", "hdr10", "dolby_vision"]


class UnsupportedInputError(ValueError):
    """The file cannot be processed; the message is shown to the user as-is."""


def _rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "0"}:
        return None
    return float(Fraction(value))


def _hdr_format(stream: dict[str, Any]) -> HdrFormat:
    side = cast(list[dict[str, Any]], stream.get("side_data_list") or [])
    tag = str(stream.get("codec_tag_string", "")).lower()
    if tag in {"dvh1", "dvhe"} or any("DOVI" in str(s.get("side_data_type", "")) for s in side):
        return "dolby_vision"
    transfer = stream.get("color_transfer")
    if transfer == "arib-std-b67":
        return "hlg"
    if transfer == "smpte2084":
        return "hdr10"
    return "none"


def _rotation(stream: dict[str, Any]) -> int:
    for s in cast(list[dict[str, Any]], stream.get("side_data_list") or []):
        if "rotation" in s:
            return round(float(s["rotation"])) % 360
    tags = cast(dict[str, str], stream.get("tags") or {})
    return int(tags.get("rotate", 0)) % 360


def _bit_depth(stream: dict[str, Any]) -> int:
    raw = stream.get("bits_per_raw_sample")
    if raw and str(raw).isdigit():
        return int(raw)
    pix = str(stream.get("pix_fmt", ""))
    return 10 if "10" in pix else 12 if "12" in pix else 8


def parse_probe(path: str, data: dict[str, Any]) -> SourceInfo:
    streams = cast(list[dict[str, Any]], data.get("streams") or [])
    fmt = cast(dict[str, Any], data.get("format") or {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise UnsupportedInputError(f"{path}: no video stream found")
    codec = str(video.get("codec_name", "unknown"))
    if codec not in SUPPORTED_CODECS:
        raise UnsupportedInputError(
            f"{path}: video codec '{codec}' is not supported (H.264 or HEVC)"
        )
    duration = float(video.get("duration") or fmt.get("duration") or 0)
    if duration <= 0:
        raise UnsupportedInputError(f"{path}: duration is unknown")
    if duration > MAX_DURATION_S:
        raise UnsupportedInputError(
            f"{path}: {duration / 3600:.2f} h is longer than the 1.5 h limit"
        )

    avg = _rate(video.get("avg_frame_rate"))
    real = _rate(video.get("r_frame_rate"))
    fps = avg or real
    if fps is None:
        raise UnsupportedInputError(f"{path}: frame rate is unknown")
    is_vfr = avg is not None and real is not None and abs(avg - real) / real > 0.001
    nb = video.get("nb_frames")
    frame_count = int(nb) if nb and str(nb).isdigit() else round(duration * fps)

    tags = cast(dict[str, str], video.get("tags") or {}) | cast(
        dict[str, str], fmt.get("tags") or {}
    )
    return SourceInfo(
        path=path,
        container=str(fmt.get("format_name", "")),
        codec=codec,
        profile=video.get("profile"),
        width=int(video["width"]),
        height=int(video["height"]),
        duration_s=duration,
        frame_count=frame_count,
        avg_fps=fps,
        is_vfr=is_vfr,
        bit_depth=_bit_depth(video),
        pix_fmt=str(video.get("pix_fmt", "")),
        color_primaries=video.get("color_primaries"),
        color_transfer=video.get("color_transfer"),
        color_space=video.get("color_space"),
        hdr_format=_hdr_format(video),
        rotation=_rotation(video),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        device_hints={k: v for k, v in tags.items() if k in _HINT_TAGS},
    )


def probe(path: Path) -> SourceInfo:
    if not path.is_file():
        raise UnsupportedInputError(f"{path}: file not found")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise UnsupportedInputError(f"{path}: ffprobe failed: {result.stderr.strip()}")
    return parse_probe(str(path), json.loads(result.stdout))
