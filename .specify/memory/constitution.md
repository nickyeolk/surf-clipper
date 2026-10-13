# Surf Session Clipper Constitution

## Core Principles

### I. Local-First and Personal

Footage and rider data MUST never leave the machine. The pipeline MUST make no cloud calls and
MUST emit no telemetry. Face recognition MUST NOT be used. Appearance descriptors MUST live for
one session only and MUST NOT be persisted across sessions.

Rationale: this is a personal tool processing footage of other people; privacy is a hard boundary.

### II. Evaluation Before Features

Every detection, zone, camera-shift, on/off-wave or re-ID component MUST report its metric on the
labelled evaluation set, including the 0.5x, bumped, night-HDR and held-out sessions. No change
merges if it regresses an agreed metric. The held-out session MUST NOT be used for tuning.

Rationale: footage varies wildly between sessions; only measured results on every case count.

### III. Scale-, Perspective- and Mirror-Invariant

Logic MUST work with the camera head-on or up to about 45° to the left or right of the wave, at
1x or 0.5x zoom. No threshold may be expressed in raw pixels or frames: use pool-plane
coordinates, the rider's current box height, and seconds. No logic may assume which side the
camera, the entrance or the waiting areas are on, or the direction a rider moves.

Rationale: framing, zoom, angle and frame rate change every session.

### IV. Assume the Camera Moves

Every spatial artefact (zone, deck/water boundary, regions, positions) MUST belong to a camera
epoch. Nothing may assume one fixed frame for a whole video.

Rationale: the phone is on a stand and gets bumped mid-session.

### V. Confirm Late, Start Early

Ride decisions MAY wait for sustained evidence, but timestamps MUST be back-dated to the true
onset (boundary crossing or drop-in).

Rationale: avoids false rides from sitters and splashes without clipping drop-ins late.

### VI. Human Corrections Are Ground Truth

Confirmed zones, edited ride boundaries and rider labels are hard constraints. Re-runs MUST
never overwrite them.

Rationale: the user's few minutes of review must never be lost or repeated.

### VII. Staged, Cached Pipeline

Each stage MUST read and write versioned files (e.g. `epochs.json`, `rides.json`,
`labels.json`) and MUST be re-runnable on its own. An edit MUST NOT force detection to run again.

Rationale: an hour of footage is expensive to process; iteration must stay cheap.

### VIII. Simple First

Heuristics and pretrained models come before any training. A new model MUST beat the baseline
on the evaluation set, within the laptop's GPU budget, before it is adopted.

Rationale: keeps the MVP small and its behaviour explainable.

### IX. Config, Not Constants

Thresholds MUST live in a versioned config file, not in code. The user MUST be able to set the
minimum ride length before processing.

Rationale: tuning per session and per release must be traceable and reversible.

### X. Engineering Standards

Python 3.11+, managed with uv; typed and checked with pyright; linted and formatted with ruff;
tested with pytest. ffmpeg handles media and MUST be HDR-aware. The pipeline is a library with a
CLI. A local backend service exposes it to a browser UI; the UI MUST contain no pipeline logic.
The host is the user's Windows laptop. The backend MAY run natively on Windows or in a Linux
container under WSL2; the choice MUST be justified by a benchmark on the sample footage (decode,
detection and HDR export speed) and MUST NOT change pipeline behaviour.

Rationale: one consistent, reproducible toolchain; the UI stays thin so the pipeline is testable
on its own.

### XI. Scope Discipline

Manoeuvres, turn counting, pose analysis and cross-session rider identity are out of scope until
their roadmap phase (F1–F4) opens.

Rationale: the MVP finds, cuts, groups and compiles rides; it does not judge them.

## Technical Constraints

- Target hardware: a Windows laptop with a small GPU (currently an NVIDIA RTX 2060), with a
  CPU-only fallback.
- The backend and browser UI are reachable only from this machine by default.
- Input: local MP4/MOV phone video (H.264 or HEVC, 8-bit SDR or 10-bit HDR, 720p–4K,
  30–120 fps, up to 1.5 h). Container and HDR metadata are hints, never requirements.
- Analysis uses a low-fps, tone-mapped SDR proxy; exports keep the original's HDR.
- Sample footage is read-only: pipeline code and tests MUST NOT modify, move or re-encode source
  files in place.

## Development Workflow & Quality Gates

- Each feature (001 rides, 002 riders, 003 compilation/viewer/packaging) follows specify → clarify → plan → tasks
  → implement as its own Spec Kit feature.
- Every plan MUST pass a Constitution Check against these principles before tasks are generated.
- Changes touching detection, zones, shifts, on/off-wave state or re-ID MUST include an
  evaluation-set metric report (Principle II).
- ruff, pyright and pytest MUST pass before merge.

## Governance

This constitution supersedes other practices for this project. Amendments are made by editing
this file through `/speckit-constitution`, with a Sync Impact Report and a version bump:
MAJOR for removing or redefining a principle, MINOR for adding a principle or materially
expanding guidance, PATCH for clarifications. Plans and reviews MUST verify compliance; any
deviation MUST be justified in the plan's Complexity Tracking section.

**Version**: 1.1.0 | **Ratified**: 2026-10-13 | **Last Amended**: 2026-10-13
