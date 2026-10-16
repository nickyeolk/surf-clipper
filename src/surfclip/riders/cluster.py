"""Group rides into riders: constrained average-linkage clustering (research R3).

Rides are merged closest-first while the average distance between two groups stays under the
threshold, and never across a cannot-link: two rides that overlap in time (one person cannot ride
twice at once), an explicit "not the same rider" from the user, or rides fixed to different named
riders. Must-links (the user said "same rider", or fixed the rides to one name) are merged before
clustering. With ~100 rides this exact O(n^3) loop takes milliseconds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
Distance = Callable[[FloatArray, FloatArray], float]


@dataclass(frozen=True)
class Constraints:
    must: Sequence[tuple[str, str]] = ()  # same rider
    cannot: Sequence[tuple[str, str]] = ()  # different riders
    fixed: Mapping[str, str] = field(default_factory=dict[str, str])  # ride -> rider name


class _UnionFind:
    def __init__(self, items: Sequence[str]) -> None:
        self.parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def overlaps(a: tuple[float, float], b: tuple[float, float], allowed_s: float) -> bool:
    return min(a[1], b[1]) - max(a[0], b[0]) > allowed_s


def group_rides(
    descriptors: Mapping[str, FloatArray],
    spans: Mapping[str, tuple[float, float]],
    distance: Distance,
    *,
    threshold: float,
    overlap_allowed_s: float,
    constraints: Constraints | None = None,
    stop_at: int = 1,
) -> list[list[str]]:
    """Groups of ride ids, largest first (ties: earliest first). ``stop_at`` stops merging when
    that many groups remain (used to split a mixed group in two with an infinite threshold)."""
    c = constraints or Constraints()
    ids = sorted(descriptors, key=lambda r: spans[r][0])
    if not ids:
        return []
    uf = _UnionFind(ids)
    for a, b in c.must:
        if a in uf.parent and b in uf.parent:
            uf.union(a, b)
    by_name: dict[str, str] = {}
    for ride, name in c.fixed.items():
        if ride not in uf.parent:
            continue
        if name in by_name:
            uf.union(by_name[name], ride)
        else:
            by_name[name] = ride
    roots = sorted({uf.find(i) for i in ids}, key=lambda r: spans[r][0])
    members: list[list[str]] = [[i for i in ids if uf.find(i) == r] for r in roots]
    n = len(members)

    # Cannot-links between the initial nodes.
    index = {ride: k for k, group in enumerate(members) for ride in group}
    cannot = np.zeros((n, n), dtype=bool)
    for i in range(n):
        for j in range(i + 1, n):
            if any(
                overlaps(spans[a], spans[b], overlap_allowed_s)
                for a in members[i]
                for b in members[j]
            ):
                cannot[i, j] = cannot[j, i] = True
    for a, b in c.cannot:
        if a in index and b in index and index[a] != index[b]:
            cannot[index[a], index[b]] = cannot[index[b], index[a]] = True
    names = [{c.fixed[r] for r in g if r in c.fixed} for g in members]
    for i in range(n):
        for j in range(i + 1, n):
            if names[i] and names[j] and names[i] != names[j]:
                cannot[i, j] = cannot[j, i] = True

    # Average-linkage distances between nodes: the mean distance between their rides. (Using
    # the distance between node means instead made a named group, whose example rides are
    # merged up front, swallow other riders: a mean is close to everything.)
    pair: dict[tuple[str, str], float] = {}

    def d(a: str, b: str) -> float:
        key = (a, b) if a < b else (b, a)
        if key not in pair:
            pair[key] = distance(descriptors[a], descriptors[b])
        return pair[key]

    dist = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(i + 1, n):
            dist[i, j] = dist[j, i] = float(
                np.mean([d(a, b) for a in members[i] for b in members[j]])
            )
    size = np.array([len(g) for g in members], dtype=np.float64)
    alive = np.ones(n, dtype=bool)
    while int(alive.sum()) > stop_at:
        masked = np.where(cannot | ~alive[:, None] | ~alive[None, :], np.inf, dist)
        np.fill_diagonal(masked, np.inf)
        i, j = np.unravel_index(int(np.argmin(masked)), masked.shape)
        if not np.isfinite(masked[i, j]) or masked[i, j] > threshold:
            break
        # Merge j into i (Lance-Williams update for average linkage).
        ni, nj = size[i], size[j]
        dist[i, :] = dist[:, i] = (ni * dist[i, :] + nj * dist[j, :]) / (ni + nj)
        dist[i, i] = np.inf
        cannot[i, :] = cannot[:, i] = cannot[i, :] | cannot[j, :]
        size[i] = ni + nj
        members[i] = members[i] + members[j]
        alive[j] = False
    groups = [sorted(members[k], key=lambda r: spans[r][0]) for k in range(n) if alive[k]]
    return sorted(groups, key=lambda g: (-len(g), spans[g[0]][0]))
