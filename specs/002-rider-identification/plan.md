# Implementation Plan: Rider Identification

**Branch**: `002-rider-identification` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-rider-identification/spec.md`

## Summary

Group each session's rides by the person riding, let the user name riders (optionally just
"me"), and play, review and export rides per rider. A new cached **riders** stage runs after the
rides stage of 001: it samples crops of the ride's tracked person from the existing 720p review
copy (no new detection), describes each ride's appearance (clothing, board and colours, plus a
pretrained image embedding if it beats colours on the labels), and groups rides with constrained
clustering (rides overlapping in time are never the same rider). User actions (name, same as,
mixed, ignore, confirm, reassign) are append-only rider edits anchored to rides by time span, so
they survive ride edits and re-runs exactly like 001's ride edits. A Riders screen does naming and
the review queue; the Review screen gains a rider filter, per-rider play-all and per-rider
one-video export; exports gain per-rider folders and a manifest.

## Technical Context

**Language/Version**: Python 3.12 (pipeline, CLI, backend); TypeScript 5 + Svelte 5 (UI)

**Primary Dependencies**: as 001 (ffmpeg, NumPy, OpenCV, PyTorch CUDA, pydantic v2, FastAPI,
Typer, pyarrow); new: SciPy (hierarchical clustering) and, if it wins the spike (R2), a pretrained
image-embedding model loaded through PyTorch (DINOv2 ViT-S/14 weights downloaded once by
`surfclip models download`, like the YOLO weights)

**Storage**: per-session files under `artifacts/<session>/`: `appearance.parquet` (per-crop and
per-ride descriptors, this session only), `riders.json` (groups and assignments, stage output);
rider edits appended to the existing `edits.json`; rider labels for evaluation in
`labels/riders/<video>.json`

**Testing**: pytest (unit: clustering, constraints, propagation, edit re-attachment; contract:
API; integration: riders stage on a fixture); evaluation harness `surfclip eval riders` for
SC-001/SC-002 per labelled session

**Target Platform**: as 001 (Windows 11 laptop, RTX 2060 6 GB; backend in WSL2; UI in Chrome)

**Project Type**: Python library + CLI + local web service, browser frontend (as 001)

**Performance Goals**: riders stage ≤ 5 min per hour of footage after rides exist (SC-006);
re-assignment after a user action ≤ 2 s for 100 rides (FR-013)

**Constraints**: no face recognition; appearance data and names stay inside one session folder and
are never compared across sessions (FR-009, constitution I); no second detection pass (FR-013,
constitution VII); thresholds in config (constitution IX); invariant to zoom, angle and lighting
(constitution III)

**Scale/Scope**: up to ~15 riders and ~100 rides per session; 8-16 crops per ride

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | How this plan complies | Status |
| --- | --- | --- | --- |
| I | Local-first and personal | No network during processing; no faces (crops are whole-person, descriptors are clothing/board/body appearance); descriptors and names stay in the session folder and are never compared across sessions | Pass |
| II | Evaluation before features | Rider labels for every ride on the five labelled sessions; `surfclip eval riders` reports SC-001/SC-002 per session; PXL held out from tuning; descriptor choice decided by measured SC-001 (R2) | Pass |
| III | Scale-, perspective-, mirror-invariant | Crops resized to a fixed height; no pixel-size features; colour normalised per session (and per epoch when 001's epochs exist); no left/right assumptions | Pass |
| IV | Assume the camera moves | Colour normalisation per camera epoch; descriptors do not use image position | Pass |
| V | Confirm late, start early | Not applicable (no ride timing changes); automatic frame-edge joins only when confident (FR-011) | Pass |
| VI | Human corrections are ground truth | Rider edits append-only in `edits.json`, anchored to ride spans, applied as hard constraints after every recompute; automatic joins recorded as undoable edits and never repeated after an undo | Pass |
| VII | Staged, cached pipeline | New `riders` stage with its own cache key (rides + rider edits + config); crops come from the review copy; detection never re-runs | Pass |
| VIII | Simple first | Colour descriptors are the baseline; a pretrained embedding is adopted only if it beats the baseline on SC-001 within the time budget (R2); no training | Pass |
| IX | Config, not constants | `[riders]` section: crops per ride, clustering threshold, confidence threshold, join gap and confidence | Pass |
| X | Engineering standards | Library + CLI + thin API; UI has no grouping logic; pyright, ruff, pytest | Pass |
| XI | Scope discipline | Within-session riders only (cross-session identity out of scope by the clarification); no manoeuvres or pose | Pass |

Post-design re-check (after Phase 1): **Pass**. The data model keeps rider edits separate from the
stage output (`riders.json` is reproducible from rides + appearance + edits); contracts expose
operations only; appearance files live in the session folder.

## Project Structure

### Documentation (this feature)

```text
specs/002-rider-identification/
├── plan.md              # This file
├── research.md          # Phase 0: decisions (descriptor spike, clustering, propagation, UI)
├── data-model.md        # Phase 1: entities, stage files, rider edits
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── cli.md           # surfclip riders / labels riders / eval riders / export --rider
│   ├── http-api.md      # riders, rider edits, queue, rider labels, per-rider export
│   └── session-files.md # appearance.parquet, riders.json, rider edit ops, rider labels
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/surfclip/
├── riders/
│   ├── crops.py         # sample crops of a ride's tracked person from the review copy
│   ├── describe.py      # colour descriptor; optional embedding; per-session colour normalisation
│   ├── cluster.py       # constrained agglomerative grouping (cannot-link: overlapping rides)
│   ├── assign.py        # propagation to riders, confidences, review queue, frame-edge joins
│   └── edits.py         # apply rider edits (anchor re-attachment by time overlap)
├── stages.py            # + RidersStage (after rides)
├── media/export.py      # + per-rider folders, per-rider reel, manifest JSON/CSV
├── eval/riders.py       # rider labels, SC-001/SC-002 metrics
├── api/app.py           # + rider routes
└── cli.py               # + riders, labels riders, eval riders, export --rider

web/src/
├── routes/Riders.svelte # groups: name / same as / mixed / ignore; review queue
├── routes/Review.svelte # + rider filter, per-rider play-all and one-video export
└── routes/RiderLabels.svelte  # evaluation labelling (accept/correct proposed groups)

tests/
├── unit/test_rider_cluster.py, test_rider_assign.py, test_rider_edits.py, test_describe.py
├── contract/test_api_riders.py
└── integration/test_riders_stage.py
```

**Structure Decision**: extend the existing single library (`src/surfclip`) with a `riders`
package and one new stage, the existing FastAPI app and the existing Svelte UI, as in 001.

## Complexity Tracking

No constitution violations. One new runtime dependency group (SciPy; embedding weights only if
R2's spike adopts them) is justified by R2/R3.
