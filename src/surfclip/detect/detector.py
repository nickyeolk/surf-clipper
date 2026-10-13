"""Person and surfboard detection with pretrained YOLO11 (research R3; constitution VIII).

Each frame is detected whole (large, close riders) and, with tiling on, as 2x2 overlapping
tiles (small, far riders). Results are merged per frame. Runs on CUDA with FP16 when available,
otherwise on the CPU.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from numpy.typing import NDArray

from surfclip.config import DetectConfig
from surfclip.detect.tiling import Window, merge, tile_windows, touches_inner_border
from surfclip.media.decode import Image

ClassName = Literal["person", "surfboard"]
CLASS_INDEX: dict[ClassName, int] = {"person": 0, "surfboard": 1}


@dataclass(frozen=True)
class FrameDetections:
    boxes: NDArray[np.float64]  # (N, 4) x0, y0, x1, y1 in frame pixels
    scores: NDArray[np.float64]  # (N,)
    classes: NDArray[np.int64]  # (N,) CLASS_INDEX values

    def of(self, name: ClassName) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        mask = self.classes == CLASS_INDEX[name]
        return self.boxes[mask], self.scores[mask]


def _empty() -> FrameDetections:
    return FrameDetections(
        np.zeros((0, 4), np.float64), np.zeros(0, np.float64), np.zeros(0, np.int64)
    )


def _use_tiles(cfg: DetectConfig, width: int, height: int) -> bool:
    if cfg.tiling == "always":
        return True
    if cfg.tiling == "off":
        return False
    # "auto": at the detector's input size, the smallest riders (~4% of frame height in the
    # samples) shrink by imgsz / longest side; tile when they fall below the threshold.
    smallest_at_input = 0.04 * height * cfg.imgsz / max(width, height)
    return smallest_at_input < cfg.tiling_min_height_px_at_720p * cfg.imgsz / 720


class Detector:
    def __init__(self, cfg: DetectConfig, *, cpu: bool = False) -> None:
        from ultralytics import YOLO  # heavy import, kept local

        Path(cfg.model).parent.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.device = "cpu" if cpu or not torch.cuda.is_available() else "cuda:0"
        self.model: Any = YOLO(cfg.model)
        names: dict[int, str] = self.model.names
        by_name = {v: k for k, v in names.items()}
        self._yolo_ids = [by_name[c] for c in cfg.classes]
        self._to_local = {by_name[c]: CLASS_INDEX[c] for c in ("person", "surfboard")}  # type: ignore[index]

    def _predict(self, images: Sequence[Image]) -> list[FrameDetections]:
        out: list[FrameDetections] = []
        for i in range(0, len(images), self.cfg.batch_size):
            results = self.model.predict(
                list(images[i : i + self.cfg.batch_size]),
                imgsz=self.cfg.imgsz,
                classes=self._yolo_ids,
                conf=self.cfg.confidence,
                device=self.device,
                quantize=16 if self.cfg.half_precision and self.device != "cpu" else None,
                verbose=False,
            )
            for r in results:
                b = r.boxes
                cls = b.cls.cpu().numpy().astype(np.int64)
                out.append(
                    FrameDetections(
                        b.xyxy.cpu().numpy().astype(np.float64),
                        b.conf.cpu().numpy().astype(np.float64),
                        np.array([self._to_local[int(c)] for c in cls], dtype=np.int64),
                    )
                )
        return out

    def detect(self, frames: Sequence[Image]) -> list[FrameDetections]:
        if not frames:
            return []
        height, width = frames[0].shape[:2]
        full = self._predict(frames)
        if not _use_tiles(self.cfg, width, height):
            return full
        windows: list[Window] = tile_windows(width, height, self.cfg.tile_overlap_frac)
        crops = [f[y0:y1, x0:x1] for f in frames for (x0, y0, x1, y1) in windows]
        tiled = self._predict(crops)
        merged: list[FrameDetections] = []
        for fi, whole in enumerate(full):
            boxes = [whole.boxes]
            scores = [whole.scores]
            classes = [whole.classes]
            for wi, win in enumerate(windows):
                det = tiled[fi * len(windows) + wi]
                if len(det.boxes) == 0:
                    continue
                shifted = det.boxes + np.array([win[0], win[1], win[0], win[1]], np.float64)
                keep = [
                    k
                    for k in range(len(shifted))
                    if not touches_inner_border(shifted[k], win, width, height)
                ]
                boxes.append(shifted[keep])
                scores.append(det.scores[keep])
                classes.append(det.classes[keep])
            all_boxes = np.concatenate(boxes) if boxes else _empty().boxes
            all_scores = np.concatenate(scores)
            all_classes = np.concatenate(classes)
            keep_idx = merge(all_boxes, all_scores, all_classes, self.cfg.nms_iou)
            merged.append(
                FrameDetections(all_boxes[keep_idx], all_scores[keep_idx], all_classes[keep_idx])
            )
        return merged
