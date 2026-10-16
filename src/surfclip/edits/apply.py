"""Apply user edits to detected rides: rides.json = rides.detected.json + edits.json (T028, T056).

Deterministic: the same inputs always give the same rides. Zone confirmations are used by the
rides stage, not here.

Re-attachment (FR-022): ride ids come from start frames, so a re-run with other settings can give
the same ride another id. Edits therefore record the span each target ride had when the edit was
made (``payload["spans"]``). A target id is kept when its ride still overlaps that span with
IoU >= 0.5; otherwise the ride overlapping it best (IoU >= 0.5) is used. A trimmed ride that
matches nothing is kept as a user-added ride with the trimmed times; other unmatched edits are
skipped and logged. ``undo`` edits cancel an earlier edit (the log itself stays append-only).
"""

from __future__ import annotations

import logging

from surfclip.store.schemas import Edits, Ride, RideFlags, RideRef, Rides, UserEdit

log = logging.getLogger(__name__)

REATTACH_IOU = 0.5
# Rider edits (002) do not change rides; riders/edits.py applies them.
RIDER_OPS = frozenset(
    {"rider_name", "rider_same_as", "rider_mixed", "rider_ignore", "ride_rider", "rider_unjoin"}
)


def _num(edit: UserEdit, key: str) -> float:
    value = edit.payload[key]
    assert isinstance(value, int | float), f"edit {edit.edit_id}: {key} must be a number"
    return float(value)


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def _respan(ride: Ride, start_s: float, end_s: float, fps: float, rides: Rides) -> Ride:
    s = rides.settings
    return ride.model_copy(
        update={
            "start_s": start_s,
            "end_s": end_s,
            "start_frame": round(start_s * fps),
            "end_frame": round(end_s * fps),
            "clip_start_s": max(0.0, start_s - s.pad_before_s),
            "clip_end_s": end_s + s.pad_after_s,
            "export": None,
        }
    )


def _spans(edit: UserEdit) -> dict[str, tuple[float, float]]:
    raw = edit.payload.get("spans")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for rid, span in raw.items():  # pyright: ignore[reportUnknownVariableType]
        if isinstance(span, list | tuple) and len(span) == 2:  # pyright: ignore[reportUnknownArgumentType]
            out[str(rid)] = (float(span[0]), float(span[1]))  # pyright: ignore[reportUnknownArgumentType]
    return out


def resolve_ride(rid: str, span: tuple[float, float] | None, rides: dict[str, Ride]) -> str | None:
    """The current id of the ride an edit pointed at (see module docstring)."""
    if span is None:
        return rid if rid in rides else None
    here = rides.get(rid)
    if here is not None and iou((here.start_s, here.end_s), span) >= REATTACH_IOU:
        return rid
    best = max(rides.values(), key=lambda r: iou((r.start_s, r.end_s), span), default=None)
    if best is not None and iou((best.start_s, best.end_s), span) >= REATTACH_IOU:
        return best.ride_id
    return None


def _user_ride(rid: str, start: float, end: float, fps: float, detected: Rides) -> Ride:
    base = Ride(
        ride_id=rid,
        start_s=start,
        end_s=end,
        confidence=1.0,
        start_frame=0,
        end_frame=0,
        clip_start_s=0,
        clip_end_s=0,
        epochs=[0],
        track_ids=[],
        flags=RideFlags(user_added=True),
    )
    return _respan(base, start, end, fps, detected)


def undone_ids(edits: Edits) -> set[int]:
    """Edits cancelled by an ``undo`` (an undo can itself be undone: redo)."""
    undone: set[int] = set()
    for edit in reversed(edits.edits):
        if edit.op == "undo" and edit.edit_id not in undone:
            target = edit.payload.get("edit_id")
            if isinstance(target, int):
                undone.add(target)
    return undone


