"""Multi-person tracking with ByteTrack (research R4).

Turns per-frame detections into per-person observations (``Obs``): a stable track id, the
box, the feet point, whether a board is under the feet, stance, and which frame edge the box
touches. Ride-level joining (acid drops, frame-edge returns) happens later, not here.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import numpy as np
import supervision as sv

from surfclip.config import TrackConfig
from surfclip.detect.detector import FrameDetections
from surfclip.rides.evidence import Obs
from surfclip.track.people import Box, feet_point, frame_edge, match_boards, stance


@dataclass(frozen=True)
class AnalysedFrame:
    t: float  # presentation time on the source timeline
    frame: int  # source frame number
    detections: FrameDetections


def _box(row: np.ndarray) -> Box:  # type: ignore[type-arg]
    return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))


def scale_boxes(xyxy: np.ndarray, factor: float) -> np.ndarray:  # type: ignore[type-arg]
    """Scale boxes about their centres (exactly invertible with 1 / factor)."""
    c = (xyxy[:, :2] + xyxy[:, 2:]) / 2
    half = (xyxy[:, 2:] - xyxy[:, :2]) / 2 * factor
    return np.hstack([c - half, c + half])


def track_people(
    frames: Iterable[AnalysedFrame],
    *,
    width: int,
    height: int,
    fps: float,
    cfg: TrackConfig,
    activation: float = 0.25,
) -> Iterator[Obs]:
    tracker = sv.ByteTrack(
        track_activation_threshold=activation,
        lost_track_buffer=max(1, round(cfg.max_gap_s * fps)),
        minimum_matching_threshold=cfg.match_iou,
        frame_rate=fps,
    )
    for af in frames:
        people, people_scores = af.detections.of("person")
        boards, _ = af.detections.of("surfboard")
        # Enlarged boxes for matching only: fast carving riders barely overlap between frames.
        dets = sv.Detections(
            xyxy=scale_boxes(people, cfg.assoc_box_scale).astype(np.float32),
            confidence=people_scores.astype(np.float32),
            class_id=np.zeros(len(people), dtype=int),
        )
        tracked = tracker.update_with_detections(dets)
        if len(tracked) == 0 or tracked.tracker_id is None:
            continue
        boxes = [
            _box(r) for r in scale_boxes(tracked.xyxy.astype(np.float64), 1 / cfg.assoc_box_scale)
        ]
        board_boxes = [_box(r) for r in boards]
        board_of = match_boards(boxes, board_boxes, cfg)
        scores = tracked.confidence if tracked.confidence is not None else np.ones(len(boxes))
        for k, box in enumerate(boxes):
            edge = frame_edge(box, width, height, cfg)
            bi = board_of[k]
            board = board_boxes[bi] if bi is not None else None
            yield Obs(
                t=af.t,
                frame=af.frame,
                track_id=int(tracked.tracker_id[k]),
                box=box,
                feet=feet_point(box, board, edge),
                score=float(scores[k]),
                board=board is not None,
                stance=stance(box, cfg),
                edge=edge,
            )
