---

description: "Task list for feature 001: ride detection and clipping"
---

# Tasks: Ride Detection and Clipping

**Input**: Design documents from `/specs/001-ride-detection-clipping/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The constitution requires pytest (X), metrics on the evaluation set (II), and
SC-007 requires a re-run regression test. Pure-logic modules (geometry, state machine, joining,
edits) are test-first; media and UI tasks get integration tests.

**Organization**: Grouped by user story. US1 is the MVP: it uses a zone supplied as a file (via
`surfclip zone --from-file`), so it can be built and measured before the zone proposal and UI (US2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 from spec.md
- Paths follow plan.md: `src/surfclip/`, `web/`, `tests/`, `config/`, `scripts/`, `artifacts/` (gitignored)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify research assumptions, then initialise the project

- [x] T001 Spike: verify research items marked "Verify in T001" inside WSL2 and record measured results under a new "T001 results" heading in specs/001-ride-detection-clipping/research.md — (a) `ffmpeg -filters` lists `zscale` and `tonemap`; (b) YOLO11s throughput on the RTX 2060 for 5 min of `20250326_1.MP4` at 5 fps, with and without 2×2 tiling, target ≤ 15 min/h extrapolated; (c) HLG and PQ round-trip through `hevc_nvenc` main10 keeps `color_primaries`/`color_transfer`/`color_space` per `ffprobe` (generate 10 s HDR test sources with ffmpeg if no HDR sample exists); (d) Chrome/Edge on Windows seeks within ≤ 1 s in a 1 h `review.mp4` served with HTTP Range from WSL2 `localhost`; (e) `docker run --gpus all` with a CUDA base image sees the GPU under Docker Desktop. Scripts go in scripts/spikes/, outputs in artifacts/spikes/; sources read-only
- [x] T002 Create the project layout from plan.md: src/surfclip/{config.py,pipeline.py,cli.py,store/,media/,detect/,track/,epochs/,zone/,rides/,edits/,eval/,api/}, tests/{unit,contract,integration}/, scripts/, config/, web/
- [x] T003 Initialise the uv project in pyproject.toml (Python 3.12, package `surfclip`, console script `surfclip = surfclip.cli:app`; deps numpy, opencv-python-headless, ultralytics, torch (CUDA wheel index), supervision, pydantic>=2, fastapi, uvicorn, typer, pyarrow, tomli-w; dev deps pytest, pyright, ruff)
- [x] T004 [P] Configure ruff and pyright (strict for src/surfclip) in pyproject.toml; add a `pytest` marker `integration` that requires artifacts/fixtures/
- [x] T005 [P] Initialise web/ with Vite + Svelte 5 + TypeScript (web/package.json, web/vite.config.ts with dev proxy `/api` → `http://127.0.0.1:8765`, build output web/dist/)
- [x] T006 [P] Write config/default.toml with every key listed in data-model.md "Config" (incl. `rides.confirm_window_s = 1.5`, `rides.acid_link_s = 1.0`, `rides.frame_edge_grace_s = 2.0`, `rides.min_length_s = 10`, `rides.pad_before_s = 1.0`, `rides.pad_after_s = 1.5`, `rides.refine_window_s = 2.0`, `analysis.fps = 5`, `server.host = "127.0.0.1"`, `server.port = 8765`) and a `config_version`
- [ ] T007 [P] Write scripts/make_fixtures.py: cut short fixture clips (stream copy, never writing to the source folder) from the sample sessions into artifacts/fixtures/ — an acid drop from a side wall, a side-wall sitter, a lesson segment from `20241004.MP4`, a near-edge truncated ride, an off-frame entry and a portrait night ride from `20260928_IMG_1652.MOV`, a blurred HDR ride from `20261012_110549566.mp4`, and a 3 min multi-ride stretch from `20240924.MP4`; list chosen timestamps in scripts/fixtures.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, storage, media primitives and schemas used by every story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T008 Implement config loading and per-session overrides (dotted keys like `rides.min_length_s`) in src/surfclip/config.py; unit test in tests/unit/test_config.py
- [x] T009 [P] Define pydantic models for every file in contracts/session-files.md (Session, SourceInfo, CameraEpoch, Zone, Ride, ShortAttempt, UserEdit, markers) with `schema_version` in src/surfclip/store/schemas.py; Ride validation "`end > start`; rides ≥ `min_length_s` unless `user_added`"
- [x] T010 [P] Contract tests: the JSON examples in contracts/session-files.md validate against the models, and models serialise to the documented shapes, in tests/contract/test_session_files.py
- [x] T011 Implement session folders and stage records in src/surfclip/store/session.py: `session_id` = short hash of source path + size + mtime; folder artifacts/<session_id>/; stage status with cache key (hash of inputs + config section + `config_version` + stage code version); atomic JSON writes; refuse any path inside the source video's folder
- [x] T012 [P] Implement ffprobe wrapper → SourceInfo (codec, fps, VFR detection, bit depth, colour tags, hdr_format none/hlg/hdr10/dolby_vision, rotation) and input validation (reject > 1.5 h or unsupported codec with a clear message) in src/surfclip/media/probe.py; tests on fixture clips in tests/integration/test_probe.py
- [x] T013 [P] Implement decode pipes in src/surfclip/media/decode.py: low-fps analysis proxy (≤ 720p height, SDR; HDR tone-mapped with zscale+tonemap per research R2) yielding (frame_index, pts_s, ndarray), and full-rate window decode for [t0, t1]; timestamps from PTS
- [x] T014 [P] Implement pool-coordinate geometry in src/surfclip/zone/geometry.py: role-ordered corners → image↔pool homography, point-in-region tests, distances in pool units and rider heights; mirror test (same scene flipped left-right gives identical pool results) in tests/unit/test_geometry.py
- [x] T015 Implement the stage runner with cache checks in src/surfclip/pipeline.py (stages: probe, proxy, review_copy, detect, track, epochs, zone_proposal, rides, refine, apply_edits) and logging to artifacts/<session>/pipeline.log
- [x] T016 [P] Implement CLI skeleton with `probe` and `ingest` (contracts/cli.md: `--artifacts`, `--config`, `--json`, exit codes 0/1/2) in src/surfclip/cli.py

