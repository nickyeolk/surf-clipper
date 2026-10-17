---

description: "Task list for feature 004: ride analysis (rescoped 2026-10-17)"
---

# Tasks: Ride Analysis

**Input**: Design documents from `/specs/004-ride-analysis/`

**Tests**: Included (constitution X).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup and foundation (built before the rescope)

- [x] T001 `[analysis_pose]` config, pose weights in models download and health
- [x] T002 Analysis schemas and edit ops
- [x] T005 Keypoint extraction (src/surfclip/analysis/pose.py)
- [x] T006 Analysis stage, `surfclip analyse-rides`
- [x] T007 Signal unit tests (zoom and mirror invariance, unclear frames)
- [x] T008 Event unit tests (turns vs pumps, endings)
- [x] T009 Compression signal (src/surfclip/analysis/signals.py)
- [x] T010 Turns, pumps, shares, endings (src/surfclip/analysis/events.py)
- [x] R001 Remove the turn-marking screen, marks module, routes and tests (rescope: stars replace marks); edit ops become `ride_star`, `trick_tag`

## Phase 2: Measures and keypoints for the UI

- [ ] T011 [P] Unit tests: lean, arm spread, stance width are zoom- and mirror-invariant (lean flips sign when mirrored); unclear → null
- [ ] T012 Measures in src/surfclip/analysis/signals.py; series `lean`, `arms`, `stance` in `RideAnalysis`
- [ ] T013 Routes: `GET /sessions/{id}/analysis` (with stars and tags applied), `POST /sessions/{id}/analysis` (job), `GET /sessions/{id}/analysis/{ride}/keypoints` (review-copy pixels + crop box per frame); contract tests

## Phase 3: US1 - Side by side (P1) 🎯

- [ ] T014 web/src/lib/Skeleton.svelte: canvas overlay drawing keypoints interpolated to the video time, scaled into a crop, mirror-aware
- [ ] T015 web/src/lib/CropPlayer.svelte: review video in a container whose CSS transform follows the surfer's smoothed crop box; skeleton; exposes time, seek, play, rate, frame step; mirror toggle
- [ ] T016 web/src/routes/Compare.svelte (`#/compare?a=…&b=…`): pickers for A and B (my rides, named riders' rides in any session, references, trick tags), sync point per side ("set sync here", "snap to nearest turn/tag"), shared transport keeping B at A's offset (resync each frame when drift > half a frame), measure curves of both aligned at sync (SVG); entry points from Review, Riders and Tricks
- [ ] T017 Browser check (SC-001, SC-005): two rides synced within one frame over 30 s at 1x and 0.25x; skeletons keep up; record in eval-log.md

## Phase 4: US2 - Reference clips (P1)

- [ ] T018 [P] Unit tests: track chosen by a click (box containing the point, nearest centre otherwise); the clip's ride spans that track
- [ ] T019 `Session.kind` (`footage` | `reference`) and `reference.json`; `POST /references` (import from the footage folder: probe → review copy → detect → track job), `GET /references`, `GET /references/{id}/frame.jpg?t=` with people boxes, `POST /references/{id}/surfer` {t, x, y} → choose track, analyse; src/surfclip/analysis/reference.py; CLI `surfclip reference add|pick`
- [ ] T020 UI: References section on Sessions (import, status, pick-surfer view: click a person on a frame scrubber), references available in Compare
- [ ] T021 Check: import a 60 s clip (SC-003); a two-person clip, pick the second person

## Phase 5: US3 - Best rides (P2)

- [ ] T022 [P] Unit tests for src/surfclip/analysis/score.py: feature standardisation, default weights, fit raises starred rides' rank on synthetic data, explanation lists top contributions in words
- [ ] T023 score.py: features, defaults from `[score]`, fit to stars pooled over sessions (≥ 5 starred and ≥ 5 unstarred, else defaults), `artifacts/score.json`; `ride_star` edits; `POST /sessions/{id}/stars`; scores in `GET /analysis`; `surfclip eval-score` (SC-002, leave one session out)
- [ ] T024 web/src/routes/Best.svelte (`#/best/<id>`): your rides by score with thumbnails, explanation, star toggle, play, select → compilation (003); star toggle also in Review
- [ ] T025 User stars ≥ 10 rides over 2 sessions; run eval-score; record in eval-log.md

## Phase 6: US4 - Trick tags (P3)

- [ ] T026 `trick_tag` edits (`POST /sessions/{id}/tricks`, delete via undo), `GET /api/tricks?name=`; tag button / `g` key in Review; web/src/routes/Tricks.svelte (by name, play all, open in Compare)
- [ ] T027 Contract tests for tags

## Phase 7: Polish

- [ ] T028 Run on all named sessions; timings (SC-004) in eval-log.md
- [ ] T029 [P] Docs (quickstart, contracts), scripts/README
- [ ] T030 scripts/check.sh, web check/build
