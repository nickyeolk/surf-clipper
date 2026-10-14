"""Review copy for browser playback (FR-026, research R12).

720p H.264 SDR with a keyframe every ``keyframe_interval_s`` and faststart, so seeking anywhere
in an hour starts within a second and frame steps are instant (T001: median seek 267 ms in
Chrome). HDR sources are tone-mapped here only; final clips keep HDR. No audio.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from surfclip.config import ReviewConfig
from surfclip.media.decode import output_size
from surfclip.store.schemas import SourceInfo

_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


def review_command(info: SourceInfo, out: Path, cfg: ReviewConfig, *, cpu: bool) -> list[str]:
    width, height = output_size(info, cfg.height)
    filters = [_TONEMAP] if info.hdr_format != "none" else []
    filters.append(f"scale={width}:{height}:flags=area,format=yuv420p")
    gop = max(1, round(info.avg_fps * cfg.keyframe_interval_s))
    # Bitrate capped: uncapped constant quality with a 0.5 s keyframe interval gave 2.2 GB per hour.
    rate = [
        "-maxrate",
        f"{cfg.max_kbps}k",
        "-bufsize",
        f"{2 * cfg.max_kbps}k",
    ]
    codec = (
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", *rate]
        if cpu
        else [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p4",
            "-rc",
            "vbr",
            "-cq",
            "28",
            "-b:v",
            f"{cfg.max_kbps * 2 // 3}k",
            *rate,
        ]
    )
    return [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        info.path,
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        ",".join(filters),
        *codec,
        "-g",
        str(gop),
        "-keyint_min",
        str(gop),
        "-bf",
        "0",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-movflags",
        "+faststart",
        str(out),
    ]


def make_review_copy(info: SourceInfo, out: Path, cfg: ReviewConfig, *, cpu: bool = False) -> None:
    tmp = out.with_name(out.stem + ".tmp.mp4")
    result = subprocess.run(
        review_command(info, tmp, cfg, cpu=cpu), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"review copy failed: {result.stderr.strip()[-500:]}")
    tmp.replace(out)
