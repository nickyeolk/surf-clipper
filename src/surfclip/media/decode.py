"""Frame decoding through ffmpeg pipes (research R2).

* ``iter_proxy_frames``: the low-fps analysis proxy, streamed frame by frame so an hour of
  video never sits in memory (~50 GB at 720p/5 fps). HDR is tone-mapped to SDR.
* ``decode_window``: every source frame between two times, for full-frame-rate boundary
  refinement (FR-017).

Every frame carries its true presentation time on the source timeline: ffmpeg keeps the
original timestamps (``-copyts``) and reports each output frame's time through the
``showinfo`` filter. Timestamps are never inferred from frame counts, because phone files
(edit lists, variable frame rate) can deliver the first frame after a seek a few frames
later than requested.

Sources are opened read-only; nothing is written next to them.
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO

import numpy as np
from numpy.typing import NDArray

from surfclip.store.schemas import SourceInfo

Image = NDArray[np.uint8]

_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap={op}:desat=0,zscale=t=bt709:m=bt709:r=tv"
)
_PTS = re.compile(r"Parsed_showinfo.*?\bpts_time:\s*(-?[\d.]+)")
_PTS_TIMEOUT_S = 30.0


class DecodeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Frame:
    index: int  # source frame number, from pts and the average frame rate
    pts_s: float  # presentation time on the source timeline
    image: Image  # H x W x 3, BGR


def output_size(info: SourceInfo, max_height: int) -> tuple[int, int]:
    """(width, height) after ffmpeg's auto-rotation and downscaling to max_height."""
    w, h = (info.height, info.width) if info.rotation in {90, 270} else (info.width, info.height)
    if h <= max_height:
        return w, h
    scaled_w = int(w * max_height / h / 2 + 0.5) * 2  # nearest even width, halves round up
    return scaled_w, max_height


def build_filter(info: SourceInfo, *, fps: float | None, max_height: int, tonemap: str) -> str:
    parts: list[str] = []
    if fps is not None:
        # Keep real source frames about every 1/fps s. Unlike the fps filter, select never
        # relabels a frame's timestamp, so pts stays true on VFR and edit-listed files.
        step = 1 / fps - 0.5 / info.avg_fps
        parts.append(f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{step:.6f})'")
    if info.hdr_format != "none":
        parts.append(_TONEMAP.format(op=tonemap))
    w, h = output_size(info, max_height)
    parts.append(f"scale={w}:{h}:flags=area")
    parts.append("format=bgr24")
    parts.append("showinfo")
    return ",".join(parts)


def _pump_stderr(stream: IO[bytes], times: queue.Queue[float | None], errors: list[str]) -> None:
    for raw in stream:
        line = raw.decode("utf-8", "replace")
        m = _PTS.search(line)
        if m:
            times.put(float(m.group(1)))
        elif "error" in line.lower():
            errors.append(line.strip())
    times.put(None)


def _run(cmd: list[str], info: SourceInfo, width: int, height: int) -> Iterator[Frame]:
    size = width * height * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None and proc.stderr is not None
    times: queue.Queue[float | None] = queue.Queue()
    errors: list[str] = []
    pump = threading.Thread(target=_pump_stderr, args=(proc.stderr, times, errors), daemon=True)
    pump.start()
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            pts = times.get(timeout=_PTS_TIMEOUT_S)
            if pts is None:
                raise DecodeError("ffmpeg produced a frame without a timestamp")
            image = np.frombuffer(buf, np.uint8).reshape(height, width, 3)
            yield Frame(index=round(pts * info.avg_fps), pts_s=pts, image=image)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
        pump.join(timeout=5)
    if errors and proc.returncode not in (0, -9):
        raise DecodeError("; ".join(errors[-3:]))


def _base_cmd(info: SourceInfo, start_s: float, duration_s: float | None = None) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin"]
    if start_s > 0:
        cmd += ["-ss", f"{start_s:.6f}"]
    if duration_s is not None:  # input-side limit: relative to the seek point even with -copyts
        cmd += ["-t", f"{duration_s:.6f}"]
    return [*cmd, "-copyts", "-i", info.path, "-map", "0:v:0", "-an", "-sn", "-dn"]


def iter_proxy_frames(
    info: SourceInfo,
    *,
    fps: float,
    max_height: int,
    tonemap: str = "hable",
    start_s: float = 0.0,
    duration_s: float | None = None,
) -> Iterator[Frame]:
    w, h = output_size(info, max_height)
    cmd = _base_cmd(info, start_s, duration_s)
    cmd += [
        "-fps_mode",
        "passthrough",
        "-vf",
        build_filter(info, fps=fps, max_height=max_height, tonemap=tonemap),
    ]
    cmd += ["-f", "rawvideo", "-"]
    yield from _run(cmd, info, w, h)


def decode_window(
    info: SourceInfo, start_s: float, end_s: float, *, max_height: int, tonemap: str = "hable"
) -> list[Frame]:
    """All source frames with start_s <= pts < end_s, at full frame rate."""
    start_s = max(0.0, start_s)
    end_s = min(info.duration_s, end_s)
    w, h = output_size(info, max_height)
    # Seek a little early; frames before start_s are discarded using their true times.
    cmd = _base_cmd(info, max(0.0, start_s - 1.0))
    cmd += ["-fps_mode", "passthrough"]
    cmd += ["-vf", build_filter(info, fps=None, max_height=max_height, tonemap=tonemap)]
    cmd += ["-f", "rawvideo", "-"]
    eps = 1e-4
    frames: list[Frame] = []
    for frame in _run(cmd, info, w, h):
        if frame.pts_s >= end_s - eps:
            break
        if frame.pts_s >= start_s - eps:
            frames.append(frame)
    return frames
