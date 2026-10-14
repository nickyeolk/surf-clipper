"""Draw tracked people (id, board, stance, region) and the zone on frames, for debugging.

Usage: draw_tracks.py VIDEO SECONDS [SECONDS ...] [--artifacts artifacts]
Writes artifacts/review/tracks_<video>_<t>.jpg
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from surfclip.config import load_config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.media.decode import iter_proxy_frames
from surfclip.rides.evidence import classify, to_source_pixels
from surfclip.stages import source_scale
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import SourceInfo
from surfclip.store.session import SessionStore
from surfclip.zone.geometry import PoolMapping

COLOURS = {"zone": (0, 220, 0), "side_wall": (0, 200, 255), "outside": (160, 160, 160)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("times", type=float, nargs="+")
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    store = SessionStore.open(args.video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides)
    info = store.read_model("probe.json", SourceInfo)
    zone = confirmed_zone(read_edits(store))
    assert zone is not None
    mapping = PoolMapping.from_corners(zone.corners)
    tracks_file = store.path("tracks.parquet")
    sx, sy = source_scale(info, read_meta(tracks_file))
    obs = read_observations(tracks_file)  # analysis-frame pixels, as drawn
    for t in args.times:
        frame = next(iter_proxy_frames(info, fps=5, max_height=720, start_s=t, duration_s=0.3))
        img = frame.image.copy()
        quad = mapping.to_image(np.array([(0, 0), (1, 0), (1, 1), (0, 1)], dtype=float))
        quad = quad / np.array([sx, sy])  # zone is in source pixels
        cv2.polylines(img, [quad.astype(np.int32)], True, (255, 255, 0), 2)
        here = [o for o in obs if abs(o.t - frame.pts_s) < 0.11]
        evs = classify(to_source_pixels(here, sx, sy), zone, cfg.rides)
        for o, ev in zip(sorted(here, key=lambda x: x.t), evs, strict=True):
            colour = COLOURS[ev.region]
            x0, y0, x1, y1 = (int(v) for v in o.box)
            cv2.rectangle(img, (x0, y0), (x1, y1), colour, 3 if ev.candidate else 1)
            label = f"#{o.track_id} {o.stance[:2]}{' B' if o.board else ''} u{ev.u:.2f}"
            cv2.putText(
                img,
                label,
                (x0, max(15, y0 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                colour,
                1,
                cv2.LINE_AA,
            )
        cv2.putText(
            img,
            f"t={frame.pts_s:.1f}s  thick = riding candidate",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        out = store.path("../review").resolve() / f"tracks_{args.video.stem}_{int(t)}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), img)
        print(out)


if __name__ == "__main__":
    main()
