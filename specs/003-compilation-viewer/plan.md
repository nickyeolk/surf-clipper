# Implementation Plan: Compilations, Stills, Viewer and Packaging

**Branch**: `003-compilation-viewer` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-compilation-viewer/spec.md`

## Summary

Turn 002's per-rider "export as one video" into a finished **compilation**: each of the rider's
rides is re-encoded from the source once, exactly like a 001 clip but with a burned-in caption
("me · ride 3 of 12 · 10:42") for its first 3 s, then the captioned rides are joined without
re-encoding. Captions are drawn in grey at reference white, so HDR stays HDR and the text is not
glaring (spike R1). **Stills** are single source frames at full resolution, tone-mapped to SDR
JPEG like the review copy, saved from the Review player or the viewer. A **viewer** screen lists a
session's compilations, clips per rider and stills, and plays the exported files themselves (the
laptop's Chromium decodes HEVC Main10 HLG at 1080p, R3) with frame stepping and slow motion.
**Packaging** is a pair of Windows desktop shortcuts: start runs the existing WSL backend in a
hidden window, waits for it and opens the browser; stop asks the backend to shut down. A health
endpoint tells the UI whether the GPU and model weights are present, and a button downloads
missing weights.

## Technical Context

**Language/Version**: Python 3.12 (backend, CLI); TypeScript 5 + Svelte 5 (UI); Windows
PowerShell 5.1 (launcher scripts)

**Primary Dependencies**: as 001/002 (ffmpeg 6.1 with libfreetype `drawtext` and `zscale`,
FastAPI, Typer, pydantic v2); fonts: DejaVu Sans Bold (installed in WSL Ubuntu); no new Python
packages

**Storage**: per-session files under `artifacts/<session>/clips/`: `captioned/<ride>.mp4`
(captioned ride segments, cached), `reel_<rider>.mp4` (compilation), `compilations.json`
(records: rides, offsets, captions, cache keys), `stills/<ride>_f<frame>.jpg` and
`stills.json`; launcher log at `artifacts/logs/server.log`

**Testing**: pytest (unit: caption text and numbering, cache keys, still frame snapping;
integration with ffmpeg: compilation of a synthetic HDR clip keeps tags and duration, caption
pixels at most reference white; still equals the source frame; contract: new routes); manual
quickstart for the shortcuts

**Target Platform**: as 001 (Windows 11 laptop, RTX 2060; backend in WSL2; UI in Chromium/Edge/
Chrome)

**Project Type**: Python library + CLI + local web service, browser frontend (as 001)

**Performance Goals**: compilation of 20 rides ≤ 5 min (SC-001; spike: 6 s of 1080p HLG
captioned in 2 s with NVENC, so ~20 rides × 30 s ≈ 3-4 min); still ≤ 3 s; start to Sessions page
≤ 60 s (SC-005)

**Constraints**: captions only on compilations (single clips stay clean); captions at most
reference white on HDR (FR-003); exact source frame for stills (FR-004); loopback only (FR-025 of
001); no names leave the session folder (002); launcher must not need admin rights or a
terminal

**Scale/Scope**: up to ~40 rides per compilation, ~100 stills per session

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | How this plan complies | Status |
| --- | --- | --- | --- |
| I | Local-first and personal | Everything stays in the session folder; the server stays on loopback; model downloads only on the user's button press, never during processing | Pass |
| II | Evaluation before features | SC-002/003/004 are automated checks (caption text per ride, HDR tags and caption level, still vs source frame) run in the integration tests on the real HDR session as well as fixtures | Pass |
| III | Scale-, perspective-, mirror-invariant | Caption size and margins are fractions of the shorter frame side; works for portrait | Pass |
| IV | Assume the camera moves | Not applicable (no geometry) | Pass |
| V | Confirm late, start early | Not applicable | Pass |
| VI | Human corrections are ground truth | Compilations read the current rides and riders (after edits); stills are user outputs and never edit rides | Pass |
| VII | Staged, cached pipeline | Compilations are on-demand exports, not stages; captioned segments cached by clip span + caption + settings, so a renamed rider re-captions only, unchanged rides are never re-encoded (FR-007) | Pass |
| VIII | Simple first | ffmpeg `drawtext` + concat copy; no compositor, no new libraries; launcher is two PowerShell scripts | Pass |
| IX | Config, not constants | `[compilation]` section: caption seconds, size, position, margin, level per transfer, box opacity, font | Pass |
| X | Engineering standards | Library (`media/compile.py`, `media/stills.py`) + CLI + thin API; UI has no media logic; pyright, ruff, pytest | Pass |
| XI | Scope discipline | No cross-session compilations, no music or transitions, no HDR stills, no Windows-native build, no auto-update | Pass |

Post-design re-check (after Phase 1): **Pass**.

## Project Structure

### Documentation (this feature)

```text
specs/003-compilation-viewer/
├── plan.md              # This file
├── research.md          # R1-R6
├── data-model.md        # Compilation, CaptionedSegment, Still, Health, config
├── quickstart.md        # How to try it
├── contracts/
│   ├── http-api.md      # New and changed routes
│   ├── session-files.md # compilations.json, stills.json, folders
│   └── cli.md           # export --compilation, still
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
config/default.toml                 # + [compilation]
src/surfclip/
├── config.py                       # + CompilationConfig
├── media/
│   ├── export.py                   # export_reel(rider=…) delegates to compile
│   ├── compile.py                  # NEW: captions, captioned segments, compilation records
│   └── stills.py                   # NEW: exact-frame SDR JPEG stills
├── api/app.py                      # + compilation, stills, exports listing, health, shutdown, models
├── health.py                       # NEW: GPU / encoder / model checks
└── cli.py                          # export --compilation, still, serve --log
web/src/
├── lib/api.ts                      # + types and calls
├── lib/Player.svelte               # NEW: shared frame-step / speed controls (viewer)
├── routes/Viewer.svelte            # NEW: #/viewer/<id>
├── routes/Review.svelte            # + save still
├── routes/Riders.svelte            # compilation button per rider
└── routes/Sessions.svelte          # + health banner, models button, Exports link, Stop
scripts/windows/
├── start.ps1                       # hidden start, wait for /api/health, open browser
├── stop.ps1                        # POST /api/shutdown (falls back to wsl pkill)
└── install-shortcuts.ps1           # Desktop shortcuts; builds the UI once
tests/unit/test_compile.py, tests/unit/test_stills.py
tests/integration/test_compilation.py, tests/contract/test_api_exports.py
```

**Structure Decision**: same single-project layout as 001/002; the two new media modules sit next
to `export.py`, the launcher scripts in `scripts/windows/`. `scripts/serve.cmd` is replaced by
the shortcuts (kept as a fallback that shows the console).

## Complexity Tracking

No violations.
