# Research: Rider Identification (002)

**Date**: 2026-10-16 · **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Each entry: Decision / Rationale / Alternatives considered. Items marked **Spike** are settled by
the first implementation task (measured on the rider labels) before anything is built on them.

## R1. Where the rider crops come from

- **Decision**: For each ride, sample 12 moments evenly across the ride (configurable), take the
  ride's own tracked person at each moment (001's `tracks.parquet`, track ids of the ride) and
  crop the box, padded 15%, from the 720p review copy (`review.mp4`, SDR, already tone-mapped,
  keyframe every 0.5 s, so seeks are cheap). Keep the sharpest 8 (variance of the Laplacian) with
  boxes at least 48 px tall; rides with fewer usable crops get lower confidence. Also crop the
  matched board box when one exists.
- **Rationale**: no second detection pass (constitution VII); the review copy already solves HDR
  tone mapping, and its frames are decoded quickly (001 measured seeks at ~0.27 s; 100 rides × 12
  crops ≈ 1200 frames ≈ 2-3 min by sequential decode of the needed ranges). Track ids identify the
  rider without guessing who is who.
- **Alternatives**: crops from the source at full resolution: better for far riders at 0.5x, but
  4K HEVC seeks cost ~1 s each (≈ 20 min per session; over SC-006). Kept as a fallback for rides
  whose 720p crops are under 48 px tall, if the spike shows they matter. Crops from the analysis
  proxy: not stored.

## R2. Describing a ride's appearance — **Spike**

- **Decision**: two candidates, measured by SC-001 on the labelled sessions (except held-out PXL):
  1. **Colour baseline**: per crop, HSV histograms of the upper body (20-50% of box height),
     lower body (50-85%) and board, after per-session colour normalisation (R4); ride descriptor =
     mean over its crops; distance = 1 - histogram intersection, weighted per region.
  2. **Pretrained embedding**: DINOv2 ViT-S/14 image embedding of the person crop resized to
     224 px high (no training), mean over the ride's crops, cosine distance; optionally combined
     with (1).
  Adopt (2) or the combination only if it beats (1) on SC-001 on every non-held-out session
  within the time budget (constitution VIII).
- **Rationale**: riders differ mostly by clothing and board colours, which survive low resolution;
  a general self-supervised embedding also captures shape and pattern and is less sensitive to
  colour casts. Per-ride averaging over many crops reduces blur and pose noise (PRD).
- **Alternatives**: OSNet / torchreid person re-ID (trained on pedestrians; extra dependency;
  third candidate if both fail); CLIP image embeddings (larger, no clear advantage); face
  recognition (forbidden by constitution I).

## R3. Grouping rides into riders

- **Decision**: agglomerative clustering (average linkage) over ride descriptors with a
  configurable distance threshold, under **cannot-link** constraints: two rides that overlap in
  time (beyond a changeover overlap) are never the same rider. Implemented by setting the
  distance of such pairs to infinity before linkage, then cutting at the threshold. Lesson rides
  (001 flag) are excluded and form the "Lesson" group. Groups are numbered by size.
- **Rationale**: the number of riders is unknown (3-15); a distance threshold adapts to it,
  average linkage is robust to a few outlier crops, and cannot-link uses the strongest free fact
  available (one person cannot ride twice at once). Fast for ~100 rides (milliseconds).
- **Alternatives**: k-means (needs the number of riders); DBSCAN/HDBSCAN (leaves rides
  unassigned as noise; awkward with constraints); graph-based with turn order as a hard rule
  (rotation is common but not fixed: PRD).

## R4. Lighting and colour normalisation

- **Decision**: per session (and per camera epoch when 001 provides epochs), estimate a grey-world
  colour correction from the review copy's background (the pool and walls outside rider boxes) at
  ~20 moments; apply it to every crop before the colour descriptor. When the estimated tint is
  strong (night LED), down-weight hue relative to saturation/value and the embedding (if adopted).
  Rides within ±30 s of a detected lighting change (background brightness or hue jump) get lower
  confidence so they reach the queue.
- **Rationale**: LED colours are usually fixed for a session (PRD); one correction per session or
  epoch is cheap and stable.
- **Alternatives**: per-frame white balance (unstable with riders filling the frame); no
  correction (night sessions break colour matching).

## R5. Assignment, confidence and the review queue

- **Decision**: riders = groups (named or not, minus ignored). Each ride's rider is its group's;
  its confidence is the margin between its distance to its own rider's centroid and to the
  nearest other rider's centroid, mapped to 0-1. User confirmations and reassignments are fixed
  (must-link to that rider, cannot-link to others); after each user action the clustering re-runs
  with all constraints (≤ 100 rides: well under a second). The queue lists rides with confidence
  below `riders.queue_below` whose own rider **or** nearest other rider is a named rider (FR-005,
  clarification 3), lowest first.
- **Rationale**: the margin measures ambiguity; recomputing with constraints lets each answer fix
  its neighbours too (PRD step 5).
- **Alternatives**: nearest-centroid only without re-clustering (answers do not propagate);
  probabilistic models (more complex, no clear gain at this scale).

## R6. Storing user actions so they survive re-runs

