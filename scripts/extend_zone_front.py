"""Suggest how far to extend a zone's front edge so it covers where people stand on boards.

Keeps the back wall and both side walls; moves front_a/front_b along the side walls to pool
depth v_max (from the 99th percentile of board-standing feet between the side walls, plus a
margin). Prints the depth distribution and, with --write, writes the adjusted zone file.

Usage: extend_zone_front.py VIDEO ZONE.json [--write OUT.json] [--artifacts artifacts]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from surfclip.rides.evidence import to_source_pixels
from surfclip.stages import source_scale
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import SourceInfo, Zone, ZoneCorners
from surfclip.store.session import SessionStore
from surfclip.zone.geometry import PoolMapping


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("zone", type=Path)
    ap.add_argument("--write", type=Path)
    ap.add_argument("--margin", type=float, default=0.05)
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    store = SessionStore.open(args.video, args.artifacts)
    zone = Zone.model_validate_json(args.zone.read_text())
    mapping = PoolMapping.from_corners(zone.corners)
    tf = store.path("tracks.parquet")
    sx, sy = source_scale(store.read_model("probe.json", SourceInfo), read_meta(tf))
    obs = [
        o
        for o in to_source_pixels(read_observations(tf), sx, sy)
        if o.board and o.stance in ("standing", "crouched")
    ]
    uv = mapping.to_pool(np.array([o.feet for o in obs]))
    in_depth = (uv[:, 1] > -0.1) & (uv[:, 1] < 1.1)
    u = uv[in_depth, 0]
    print(
        f"u (along the wave) of board-standing feet within the zone depth: "
        f"beyond side a (u<0) {np.mean(u < 0):.1%}, between {np.mean((u >= 0) & (u <= 1)):.1%}, "
        f"beyond side b (u>1) {np.mean(u > 1):.1%}; "
        f"u percentiles 1/5/95/99: {np.percentile(u, [1, 5, 95, 99]).round(2).tolist()}"
    )
    between = uv[(uv[:, 0] > 0) & (uv[:, 0] < 1) & (uv[:, 1] > -0.1)]
    v = between[:, 1]
    print(f"{len(v)} board-standing feet between the side walls")
    print(
        "v percentiles 50/90/95/99/99.5:",
        np.percentile(v, [50, 90, 95, 99, 99.5]).round(2).tolist(),
    )
    print(f"share beyond the current front (v > 1.05): {(v > 1.05).mean():.1%}")
    v_max = max(1.0, float(np.percentile(v, 99)) + args.margin)
    print(f"suggested front depth v_max = {v_max:.2f}")
    if args.write:
        fa, fb = mapping.to_image(np.array([(0.0, v_max), (1.0, v_max)]))
        corners = ZoneCorners(
            back_a=zone.corners.back_a,
            back_b=zone.corners.back_b,
            front_a=(round(float(fa[0])), round(float(fa[1]))),
            front_b=(round(float(fb[0])), round(float(fb[1]))),
        )
        out = zone.model_copy(update={"corners": corners})
        PoolMapping.from_corners(out.corners)
        args.write.write_text(out.model_dump_json(indent=2) + "\n")
        print(f"wrote {args.write}: front_a {corners.front_a}, front_b {corners.front_b}")


if __name__ == "__main__":
    main()
