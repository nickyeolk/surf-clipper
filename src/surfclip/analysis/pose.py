"""Rider keypoints through a ride (004 T005, research R1).

The ride is decoded from the full-resolution source at ``fps`` (tone-mapped like the review copy
when HDR), the tracked rider is cropped with a margin (track boxes interpolated between the
analysis frames of 001), and YOLO11-pose runs on the crop. Of the people the model finds in the
crop, the one nearest the crop centre is the tracked rider. Keypoints are kept in source
display pixels; ``other_iou`` says how much the crop overlaps another tracked person (overlap
makes the keypoints unreliable: research R4 "unclear").
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]

from surfclip.config import AnalysisPoseConfig
from surfclip.media.decode import output_size
from surfclip.media.review import TONEMAP
from surfclip.rides.evidence import Obs
from surfclip.store.schemas import Ride, SourceInfo

FloatArray = np.ndarray[Any, np.dtype[np.float64]]
# pyarrow ships no type information: untyped at the storage boundary (as store/frames.py)
pa: Any = _pyarrow
pq: Any = _parquet
N_KP = 17  # COCO keypoints


@dataclass
class Keypoints:
    t: FloatArray  # (n,) source seconds
    box: FloatArray  # (n, 4) crop box x0, y0, x1, y1 in source display pixels
    kp: FloatArray  # (n, 17, 3) x, y, confidence
    other_iou: FloatArray  # (n,)

    def __len__(self) -> int:
        return len(self.t)


def interpolate_boxes(track: list[Obs], times: FloatArray) -> FloatArray:
    """The rider's box at each time, linear between observations, held at the ends."""
    pts = sorted(track, key=lambda o: o.t)
    if not pts:
        raise ValueError("ride has no observations")
    ts = np.array([o.t for o in pts])
    bx = np.array([o.box for o in pts], dtype=float)
    return np.stack([np.interp(times, ts, bx[:, k]) for k in range(4)], axis=1)


def box_iou(a: FloatArray, b: FloatArray) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


def crop_box(box: FloatArray, margin: float, size: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = size
    m = margin * (box[3] - box[1])
    return (
        int(max(0, box[0] - m)),
        int(max(0, box[1] - m)),
        int(min(w, box[2] + m)),
        int(min(h, box[3] + m)),
    )


def pick_rider(centres: FloatArray, crop_wh: tuple[int, int]) -> int | None:
    """Index of the detected person nearest the crop centre (the tracked rider)."""
    if len(centres) == 0:
        return None
    mid = np.array([crop_wh[0] / 2, crop_wh[1] / 2])
    return int(np.argmin(np.linalg.norm(centres - mid, axis=1)))


def _frames(
    info: SourceInfo, start: float, length: float, fps: float
) -> Iterator[np.ndarray[Any, np.dtype[np.uint8]]]:
    w, h = output_size(info, max(info.width, info.height))
    vf = (TONEMAP + "," if info.hdr_format != "none" else "") + f"fps={fps},format=bgr24"
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{start:.3f}", "-i", info.path,
         "-t", f"{length:.3f}", "-vf", vf, "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE,
    )  # fmt: skip
    assert proc.stdout is not None
    n = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


class PoseModel:
    def __init__(self, cfg: AnalysisPoseConfig, *, cpu: bool = False) -> None:
        from ultralytics import YOLO  # heavy import, kept local

        if not Path(cfg.model).is_file():
            raise RuntimeError("pose weights are not downloaded: run `surfclip models download`")
        self.model: Any = YOLO(cfg.model)
        self.cfg = cfg
        self.device = "cpu" if cpu else 0

    def predict(self, crops: list[np.ndarray[Any, np.dtype[np.uint8]]]) -> list[FloatArray]:
        """Keypoints (17, 3) of the person nearest each crop's centre (NaN when nobody)."""
        out: list[FloatArray] = []
        results: Any = self.model.predict(
            crops, imgsz=self.cfg.imgsz, conf=0.2, verbose=False, device=self.device
        )
        for crop, res in zip(crops, results, strict=True):
            kp = np.full((N_KP, 3), np.nan)
            if res.keypoints is not None and len(res.keypoints) > 0:
                centres = res.boxes.xywh.cpu().numpy()[:, :2]
                i = pick_rider(centres, (crop.shape[1], crop.shape[0]))
                if i is not None:
                    kp[:, :2] = res.keypoints.xy[i].cpu().numpy()
                    kp[:, 2] = res.keypoints.conf[i].cpu().numpy()
            out.append(kp)
        return out


