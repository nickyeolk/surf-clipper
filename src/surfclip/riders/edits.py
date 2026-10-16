"""The user's rider edits, applied to the cards one by one (research R6, data-model "Rider edits").

Cards come from grouping by appearance once; every user action then changes exactly what the
user touched, in order, and nothing else (2026-10-16: re-grouping after each action made
untouched rides drift between cards). Edits never mention card ids, which change when rides
are re-detected; they name the rides the user saw, with their spans, re-attached to the current
rides by time overlap like 001's ride edits. A card is found as the one holding most of an
edit's rides.

* ``rider_name``: the card gets the name (a name another card already has: same person, merged).
* ``rider_same_as``: the two cards become one (keeping the first card's name, else the other's).
* ``rider_mixed``: the card is split in two by appearance.
* ``rider_ignore``: the card is ignored (or not, with ``ignore: false``).
* ``ride_rider``: one ride moves to the card of another ride (``same_as_ride``) or to a named
  rider (``name``; a new card if nobody has that name yet), or out of a named rider
  (``not_name``: to the most similar other card).

``undo`` edits from 001 cancel rider edits too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from surfclip.edits.apply import resolve_ride, undone_ids
from surfclip.riders.cluster import split_two
from surfclip.store.schemas import Edits, Ride, UserEdit

FloatArray = NDArray[np.float64]
Distance = Callable[[FloatArray, FloatArray], float]


@dataclass
class Card:
    rides: list[str]
    name: str | None = None
    ignored: bool = False
    confirmed: set[str] = field(default_factory=set[str])  # rides the user placed or showed


@dataclass(frozen=True)
class RiderOp:
    kind: str  # name | same_as | mixed | ignore | move | not
    rides: tuple[str, ...] = ()
    other: tuple[str, ...] = ()
    name: str | None = None
    flag: bool = True


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


def _resolve_all(spans: dict[str, tuple[float, float]], rides: dict[str, Ride]) -> tuple[str, ...]:
    out: list[str] = []
    for rid, span in spans.items():
        got = resolve_ride(rid, span, rides)
        if got is not None and got not in out:
            out.append(got)
    return tuple(out)


def _one(value: object, rides: dict[str, Ride]) -> str | None:
    ref = _ride_ref(value)
    return resolve_ride(ref[0], ref[1], rides) if ref is not None else None


def rider_ops(edits: Edits, rides: list[Ride]) -> list[RiderOp]:
    """The rider edits still in effect, with their rides resolved to the current rides."""
    by_id = {r.ride_id: r for r in rides}
    undone = undone_ids(edits)
    ops: list[RiderOp] = []
    for edit in edits.edits:
        if edit.edit_id not in undone:
            op = _op(edit, by_id)
            if op is not None:
                ops.append(op)
    return ops


def _op(edit: UserEdit, rides: dict[str, Ride]) -> RiderOp | None:
    p = edit.payload
    if edit.op == "rider_name":
        name = str(p.get("name", "")).strip()
        anchors = _resolve_all(_span_map(p.get("rides")), rides)
        if not name or not anchors:
            return None
        examples = _resolve_all(_span_map(p.get("examples")), rides)[:1]
        return RiderOp("name", anchors, examples, name)
    if edit.op == "rider_same_as":
        a = _resolve_all(_span_map(p.get("rides")), rides)
        b = _resolve_all(_span_map(p.get("other")), rides)
        return RiderOp("same_as", a, b) if a and b else None
    if edit.op == "rider_mixed":
        group = _resolve_all(_span_map(p.get("rides")), rides)
        return RiderOp("mixed", group) if len(group) >= 2 else None
    if edit.op == "rider_ignore":
        anchors = _resolve_all(_span_map(p.get("rides")), rides)
        return RiderOp("ignore", anchors, flag=bool(p.get("ignore", True))) if anchors else None
    if edit.op == "ride_rider":
        ride = _one(p.get("ride"), rides)
        if ride is None:
            return None
        target = _one(p.get("same_as_ride"), rides)
        if target is not None and target != ride:
            return RiderOp("move", (ride,), (target,))
        if isinstance(p.get("name"), str) and str(p.get("name")).strip():
            return RiderOp("move", (ride,), name=str(p["name"]).strip())
        if isinstance(p.get("not_name"), str) and p.get("not_name"):
            return RiderOp("not", (ride,), name=str(p["not_name"]))
    return None


def _centre(card: Card, vectors: Mapping[str, FloatArray]) -> FloatArray:
    return np.asarray(np.mean([vectors[r] for r in card.rides if r in vectors], axis=0))


def apply_ops(
    cards: list[Card],
    ops: list[RiderOp],
    vectors: Mapping[str, FloatArray],
    distance: Distance,
) -> list[Card]:
    """Apply the user's actions to the cards in order; nothing else changes."""
    cards = [Card(list(c.rides), c.name, c.ignored, set(c.confirmed)) for c in cards]

    def holder(rides: tuple[str, ...]) -> Card | None:
        counts = [(sum(r in c.rides for r in rides), -k) for k, c in enumerate(cards)]
        best = max(range(len(cards)), key=lambda k: counts[k], default=None)
        return cards[best] if best is not None and counts[best][0] > 0 else None

    def card_of(ride: str) -> Card | None:
        return next((c for c in cards if ride in c.rides), None)

    def named(name: str) -> Card | None:
        return next((c for c in cards if c.name == name), None)

    def merge(into: Card, other: Card) -> None:
        if into is other:
            return
        into.rides += [r for r in other.rides if r not in into.rides]
        into.confirmed |= other.confirmed
        into.name = into.name or other.name
        into.ignored = into.ignored and other.ignored
        cards.remove(other)

    for op in ops:
        if op.kind == "name":
            card = holder(op.rides)
            if card is None or op.name is None:
                continue
            same = named(op.name)
            card.name = op.name
            card.confirmed |= set(op.other)
            if same is not None and same is not card:  # a second card of the same person
                merge(card, same)
        elif op.kind == "same_as":
            a, b = holder(op.rides), holder(op.other)
            if a is not None and b is not None:
                merge(a, b)
        elif op.kind == "mixed":
            card = holder(op.rides)
            if card is None:
                continue
            present = [r for r in card.rides if r in vectors]
            if len(present) < 2:
                continue
            first, second = split_two(present, vectors, distance)
            if not first or not second:
                continue
            rest = [r for r in card.rides if r not in vectors]  # no appearance: stay
            card.rides = [r for r in card.rides if r in first or r in rest]
            cards.insert(
                cards.index(card) + 1, Card(second, confirmed=card.confirmed & set(second))
            )
            card.confirmed -= set(second)
        elif op.kind == "ignore":
            card = holder(op.rides)
            if card is not None:
                card.ignored = op.flag
        elif op.kind in ("move", "not"):
            ride = op.rides[0]
            source = card_of(ride)
            if op.kind == "not":
                if source is None or source.name != op.name or ride not in vectors:
                    continue
                others = [
                    c
                    for c in cards
                    if c is not source and not c.ignored and any(r in vectors for r in c.rides)
                ]
                if not others:
                    continue
                target = min(others, key=lambda c: distance(vectors[ride], _centre(c, vectors)))
            elif op.other:
                target = card_of(op.other[0])
            else:
                target = named(op.name or "")
                if target is None:
                    target = Card([], op.name)
                    cards.append(target)
            if target is None:
                continue
            if target is source:  # "yes, that's right": the ride stays and is confirmed
                target.confirmed.add(ride)
                continue
            if source is not None:
                source.rides.remove(ride)
                source.confirmed.discard(ride)
            target.rides.append(ride)
            target.confirmed.add(ride)
        cards = [c for c in cards if c.rides]
    return cards
