"""T001 (b): YOLO11 person/surfboard detection throughput on the local GPU.

Decodes the first N minutes of a session at 5 fps (read-only) and times detection at
640 px, 1280 px, and 2x2 tiles of 640 px. Prints per-hour extrapolations.

Usage: python scripts/spikes/t001_detect_speed.py SOURCE.MP4 [--minutes 5] [--model yolo11s.pt]
"""

from __future__ import annotations

import argparse
import subprocess
import time

import numpy as np
import torch
from ultralytics import YOLO

PERSON, SURFBOARD = 0, 37  # COCO class ids


def decode(src: str, minutes: float, fps: int) -> np.ndarray:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            src,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = (int(v) for v in probe.stdout.strip().split(","))
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-t",
            str(minutes * 60),
            "-i",
            src,
            "-vf",
            f"fps={fps}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def tiles(frame: np.ndarray) -> list[np.ndarray]:
    h, w = frame.shape[:2]
    th, tw = int(h * 0.6), int(w * 0.6)  # 2x2 with ~20% overlap
    return [frame[y : y + th, x : x + tw] for y in (0, h - th) for x in (0, w - tw)]


def run(model: YOLO, batches: list[list[np.ndarray]], imgsz: int) -> tuple[float, int]:
    n_boxes = 0
    torch.cuda.synchronize()
    start = time.perf_counter()
    for batch in batches:
        for r in model.predict(
            batch, imgsz=imgsz, classes=[PERSON, SURFBOARD], conf=0.2, half=True, verbose=False
        ):
            n_boxes += len(r.boxes)
    torch.cuda.synchronize()
    return time.perf_counter() - start, n_boxes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--minutes", type=float, default=5)
    ap.add_argument("--model", default="yolo11s.pt")
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()

    print(
        f"torch {torch.__version__}, cuda {torch.cuda.is_available()}, "
        f"{torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}"
    )
    t0 = time.perf_counter()
    frames = decode(args.source, args.minutes, fps=5)
    print(
        f"decoded {len(frames)} frames {frames.shape[2]}x{frames.shape[1]} "
        f"in {time.perf_counter() - t0:.1f}s"
    )

    model = YOLO(args.model)
    model.predict(list(frames[:2]), imgsz=640, half=True, verbose=False)  # warm-up

    def batched(items: list[np.ndarray]) -> list[list[np.ndarray]]:
        return [items[i : i + args.batch] for i in range(0, len(items), args.batch)]

    scale = 60 / args.minutes
    for label, items, imgsz in [
        ("full frame @640", list(frames), 640),
        ("full frame @1280", list(frames), 1280),
        ("2x2 tiles @640", [t for f in frames for t in tiles(f)], 640),
    ]:
        secs, boxes = run(model, batched(items), imgsz)
        print(
            f"{label:18s} {secs:7.1f}s  {len(frames) / secs:6.1f} frames/s  "
            f"-> {secs * scale / 60:5.1f} min per hour  ({boxes} boxes)"
        )


if __name__ == "__main__":
    main()
