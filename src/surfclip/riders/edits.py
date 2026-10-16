"""Turn the user's rider edits into grouping rules (research R6, data-model "Rider edits").

Rider edits never mention group ids (groups change whenever grouping re-runs); they name the
rides the user saw, with their spans, and are re-attached to the current rides by time overlap
like 001's ride edits. In time order:

* ``rider_name``: the rides' group gets the name; the example rides the user looked at are fixed
  to it. Naming a group that already has a name renames every ride fixed to the old name.
* ``rider_same_as``: all rides of both groups (as they were) must be one rider.
* ``rider_mixed``: those rides are split in two (decided by appearance when grouping).
* ``rider_ignore``: the group holding those rides is ignored (or not, with ``ignore: false``).
* ``ride_rider``: one ride fixed to a name, or must be with another ride, or must not be with a
  name (``not_name``).

``undo`` edits from 001 cancel rider edits too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from surfclip.edits.apply import resolve_ride, undone_ids
from surfclip.riders.cluster import Constraints
from surfclip.store.schemas import Edits, Ride, UserEdit


@dataclass
class RiderRules:
    must: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    cannot: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    fixed: dict[str, str] = field(default_factory=dict[str, str])  # ride -> name (hard)
    names: dict[str, str] = field(default_factory=dict[str, str])  # anchor ride -> group name
    ignored: set[str] = field(default_factory=set[str])  # anchor rides of ignored groups
    mixed: list[list[str]] = field(default_factory=list[list[str]])  # rides to split in two
    not_names: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    def constraints(self) -> Constraints:
        cannot = list(self.cannot)
        for ride, name in self.not_names:  # "not X": apart from every ride fixed to X
            cannot += [(ride, r) for r, n in self.fixed.items() if n == name and r != ride]
        return Constraints(must=self.must, cannot=cannot, fixed=self.fixed)


def _span_map(value: object) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    if isinstance(value, dict):
        for rid, span in value.items():  # pyright: ignore[reportUnknownVariableType]
            if isinstance(span, list | tuple) and len(span) == 2:  # pyright: ignore[reportUnknownArgumentType]
                out[str(rid)] = (float(span[0]), float(span[1]))  # pyright: ignore[reportUnknownArgumentType]
    return out


def _ride_ref(value: object) -> tuple[str, tuple[float, float]] | None:
    if isinstance(value, list | tuple) and len(value) == 3:  # pyright: ignore[reportUnknownArgumentType]
        rid, s, e = value  # pyright: ignore[reportUnknownVariableType]
        return str(rid), (float(s), float(e))  # pyright: ignore[reportUnknownArgumentType]
    return None


def _resolve_all(spans: dict[str, tuple[float, float]], rides: dict[str, Ride]) -> list[str]:
    out: list[str] = []
    for rid, span in spans.items():
        got = resolve_ride(rid, span, rides)
        if got is not None and got not in out:
            out.append(got)
    return out


def rider_rules(edits: Edits, rides: list[Ride]) -> RiderRules:
    by_id = {r.ride_id: r for r in rides}
    undone = undone_ids(edits)
    rules = RiderRules()
    for edit in edits.edits:
        if edit.edit_id in undone:
            continue
        _apply(edit, by_id, rules)
    return rules


def _apply(edit: UserEdit, rides: dict[str, Ride], rules: RiderRules) -> None:
    p = edit.payload
    if edit.op == "rider_name":
        name = str(p.get("name", "")).strip()
        anchors = _resolve_all(_span_map(p.get("rides")), rides)
        examples = _resolve_all(_span_map(p.get("examples")), rides)
        if not name or not anchors:
            return
        old = {rules.fixed[r] for r in anchors if r in rules.fixed} | {
            rules.names[r] for r in anchors if r in rules.names
        }
        for o in old - {name}:  # renaming: everything fixed or anchored to the old name
            for r, n in list(rules.fixed.items()):
                if n == o:
                    rules.fixed[r] = name
            for r, n in list(rules.names.items()):
                if n == o:
                    rules.names[r] = name
        for r in anchors:
            rules.names[r] = name
        for r in examples:
            rules.fixed[r] = name
    elif edit.op == "rider_same_as":
        a = _resolve_all(_span_map(p.get("rides")), rides)
        b = _resolve_all(_span_map(p.get("other")), rides)
        if a and b:
            rules.must += [(a[0], x) for x in a[1:] + b]
    elif edit.op == "rider_mixed":
        group = _resolve_all(_span_map(p.get("rides")), rides)
        if len(group) >= 2:
            inside = set(group)  # a later "mixed" overrides earlier "same as" inside the group
            rules.must = [(a, b) for a, b in rules.must if not (a in inside and b in inside)]
            rules.mixed.append(group)
    elif edit.op == "rider_ignore":
        anchors = _resolve_all(_span_map(p.get("rides")), rides)
        if p.get("ignore", True):
            rules.ignored.update(anchors)
        else:
            rules.ignored.difference_update(anchors)
    elif edit.op == "ride_rider":
        ref = _ride_ref(p.get("ride"))
        if ref is None:
            return
        ride = resolve_ride(ref[0], ref[1], rides)
        if ride is None:
            return
        if isinstance(p.get("name"), str) and p.get("name"):
            rules.fixed[ride] = str(p["name"])
        other = _ride_ref(p.get("same_as_ride"))
        if other is not None:
            target = resolve_ride(other[0], other[1], rides)
            if target is not None and target != ride:
                rules.must.append((ride, target))
        if isinstance(p.get("not_name"), str) and p.get("not_name"):
            rules.fixed.pop(ride, None)
            rules.not_names.append((ride, str(p["not_name"])))
