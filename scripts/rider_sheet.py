"""Contact sheet of a session's rider groups: one row per group, a still per ride.

Usage: rider_sheet.py VIDEO OUT.jpg [--groups 8] [--per-group 10] [--artifacts artifacts]
Reads riders.json; stills come from the review copy (cached in the session's stills/ folder).
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from surfclip.riders.stills import STILL_HEIGHT, rider_still
from surfclip.stages import session_observations
from surfclip.store.schemas import Riders, Rides
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("video", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--groups", type=int, default=8)
ap.add_argument("--per-group", type=int, default=10)
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()
store = SessionStore.open(args.video, args.artifacts)
riders = store.read_model("riders.json", Riders)
rides = {r.ride_id: r for r in store.read_model("rides.json", Rides).rides}
obs = session_observations(store)
W = 110
rows = []
for g in riders.riders[: args.groups]:
    tiles = []
    for rid in g.ride_ids[: args.per_group]:
        ride = rides[rid]
        got = rider_still(store, ride, (ride.start_s + ride.end_s) / 2, obs)
        tile = np.full((STILL_HEIGHT, W, 3), 30, np.uint8)
        if got:
            img = cv2.imdecode(np.frombuffer(got[0], np.uint8), cv2.IMREAD_COLOR)
            img = img[:, :W] if img.shape[1] > W else img
            tile[:, : img.shape[1]] = img
        tiles.append(tile)
    tiles += [np.full((STILL_HEIGHT, W, 3), 30, np.uint8)] * (args.per_group - len(tiles))
    label = np.full((STILL_HEIGHT, 90, 3), 30, np.uint8)
    cv2.putText(label, f"{g.rider_id}", (6, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(
        label,
        f"{len(g.ride_ids)} rides",
        (6, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (200, 200, 200),
        1,
    )
    rows.append(np.hstack([label, *tiles]))
cv2.imwrite(str(args.out), np.vstack(rows))
print(f"wrote {args.out}")