**Checkpoint**: `surfclip probe` and `surfclip ingest` work on every sample session

---

## Phase 3: User Story 1 - Get every ride from a session video (Priority: P1) 🎯 MVP

**Goal**: Ride list + final-quality clips for a session whose zone is provided as a file

**Independent Test**: With hand-made zone files for the four evaluation sessions (`20260928_IMG_1652`, `20240924`, `20241004`, `20261012_110549566`), run
`surfclip run`, compare `rides.json` with hand labels via `surfclip eval`, and play exported clips

### Tests for User Story 1 ⚠️ (write first, must fail)

- [ ] T017 [P] [US1] State-machine unit tests with synthetic tracks in tests/unit/test_state_machine.py: side-wall sitter overlapping the zone in the image stays `off`; person in water without board stays `off`; ride confirmed after 1.5 s and start back-dated to the drop-in; track first seen at the frame edge already on the wave (entry wall off-frame) starts at first appearance with `start_kind = off_frame`; fall ends ride on last on-wave frame; changeover overlap gives two rides
- [ ] T018 [P] [US1] Ride-joining unit tests in tests/unit/test_joining.py: acid-drop link (track end on/at an entry side wall + on-wave track start within 1 s and N rider heights) starts at the jump; same-edge frame-edge exit and return within 2 s is one ride; return after 2.5 s is two rides; ride < `min_length_s` becomes a short attempt; lesson stretch → only the person on a board rides, flagged `lesson`
- [ ] T019 [P] [US1] Eval metric unit tests (IoU ≥ 0.5 matching, recall, precision, boundary error p95/median, acid drops separately) in tests/unit/test_eval_metrics.py
- [ ] T020 [P] [US1] Integration test: pipeline on the 3 min multi-ride fixture with a fixture zone file produces rides.json that validates against the schema and finds the labelled rides, in tests/integration/test_rides_pipeline.py

