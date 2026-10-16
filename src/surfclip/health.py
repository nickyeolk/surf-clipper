"""What the UI needs to know at start (003 research R6): GPU, encoder and model weights.

Checks are cheap and cached per server start, except the model files, which the user can
download from the UI while the server runs.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel

from surfclip.config import Config


class Models(BaseModel):
    detector: bool
    embedder: bool


class Health(BaseModel):
    ok: bool = True
    version: str
    gpu: bool
    encoder: str  # "nvenc" | "cpu"
    models: Models


@functools.cache
def gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and b"GPU" in out.stdout


@functools.cache
def nvenc() -> bool:
    """One tiny NVENC encode: the driver, the GPU and ffmpeg's build all have to agree."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=size=256x256",
           "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"]  # fmt: skip
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def torch_hub_dir() -> Path:
    """torch.hub.get_dir() without importing torch."""
    home = os.environ.get("TORCH_HOME") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "torch"
    )
    return Path(home) / "hub"


def models(cfg: Config) -> Models:
    hub = torch_hub_dir()
    embedder = (hub / "facebookresearch_dinov2_main").is_dir() and any(
        (hub / "checkpoints").glob("dinov2_vits14*.pth")
    )
    return Models(
        detector=Path(cfg.detect.model).is_file(),
        embedder=embedder or cfg.riders.descriptor == "colour",
    )


def health(cfg: Config) -> Health:
    try:
        ver = version("surfclip")
    except PackageNotFoundError:
        ver = "dev"
    encoder = "nvenc" if cfg.export.encoder != "cpu" and nvenc() else "cpu"
    return Health(version=ver, gpu=gpu(), encoder=encoder, models=models(cfg))
