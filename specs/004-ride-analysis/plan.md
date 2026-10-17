# Implementation Plan: Ride Analysis

**Branch**: `004-ride-analysis` | **Date**: 2026-10-17 (rescoped) | **Spec**: [spec.md](spec.md)

## Summary

A cached **analysis** stage (built) runs pose on full-resolution crops of named riders' rides and
derives body-relative signals: compression, lean, arm spread, stance width, turns and the ending.
On top of it:

1. **Comparison** (P1): a screen with two players, each showing the review copy cropped to its
   surfer (crop follows the analysed box), skeleton overlay, mirror toggle, a sync point per
   clip, shared transport (play, 0.25-1x, frame step) and the four measure curves of both on one
   time axis aligned at the sync points. Sync can snap to a detected turn or a trick tag.
2. **Reference clips** (P1): a video imported from the footage folder becomes a session of kind
   `reference`: probe, review copy, detect and track as usual (no zone, rides or riders); the user
   clicks the surfer on a frame, the clicked track becomes the clip's single "ride", and the same
   analysis runs on it.
3. **Score** (P2): per analysed ride, a weighted sum of standardised features (length, clean
   ending, compressions and their depth, rhythm regularity, tagged tricks), with weights fitted to
   the user's stars (L2-regularised logistic regression, pooled over sessions; defaults below 5
   stars), explained by its top contributions. Rides sortable by score; "compilation of these".
4. **Trick tags** (P3): `trick_tag` edits; lists per session and across sessions; open in the
   comparison with the tag as sync point.

Stars and tags are append-only edits anchored to rides by span (constitution VI); stars are
also the evaluation labels for the score (SC-002).

## Technical Context

**Language/Version**: Python 3.12; TypeScript 5 + Svelte 5

**Primary Dependencies**: as before; YOLO11s-pose (downloaded); no new packages (score fit in NumPy)

**Storage**: `artifacts/<session>/analysis/<ride>.parquet`, `analysis.json` (now with measure
series, score parts); reference clips are sessions with `kind = "reference"` and
`reference.json` (chosen track, time span); stars and tags in `edits.json`; score weights in
`artifacts/score.json` (fitted, per user, not per session)

**Testing**: pytest (signals/measures invariance, score fit and explanation, reference track
choice, edits); contract tests for routes; browser check of the comparison sync (SC-001);
`surfclip eval-score` for SC-002 with one session held out

**Performance Goals**: ≤ 20 s per ride (measured 6 s); reference import ≤ 3 min for 60 s;
comparison playback in sync within one frame

**Constraints**: body-relative measures (FR-002); named riders and references only (FR-011);
imported clips read-only from the footage folder; no network

## Constitution Check

| # | Principle | How this plan complies | Status |
| --- | --- | --- | --- |
| I | Local-first and personal | Pose local; only named riders and user-imported references analysed; score pools only the user's own starred rides by their naming | Pass |
| II | Evaluation before features | Score evaluated on stars (SC-002, held-out session); comparison sync measured in the browser (SC-001); turn detection is a helper (snap), not a reported metric | Pass |
| III | Scale-, perspective-, mirror-invariant | Body ratios; mirror toggle for stance/direction; lean labelled camera-relative | Pass |
| IV | Assume the camera moves | Crops follow the surfer per frame; handheld clips supported | Pass |
| V | Confirm late, start early | Not applicable | Pass |
| VI | Human corrections are ground truth | Stars and tags are edits; stars override nothing but steer the score | Pass |
| VII | Staged, cached pipeline | Reference clips reuse probe/review/detect/track stages; analysis cached per ride | Pass |
| VIII | Simple first | CSS crop + canvas overlay; logistic regression on 7 features; manual sync points | Pass |
| IX | Config, not constants | `[analysis_pose]` and `[score]` sections | Pass |
| X | Engineering standards | Library + CLI + thin API; UI renders only | Pass |
| XI | Scope discipline | No trick recognition, no auto-sync, no trends/fall comparison | Pass |

## Project Structure

```text
src/surfclip/analysis/
├── pose.py       # keypoints (built)
├── signals.py    # compression (built) + lean, arm spread, stance width
├── events.py     # turns, pumps, ending (built)
├── score.py      # features, fit to stars, explanation
├── reference.py  # reference clips: track at a click, the clip's ride
└── service.py    # analysis stage (built) + edits (stars, tags) applied on read
src/surfclip/api/app.py   # analysis, keypoints, references, stars, tags, score routes
src/surfclip/cli.py       # analyse-rides (built), reference add/pick, eval-score
web/src/lib/Skeleton.svelte      # canvas overlay (crop-aware, mirror)
web/src/lib/CropPlayer.svelte    # review video cropped to the surfer + skeleton
web/src/routes/Compare.svelte    # #/compare?a=<sid>:<ride>&b=<sid>:<ride>
web/src/routes/Best.svelte       # #/best/<sid>: rides by score, stars, compilation
web/src/routes/Tricks.svelte     # #/tricks: tags across sessions
web/src/routes/Sessions.svelte   # References section, import a clip
```

Removed in the rescope: the Marks screen and `labels/analysis` (turn marking), fall comparison,
trends.

## Complexity Tracking

No violations.