### Implementation for User Story 1

- [ ] T021 [P] [US1] Implement person + surfboard detection with YOLO11 (model and confidence from config, CUDA with CPU fallback via `--cpu`) and selective 2×2 tiling where expected rider height < `detect.tiling_min_height_px_at_720p`, writing detections.parquet, in src/surfclip/detect/detector.py
- [ ] T022 [P] [US1] Implement ByteTrack tracking with gap tolerance in seconds, truncated-edge flags, and feet-point estimation (bottom-centre; from board when feet hidden; from box top + usual height otherwise) → tracks.parquet in src/surfclip/track/tracker.py
- [ ] T023 [US1] Implement `surfclip zone SESSION --from-file zone.json` (appends a `confirm_zone` edit) in src/surfclip/cli.py and src/surfclip/edits/log.py (append-only writer for edits.json; pipeline stages must not import the writer)
- [ ] T024 [US1] Implement per-frame evidence (region via feet point in pool coords, board contact, stance from box aspect, lateral speed in pool units/s) in src/surfclip/rides/evidence.py
- [ ] T025 [US1] Implement the per-track state machine (data-model.md transitions) in src/surfclip/rides/state_machine.py until T017 passes
- [ ] T026 [US1] Implement ride assembly in src/surfclip/rides/assemble.py: acid-drop linking, frame-edge grace joining, lesson flag, minimum length → short attempts, padding, confidence score, `start_kind`, stable `ride_id` (`r` + start frame), output rides.detected.json; until T018 passes
- [ ] T027 [US1] Implement boundary refinement at full frame rate within ±`rides.refine_window_s` (decode window, detect, re-evaluate evidence, move boundary) in src/surfclip/rides/refine.py
- [ ] T028 [US1] Implement apply-edits (rides.detected.json + edits.json → rides.json, deterministic) in src/surfclip/edits/apply.py
- [ ] T029 [US1] Implement final clip export in src/surfclip/media/export.py: frame-accurate re-encode of `clip_start_s`..`clip_end_s`; HDR sources → hevc_nvenc main10 copying colour primaries/transfer/matrix and HDR10 mastering metadata, Dolby Vision → HLG base layer; SDR → h264_nvenc high quality; libx265/libx264 with `--cpu`; skip rides whose export cache key (boundaries + source + encoder settings) is unchanged; write clips/<ride_id>.mp4 and update `export` in rides.json
- [ ] T030 [US1] Add CLI commands `analyse`, `rides`, `run` (with `--min-length`, `--timings`) and `export` (`--all`, `--rides`, `--cpu`) per contracts/cli.md in src/surfclip/cli.py
- [ ] T031 [US1] Implement eval: label file format (rides with start/end, `acid_drop`, camera-shift times, `origin: accepted | corrected | added`), `surfclip labels propose SESSION` (writes labels/<session>.json and labels/<session>.proposed.csv with every ride `status: proposed`; report counts of added/corrected rides in eval output), and `surfclip eval SESSION --labels FILE` / `eval all --labels-dir DIR --exclude-held-out` printing per-session SC-001…SC-003 in src/surfclip/eval/metrics.py and src/surfclip/eval/cli.py; until T019 passes
- [ ] T032 [US1] Integration test for export: SDR fixture clip keeps bt709 tags; HLG and PQ synthetic sources keep their tags (ffprobe), clip duration = ride + 2.5 s padding ± 1 frame, in tests/integration/test_export.py
- [ ] T033 [US1] Tune evidence thresholds in config/default.toml on non-held-out sessions only and record per-session SC-001…SC-003 results in specs/001-ride-detection-clipping/eval-log.md

**Checkpoint**: MVP — rides and HDR-preserving clips from a session with a file-supplied zone; metrics reported per session

