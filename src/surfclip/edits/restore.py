"""Deleted rides and restoring them (Review's "deleted rides" list).

A deleted ride stays a ``delete`` edit in edits.json; restoring it appends an ``undo`` of that
edit, so nothing is erased and a restore can itself be undone. Only deletes are undone: splits,
trims and merges made around them stay.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from surfclip.edits.apply import undone_ids
from surfclip.edits.log import append_edit, read_edits
from surfclip.store.schemas import Edits, EditTarget
from surfclip.store.session import SessionStore


class DeletedRide(BaseModel):
    edit_id: int
    ride_id: str
    start_s: float | None  # where the ride was when deleted (None for very old edits)
    end_s: float | None
    at: datetime


def deleted_rides(edits: Edits) -> list[DeletedRide]:
    """Rides deleted and not restored, in time order."""
    undone = undone_ids(edits)
    out: list[DeletedRide] = []
    for e in edits.edits:
        if e.op != "delete" or e.edit_id in undone:
            continue
        raw = e.payload.get("spans")
        spans: dict[str, object] = raw if isinstance(raw, dict) else {}  # pyright: ignore[reportUnknownVariableType]
        for rid in e.target.ride_ids or ([e.target.ride_id] if e.target.ride_id else []):
            span = spans.get(rid)
            start, end = (
                (float(span[0]), float(span[1]))  # pyright: ignore[reportUnknownArgumentType]
                if isinstance(span, list | tuple) and len(span) == 2  # pyright: ignore[reportUnknownArgumentType]
                else (None, None)
            )
            out.append(
                DeletedRide(edit_id=e.edit_id, ride_id=rid, start_s=start, end_s=end, at=e.at)
            )
    return sorted(out, key=lambda d: (d.start_s is None, d.start_s or 0.0))


def restore_deleted(store: SessionStore, edit_ids: list[int] | None = None) -> list[int]:
    """Append an undo for each given delete edit (all deleted rides when None).

    Returns the restored edit ids. Raises KeyError for an id that is not an active delete."""
    active = {d.edit_id for d in deleted_rides(read_edits(store))}
    wanted = sorted(active) if edit_ids is None else list(dict.fromkeys(edit_ids))
    missing = [i for i in wanted if i not in active]
    if missing:
        raise KeyError(missing)
    for i in wanted:
        append_edit(store, "undo", EditTarget(), {"edit_id": i, "how": "restore"})
    return wanted