- **Decision**: rider edits are appended to the session's `edits.json` as new ops (`rider_name`,
  `rider_same_as`, `rider_mixed`, `rider_ignore`, `ride_rider` for confirm/reassign,
  `rider_unjoin`). They are anchored to **rides**, never to group numbers: naming a group records
  the group's rides at that moment (ids + spans) and the shown example rides as confirmed; a
  re-run re-attaches anchors to rides by time overlap (IoU ≥ 0.5), exactly as 001's ride edits do
  (`edits/apply.py`). `riders.json` is recomputed from rides + appearance + rider edits.
- **Rationale**: group numbers change whenever clustering re-runs; rides (by time) are what the
  user actually saw. Re-using 001's anchoring keeps one proven mechanism (constitution VI).
- **Alternatives**: a separate `riders_edits.json` (two logs to keep in step); storing group ids
  (breaks on every recompute).

## R7. Joining rides split at the frame edge (FR-011)

- **Decision**: after assignment, for consecutive rides A, B of the same rider where A ends with
  the rider at a frame edge and B starts off-frame (001 flags/`start_kind`), with gap
  ≤ `riders.join_gap_s` and both confidences ≥ `riders.join_confidence`, append a `merge` ride
  edit with `how: auto_join`. Otherwise show a one-click join suggestion. Undoing an auto join
  appends `rider_unjoin` for that pair so it is never re-joined.
- **Rationale**: uses 001's own edit mechanism, so joins are visible, undoable and survive re-runs.
- **Alternatives**: changing 001's assembly (it has no rider identity); always suggesting
  (clarification chose automatic when confident).

## R8. Evaluation labels and metrics

- **Decision**: `labels/riders/<video>.json` maps each labelled ride (from 001's labels) to a
  rider name. The labelling screen proposes the tool's groups; the user accepts or corrects each
  ride (expected ~15 min per session). Metrics: SC-001 = share of labelled rides whose detected
  ride's group is the group holding most of that true rider's rides (majority mapping,
  one-to-one); SC-002 = corrections a simulated user needs, answering the queue lowest-first with
  the truth, until every ride of the riders named in the label file (the user + any others) is
  right.
- **Rationale**: matches the clarifications (every ride labelled; corrections counted for named
  riders) and runs offline on every change (constitution II).
- **Alternatives**: pairwise precision/recall (harder to read); counting corrections by hand.

## R9. User interface

- **Decision**: a Riders screen per session: a grid of groups (example ride playable, a strip of
  stills, ride count), each with a name field, "same as…", "mixed", "ignore"; a queue panel
  showing one ride at a time beside the candidate rider's stills with "yes, it's X" / "no, it's…"
  buttons; join suggestions listed. The Review screen gains a rider filter that drives the ride
  list, play-all and "export as one video". Rider names are free text per session.
- **Rationale**: naming needs to see groups side by side; everyday use (play/export my rides)
  stays in Review.
- **Alternatives**: naming inside Review only (too cramped for comparing groups).

## R10. Exports

- **Decision**: per-rider export writes `clips/<rider>/<ride_id>.mp4` (hard links to the existing
  per-ride clips where possible, else copies) and `clips/reel_<rider>.mp4`; the manifest
  `clips/manifest.json` and `.csv` list ride id, start, end, rider, confidence, confirmed and clip
  path. Ignored riders and unassigned rides are left out of per-rider folders but listed in the
  manifest.
- **Rationale**: re-uses 001's clip cache and one-video join; no re-encoding per rider.
- **Alternatives**: re-encoding per rider (slow, duplicate files).

## T014 results (2026-10-16)

Rider labels: every labelled ride of the five sessions (4-9 riders each). Descriptors computed
from the same 8 sharpest crops per ride; the cut-off was swept on the four tuning sessions
(PXL_20261014_100546073 held out), picking the best worst-session score.

| Descriptor | Same / different rider median distance | SC-001 mean (tuning) | Worst tuning session | PXL (held out) |
| --- | --- | --- | --- | --- |
| colour (cut 0.14) | separation 1.14-1.60x | 48.8% | 38.6% (night HDR) | 75.3% |
| **embedding (cut 0.075)** | separation 1.53-2.07x | **82.8%** | 58.0% (night HDR) | **92.2%** |
| both (calibrated, cut 0.80) | separation 1.21-1.66x | 68.5% | 53.2% | 79.2% |

Per session with the embedding: 20240924 79.7%, 20241004 93.3%, 20260928_IMG_1652 100%,
20261012_110549566 58.0%, PXL 92.2%. Describing a 1 h session with embeddings takes 19-42 s on
the RTX 2060 (SC-006: ≤ 5 min).

**Decision**: `riders.descriptor = "embedding"`, `riders.cluster_threshold = 0.075`. The pretrained
embedding beats the colour baseline on every session (constitution VIII). Colour adds nothing
when mixed in. The night HDR session over-splits (3 riders → 9 groups), which "same as" merges
fix; SC-001 counts over-splitting as errors. Not tuned further on these sessions to avoid
over-fitting; the user's merges and queue answers (US1/US2) are the intended remedy.