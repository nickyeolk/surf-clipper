# Implementation Plan: Ride Detection and Clipping

**Branch**: `001-ride-detection-clipping` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ride-detection-clipping/spec.md`

## Summary

Turn a ~1 h phone video of a standing-wave session into a reviewed list of rides and one
final-quality (HDR-preserving) clip per ride. A Python pipeline library runs cached stages
(probe → analysis proxy and review copy → detection and tracking → camera epochs → zone proposal
and confirmation → ride state machine → boundary refinement → rides) and is exposed through a CLI
and a localhost FastAPI backend. A Svelte browser UI handles zone confirmation and ride review,
with frame stepping and slow motion. The backend runs under Linux in WSL2 on the user's laptop,
based on measurements in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend, pipeline, CLI); TypeScript 5 (browser UI)

**Primary Dependencies**: ffmpeg/ffprobe 6.1+ (NVDEC/NVENC, zscale); NumPy; OpenCV
(ORB, homography); Ultralytics YOLO11 (person, surfboard) on PyTorch CUDA; supervision (ByteTrack);
pydantic v2; FastAPI + uvicorn; Typer (CLI); pyarrow (Parquet); Svelte 5 + Vite

**Storage**: Files only — per-session folders under `artifacts/` (JSON for stage outputs and edits,
Parquet for per-frame detections and tracks, MP4 for review copy and clips); versioned config in
`config/default.toml`

**Testing**: pytest (unit, contract, integration); pyright; ruff; evaluation harness
(`surfclip eval`) for spec success criteria

**Target Platform**: User's Windows 11 laptop (i7-9750H, 32 GB, RTX 2060 6 GB); backend in WSL2
Ubuntu 24.04; UI in Chrome or Edge on Windows via `http://localhost`

**Project Type**: Python library + CLI + local web service, with a separate browser frontend

**Performance Goals**: 1 h video ready for review ≤ 30 min with GPU, ≤ 90 min CPU-only (SC-006);
seek ≤ 1 s, frame step ≤ 0.2 s in review (SC-009); clip export ~3 s per 30 s ride at 720p (measured)

**Constraints**: Local only, bound to 127.0.0.1 (FR-025); source videos read-only (FR-003);
thresholds in seconds / pool units / rider heights (FR-024); 6 GB VRAM; edits never overwritten
(FR-022)

**Scale/Scope**: One user; sessions up to 1.5 h, up to 10 riders, ~30–100 rides per session;
720p–4K, 30–120 fps; ~18k analysis frames per hour at 5 fps

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | How this plan complies | Status |
| --- | --- | --- | --- |
| I | Local-first and personal | No network calls in pipeline; server bound to 127.0.0.1; no face recognition; no descriptors in 001 | Pass |
| II | Evaluation before features | `surfclip eval` reports SC-001…SC-005 per labelled session; labels made in the review UI; held-out session excluded from tuning | Pass |
| III | Scale-, perspective-, mirror-invariant | Pool-coordinate homography; thresholds in seconds, pool units, rider heights; corners by role; both orientations tried | Pass |
| IV | Assume the camera moves | Every zone and position belongs to an epoch (`epochs.json`); ORB/RANSAC shift detection | Pass |
| V | Confirm late, start early | 1.5 s confirmation; back-dated starts; acid-drop linking; ±2 s full-rate refinement | Pass |
| VI | Human corrections are ground truth | Append-only `edits.json`, never written by pipeline stages; rides = detected + edits | Pass |
| VII | Staged, cached pipeline | Stage files with schema versions and cache keys; edits only re-run downstream stages | Pass |
| VIII | Simple first | Pretrained YOLO11 + ByteTrack + heuristics; no training | Pass |
| IX | Config, not constants | `config/default.toml` versioned; per-session overrides incl. minimum ride length | Pass |
| X | Engineering standards | Python 3.12, uv, pyright, ruff, pytest; HDR-aware ffmpeg; library + CLI + thin backend + UI without pipeline logic; backend in Linux under WSL2, justified by benchmark | Pass |
| XI | Scope discipline | No re-ID, compilation, overlays, viewer or stills (002/003) | Pass |

