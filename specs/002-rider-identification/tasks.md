---

description: "Task list for feature 002: rider identification"
---

# Tasks: Rider Identification

**Input**: Design documents from `/specs/002-rider-identification/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The constitution requires pytest (X) and evaluation metrics (II); grouping,
constraints, propagation and edit re-attachment are pure logic and test-first.

**Organization**: Setup and Foundational phases build a colour-baseline riders stage and the
rider-labelling screen first, so the user can label the five evaluation sessions while the rest
is built and the descriptor spike (T014) is decided on real labels. US1 is the MVP.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1-US4 from spec.md
- Paths follow plan.md: `src/surfclip/riders/`, `web/src/routes/`, `tests/`, `config/`, `scripts/`

---

## Phase 1: Setup

**Purpose**: Configuration and dependencies

- [x] T001 Add `scipy>=1.13` to pyproject.toml dependencies (already installed transitively; make it explicit)
- [x] T002 [P] Add a `[riders]` section to config/default.toml and a typed `RidersConfig` in src/surfclip/config.py with the keys of data-model.md "Config": `crops_per_ride = 12`, `keep_sharpest = 8`, `min_crop_height_px = 48`, `min_crops = 3`, `descriptor = "colour"` (`colour` | `embedding` | `both`), `cluster_threshold`, `queue_below = 0.5`, `stills = 6`, `join_gap_s = 6.0`, `join_confidence = 0.8`, `lighting_change_window_s = 30`
- [x] T003 [P] Add schemas to src/surfclip/store/schemas.py per contracts/session-files.md: `RiderGroup` (`kind` is `rider` | `lesson`), `RideAssignment` (`confidence` 0-1), `JoinSuggestion`, `Riders` (schema_version 1.0.0), and extend `EditOp` with `rider_name`, `rider_same_as`, `rider_mixed`, `rider_ignore`, `ride_rider`, `rider_unjoin`

---

## Phase 2: Foundational (riders stage with the colour baseline, and rider labels)

**Purpose**: Group rides by appearance and let the user label true riders; blocks all stories

### Tests

- [x] T004 [P] Unit tests for grouping in tests/unit/test_rider_cluster.py: synthetic ride descriptors in 3 well-separated clusters are recovered; two rides overlapping in time by more than `changeover_overlap_max_s` are never in one group (cannot-link); lesson rides form the `lesson` group; groups numbered by size
- [x] T005 [P] Unit tests for the colour descriptor in tests/unit/test_describe.py: region histograms of synthetic crops (red top / blue shorts vs blue top / red shorts) differ; the same crop under a uniform colour cast is close after grey-world normalisation; crops under `min_crop_height_px` are dropped and a ride with fewer than `min_crops` usable crops is `low_evidence`

### Implementation

- [x] T006 Implement crop sampling in src/surfclip/riders/crops.py: for each ride, `crops_per_ride` moments evenly across the ride, the ride's own track at each moment (tracks.parquet, ride.track_ids, source→review-copy scaling), 15% padded box crops from review.mp4 decoded once in time order; sharpness = variance of the Laplacian; keep the `keep_sharpest` sharpest with box height ≥ `min_crop_height_px`; matched board crop when present
- [x] T007 Implement the colour descriptor and per-session normalisation in src/surfclip/riders/describe.py (R2 option 1, R4): HSV histograms of upper body (20-50% of box height), lower body (50-85%) and board; grey-world correction from ~20 background samples of the review copy outside rider boxes; down-weight hue when the tint is strong; ride descriptor = mean over crops; until T005 passes
- [x] T008 Implement constrained grouping in src/surfclip/riders/cluster.py (R3): average-linkage agglomerative clustering on ride descriptors (SciPy), cannot-link pairs set to infinite distance, cut at `cluster_threshold`, lesson rides excluded into a `lesson` group, groups ordered by size; example ride = most sharp large crops; stills from different rides; until T004 passes
- [x] T009 Implement `RidersStage` in src/surfclip/stages.py after `rides`: writes appearance.parquet (reusing descriptors of rides whose span is unchanged) and riders.json; code version via `source_version("riders/*.py", ...)`; extra inputs = the rider ops in edits.json; add to `default_pipeline()` and to process.py's stage weights
- [x] T010 [P] Implement rider labels in src/surfclip/eval/riders.py: label work from 001's labels + current groups (proposed rider per labelled ride by time overlap), save/finalize `labels/riders/<video>.json` (contracts/session-files.md); never touches rides or edits
- [x] T011 Add rider-label routes to src/surfclip/api/app.py per contracts/http-api.md (`GET/PUT /sessions/{id}/rider-labels`, `POST .../finalize`, `GET .../media/rider-still.jpg`) and contract tests in tests/contract/test_api_riders.py
- [x] T012 Build the rider-labelling screen in web/src/routes/RiderLabels.svelte (route `#/rider-labels/<id>`): proposed groups as columns of ride stills; accept a group with a name, move a ride to another group with one click, play any ride; progress and finalize; link from Sessions
- [x] T013 Implement `surfclip eval-riders` (a separate command: `surfclip eval VIDEO` already scores rides) in src/surfclip/eval/riders.py and src/surfclip/cli.py (R8): SC-001 = share of labelled rides in their true rider's majority group (one-to-one mapping); SC-002 = corrections a simulated user needs, answering the queue lowest-first with the truth, until every ride of the label file's `named` riders is right *(SC-002 simulation moves to T024, which builds the queue)*

