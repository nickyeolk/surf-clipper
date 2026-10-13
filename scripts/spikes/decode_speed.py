"""Time the analysis proxy decode (frames are discarded). Usage: decode_speed.py SRC [minutes]"""

import sys
import time
from pathlib import Path

from surfclip.media.decode import iter_proxy_frames
from surfclip.media.probe import probe

info = probe(Path(sys.argv[1]))
minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 5
t0 = time.perf_counter()
n = sum(1 for _ in iter_proxy_frames(info, fps=5, max_height=720, duration_s=minutes * 60))
secs = time.perf_counter() - t0
print(f"{n} frames in {secs:.1f}s -> {secs * 60 / minutes / 60:.1f} min per hour")
