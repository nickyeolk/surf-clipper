# Evaluation log: Rider Identification (002)

## 2026-10-16 - T014 spike

See research.md "T014 results": embedding (DINOv2 ViT-S/14, cut 0.075) adopted. SC-001 on the
labelled sessions: 20240924 79.7%, 20241004 93.3%, 20260928_IMG_1652 100%,
20261012_110549566 58.0% (night HDR, over-split), PXL_20261014_100546073 92.2% (held out).

## 2026-10-16 - first new session in normal use: 20250206

The user processed 20250206.MP4 (not used for tuning), grouped riders in the Riders screen and
accepted the result as labels (`labels/riders/20250206.json`, built from riders.json).

| | Result | Target |
| --- | --- | --- |
| SC-001 (untouched grouping vs the user's final cards) | 96.3% (103/107; 6 riders, 10 cards) | >= 85% |
| User actions | 6 names, 4 same-as merges, 0 single-ride moves | SC-002 <= 10 corrections |

Caveat: the labels are the tool's cards after the user's corrections, so errors the user did not
notice count as correct; 96.3% is an upper bound.
## 2026-10-16 - frame-edge joins (US3, T028/T029)

Rides split because the rider left the frame are joined when they are consecutive rides of the
same card, gap <= 6 s, rider at the frame edge, both cards' confidence >= 0.4 (0.8 was too strict:
the portrait session's 3 true splits are same-card pairs at 0.44-0.66, and no different-card
pair is a true split). `scripts/join_eval.py`, 001 ride metrics on the detected rides:

| Session | Joins | Recall | Precision | Complete |
| --- | --- | --- | --- | --- |
| 20260928_IMG_1652 (portrait) | 3 | 96.2% -> 100% | 91.1% -> 100% | 79.2% -> 84.9% |
| other four labelled sessions | 0 (1 suggestion on night HDR) | unchanged | unchanged | unchanged |