def ride_keypoints(
    info: SourceInfo,
    ride: Ride,
    track: list[Obs],
    others: list[Obs],
    model: PoseModel,
    *,
    progress: Callable[[float], None] | None = None,
) -> Keypoints:
    cfg = model.cfg
    size = output_size(info, max(info.width, info.height))
    times_l: list[float] = []
    crops: list[np.ndarray[Any, np.dtype[np.uint8]]] = []
    boxes_l: list[tuple[int, int, int, int]] = []
    kps: list[FloatArray] = []
    expected = max(1, int(ride.length_s * cfg.fps))
    track_t = np.array([o.t for o in sorted(track, key=lambda o: o.t)])
    for i, img in enumerate(_frames(info, ride.start_s, ride.length_s, cfg.fps)):
        t = ride.start_s + i / cfg.fps
        box = interpolate_boxes(track, np.array([t]))[0]
        c = crop_box(box, cfg.crop_margin, size)
        if c[2] - c[0] < 8 or c[3] - c[1] < 8 or not len(track_t):
            continue
        times_l.append(t)
        boxes_l.append(c)
        crops.append(np.ascontiguousarray(img[c[1] : c[3], c[0] : c[2]]))
        if len(crops) >= cfg.batch:
            kps += _to_source(model.predict(crops), boxes_l[len(kps) :])
            crops = []
            if progress:
                progress(min(1.0, len(kps) / expected))
    if crops:
        kps += _to_source(model.predict(crops), boxes_l[len(kps) :])
    t_arr = np.array(times_l)
    box_arr = np.array(boxes_l, dtype=float).reshape(-1, 4)
    return Keypoints(
        t=t_arr,
        box=box_arr,
        kp=np.array(kps).reshape(-1, N_KP, 3),
        other_iou=_other_iou(t_arr, box_arr, others),
    )


def _to_source(kps: list[FloatArray], boxes: list[tuple[int, int, int, int]]) -> list[FloatArray]:
    out: list[FloatArray] = []
    for kp, (x0, y0, _, _) in zip(kps, boxes, strict=False):
        k = kp.copy()
        k[:, 0] += x0
        k[:, 1] += y0
        out.append(k)
    return out


def _other_iou(times: FloatArray, boxes: FloatArray, others: list[Obs]) -> FloatArray:
    out = np.zeros(len(times))
    if not others:
        return out
    ot = np.array([o.t for o in others])
    ob = np.array([o.box for o in others], dtype=float)
    for i, (t, b) in enumerate(zip(times, boxes, strict=True)):
        near = np.abs(ot - t) <= 0.15
        if near.any():
            out[i] = max(box_iou(b, o) for o in ob[near])
    return out


def write_keypoints(path: Path, kp: Keypoints) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "t": kp.t,
            "box": pa.array(kp.box.tolist(), type=pa.list_(pa.float64(), 4)),
            "kp": pa.array(kp.kp.reshape(len(kp), -1).tolist(), type=pa.list_(pa.float64(), 51)),
            "other_iou": kp.other_iou,
        }
    )
    tmp = path.with_suffix(".tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)


def read_keypoints(path: Path) -> Keypoints:
    table = pq.read_table(path)
    n = table.num_rows
    return Keypoints(
        t=np.array(table.column("t").to_pylist(), dtype=float),
        box=np.array(table.column("box").to_pylist(), dtype=float).reshape(n, 4),
        kp=np.array(table.column("kp").to_pylist(), dtype=float).reshape(n, N_KP, 3),
        other_iou=np.array(table.column("other_iou").to_pylist(), dtype=float),
    )


def download_pose(cfg: AnalysisPoseConfig) -> Path:
    """Fetch the pose weights once (network; never during processing)."""
    from ultralytics import YOLO

    path = Path(cfg.model)
    path.parent.mkdir(parents=True, exist_ok=True)
    YOLO(str(path))
    return path
