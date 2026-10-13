"""The append-only user edit log, edits.json (constitution VI, FR-022).

Only user actions (CLI or UI) call ``append_edit``. Pipeline stages read edits and must never
import the writer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from surfclip.store.schemas import EditOp, Edits, EditTarget, UserEdit, Zone
from surfclip.store.session import SessionStore

EDITS_FILE = "edits.json"


def read_edits(store: SessionStore) -> Edits:
    if not store.path(EDITS_FILE).exists():
        return Edits()
    return store.read_model(EDITS_FILE, Edits)


def append_edit(
    store: SessionStore, op: EditOp, target: EditTarget, payload: dict[str, object]
) -> UserEdit:
    edits = read_edits(store)
    edit = UserEdit(
        edit_id=len(edits.edits) + 1,
        at=datetime.now(UTC),
        op=op,
        target=target,
        payload=payload,
    )
    edits.edits.append(edit)
    store.write_model(EDITS_FILE, edits)
    return edit


def confirmed_zone(edits: Edits, epoch_id: int = 0) -> Zone | None:
    """The most recent zone the user confirmed for an epoch."""
    for edit in reversed(edits.edits):
        if edit.op == "confirm_zone" and edit.target.epoch_id == epoch_id:
            return Zone.model_validate(edit.payload["zone"])
    return None
