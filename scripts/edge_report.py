"""Share of riding frames where the rider is cut off by a frame edge, per session.

Usage: edge_report.py VIDEO [VIDEO ...] [--artifacts artifacts]
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from surfclip.config import load_config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.rides.evidence import Obs, classify, to_source_pixels
from surfclip.rides.state_machine import track_rides
from surfclip.rides.stitch import stitch
from surfclip.stages import source_scale
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import SourceInfo
from surfclip.store.session import SessionStore

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
    edges: Counter[str] = Counter()
    for obs in chains.values():
        evs = classify(obs, zone, cfg)
        states, _ = track_rides(evs, cfg)
        for ev, st in zip(evs, states, strict=True):
            if st == "on_wave":
                edges[ev.obs.edge] += 1
    total = sum(edges.values())
    cut = total - edges["none"]
    detail = ", ".join(f"{k} {v / total:.0%}" for k, v in edges.most_common() if k != "none")
    print(
        f"{video.name:26s} rider cut off by the frame in {cut / total:5.1%} of riding frames"
        f" ({detail})"
    )
