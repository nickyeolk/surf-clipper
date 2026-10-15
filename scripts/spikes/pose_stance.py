"""Spike: box-shape stance vs pose keypoints on riders, as a contact sheet to judge by eye.

Usage: pose_stance.py VIDEO OUT.jpg [--n 36] [--seed 0] [--artifacts artifacts]
Samples riding moments from detected rides, crops each rider from the full-resolution source,
runs YOLO11s-pose on the crop and labels the tile with the box-shape stance and the knee angle
(hip-knee-ankle, 180 = straight leg) of the better-seen leg.
"""

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from surfclip.stages import session_observations
from surfclip.store.schemas import Rides, SourceInfo
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("video", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--n", type=int, default=36)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()

store = SessionStore.open(args.video, args.artifacts)
info = store.read_model("probe.json", SourceInfo)
rides = store.read_model("rides.detected.json", Rides).rides
obs = session_observations(store)
by_track: dict[int, list] = {}
for o in obs:
    by_track.setdefault(o.track_id, []).append(o)
rng = np.random.default_rng(args.seed)
picks = []
for r in rng.permutation(len(rides))[: args.n]:
    ride = rides[int(r)]
    cands = [o for t in ride.track_ids for o in by_track.get(t, []) if ride.start_s <= o.t <= ride.end_s]
    if cands:
        picks.append(cands[int(rng.integers(len(cands)))])
picks.sort(key=lambda o: o.t)

TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
)


def frame_at(t: float) -> np.ndarray:
    vf = (TONEMAP if info.hdr_format != "none" else "") + "format=bgr24"
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", info.path, "-frames:v", "1",
         "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True,
    ).stdout
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def knee_angle(kp: np.ndarray, conf: np.ndarray) -> tuple[float | None, float]:
    best: tuple[float | None, float] = (None, 0.0)
    for hip, knee, ankle in ((11, 13, 15), (12, 14, 16)):
        c = float(min(conf[hip], conf[knee], conf[ankle]))
        if c <= best[1]:
            continue
        a, b = kp[hip] - kp[knee], kp[ankle] - kp[knee]
        cos = float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-9))
        best = (float(np.degrees(np.arccos(np.clip(cos, -1, 1)))), c)
    return best


model = YOLO("artifacts/models/yolo11s-pose.pt")
tiles = []
TILE = 220
for o in picks:
    img = frame_at(o.t)
    x0, y0, x1, y1 = o.box
    h = y1 - y0
    m = 0.25 * h
    cx0, cy0 = int(max(0, x0 - m)), int(max(0, y0 - m))
    cx1, cy1 = int(min(img.shape[1], x1 + m)), int(min(img.shape[0], y1 + m))
    crop = img[cy0:cy1, cx0:cx1].copy()
    res = model.predict(crop, imgsz=320, conf=0.25, verbose=False)[0]
    label = "no pose"
    if res.keypoints is not None and len(res.keypoints) > 0:
        i = int(np.argmax(res.boxes.conf.cpu().numpy()))
        kp = res.keypoints.xy[i].cpu().numpy()
        kc = res.keypoints.conf[i].cpu().numpy()
        ang, c = knee_angle(kp, kc)
        if ang is not None and c >= 0.3:
            label = f"knee {ang:.0f}"
        else:
            label = f"legs unclear ({c:.1f})"
        for (x, y), cc in zip(kp, kc, strict=True):
            if cc >= 0.3:
                cv2.circle(crop, (int(x), int(y)), max(2, int(h / 60)), (0, 255, 255), -1)
    scale = TILE / max(crop.shape[:2])
    crop = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))))
    tile = np.full((TILE + 44, TILE, 3), 24, np.uint8)
    tile[: crop.shape[0], : crop.shape[1]] = crop
    aspect = h / max(x1 - x0, 1)
    cv2.putText(tile, f"box: {o.stance} ({aspect:.2f})", (4, TILE + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(tile, f"pose: {label}", (4, TILE + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 220, 255), 1)
    tiles.append(tile)

cols = 6
rows = [np.hstack(tiles[i : i + cols] + [np.full_like(tiles[0], 24)] * (cols - len(tiles[i : i + cols])))
        for i in range(0, len(tiles), cols)]
cv2.imwrite(str(args.out), np.vstack(rows))
print(f"wrote {args.out} ({len(tiles)} riders)")