**Checkpoint**: the user labels the five evaluation sessions (about 15 min each) while US1 is built.

- [x] T014 Spike (R2): add the DINOv2 ViT-S/14 embedding as `descriptor = "embedding"` / `"both"` in src/surfclip/riders/describe.py (weights fetched by `surfclip models download`, never during processing); measure SC-001 and the riders-stage time for `colour`, `embedding`, `both` on every labelled session except PXL; adopt a non-colour option only if it beats colour on every session within SC-006; record results in specs/002-rider-identification/research.md under "T014 results" and set `riders.descriptor`; tune `cluster_threshold` on the same sessions only

---

## Phase 3: User Story 1 - Get my rides from a session (Priority: P1) 🎯 MVP

**Goal**: name groups, merge, split, ignore; play and export one rider's rides

**Independent Test**: on a labelled session, name the user's group (plus a few merges/splits) and
play/export that rider's rides; compare with the rider labels

### Tests

- [x] T015 [P] [US1] Unit tests for rider edits in tests/unit/test_rider_edits.py: `rider_name` names the group holding its anchor rides and confirms the example rides; `rider_same_as` joins two groups; `rider_mixed` splits a group in two; `rider_ignore` excludes a group; anchors re-attach by IoU ≥ 0.5 after ride ids change; `undo` reverts a rider edit
- [x] T016 [P] [US1] Contract tests for `GET /sessions/{id}/riders`, `POST /sessions/{id}/rider-edits` (records spans, returns recomputed riders; 400 `invalid_edit`, 404 `ride_not_found`) and `GET /sessions/{id}/rides?rider=` in tests/contract/test_api_riders.py

### Implementation

- [x] T017 [US1] Implement rider edits in src/surfclip/riders/edits.py (R6): resolve anchors to current rides (reuse `iou` and the resolution rules of src/surfclip/edits/apply.py), turn edits into must-link / cannot-link / name / ignore constraints, apply them in src/surfclip/riders/cluster.py; until T015 passes
- [x] T018 [US1] Add riders routes to src/surfclip/api/app.py (`GET riders`, `POST rider-edits` recording ride spans server-side and recomputing within 2 s, `rides?rider=` filter with `rider`/`rider_confidence` per ride); until T016 passes
- [x] T019 [US1] Build the Riders screen in web/src/routes/Riders.svelte (route `#/riders/<id>`, R9): groups largest first with example ride (playable), stills strip, ride count; name field, "same as…", "mixed", "ignore"; unnamed groups shown as "Rider N"; Lesson group separate; links from Sessions and Review
- [x] T020 [US1] Add a rider filter to web/src/routes/Review.svelte: the filter drives the ride list, timeline bars, play-all and "export as one video" (export with `rider`); show each ride's rider and confidence
- [x] T021 [US1] Per-rider reel in src/surfclip/media/export.py and the export route: `rider` restricts to that rider's rides; output `clips/reel_<rider>.mp4`; `GET .../media/reel.mp4?rider=`
- [x] T022 [US1] `surfclip riders VIDEO` and `surfclip riders name VIDEO --ride ID --name NAME` in src/surfclip/cli.py per contracts/cli.md

**Checkpoint**: "my rides" work end to end; measure SC-001 with `surfclip eval riders`

---

## Phase 4: User Story 2 - Fix uncertain assignments quickly (Priority: P2)

**Goal**: queue limited to named riders; each answer re-assigns the rest

**Independent Test**: count corrections to make the named riders' rides right on each labelled
session (SC-002 ≤ 10)

