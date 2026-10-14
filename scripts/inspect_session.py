"""Diagnostics for a processed session: tracks, evidence and short attempts.

Usage: inspect_session.py VIDEO [--artifacts artifacts]
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from surfclip.config import load_config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.rides.evidence import Obs, classify, to_source_pixels
from surfclip.stages import source_scale
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import Rides, SourceInfo
from surfclip.store.session import SessionStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    store = SessionStore.open(args.video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides)
    meta = read_meta(store.path("tracks.parquet"))
    info = store.read_model("probe.json", SourceInfo)
    sx, sy = source_scale(info, meta)
    obs = to_source_pixels(read_observations(store.path("tracks.parquet")), sx, sy)
    print(f"frame {meta.width}x{meta.height} @ {meta.fps} fps; {len(obs)} observations")
    ts = np.array([o.t for o in obs])
    print(f"time range {ts.min():.1f}..{ts.max():.1f} s")
    by_track: dict[int, list[Obs]] = defaultdict(list)
    for o in obs:
        by_track[o.track_id].append(o)
    lens = np.array([t[-1].t - t[0].t for t in by_track.values()])
    print(
        f"{len(by_track)} tracks; duration median {np.median(lens):.1f}s, "
        f"p90 {np.percentile(lens, 90):.1f}s, max {lens.max():.1f}s"
    )
    print("stance:", Counter(o.stance for o in obs).most_common())
    print("edge:", Counter(o.edge for o in obs).most_common())
    print(f"board under feet: {np.mean([o.board for o in obs]):.1%} of observations")
    zone = confirmed_zone(read_edits(store))
    assert zone is not None
    evs = [e for t in by_track.values() for e in classify(t, zone, cfg.rides)]
    print("region:", Counter(e.region for e in evs).most_common())
    cand = [e for e in evs if e.candidate]
    print(f"candidates: {len(cand)} ({len(cand) / max(1, len(evs)):.1%})")
    hist = np.histogram([e.t for e in cand], bins=12, range=(0, ts.max()))[0]
    print("candidates per 5-min bin:", hist.tolist())
    rides = store.read_model("rides.json", Rides)
    sl = np.array([s.end_s - s.start_s for s in rides.short_attempts])
    if len(sl):
        print(f"short attempts: {len(sl)}; length median {np.median(sl):.1f}s, max {sl.max():.1f}s")
        st = np.histogram([s.start_s for s in rides.short_attempts], bins=12, range=(0, ts.max()))[
            0
        ]
        print("short attempts per 5-min bin:", st.tolist())


if __name__ == "__main__":
    main()