Post-design re-check (after Phase 1): **Pass** — data model and contracts keep edits separate from
detected output, all thresholds live in config, and the API exposes pipeline operations without
embedding logic in the UI.

## Project Structure

### Documentation (this feature)

```text
specs/001-ride-detection-clipping/
├── plan.md              # This file
├── research.md          # Phase 0: decisions + laptop benchmark
├── data-model.md        # Phase 1: entities and stage files
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── cli.md           # surfclip commands
│   ├── http-api.md      # backend endpoints used by the UI
│   └── session-files.md # artifacts/<session>/ layout and JSON schemas
└── tasks.md             # Phase 2 (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
pyproject.toml               # uv project: surfclip package, dev tools
config/
└── default.toml             # all thresholds and defaults (versioned)
src/surfclip/
├── config.py                # load/merge config, per-session overrides
├── store/                   # session folders, stage files, cache keys, schemas (pydantic)
├── media/                   # ffprobe, decode pipes, tone mapping, review copy, thumbnails, clip export
├── detect/                  # YOLO detection, tiling
├── track/                   # ByteTrack wrapper, track post-processing
├── epochs/                  # background matching, homography, epoch splitting, zone re-map
├── zone/                    # zone proposal, pool-coordinate geometry, regions
├── rides/                   # state machine, linking/joining, min length, refinement
├── edits/                   # edit log, applying edits, matching on re-run
├── pipeline.py              # stage orchestration and caching
├── eval/                    # metrics vs labels, synthetic shift generation
├── api/                     # FastAPI app, routes, background jobs
└── cli.py                   # Typer CLI (surfclip ...)
web/
├── package.json
├── vite.config.ts
└── src/
    ├── lib/api.ts           # typed client for contracts/http-api.md
    ├── lib/player/          # frame stepping, slow motion, timeline, thumbnails
    └── routes/              # Sessions, ZoneEditor, Review
tests/
├── unit/                    # geometry, state machine, joining, edits, cache keys
├── contract/                # JSON schemas and API responses
└── integration/             # pipeline on fixture clips in artifacts/fixtures/
scripts/
└── make_fixtures.py         # cut short fixture clips from the (read-only) sample sessions
docker/                      # later in 001: GPU image for reproducible runs
artifacts/                   # gitignored: per-session outputs, fixtures, eval outputs
```

**Structure Decision**: One Python package (`src/surfclip`) holds all pipeline logic, the CLI and
the API, so the library is testable without the UI. The browser UI lives in `web/` and talks only
to the API. Docker packaging is added after the pipeline works (research R1).

## Delivery Order (for /speckit-tasks)

1. **T001 spike — verify research assumptions**: zscale in ffmpeg; YOLO11 throughput on the RTX
   2060; HDR metadata round-trip with NVENC; Range-request seeking from Windows browser to WSL2;
   GPU inside a Docker Desktop container. Record results in research.md.
2. Project skeleton, config, store, probe, analysis proxy, review copy (US1 foundation).
3. Detection + tracking + first-pass zone proposal + zone editor UI (US2).
4. Ride state machine, linking, refinement, `rides.json`, eval harness (US1) — gate on SC-001…SC-003.
5. Camera epochs and re-mapping (US3) — gate on SC-005.
6. Review UI with edits, frame stepping, slow motion, on-demand HDR export (US4) — gate on SC-007,
   SC-008, SC-009.
7. Docker image; end-to-end timing on 1 h sessions (SC-006).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
| Second toolchain (Node/Vite for `web/`) | Zone editor and review player need interactive canvas and video control | Server-rendered HTML cannot do frame stepping or point dragging well |
