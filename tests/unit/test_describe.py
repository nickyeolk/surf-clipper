"""T005: colour descriptor of rider crops."""

import numpy as np

from surfclip.riders.describe import (
    PAD,
    colour_descriptor,
    colour_distance,
    grey_world_gains,
    hue_weight,
    ride_descriptor,
)

BGR = {
    "red": (30, 30, 200),
    "blue": (200, 60, 30),
    "white": (230, 230, 230),
    "skin": (120, 150, 200),
}


def rider(top: str, bottom: str, board: str = "white", box_h: int = 100) -> np.ndarray:
    """A padded crop: head (skin), top colour, shorts colour, board under the feet."""
    h = round(box_h * (1 + 2 * PAD))
    img = np.full((h, 40, 3), 90, np.uint8)
    top0 = int(PAD * box_h)

    def band(a: float, b: float, colour: str) -> None:
        img[top0 + int(a * box_h) : top0 + int(b * box_h), 10:30] = BGR[colour]

    band(0.0, 0.2, "skin")
    band(0.2, 0.5, top)
    band(0.5, 0.85, bottom)
    band(0.85, 1.0 + PAD, board)
    return img


def test_different_outfits_are_far_apart() -> None:
    g = np.ones(3)
    a = colour_descriptor(rider("red", "blue"), g)
    b = colour_descriptor(rider("blue", "red"), g)
    a2 = colour_descriptor(rider("red", "blue", box_h=60), g)  # same outfit, smaller rider
    same, swapped = colour_distance(a, a2), colour_distance(a, b)
    assert same < 0.15
    assert swapped > 0.3 and swapped > 3 * same  # same board and brightness: hue decides


def test_colour_cast_is_corrected_per_session() -> None:
    plain = rider("red", "blue")
    cast = np.clip(plain.astype(np.float64) * np.array([1.0, 0.7, 1.5]), 0, 255).astype(np.uint8)
    gains = grey_world_gains([cast])
    assert hue_weight(gains) < 1.0  # strong tint: hue trusted less
    d_raw = colour_distance(
        colour_descriptor(plain, np.ones(3)), colour_descriptor(cast, np.ones(3))
    )
    d_fix = colour_distance(
        colour_descriptor(plain, grey_world_gains([plain])), colour_descriptor(cast, gains)
    )
    assert d_fix < d_raw


def test_low_evidence_ride() -> None:
    d = colour_descriptor(rider("red", "blue"), np.ones(3))
    assert ride_descriptor("r1", [d, d], [80, 80], min_crops=3).low_evidence
    assert not ride_descriptor("r1", [d, d, d], [80, 80, 80], min_crops=3).low_evidence
    assert ride_descriptor("r1", [], [], min_crops=3).crops == 0
