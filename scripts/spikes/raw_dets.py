import sys
from pathlib import Path

from surfclip.store.frames import read_detections
from surfclip.store.session import SessionStore

store = SessionStore.open(Path(sys.argv[1]), Path("artifacts"))
t0, t1 = float(sys.argv[2]), float(sys.argv[3])
for af in read_detections(store.path("detections.parquet")):
    if af.t < t0:
        continue
    if af.t > t1:
        break
    people, ps = af.detections.of("person")
    boards, _ = af.detections.of("surfboard")
    desc = "; ".join(
        f"P({b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f}) {s:.2f}" for b, s in zip(people, ps)
    )
    print(f"{af.t:8.1f}  boards={len(boards)}  {desc}")
