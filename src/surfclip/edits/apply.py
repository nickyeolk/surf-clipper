"""Apply user edits to detected rides: rides.json = rides.detected.json + edits.json (T028).

Deterministic: the same inputs always give the same rides. Zone confirmations are used by the
rides stage, not here. Edits that point at a ride that no longer exists are skipped and logged;
re-attaching them to re-detected rides by time overlap is task T056.
"""

from __future__ import annotations

import logging

from surfclip.store.schemas import Edits, Ride, RideFlags, Rides, UserEdit

log = logging.getLogger(__name__)


def _num(edit: UserEdit, key: str) -> float:
    value = edit.payload[key]
    assert isinstance(value, int | float), f"edit {edit.edit_id}: {key} must be a number"
    return float(value)


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


def apply_edits(detected: Rides, edits: Edits) -> Rides:
    fps = detected.source.fps
    rides: dict[str, Ride] = {r.ride_id: r for r in detected.rides}
    for edit in edits.edits:
        tgt = edit.target
        if edit.op == "confirm_zone":
            continue
        if edit.op == "add":
            start, end = _num(edit, "start_s"), _num(edit, "end_s")
            rid = f"u{edit.edit_id:04d}"
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
            rides[rid] = _respan(base, start, end, fps, detected)
            continue
        ids = tgt.ride_ids or ([tgt.ride_id] if tgt.ride_id else [])
        missing = [i for i in ids if i not in rides]
        if not ids or missing:
            log.warning(
                "edit %d (%s): ride(s) %s not found; skipped", edit.edit_id, edit.op, missing or ids
            )
            continue
        if edit.op == "delete":
            del rides[ids[0]]
        elif edit.op == "trim":
            r = rides[ids[0]]
            start = _num(edit, "start_s") if "start_s" in edit.payload else r.start_s
            end = _num(edit, "end_s") if "end_s" in edit.payload else r.end_s
            trimmed = _respan(r, start, end, fps, detected)
            rides[r.ride_id] = trimmed.model_copy(
                update={"flags": trimmed.flags.model_copy(update={"user_edited": True})}
            )
        elif edit.op == "split":
            r = rides.pop(ids[0])
            at = _num(edit, "at_s")
            flags = r.flags.model_copy(update={"user_edited": True})
            for suffix, (s, e) in (("a", (r.start_s, at)), ("b", (at, r.end_s))):
                part = _respan(r, s, e, fps, detected)
                rides[r.ride_id + suffix] = part.model_copy(
                    update={"ride_id": r.ride_id + suffix, "flags": flags}
                )
        elif edit.op == "merge":
            parts = [rides.pop(i) for i in ids]
            first = min(parts, key=lambda p: p.start_s)
            merged = _respan(
                first, min(p.start_s for p in parts), max(p.end_s for p in parts), fps, detected
            )
            rides[first.ride_id] = merged.model_copy(
                update={
                    "track_ids": sorted({t for p in parts for t in p.track_ids}),
                    "epochs": sorted({e for p in parts for e in p.epochs}),
                    "flags": first.flags.model_copy(update={"user_edited": True}),
                }
            )
    ordered = sorted(rides.values(), key=lambda r: r.start_s)
    return detected.model_copy(update={"rides": ordered})
