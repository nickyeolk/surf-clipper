---

description: "Task list for feature 003: compilations, stills, viewer and packaging"
---

# Tasks: Compilations, Stills, Viewer and Packaging

**Input**: Design documents from `/specs/003-compilation-viewer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included (constitution X); caption text, cache keys and frame snapping are pure logic
and test-first; ffmpeg behaviour is checked in integration tests.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 compilation, US2 stills, US3 viewer, US4 start/stop

---

## Phase 1: Setup

- [ ] T001 Add a `[compilation]` section to config/default.toml and `CompilationConfig` in src/surfclip/config.py with the keys of data-model.md "Config"; bump `config_version`
- [ ] T002 [P] Add schemas to src/surfclip/store/schemas.py per contracts/session-files.md: `CaptionedSegment`, `CompilationRide`, `Compilation`, `Compilations`, `Still`, `Stills`

---

## Phase 2: US1 - A finished compilation of my rides (P1) 🎯 MVP

**Goal**: per-rider compilation with captions at the start of each ride, HDR kept

### Tests

- [ ] T003 [P] [US1] Unit tests in tests/unit/test_compile.py: caption text and numbering (time order, "ride k of n", m:ss and h:mm:ss, "Rider N" for unnamed); drawtext filter escapes `:` `'` `\` `%` in names; text level per transfer (sdr/hlg/pq) as a neutral grey; size and margins from the shorter side (portrait); segment cache key changes with caption text and settings, not with unrelated config
- [ ] T004 [P] [US1] Integration test in tests/integration/test_compilation.py (synthetic HLG and SDR sources made with ffmpeg): compilation of 3 rides has the summed duration, keeps colour tags and pix_fmt; caption pixels' max luma ≤ HLG reference white + tolerance in the first `caption_s` and absent after; re-running with unchanged rides re-encodes nothing; renaming the rider re-captions all segments

### Implementation

- [ ] T005 [US1] Implement src/surfclip/media/compile.py: `captions(rides, riders, rider_id)`, `caption_filter(info, cfg, text)`, `segment_key(...)`, `export_captioned(...)` (001's `_codec_args` + `-vf drawtext`, tmp file then rename, duration via ffprobe), `export_compilation(store, export_cfg, comp_cfg, rider_id, cpu, progress)` → concat copy into `reel_file(rider)`, writes `clips/compilations.json`; `compilation_current(...)`
- [ ] T006 [US1] Route per-rider reels through `export_compilation` in src/surfclip/media/export.py / api/app.py export job and cli.py `export --reel --rider`; plain `--reel` unchanged
- [ ] T007 [US1] UI: in web/src/routes/Riders.svelte a "Compilation" button per card (job progress, then play/download); Review's per-rider "Export as one video" says "compilation with captions"
- [ ] T008 [US1] Run on the PXL HLG session: check tags with ffprobe, look at a tone-mapped frame with and after the caption, record time per ride and SC-002/SC-003 in specs/003-compilation-viewer/eval-log.md

**Checkpoint**: the user can export "me" with captions.

---

## Phase 3: US4 - Start the tool without a developer (P1)

### Tests

- [ ] T009 [P] [US4] Contract tests in tests/contract/test_api_exports.py: `GET /api/health` shape (gpu/model checks stubbed); `POST /api/shutdown` calls the server's exit hook and cancels queued jobs; `POST /api/models/download` 409 when running

### Implementation

- [ ] T010 [US4] Implement src/surfclip/health.py (GPU via `nvidia-smi -L`, NVENC 1-frame test cached, model files present) and `/api/health`, `/api/models/download`, `/api/shutdown` in src/surfclip/api/app.py; `Jobs.shutdown()` in api/jobs.py cancels queued jobs and terminates a running ffmpeg subprocess
- [ ] T011 [US4] `surfclip serve --log PATH` in src/surfclip/cli.py (rotating file log; uvicorn `should_exit` hook passed to the app)
- [ ] T012 [P] [US4] scripts/windows/start.ps1, stop.ps1, install-shortcuts.ps1 per research R5 (hidden window, health poll ≤ 60 s, browser open, message box with the log path on failure; shortcuts with icon; UI build once); keep scripts/serve.cmd as the console fallback; document in scripts/README.md
- [ ] T013 [US4] Sessions page: health banner (no GPU / missing models + Download models button), Stop button with confirmation, "Exports" link per session
- [ ] T014 [US4] Manual check on the laptop per quickstart.md: install, start from the shortcut (time to Sessions page), stop, start again with a job in progress (resumes from cache); record in eval-log.md

---

## Phase 4: US2 - Save a frame as a photo (P2)

### Tests

- [ ] T015 [P] [US2] Unit tests in tests/unit/test_stills.py: frame snapping, naming, ride lookup by time, out-of-range rejection, same frame returns the existing still
- [ ] T016 [P] [US2] Integration test in tests/integration/test_compilation.py: a still from a synthetic source with a frame counter burned in shows the requested frame number at full resolution (SC-004); HLG still is an SDR JPEG

### Implementation

- [ ] T017 [US2] Implement src/surfclip/media/stills.py (`save_still(store, cfg, t_s)`, `list_stills`, `delete_still`) using review.py's tone-map chain without scaling
- [ ] T018 [US2] Routes `POST /stills`, `GET /media/stills/{name}.jpg`, `DELETE /stills/{name}` in src/surfclip/api/app.py and `surfclip still` in cli.py; contract tests
- [ ] T019 [US2] Review player: "Save still" button and `s` key in web/src/routes/Review.svelte (shows a thumbnail toast with a link)

---

## Phase 5: US3 - Watch the full-quality result (P2)

- [ ] T020 [US3] `GET /api/sessions/{id}/exports` in src/surfclip/api/app.py per contracts/http-api.md; contract test
- [ ] T021 [US3] web/src/lib/Player.svelte (frame step `,`/`.` by 1/fps, 0.25/0.5/1x, current ride label from compilation offsets, HEVC support note) and web/src/routes/Viewer.svelte (`#/viewer/<id>`): compilations, clips per rider, stills grid with open/download/delete; Save still maps player time to source time
- [ ] T022 [US3] Check in the browser pane on the HLG and an SDR session: compilation plays, steps, caption visible for 3 s per ride, still saved from the viewer matches

---

## Phase 6: Polish

- [ ] T023 [P] Update README/quickstart docs and the 001 contract notes that per-rider reels are now captioned
- [ ] T024 Run scripts/check.sh (ruff, pyright, pytest) and the web build; fix everything
