"""Describe a ride's rider by appearance (research R2 option 1 and R4).

Colour baseline: per crop, histograms of hue (weighted by saturation), saturation and value in
three regions of the padded person crop: upper body (20-50% of the box height), lower body
(50-85%) and the board under the feet (85% to the bottom of the padded crop). Crops are colour
corrected first with one grey-world gain per session (coloured LED light). A ride's descriptor is
the mean over its crops. No face is used: the head (top 20%) is left out.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
Image = NDArray[np.uint8]

PAD = 0.15  # crops are padded by this share of the box height on every side (see crops.py)
# Region rows as shares of the *box* height (0 = top of box, 1 = feet).
REGIONS: tuple[tuple[str, float, float], ...] = (
    ("upper", 0.20, 0.50),
    ("lower", 0.50, 0.85),
    ("board", 0.85, 1.0 + PAD),
)
H_BINS, S_BINS, V_BINS = 8, 4, 4
REGION_LEN = H_BINS + S_BINS + V_BINS
DESC_LEN = REGION_LEN * len(REGIONS)
STRONG_TINT = 1.5  # max/min grey-world gain above this: hue is down-weighted


def grey_world_gains(frames: Sequence[Image]) -> FloatArray:
    """Per-channel (B, G, R) gains that make the session's average colour grey."""
    if not frames:
        return np.ones(3)
    means: FloatArray = np.asarray(
        np.mean([f.reshape(-1, 3).mean(axis=0) for f in frames], axis=0), dtype=np.float64
    )
    means = np.maximum(means, 1.0)
    return float(means.mean()) / means


def hue_weight(gains: FloatArray) -> float:
    """Trust hue less under a strong colour cast (night LED)."""
    return 0.4 if float(gains.max() / gains.min()) > STRONG_TINT else 1.0


def _region_hist(hsv: Image) -> FloatArray:
    if hsv.size == 0:
        return np.zeros(REGION_LEN)
    px = hsv.reshape(-1, 3).astype(np.float64)
    h, s, v = px[:, 0], px[:, 1], px[:, 2]
    weight = s / 255.0  # grey pixels carry no hue information
    hh = np.histogram(h, bins=H_BINS, range=(0, 180), weights=weight)[0]
    sh = np.histogram(s, bins=S_BINS, range=(0, 256))[0].astype(np.float64)
    vh = np.histogram(v, bins=V_BINS, range=(0, 256))[0].astype(np.float64)
    parts = [x / x.sum() if x.sum() > 0 else x for x in (hh, sh, vh)]
    return np.concatenate(parts)


def colour_descriptor(crop: Image, gains: FloatArray) -> FloatArray:
    """Descriptor of one padded person crop (BGR), after the session's colour correction."""
    corrected = np.clip(crop.astype(np.float64) * gains, 0, 255).astype(np.uint8)
    hsv: Image = np.asarray(cv2.cvtColor(corrected, cv2.COLOR_BGR2HSV), dtype=np.uint8)
    height = hsv.shape[0]
    box_h = height / (1 + 2 * PAD)  # crop height = box height padded on both sides
    top = PAD * box_h
    out: list[FloatArray] = []
    for _, a, b in REGIONS:
        y0 = round(top + a * box_h)
        y1 = round(min(height, top + b * box_h))
        out.append(_region_hist(hsv[y0:y1]))
    return np.concatenate(out)


def colour_distance(a: FloatArray, b: FloatArray, hue_w: float = 1.0) -> float:
    """0 (same colours) .. 1 (nothing in common): 1 - histogram intersection, per part."""
    total = 0.0
    weight = 0.0
    for r in range(len(REGIONS)):
        base = r * REGION_LEN
        for lo, hi, w in (
            (0, H_BINS, hue_w),
            (H_BINS, H_BINS + S_BINS, 0.5),
            (H_BINS + S_BINS, REGION_LEN, 0.5),
        ):
            pa, pb = a[base + lo : base + hi], b[base + lo : base + hi]
            if pa.sum() == 0 or pb.sum() == 0:
                continue  # region missing (e.g. no colour in it)
            total += w * (1.0 - float(np.minimum(pa, pb).sum()))
            weight += w
    return total / weight if weight else 1.0


@dataclass(frozen=True)
class RideDescriptor:
    ride_id: str
    vector: FloatArray
    crops: int
    low_evidence: bool
    clarity: float  # median crop height x sharpness rank: picks the clearest example ride


def ride_descriptor(
    ride_id: str, crops: Sequence[FloatArray], heights: Sequence[float], min_crops: int
) -> RideDescriptor:
    if not crops:
        return RideDescriptor(ride_id, np.zeros(DESC_LEN), 0, True, 0.0)
    return RideDescriptor(
        ride_id,
        np.mean(np.array(crops), axis=0),
        len(crops),
        len(crops) < min_crops,
        float(np.median(heights)),
    )


# --- pretrained embedding (research R2 option 2) --------------------------------------------

EMBED_H, EMBED_W = 224, 112  # crops are resized to this (multiples of the 14 px ViT patch)
_MEAN = np.array([0.485, 0.456, 0.406])
_STD = np.array([0.229, 0.224, 0.225])


def download_embedder() -> Path:
    """Fetch DINOv2 ViT-S/14 code and weights into the torch hub cache (network, once)."""
    import torch

    hub_api: Any = torch.hub
    hub_api.load("facebookresearch/dinov2", "dinov2_vits14", trust_repo=True)
    return Path(torch.hub.get_dir()) / "facebookresearch_dinov2_main"


class Embedder:
    """DINOv2 ViT-S/14 image embeddings of person crops, loaded from the local torch hub cache
    only (fetched once by `surfclip models download`; never downloaded while processing)."""

    def __init__(self, cpu: bool = False) -> None:
        import torch

        hub = Path(torch.hub.get_dir()) / "facebookresearch_dinov2_main"
        if not hub.is_dir():
            raise RuntimeError(
                "DINOv2 weights are not downloaded: run `surfclip models download` once"
            )
        self.torch: Any = torch
        self.device = "cuda" if torch.cuda.is_available() and not cpu else "cpu"
        hub_api: Any = torch.hub
        model: Any = hub_api.load(str(hub), "dinov2_vits14", source="local")
        self.model = model.to(self.device).eval()

    def embed(self, crops: Sequence[Image], gains: FloatArray, batch: int = 64) -> FloatArray:
        """One L2-normalised vector per crop (colour corrected like the colour descriptor)."""
        if not crops:
            return np.zeros((0, 384))
        out: list[FloatArray] = []
        for i in range(0, len(crops), batch):
            imgs: list[FloatArray] = []
            for crop in crops[i : i + batch]:
                fixed = np.clip(crop.astype(np.float64) * gains, 0, 255).astype(np.uint8)
                rgb = cv2.cvtColor(cv2.resize(fixed, (EMBED_W, EMBED_H)), cv2.COLOR_BGR2RGB)
                pixels = np.asarray(rgb, dtype=np.float64) / 255.0
                imgs.append((pixels - _MEAN) / _STD)
            x = self.torch.tensor(np.array(imgs), dtype=self.torch.float32).permute(0, 3, 1, 2)
            with self.torch.no_grad():
                feats: FloatArray = np.asarray(
                    self.model(x.to(self.device)).cpu().numpy(), dtype=np.float64
                )
            out.append(feats / np.maximum(np.linalg.norm(feats, axis=1, keepdims=True), 1e-9))
        return np.concatenate(out)


def cosine_distance(a: FloatArray, b: FloatArray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - float(a @ b) / (na * nb)
