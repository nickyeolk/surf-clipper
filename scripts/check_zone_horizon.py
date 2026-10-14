"""Check whether a zone's perspective mapping folds inside the frame.

The image-to-pool homography sends a line (the zone's "horizon") to infinity. For a physically
plausible zone that line lies outside the visible water; if it crosses the frame, points on
its far side map to bogus pool coordinates. Prints the share of the frame on the far side.

Usage: check_zone_horizon.py ZONE.json WIDTH HEIGHT
"""

import sys
from pathlib import Path

import numpy as np

from surfclip.store.schemas import Zone
from surfclip.zone.geometry import PoolMapping

zone = Zone.model_validate_json(Path(sys.argv[1]).read_text())
w, h = int(sys.argv[2]), int(sys.argv[3])
m = PoolMapping.from_corners(zone.corners).image_to_pool
xs, ys = np.meshgrid(np.linspace(0, w, 200), np.linspace(0, h, 200))
denom = m[2, 0] * xs + m[2, 1] * ys + m[2, 2]
corner = np.array(zone.corners.back_a + (1.0,))
sign = np.sign(m[2] @ corner)
folded = np.mean(np.sign(denom) != sign)
print(f"{Path(sys.argv[1]).stem}: {folded:.1%} of the frame is beyond the zone's horizon")