def apply_edits(detected: Rides, edits: Edits) -> Rides:
    fps = detected.source.fps
    rides: dict[str, Ride] = {r.ride_id: r for r in detected.rides}
    undone = undone_ids(edits)
    for edit in edits.edits:
        if edit.op in ("confirm_zone", "undo") or edit.op in RIDER_OPS or edit.edit_id in undone:
            continue
        if edit.op == "add":
            rid = f"u{edit.edit_id:04d}"
            rides[rid] = _user_ride(rid, _num(edit, "start_s"), _num(edit, "end_s"), fps, detected)
            continue
        tgt = edit.target
        wanted = tgt.ride_ids or ([tgt.ride_id] if tgt.ride_id else [])
        spans = _spans(edit)
        ids = [resolve_ride(w, spans.get(w), rides) for w in wanted]
        found = [i for i in ids if i is not None]
        if edit.op == "trim" and wanted and not found:
            # The ride is gone after a re-run: keep the user's version of it.
            rid = f"u{edit.edit_id:04d}"
            old = spans.get(wanted[0])
            start = _num(edit, "start_s") if "start_s" in edit.payload else (old or (0, 0))[0]
            end = _num(edit, "end_s") if "end_s" in edit.payload else (old or (0, 0))[1]
            if end > start:
                rides[rid] = _user_ride(rid, start, end, fps, detected)
            continue
        if not wanted or len(set(found)) != len(wanted):
            log.warning(
                "edit %d (%s): ride(s) %s not found; skipped", edit.edit_id, edit.op, wanted
            )
            continue
        if edit.op == "delete":
            del rides[found[0]]
        elif edit.op == "trim":
            r = rides[found[0]]
            start = _num(edit, "start_s") if "start_s" in edit.payload else r.start_s
            end = _num(edit, "end_s") if "end_s" in edit.payload else r.end_s
            trimmed = _respan(r, start, end, fps, detected)
            rides[r.ride_id] = trimmed.model_copy(
                update={"flags": trimmed.flags.model_copy(update={"user_edited": True})}
            )
        elif edit.op == "split":
            r = rides[found[0]]
            at = _num(edit, "at_s")
            if not r.start_s < at < r.end_s:
                log.warning("edit %d (split): %.2f s is outside %s", edit.edit_id, at, r.ride_id)
                continue
            del rides[r.ride_id]
            flags = r.flags.model_copy(update={"user_edited": True})
            for suffix, (s, e) in (("a", (r.start_s, at)), ("b", (at, r.end_s))):
                part = _respan(r, s, e, fps, detected)
                rides[r.ride_id + suffix] = part.model_copy(
                    update={"ride_id": r.ride_id + suffix, "flags": flags}
                )
        elif edit.op == "merge":
            merged = _merge([rides.pop(i) for i in found], fps, detected, user=True)
            rides[merged.ride_id] = merged
    ordered = sorted(rides.values(), key=lambda r: r.start_s)
    return detected.model_copy(update={"rides": ordered})


def _merge(parts: list[Ride], fps: float, rides: Rides, *, user: bool) -> Ride:
    first = min(parts, key=lambda p: p.start_s)
    merged = _respan(first, min(p.start_s for p in parts), max(p.end_s for p in parts), fps, rides)
    flags = {
        "lesson": any(p.flags.lesson for p in parts),
        "truncated": any(p.flags.truncated for p in parts),
        **({"user_edited": True} if user else {"joined": True}),
    }
    return merged.model_copy(
        update={
            "track_ids": sorted({t for p in parts for t in p.track_ids}),
            "epochs": sorted({e for p in parts for e in p.epochs}),
            "flags": first.flags.model_copy(update=flags),
        }
    )


def unjoined_pairs(edits: Edits) -> list[tuple[RideRef, RideRef]]:
    """Joins the user undid (``rider_unjoin`` edits still in effect)."""
    undone = undone_ids(edits)
    out: list[tuple[RideRef, RideRef]] = []
    for e in edits.edits:
        if e.op == "rider_unjoin" and e.edit_id not in undone:
            a, b = _ref(e.payload.get("first")), _ref(e.payload.get("second"))
            if a is not None and b is not None:
                out.append((a, b))
    return out


def _ref(value: object) -> RideRef | None:
    if isinstance(value, list | tuple) and len(value) == 3:  # pyright: ignore[reportUnknownArgumentType]
        rid, s, e = value  # pyright: ignore[reportUnknownVariableType]
        return (str(rid), float(s), float(e))  # pyright: ignore[reportUnknownArgumentType]
    return None


def same_pair(a: tuple[RideRef, RideRef], b: tuple[RideRef, RideRef]) -> bool:
    """The same two rides (by time overlap), whatever their ids now."""
    return all(iou((x[1], x[2]), (y[1], y[2])) >= REATTACH_IOU for x, y in zip(a, b, strict=True))


def apply_joins(
    rides: Rides, joins: list[tuple[RideRef, RideRef]], unjoined: list[tuple[RideRef, RideRef]]
) -> Rides:
    """Join rides split at the frame edge (002), except pairs the user unjoined."""
    by_id = {r.ride_id: r for r in rides.rides}
    for pair in joins:
        if any(same_pair(pair, u) for u in unjoined):
            continue
        a = resolve_ride(pair[0][0], (pair[0][1], pair[0][2]), by_id)
        b = resolve_ride(pair[1][0], (pair[1][1], pair[1][2]), by_id)
        if a is None or b is None or a == b:
            continue
        merged = _merge([by_id.pop(a), by_id.pop(b)], rides.source.fps, rides, user=False)
        by_id[merged.ride_id] = merged
    ordered = sorted(by_id.values(), key=lambda r: r.start_s)
    return rides.model_copy(update={"rides": ordered})