---

## Phase 4: User Story 2 - Confirm the wave zone on one keyframe (Priority: P1)

**Goal**: Proposed zone on a keyframe; accept, adjust or draw it in the browser in ≤ 30 s

**Independent Test**: For each sample session, open the zone editor, accept or fix the proposal,
time it (SC-004), and compare with the hand-made zone file from US1

### Tests for User Story 2 ⚠️

- [ ] T034 [P] [US2] Unit tests for zone proposal on synthetic foot-point clouds (camera left, right, head-on): corners returned by role, both orientations tried, low-density input → `unreliable`, in tests/unit/test_zone_proposal.py
- [ ] T035 [P] [US2] API contract tests for `GET/PUT /sessions/{id}/epochs/{e}/zone`, `GET .../keyframe.jpg`, `POST /sessions`, `GET /jobs/{id}` (shapes per contracts/http-api.md; error format `{"error": {"code", "message"}}`) in tests/contract/test_api_zone.py

### Implementation for User Story 2

- [ ] T036 [US2] Implement zone proposal (density of moving foot points → quadrilateral, both orientations, side walls placed where tracks appear and disappear, corners allowed outside the frame, entry walls, side waiting areas, `proposal_confidence`) writing zones.json and keyframes/<epoch>.jpg in src/surfclip/zone/propose.py; until T034 passes
- [ ] T037 [US2] Implement the FastAPI app bound to `server.host` (127.0.0.1) with error format, static serving of web/dist, and background job runner with progress/eta in src/surfclip/api/app.py and src/surfclip/api/jobs.py; add `surfclip serve` in src/surfclip/cli.py
- [ ] T038 [US2] Implement session and zone routes per contracts/http-api.md (PUT zone appends `confirm_zone` with `how` = accepted/edited/drawn and triggers ride stages) in src/surfclip/api/routes_sessions.py and src/surfclip/api/routes_zones.py; until T035 passes
- [ ] T039 [P] [US2] Implement the typed API client in web/src/lib/api.ts
- [ ] T040 [US2] Build the Sessions screen (add a source path, min length setting before processing, job progress) in web/src/routes/Sessions.svelte
- [ ] T041 [US2] Build the Zone editor in web/src/routes/ZoneEditor.svelte: keyframe canvas, draggable role-labelled corners (including off-frame corners on a padded canvas), entry side-wall toggles, side waiting-area polygons, one-click Accept, "unreliable proposal" banner with Draw mode, zone shown clipped at frame edges
- [ ] T042 [US2] Measure zone setup time on each sample session and record SC-004 results in specs/001-ride-detection-clipping/eval-log.md

**Checkpoint**: New sessions go from upload to rides without hand-made zone files

---

## Phase 5: User Story 3 - Survive camera bumps and frame-edge exits (Priority: P2)

**Goal**: Camera epochs with silent re-maps, prompts only when unreliable, rides kept whole

**Independent Test**: Synthetic jump/drift/zoom clips and the staged bump session: 100% of shifts
> 2% of width detected; re-map markers shown; zoom change prompts; spanning rides stay one ride

### Tests for User Story 3 ⚠️

- [ ] T043 [P] [US3] Unit tests for epoch splitting on synthetic homography sequences (sudden jump, slow drift crossing `epochs.drift_frac`, low inliers → `needs_confirmation`) in tests/unit/test_epochs.py
- [ ] T044 [P] [US3] Unit test: a ride whose track crosses an epoch boundary is joined into one ride with `epochs: [0, 1]`, in tests/unit/test_joining.py

### Implementation for User Story 3

