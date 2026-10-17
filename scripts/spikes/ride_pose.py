"""Spike (004): is pose usable for ride analysis on this footage?

Usage: ride_pose.py VIDEO OUT_DIR [--card 1] [--rides 3] [--fps 15] [--models s,x]

For the longest rides of one rider card: decode each ride at full resolution, crop the tracked
rider (track boxes interpolated between analysis frames), run YOLO11-pose on the crop and write
  * <ride>_<model>.mp4   the crop with the skeleton, keypoints coloured by confidence
  * <ride>.png           per-frame "body height" and "leg extension" relative to the ride's own
                         95th percentile, for each model, plus share of frames each joint is seen
  * summary.txt          joint visibility per model
"""

import argparse
import subprocess
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from ultralytics import YOLO

from surfclip.stages import session_observations
from surfclip.store.schemas import Riders, Rides, SourceInfo
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("video", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--card", type=int, default=1)
ap.add_argument("--rides", type=int, default=3)
ap.add_argument("--fps", type=float, default=15)
ap.add_argument("--models", default="s,x")
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=True)

store = SessionStore.open(args.video, args.artifacts)
info = store.read_model("probe.json", SourceInfo)
rides = {r.ride_id: r for r in store.read_model("rides.json", Rides).rides}
card = store.read_model("riders.json", Riders).riders[args.card - 1]
chosen = sorted((rides[i] for i in card.ride_ids if i in rides), key=lambda r: -r.length_s)
chosen = chosen[: args.rides]
obs = session_observations(store)
by_track: dict[int, list] = {}
for o in obs:
    by_track.setdefault(o.track_id, []).append(o)

TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
)
W, H = info.width, info.height  # rotation-free sources only (PXL is landscape)
models = {m: YOLO(f"artifacts/models/yolo11{m}-pose.pt") for m in args.models.split(",")}
JOINTS = {"shoulders": (5, 6), "hips": (11, 12), "knees": (13, 14), "ankles": (15, 16)}
EDGES = [(5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (5, 7),
         (7, 9), (6, 8), (8, 10)]  # fmt: skip
summary: list[str] = []


def boxes_at(ride, times):
    pts = sorted((o for t in ride.track_ids for o in by_track.get(t, [])), key=lambda o: o.t)
    ts = np.array([o.t for o in pts])
    bx = np.array([o.box for o in pts])
    return np.stack([np.interp(times, ts, bx[:, k]) for k in range(4)], axis=1)


def frames(ride):
    vf = (TONEMAP if info.hdr_format != "none" else "") + f"fps={args.fps},format=bgr24"
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{ride.start_s:.3f}", "-i", info.path,
         "-t", f"{ride.length_s:.3f}", "-vf", vf, "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE,
    )  # fmt: skip
    n = W * H * 3
    assert p.stdout is not None
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.wait()


for ride in chosen:
    imgs = list(frames(ride))
    times = ride.start_s + np.arange(len(imgs)) / args.fps
    boxes = boxes_at(ride, times)
    curves = {}
    for name, model in models.items():
        writer = None
        body, leg, seen = [], [], {j: 0 for j in JOINTS}
        heights = []
        for img, (x0, y0, x1, y1) in zip(imgs, boxes, strict=True):
            h = y1 - y0
            m = 0.3 * h
            cx0, cy0 = int(max(0, x0 - m)), int(max(0, y0 - m))
            cx1, cy1 = int(min(W, x1 + m)), int(min(H, y1 + m))
            crop = np.ascontiguousarray(img[cy0:cy1, cx0:cx1])
            heights.append(h)
            res = model.predict(crop, imgsz=384, conf=0.2, verbose=False)[0]
            b, lg = np.nan, np.nan
            if res.keypoints is not None and len(res.keypoints) > 0:
                # the person nearest the crop centre is the tracked rider
                centres = res.boxes.xywh.cpu().numpy()[:, :2]
                i = int(
                    np.argmin(
                        np.linalg.norm(centres - [crop.shape[1] / 2, crop.shape[0] / 2], axis=1)
                    )
                )
                kp = res.keypoints.xy[i].cpu().numpy()
                kc = res.keypoints.conf[i].cpu().numpy()
                for j, (a, c) in JOINTS.items():
                    if max(kc[a], kc[c]) >= 0.5:
                        seen[j] += 1
                mid = lambda a, c: (kp[a] + kp[c]) / 2  # noqa: E731
                if min(kc[5], kc[6], kc[15], kc[16]) >= 0.3:
                    b = float(np.linalg.norm(mid(5, 6) - mid(15, 16)))
                if min(kc[11], kc[12], kc[15], kc[16]) >= 0.3:
                    lg = float(np.linalg.norm(mid(11, 12) - mid(15, 16)))
                for a, c in EDGES:
                    if min(kc[a], kc[c]) >= 0.3:
                        cv2.line(
                            crop, tuple(map(int, kp[a])), tuple(map(int, kp[c])), (0, 255, 255), 2
                        )
                for (x, y), c in zip(kp, kc, strict=True):
                    col = (0, 200, 0) if c >= 0.5 else (0, 160, 255) if c >= 0.3 else (0, 0, 255)
                    cv2.circle(crop, (int(x), int(y)), 4, col, -1)
            body.append(b)
            leg.append(lg)
            tile = np.full((480, 360, 3), 20, np.uint8)
            s = min(360 / crop.shape[1], 440 / crop.shape[0])
            small = cv2.resize(
                crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s)))
            )
            tile[: small.shape[0], : small.shape[1]] = small
            cv2.putText(tile, f"{name} t={times[len(body) - 1] - ride.start_s:5.1f}s h={h:.0f}px",
                        (6, 468), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)  # fmt: skip
            if writer is None:
                writer = cv2.VideoWriter(str(args.out / f"{ride.ride_id}_{name}.mp4"),
                                         cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (360, 480))  # fmt: skip
            writer.write(tile)
        if writer is not None:
            writer.release()
        n = len(imgs)
        rel = lambda v: np.array(v) / np.nanpercentile(v, 95)  # noqa: E731
        curves[name] = (rel(body), rel(leg))
        vis = ", ".join(f"{j} {100 * k / n:.0f}%" for j, k in seen.items())
        line = (f"{ride.ride_id} {ride.length_s:.1f}s rider {np.median(heights):.0f}px tall "
                f"[{name}] seen: {vis}; body-height valid {100 * np.mean(~np.isnan(body)):.0f}%")  # fmt: skip
        summary.append(line)
        print(line, flush=True)
    fig, axes = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
    t = times - ride.start_s
    for name, (b, lg) in curves.items():
        axes[0].plot(t, b, label=name, lw=1)
        axes[1].plot(t, lg, label=name, lw=1)
    axes[0].set_ylabel("body height\n(÷ ride p95)")
    axes[1].set_ylabel("leg extension\n(÷ ride p95)")
    axes[1].set_xlabel("seconds into ride")
    axes[0].legend()
    for ax in axes:
        ax.set_ylim(0.3, 1.3)
        ax.grid(alpha=0.3)
    fig.suptitle(f"{ride.ride_id} ({ride.length_s:.0f} s)")
    fig.tight_layout()
    fig.savefig(args.out / f"{ride.ride_id}.png", dpi=110)
    plt.close(fig)

(args.out / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
