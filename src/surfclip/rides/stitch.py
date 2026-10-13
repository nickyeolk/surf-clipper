"""Stitch track fragments of one person into chains (research R4, found on 20241004).

At 5 analysis frames per second a fast rider moves further between frames than the tracker's
box overlap allows, so tracks break every few seconds (median 1.6 s on 20241004). A fragment
that starts shortly after another one ended, close to where it ended, is the same person:

* gap between the end of A and the start of B: ``-0.2 s .. stitch_gap_s``;
* distance between A's last and B's first feet point, in rider heights:
  ``<= stitch_base_heights + stitch_heights_per_s * gap``;
* each fragment gets at most one successor and one predecessor, nearest first.

Chains take the id of their first fragment; ``members`` maps chain ids to fragment ids.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

from surfclip.config import RidesConfig
from surfclip.rides.evidence import Obs

_OVERLAP_TOL_S = 0.2


def stitch(
    tracks: Sequence[Sequence[Obs]], cfg: RidesConfig
) -> tuple[dict[int, list[Obs]], dict[int, list[int]]]:
    frags = sorted((sorted(t, key=lambda o: o.t) for t in tracks if t), key=lambda t: t[0].t)
    successor: dict[int, int] = {}
    predecessor: dict[int, int] = {}
    candidates: list[tuple[float, int, int]] = []
    for i, b in enumerate(frags):
        first = b[0]
        for j in range(i):
            a = frags[j]
            last = a[-1]
            gap = first.t - last.t
            if gap < -_OVERLAP_TOL_S or gap > cfg.stitch_gap_s:
                continue
            height = max(last.box_height, first.box_height, 1.0)
            dist = math.hypot(first.feet[0] - last.feet[0], first.feet[1] - last.feet[1]) / height
            if dist <= cfg.stitch_base_heights + cfg.stitch_heights_per_s * max(gap, 0.0):
                candidates.append((dist, j, i))
    for _, j, i in sorted(candidates):
        if j not in successor and i not in predecessor:
            successor[j] = i
            predecessor[i] = j

    chains: dict[int, list[Obs]] = {}
    members: dict[int, list[int]] = {}
    for start in range(len(frags)):
        if start in predecessor:
            continue
        chain_id = frags[start][0].track_id
        ids: list[int] = []
        obs: list[Obs] = []
        k: int | None = start
        while k is not None:
            ids.append(frags[k][0].track_id)
            obs.extend(replace(o, track_id=chain_id) for o in frags[k])
            k = successor.get(k)
        members[chain_id] = ids
        chains[chain_id] = sorted(obs, key=lambda o: o.t)
    return chains, members