- [ ] T045 [US3] Implement `surfclip eval make-shifts VIDEO --kinds jump,drift,zoom` (translate/rotate/scale transforms, outputs to artifacts/eval/shifts/ with ground-truth shift times) in src/surfclip/eval/shifts.py
- [ ] T046 [US3] Implement background matching at `epochs.match_fps` (ORB, SIFT fallback; mask zone polygon and person boxes), RANSAC homography, inlier tracking and epoch splitting by jump/drift → epochs.json in src/surfclip/epochs/detect.py; until T043 passes
- [ ] T047 [US3] Implement zone re-mapping into new epochs (`remap = auto` when inliers sufficient, else `needs_confirmation`) and timeline markers in src/surfclip/epochs/remap.py; make the zone and rides stages per-epoch in src/surfclip/pipeline.py
- [ ] T048 [US3] Join rides across epoch boundaries in src/surfclip/rides/assemble.py; until T044 passes
- [ ] T049 [US3] Show epochs needing confirmation in the Zone editor (web/src/routes/ZoneEditor.svelte) and remap markers on the session timeline
- [ ] T050 [US3] Add shift-detection metric (SC-005) to src/surfclip/eval/metrics.py and record results for synthetic clips in specs/001-ride-detection-clipping/eval-log.md

**Checkpoint**: Bumped sessions produce correct zones and unbroken rides

---

## Phase 6: User Story 4 - Review and correct rides (Priority: P2)

**Goal**: Review screen with frame stepping and slow motion; trim/split/merge/delete/add; edits
survive re-runs; on-demand export

**Independent Test**: Make each edit type, re-run with a different minimum length, confirm all
edits remain and detection is not re-run (cache hits); seeks ≤ 1 s, frame steps ≤ 0.2 s

### Tests for User Story 4 ⚠️

- [ ] T051 [P] [US4] Unit tests for edits in tests/unit/test_edits.py: each op applied deterministically; after re-detection with shifted boundaries, edits re-attach by IoU ≥ 0.5, unmatched edited rides kept as `user_added`; edits.json byte-identical after any pipeline re-run (SC-007)
- [ ] T052 [P] [US4] API contract tests for rides, edits, export and media routes (Range requests return 206 with correct Content-Range) in tests/contract/test_api_review.py
- [ ] T053 [P] [US4] Integration test: re-run from `rides` with `rides.min_length_s = 15` keeps all edits and reports cache hits for detect/track, in tests/integration/test_rerun_keeps_edits.py

### Implementation for User Story 4

- [ ] T054 [P] [US4] Implement review assets in src/surfclip/media/review.py: review.mp4 (720p H.264 SDR, keyframe every 0.5 s, NVENC with CPU fallback), thumbnail sprite sheets (1 per 10 s) + thumbs/index.json, per-ride review_segments/<ride_id>.mp4 (padded)
- [ ] T055 [P] [US4] Implement exact-frame endpoint helper (seek + decode one frame → PNG, tone-mapped for HDR) in src/surfclip/media/frame.py
- [ ] T056 [US4] Implement edit re-attachment on re-run in src/surfclip/edits/apply.py; until T051 passes
- [ ] T057 [US4] Implement rides, edits, export, rerun and media routes (HTTP Range) per contracts/http-api.md in src/surfclip/api/routes_rides.py and src/surfclip/api/routes_media.py; until T052 passes
- [ ] T058 [US4] Build the player in web/src/lib/player/: buffered ride segment playback, frame step ←/→ using `requestVideoFrameCallback` with exact-frame endpoint fallback, slow motion (0.25×/0.5×), thumbnail-strip timeline with remap markers
- [ ] T059 [US4] Build the Review screen in web/src/routes/Review.svelte: ride list with thumbnails sorted lowest confidence first, lesson/truncated flags, short-attempt list, trim (set in/out at current frame), split at current frame, merge with neighbour, delete, add missed ride, re-run with settings, Export button (only new/changed rides)
- [ ] T060 [US4] Measure SC-009 (seek and frame-step latency) and SC-008 (hands-on time) on a 1 h session and record in specs/001-ride-detection-clipping/eval-log.md

