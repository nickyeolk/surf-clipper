"""Draw a zone (corners by role, pool grid) over a keyframe for review.

Usage: draw_zone.py KEYFRAME.jpg ZONE.json OUT.jpg [FACE.json]
ZONE.json holds a schema Zone (corners may lie outside the frame).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

from surfclip.store.schemas import Zone
from surfclip.zone.geometry import PoolMapping

ROLE_COLOURS = {
    "back_a": (255, 120, 0),
    "back_b": (255, 120, 0),
    "front_a": (255, 200, 80),
    "front_b": (255, 200, 80),
}


def main() -> None:
    img = cv2.imread(sys.argv[1])
    zone = Zone.model_validate_json(Path(sys.argv[2]).read_text())
    mapping = PoolMapping.from_corners(zone.corners)
    h, w = img.shape[:2]
    pad = 400
    canvas = np.full((h + 2 * pad, w + 2 * pad, 3), 40, np.uint8)
    canvas[pad : pad + h, pad : pad + w] = img

    def px(p: np.ndarray) -> tuple[int, int]:
        return int(p[0]) + pad, int(p[1]) + pad

    overlay = canvas.copy()
    for i in range(11):  # pool grid: u lines (along the wave) and v lines (from the back wall)
        t = i / 10
        for line in (np.array([(t, 0), (t, 1)]), np.array([(0, t), (1, t)])):
            pts = mapping.to_image(np.linspace(line[0], line[1], 40))
            cv2.polylines(overlay, [np.array([px(p) for p in pts])], False, (255, 255, 255), 1)
    walls = {
        "back": ((0, 0), (1, 0), (160, 160, 160)),
        "side_a": ((0, 0), (0, 1), (0, 200, 255)),
        "side_b": ((1, 0), (1, 1), (0, 200, 255)),
    }
    for name, (a, b, colour) in walls.items():
        if name.startswith("side") and name not in zone.entry_walls:
            colour = (160, 160, 160)
        pts = mapping.to_image(np.linspace(a, b, 40))
        cv2.polylines(overlay, [np.array([px(p) for p in pts])], False, colour, 5)
    if len(sys.argv) > 4:  # face.json from a processed session: shade the wave-face band
        face = json.loads(Path(sys.argv[4]).read_text()).get("face_v")
        if face:
            lo, hi = face
            band = np.vstack([np.linspace((0, lo), (1, lo), 40), np.linspace((1, hi), (0, hi), 40)])
            poly = np.array([px(p) for p in mapping.to_image(band)], dtype=np.int32)
            cv2.fillPoly(overlay, [poly], (80, 200, 80))
    canvas = cv2.addWeighted(overlay, 0.6, canvas, 0.4, 0)
    for role, colour in ROLE_COLOURS.items():
        p = np.array(getattr(zone.corners, role), dtype=float)
        cv2.circle(canvas, px(p), 10, colour, -1)
        cv2.putText(
            canvas,
            role,
            (px(p)[0] + 12, px(p)[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            colour,
            2,
            cv2.LINE_AA,
        )
    cv2.rectangle(canvas, (pad, pad), (pad + w, pad + h), (200, 200, 200), 1)
    cv2.putText(
        canvas,
        "orange = entry side walls, grey = back wall, green = wave face",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (230, 230, 230),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(sys.argv[3], canvas)


if __name__ == "__main__":
    main()