- [ ] T023 [P] [US2] Unit tests in tests/unit/test_rider_assign.py: confidence = margin to the nearest other rider; queue holds only rides below `queue_below` whose own or nearest other rider is named, lowest first; a `ride_rider` answer fixes that ride and changes neighbours' assignments; low-evidence rides are capped and queued; rides within `lighting_change_window_s` of a lighting change get lower confidence
- [ ] T024 [US2] Implement assignment, confidence and queue in src/surfclip/riders/assign.py (R5, R4 lighting change); re-cluster with all constraints after each answer (≤ 2 s for 100 rides); until T023 passes
- [ ] T025 [US2] Queue panel in web/src/routes/Riders.svelte: one ride at a time (playable) beside the candidate rider's stills; "yes, it's X" / "no, it's…" (pick another rider or "someone else"); remaining count; keyboard shortcuts
- [ ] T026 [US2] Mark unconfirmed rides in exports and the Review list (FR-005 acceptance 3)

---

## Phase 5: User Story 3 - Rider labels survive changes (Priority: P2)

**Goal**: rider edits survive ride edits, re-runs and zone changes; frame-edge joins

**Independent Test**: name and confirm, re-run with another min length, check labels (SC-005)

- [ ] T027 [P] [US3] Integration test in tests/integration/test_riders_rerun.py: name riders and confirm rides on a processed fixture session, re-run rides with `rides.min_length_s` changed, assert every surviving ride keeps its rider and new rides are assigned; splitting a ride keeps the rider on both parts; merging rides of different riders queues the result
- [x] T028 [P] [US3] Unit tests for joins in tests/unit/test_rider_assign.py: consecutive rides of one rider, first ending at a frame edge and second starting off-frame, gap ≤ `join_gap_s`, both ≥ `join_confidence` → auto join; otherwise a suggestion; an undone auto join (`rider_unjoin`) is never repeated
- [x] T029 [US3] Implement frame-edge joins in src/surfclip/riders/assign.py and src/surfclip/stages.py (R7): auto joins written to auto_joins.json by the riders stage (stages never write edits; constitution VI) and applied when rides.json is rebuilt; `rider_unjoin` edits win; suggestions in riders.json; `POST /sessions/{id}/joins` in src/surfclip/api/app.py; suggestions with one-click join in web/src/routes/Riders.svelte; until T028 passes
- [ ] T030 [US3] Rider behaviour on ride edits in src/surfclip/riders/edits.py: split parts inherit the rider (confirmed if the original was); a merge of rides of different riders is unconfirmed and queued; hand-added rides are described from their time span's person if found, else unassigned and queued

---

## Phase 6: User Story 4 - Per-rider export and session manifest (Priority: P3)

**Goal**: per-rider folders and the manifest

**Independent Test**: export a session with three riders and check folders and manifest

- [ ] T031 [P] [US4] Integration test in tests/integration/test_export.py: per-rider folders (hard links or copies of existing clips, no re-encode), ignored riders absent, manifest JSON/CSV rows for every ride with rider, confidence, confirmed and clip path
- [ ] T032 [US4] Implement `per_rider` and `manifest` export in src/surfclip/media/export.py, the export route and `surfclip export --rider/--per-rider/--manifest` in src/surfclip/cli.py (R10); export buttons in web/src/routes/Riders.svelte

---

## Phase 7: Polish & Cross-Cutting

- [ ] T033 Evaluation report: run `surfclip eval riders` on all five sessions (PXL held out), record SC-001/SC-002 per session and the riders-stage time per hour (SC-006) in specs/002-rider-identification/eval-log.md
- [ ] T034 [P] Measure the user's hands-on time for naming + queue on one 1 h session (SC-003) and "rides found → my reel" time (SC-004); record in eval-log.md
- [ ] T035 [P] Privacy check: appearance.parquet and riders.json are only read for their own session (grep/test), no network calls during the riders stage, no face crops stored separately
- [ ] T036 Update specs/001-ride-detection-clipping/contracts and specs/002-rider-identification/quickstart.md with any changes found while implementing; run every quickstart scenario

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (T004-T013) → user labelling (checkpoint) → T014 spike.
- US1 (Phase 3) can start after T009; it does not wait for the labels or the spike (colour
  baseline first, swapped by configuration if T014 adopts the embedding).
- US2 depends on US1's edits (T017). US3 depends on US1 (T017) and US2's assignment (T024) for
  joins. US4 depends on US1's per-rider reel (T021).
- Polish after the stories; T033 needs the labels.

## Parallel Opportunities

- T002 and T003; T004 and T005; T010 alongside T006-T009; T015 and T016; T023 alongside T019/T020;
  T027 and T028; T031 alongside T029/T030; T034 and T035.

## Implementation Strategy

1. MVP: Phase 1-2 (colour baseline + labelling screen), then US1. The user can name "me" and
   export their reel; SC-001 is measured as soon as labels exist.
2. Decide the descriptor with the spike (T014) on the labels; re-measure.
3. US2 (queue) and US3 (survive changes, joins), then US4 (exports, manifest).
4. Stop after each story to validate against quickstart.md and the labels.