**Checkpoint**: All four stories work; full session workflow in the browser

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T061 [P] Add a GPU-enabled Docker image (CUDA base, ffmpeg with NVENC/zscale, uv sync) and compose file mounting the repo, artifacts/ and the source folder read-only in docker/Dockerfile and docker/compose.yaml; document in specs/001-ride-detection-clipping/quickstart.md
- [ ] T062 [P] Edge-case handling with clear UI/CLI messages: no rides found → prompt to check zone; unsupported input; GPU unavailable → CPU fallback notice, in src/surfclip/api/app.py and src/surfclip/cli.py
- [ ] T063 Performance pass for SC-006: end-to-end `surfclip run --timings` on three 1 h sessions (GPU and `--cpu`); optimise the slowest stage if over 30 min / 90 min; record in specs/001-ride-detection-clipping/eval-log.md
- [ ] T064 Full evaluation: `surfclip eval all` on every labelled session incl. held-out; confirm every SC holds per session (constitution II) in specs/001-ride-detection-clipping/eval-log.md
- [ ] T065 [P] Verify no network calls (run the pipeline with networking disabled in WSL) and that the server rejects non-loopback connections (FR-025)
- [ ] T066 Run every scenario in specs/001-ride-detection-clipping/quickstart.md and fix gaps
- [ ] T067 [P] Update docs/prd.md FR-21 and roadmap P3 to the backend + browser UI architecture (user to confirm wording)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 first — its results may change T003 dependencies or T013/T029 details
- **Foundational (Phase 2)**: after Setup; blocks all stories
- **US1 (Phase 3)**: after Foundational — MVP
- **US2 (Phase 4)**: after Foundational; needs US1's detection/tracking (T021, T022) for proposals
- **US3 (Phase 5)**: after US1 (joins rides) and US2 (re-maps zones)
- **US4 (Phase 6)**: after US1 (rides, edits apply) and US2 (API app, web client)
- **Polish (Phase 7)**: after the stories it touches

### Within Each User Story

- Tests first and failing → models/logic → pipeline stage → API → UI → measurement task
- Each story ends with a measurement task writing to eval-log.md (constitution II)

### Parallel Opportunities

- Setup: T004, T005, T006, T007 in parallel after T002/T003
- Foundational: T009, T010, T012, T013, T014, T016 in parallel after T008/T011
- US1: tests T017–T020 together; T021 and T022 together
- US2: T034, T035, T039 together
- US3: T043, T044 together
- US4: T051–T053 together; T054 and T055 together

## Parallel Example: User Story 1

```text
Task: "State-machine unit tests in tests/unit/test_state_machine.py"            (T017)
Task: "Ride-joining unit tests in tests/unit/test_joining.py"                   (T018)
Task: "Eval metric unit tests in tests/unit/test_eval_metrics.py"               (T019)
Task: "YOLO11 detection in src/surfclip/detect/detector.py"                     (T021)
Task: "ByteTrack tracking in src/surfclip/track/tracker.py"                     (T022)
```

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 (T001 spike first) → Phase 2
2. Phase 3 (US1) with hand-made zone files
3. **STOP and VALIDATE**: `surfclip eval` on the labelled sessions (needs P0 labels for at least
   two sessions); exported clips play with correct colour

### Incremental Delivery

1. US1 → rides + clips from the CLI (MVP)
2. US2 → browser zone editor; no more zone files
3. US3 → bump-proof epochs
4. US4 → full browser review with frame stepping and on-demand export
5. Polish → Docker, performance, full evaluation

## Notes

- Labels (PRD phase P0) are needed from T031 onwards. They are proposed by the tool and validated by
  the user, including an 8× miss-scan of the whole session (research R15). Evaluation sessions:
  `20260928_IMG_1652.MOV`, `20240924.MP4`, `20241004.MP4`, `20261012_110549566.mp4`, plus the staged
  bump session (held out, to be filmed)
- T059's Review screen gains a "label" mode (confirm/trim/delete proposals, add missed rides,
  activity strip) once US4 lands
- Never write to the sample footage folder; fixtures and outputs live under artifacts/
- Commit after each task or logical group
