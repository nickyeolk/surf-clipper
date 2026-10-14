"""Plot riders' feet (on-wave frames, and other riding candidates) over the zone overlay.

Usage: feet_map.py VIDEO KEYFRAME.jpg OUT.jpg [--artifacts artifacts]
Feet are in source pixels, like the zone; the keyframe must be a full-resolution still.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from surfclip.config import load_config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.rides.evidence import Obs, classify, to_source_pixels
from surfclip.rides.state_machine import track_rides
from surfclip.rides.stitch import stitch
from surfclip.stages import source_scale
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import SourceInfo
from surfclip.store.session import SessionStore
from surfclip.zone.geometry import PoolMapping


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("keyframe", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    store = SessionStore.open(args.video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides).rides
    zone = confirmed_zone(read_edits(store))
    assert zone is not None
    tf = store.path("tracks.parquet")
    sx, sy = source_scale(store.read_model("probe.json", SourceInfo), read_meta(tf))
    by: dict[int, list[Obs]] = defaultdict(list)
    for o in to_source_pixels(read_observations(tf), sx, sy):
        by[o.track_id].append(o)
    chains, _ = stitch(list(by.values()), cfg)

    img = cv2.imread(str(args.keyframe))
    h, w = img.shape[:2]
    pad = 500
    canvas = np.full((h + 2 * pad, w + 2 * pad, 3), 30, np.uint8)
    canvas[pad : pad + h, pad : pad + w] = (img * 0.55).astype(np.uint8)
    dots = canvas.copy()
    for obs in chains.values():
        evs = classify(obs, zone, cfg)
        states, _ = track_rides(evs, cfg)
        for o, ev, st in zip(sorted(obs, key=lambda x: x.t), evs, states, strict=True):
            if not (ev.candidate or (o.board and o.stance != "sitting")):
                continue
            colour = (80, 220, 80) if st == "on_wave" else (60, 160, 255)
            cv2.circle(dots, (int(o.feet[0]) + pad, int(o.feet[1]) + pad), 3, colour, -1)
    canvas = cv2.addWeighted(dots, 0.35, canvas, 0.65, 0)
    mapping = PoolMapping.from_corners(zone.corners)
    for t in np.linspace(0, 1, 11):
        for a, b in (((t, 0), (t, 1)), ((0, t), (1, t))):
            pts = mapping.to_image(np.linspace(a, b, 40)) + pad
            cv2.polylines(canvas, [pts.astype(np.int32)], False, (220, 220, 220), 1)
    edge = mapping.to_image(np.linspace((0, 1), (1, 1), 40)) + pad
    cv2.polylines(canvas, [edge.astype(np.int32)], False, (0, 0, 255), 3)
    cv2.rectangle(canvas, (pad, pad), (pad + w, pad + h), (200, 200, 200), 1)
    cv2.putText(
        canvas,
        "green = on-wave feet, orange = other board/standing feet, red = zone front",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (230, 230, 230),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(args.out), canvas)
    print(args.out)


if __name__ == "__main__":
    main()
