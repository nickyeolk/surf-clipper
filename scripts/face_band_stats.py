"""Distribution of pool depth v for on-wave frames vs all candidate frames, per session.

Usage: face_band_stats.py VIDEO [VIDEO ...] [--artifacts artifacts]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", type=Path, nargs="+")
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    for video in args.videos:
        store = SessionStore.open(video, args.artifacts)
        cfg = load_config(overrides=store.session.config_overrides).rides
        zone = confirmed_zone(read_edits(store))
        assert zone is not None
        tf = store.path("tracks.parquet")
        sx, sy = source_scale(store.read_model("probe.json", SourceInfo), read_meta(tf))
        by: dict[int, list[Obs]] = defaultdict(list)
        for o in to_source_pixels(read_observations(tf), sx, sy):
            by[o.track_id].append(o)
        chains, _ = stitch(list(by.values()), cfg)
        on_v: list[float] = []
        cand_v: list[float] = []
        for obs in chains.values():
            evs = classify(obs, zone, cfg)
            states, _ = track_rides(evs, cfg)
            for ev, st in zip(evs, states, strict=True):
                if ev.candidate:
                    cand_v.append(ev.v)
                if st == "on_wave" and ev.candidate:
                    on_v.append(ev.v)
        on = np.array(on_v)
        pct = np.percentile(on, [1, 2, 5, 25, 50, 75, 95, 98, 99]).round(2)
        hist, edges = np.histogram(cand_v, bins=12, range=(-0.05, 1.05))
        print(
            f"{video.name}: {len(on)} on-wave frames; v percentiles 1/2/5/25/50/75/95/98/99 = "
            f"{pct.tolist()}"
        )
        print(
            "  candidate v histogram:",
            " ".join(f"{e:.2f}:{h}" for e, h in zip(edges[:-1], hist, strict=True)),
        )


if __name__ == "__main__":
    main()
