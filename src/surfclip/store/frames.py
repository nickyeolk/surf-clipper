"""Per-frame stage files: detections.parquet and tracks.parquet (internal, research R9).

Both are written incrementally, so an hour of video never sits in memory. Frame size and
analysis rate are kept in the Parquet schema metadata.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Any, cast

import numpy as np
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]

from surfclip.detect.detector import FrameDetections
from surfclip.rides.evidence import Edge, Obs, Stance
from surfclip.track.tracker import AnalysedFrame

# pyarrow ships no type information: treat it as untyped here, at the storage boundary.
pa: Any = _pyarrow
pq: Any = _parquet

_BATCH = 2000


@dataclass(frozen=True)
class FrameMeta:
    width: int
    height: int
    fps: float  # analysis rate


_DET_SCHEMA = pa.schema(
    [
        ("t", pa.float64()),
        ("frame", pa.int64()),
        ("cls", pa.int8()),
        ("score", pa.float32()),
        ("x0", pa.float32()),
        ("y0", pa.float32()),
        ("x1", pa.float32()),
        ("y1", pa.float32()),
    ]
)

_OBS_SCHEMA = pa.schema(
    [
        ("t", pa.float64()),
        ("frame", pa.int64()),
        ("track_id", pa.int64()),
        ("x0", pa.float32()),
        ("y0", pa.float32()),
        ("x1", pa.float32()),
        ("y1", pa.float32()),
        ("feet_x", pa.float32()),
        ("feet_y", pa.float32()),
        ("score", pa.float32()),
        ("board", pa.bool_()),
        ("stance", pa.string()),
        ("edge", pa.string()),
    ]
)


def _with_meta(schema: Any, meta: FrameMeta) -> Any:
    return schema.with_metadata({"surfclip": json.dumps(meta.__dict__)})


def read_meta(path: Path) -> FrameMeta:
    raw = cast(dict[bytes, bytes], pq.read_schema(path).metadata or {})
    return FrameMeta(**json.loads(raw[b"surfclip"]))


def _write(path: Path, schema: Any, rows: Iterable[dict[str, object]]) -> int:
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    with pq.ParquetWriter(tmp, schema) as writer:
        batch: list[dict[str, object]] = []
        for row in rows:
            batch.append(row)
            if len(batch) >= _BATCH:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                n += len(batch)
                batch = []
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            n += len(batch)
    tmp.replace(path)
    return n


def write_detections(path: Path, frames: Iterable[AnalysedFrame], meta: FrameMeta) -> int:
    """Write every analysed frame; a frame with no detections gets one row with cls = -1."""

    def rows() -> Iterator[dict[str, object]]:
        for af in frames:
            d = af.detections
            if len(d.boxes) == 0:
                yield {
                    "t": af.t,
                    "frame": af.frame,
                    "cls": -1,
                    "score": 0.0,
                    "x0": 0.0,
                    "y0": 0.0,
                    "x1": 0.0,
                    "y1": 0.0,
                }
            for box, score, cls in zip(d.boxes, d.scores, d.classes, strict=True):
                yield {
                    "t": af.t,
                    "frame": af.frame,
                    "cls": int(cls),
                    "score": float(score),
                    "x0": float(box[0]),
                    "y0": float(box[1]),
                    "x1": float(box[2]),
                    "y1": float(box[3]),
                }

    return _write(path, _with_meta(_DET_SCHEMA, meta), rows())


def read_detections(path: Path) -> Iterator[AnalysedFrame]:
    for batch in pq.ParquetFile(path).iter_batches(batch_size=50_000):
        rows = cast(list[dict[str, float]], batch.to_pylist())
        for (t, frame), group in groupby(rows, key=lambda r: (r["t"], r["frame"])):
            g = [r for r in group if r["cls"] >= 0]
            yield AnalysedFrame(
                t=float(t),
                frame=int(frame),
                detections=FrameDetections(
                    np.array(
                        [[r["x0"], r["y0"], r["x1"], r["y1"]] for r in g], dtype=np.float64
                    ).reshape(-1, 4),
                    np.array([r["score"] for r in g], dtype=np.float64),
                    np.array([r["cls"] for r in g], dtype=np.int64),
                ),
            )


def write_observations(path: Path, obs: Iterable[Obs], meta: FrameMeta) -> int:
    def rows() -> Iterator[dict[str, object]]:
        for o in obs:
            yield {
                "t": o.t,
                "frame": o.frame,
                "track_id": o.track_id,
                "x0": o.box[0],
                "y0": o.box[1],
                "x1": o.box[2],
                "y1": o.box[3],
                "feet_x": o.feet[0],
                "feet_y": o.feet[1],
                "score": o.score,
                "board": o.board,
                "stance": o.stance,
                "edge": o.edge,
            }

    return _write(path, _with_meta(_OBS_SCHEMA, meta), rows())


def read_observations(path: Path) -> list[Obs]:
    table = pq.read_table(path)
    out: list[Obs] = []
    rows = cast(list[dict[str, Any]], table.to_pylist())
    for r in rows:
        out.append(
            Obs(
                t=float(r["t"]),
                frame=int(r["frame"]),
                track_id=int(r["track_id"]),
                box=(float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"])),
                feet=(float(r["feet_x"]), float(r["feet_y"])),
                score=float(r["score"]),
                board=bool(r["board"]),
                stance=cast(Stance, r["stance"]),
                edge=cast(Edge, r["edge"]),
            )
        )
    return out
