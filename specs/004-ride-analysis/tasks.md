---

description: "Task list for feature 004: ride analysis"
---

# Tasks: Ride Analysis

**Input**: Design documents from `/specs/004-ride-analysis/`

**Tests**: Included (constitution X). Signals, events and ending rules are pure functions on
arrays and are test-first on synthetic signals; thresholds are tuned only on the user's marks.

**Organization**: the Marks screen and keypoint extraction come first so the user can mark rides
while the signals are built; signal choice (R3) and thresholds are decided on the marks.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Add `[analysis_pose]` to config/default.toml and `AnalysisPoseConfig` in src/surfclip/config.py (data-model.md "Config"); add the pose weights to `models download` and `/api/health` models
- [x] T002 [P] Schemas in src/surfclip/store/schemas.py: `RideAnalysis`, `AnalysisEvent`, `AnalysisFile`, `AnalysisMarks`; `EditOp` += `ride_ending`, `turn_add`, `turn_remove`, `trick_tag`; `StageName` += `analysis`

## Phase 2: Foundational (marks for evaluation, keypoints)

- [x] T003 [P] Marks: src/surfclip/analysis/marks.py (work from named riders' rides, save/finalize `labels/analysis/<video>.json`, re-attach by span) and routes `GET/PUT /sessions/{id}/marks`, `POST .../marks/finalize`; contract tests
- [x] T004 Marks screen web/src/routes/Marks.svelte (`#/marks/<id>`): your rides in order, review-copy player at 0.5x default, `t` turn at playhead, `p` pump, `f`/`e`/`u` ending, list of marks per ride with delete, progress, finalize; link from Sessions
- [x] T005 Keypoint extraction src/surfclip/analysis/pose.py: decode the ride span at `fps` from the source (tone-mapped like the review copy), interpolate the ride's track boxes, crop with margin, YOLO-pose (batched), pick the person nearest the crop centre, `other_iou` against other tracks; write `analysis/<ride>.parquet`; unit test the box interpolation and person picking on synthetic data
- [x] T006 `AnalysisStage` in src/surfclip/stages.py + src/surfclip/analysis/service.py: named riders' rides only (riders.json names), per-ride cache key, reuse unchanged rides, drop rides no longer named; `surfclip analyse`; `POST /sessions/{id}/analysis` job

**Checkpoint**: the user marks ≥ 10 of their rides on PXL and 20241004 (and later a third,
held-out session) while US1 is built.

## Phase 3: US1 - See how I move on each ride (P1) 🎯 MVP

- [x] T007 [P] [US1] Unit tests tests/unit/test_analysis_signals.py: each R3 signal is invariant to uniform scaling of keypoints (zoom) and to mirroring; unclear frames → null; smoothing keeps a 0.5 s dip
- [x] T008 [P] [US1] Unit tests tests/unit/test_analysis_events.py: synthetic compression + lateral signals with known turns/pumps → detected within 0.2 s; trimming share; endings for synthetic fall (collapse in the face band) vs exit (track ends at a side wall upright)
- [x] T009 [US1] src/surfclip/analysis/signals.py: the three R3 compression signals, lateral pool `u` (zone + epochs; null on handheld spans), torso rotation, unclear mask
- [x] T010 [US1] src/surfclip/analysis/events.py: turns, pumps, trimming, shares, endings (R4, R5); summary incl. `rhythm_cv`
- [ ] T011 [US1] src/surfclip/analysis/marks.py `eval-analysis`: SC-001 (turn precision/recall within 0.5 s), SC-002 (ending accuracy), SC-003 (share error vs marked pumps/turn windows); CLI `surfclip eval-analysis`
- [ ] T012 [US1] Choose the R3 signal and tune thresholds on the marked sessions except the held-out one; record "R3 results" in research.md and eval-log.md; set config defaults
- [ ] T013 [US1] Analysis edits (`ride_ending`, `turn_add`, `turn_remove`) applied after the stage output in service.py, re-attached by span; `POST /sessions/{id}/analysis-edits`; `GET /sessions/{id}/analysis`, keypoints route scaled to review-copy pixels; contract tests tests/contract/test_api_analysis.py
- [ ] T014 [US1] web/src/lib/Skeleton.svelte (canvas over the review video, interpolates keypoints between analysis frames, toggle `k`) and web/src/lib/AnalysisStrip.svelte (compression curve, turns ▼, pumps ·, ending, tags; click to seek; right-click a marker to remove; `+ turn` at playhead); wire into Review.svelte for analysed rides; ride summary in the selected-ride panel
- [ ] T015 [US1] Check in the browser on PXL and 20241004: overlay at 1x without lag (SC-005), strip matches what the video shows; record in eval-log.md

## Phase 4: US2 - Before falls (P2)

- [ ] T016 [P] [US2] Unit tests for the fall comparison windows and measures (summary.py) on synthetic analyses
- [ ] T017 [US2] src/surfclip/analysis/summary.py fall comparison (R6) and `GET /sessions/{id}/falls`
- [ ] T018 [US2] web/src/routes/Analysis.svelte (`#/analysis/<id>`): ride table (length, turns, pumps, rhythm, ending, shares), **Before falls** panel (per measure: falls vs exits as dots, medians), **play falls** (back-to-back pre-fall windows in the review copy)

## Phase 5: US3 - Turning, pumping, trimming and trends (P2)

- [ ] T019 [P] [US3] Unit tests for session shares and trend pooling by name (case-insensitive; unnamed and other names excluded; appearance never read)
- [ ] T020 [US3] Session shares in summary.py; `GET /api/trends?rider=`; web/src/routes/Trends.svelte (`#/trends/<name>`): one small chart per measure, a point per session in date order; links from Analysis

## Phase 6: US4 - Trick tags (P3)

- [ ] T021 [US4] `trick_tag` edits (`t` key in Review/Analysis with a name prompt remembering recent names); `GET /api/tricks?name=&rider=`; Tricks list in Analysis with play-all per name; delete via undo
- [ ] T022 [US4] Contract tests for tags and the cross-session list

## Phase 7: Polish

- [ ] T023 Run on all sessions where the user is named; timing per ride (SC-004); held-out evaluation in eval-log.md
- [ ] T024 [P] Docs: README / quickstart; scripts/README spikes
- [ ] T025 scripts/check.sh, web check/build; fix everything
