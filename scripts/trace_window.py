"""Print every observation in a time window with its evidence, chain by chain.

Usage: trace_window.py VIDEO START_S END_S [--artifacts artifacts]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from surfclip.config import load_config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.rides.evidence import Obs, classify
from surfclip.rides.stitch import stitch
from surfclip.store.frames import read_observations
from surfclip.store.session import SessionStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    store = SessionStore.open(args.video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides).rides
    zone = confirmed_zone(read_edits(store))
    assert zone is not None
    by_track: dict[int, list[Obs]] = defaultdict(list)
    for o in read_observations(store.path("tracks.parquet")):
        if args.start - 5 <= o.t <= args.end + 5:
            by_track[o.track_id].append(o)
    chains, members = stitch(list(by_track.values()), cfg)
    for cid, obs in sorted(chains.items(), key=lambda kv: kv[1][0].t):
        evs = [e for e in classify(obs, zone, cfg) if args.start <= e.t <= args.end]
        if not evs:
            continue
        print(f"chain {cid} fragments {members[cid]}")
        for e in evs:
            o = e.obs
            flag = "RIDE" if e.candidate else "    "
            print(
                f"  {e.t:8.1f} {flag} {e.region:9s} u={e.u:5.2f} v={e.v:5.2f} "
                f"{o.stance:8s} board={'Y' if o.board else '-'} h={o.box_height:4.0f} "
                f"edge={o.edge} s={o.score:.2f}"
            )


if __name__ == "__main__":
    main()
