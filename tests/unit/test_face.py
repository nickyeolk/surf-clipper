import numpy as np
import pytest

from surfclip.rides.face import estimate_face
from tests.unit.ride_synth import rides_cfg


def test_band_follows_the_main_cluster_not_a_few_outliers() -> None:
    rng = np.random.default_rng(0)
    face = rng.uniform(0.6, 0.95, 2000).tolist()
    whitewater = rng.uniform(0.05, 0.3, 40).tolist()  # 2%: e.g. near the back wall
    band = estimate_face(face + whitewater, rides_cfg())
    assert band.origin == "auto" and band.face_v is not None
    lo, hi = band.face_v
    assert 0.5 < lo < 0.65
    assert hi == pytest.approx(0.95 + 0.08, abs=0.02)


def test_too_little_riding_gives_no_band() -> None:
    band = estimate_face([0.5] * 50, rides_cfg())
    assert band.face_v is None and band.origin == "none"


def test_band_can_be_switched_off() -> None:
    cfg = rides_cfg()
    cfg = cfg.model_copy(update={"face_band": "off"})
    assert estimate_face([0.5] * 500, cfg).face_v is None
