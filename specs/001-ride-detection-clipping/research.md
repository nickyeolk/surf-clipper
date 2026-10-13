# Research: Ride Detection and Clipping (001)

**Date**: 2026-10-13 · **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Each entry: Decision / Rationale / Alternatives considered. Items marked **Verify in T001** are
decided, but the first implementation task (a spike) must confirm them before building on them.

## Measured on the target laptop (2026-10-13)

Hardware: Intel i7-9750H (6 cores), 32 GB RAM, NVIDIA RTX 2060 6 GB (driver 591.86), WSL2 with
Ubuntu 24.04.3, ffmpeg 6.1.1 (Ubuntu package), Docker Desktop installed (not running).

Source: `20250326_1.MP4` (720p30 H.264 SDR, night LED), read in place from the Windows drive via
`/mnt/c` inside WSL2. Outputs went to a temp dir and were deleted.

| Test | Time | Extrapolated to 1 h |
| --- | --- | --- |
| Raw read 800 MB from Windows drive into WSL2 | 4.2 s (~190 MB/s) | Full 1.6 GB file in ~9 s |
| Decode 5 min to 5 fps analysis frames, CPU | 9.4 s | ~2 min |
| Decode 5 min to 5 fps, CUDA NVDEC | 14.4 s | ~3 min (slower than CPU at 720p) |
| Review copy, 5 min, 720p H.264 NVENC, keyframe every 0.5 s | 27.0 s, 72 MB | ~5.5 min, ~870 MB |
| Final clip 30 s, HEVC 10-bit NVENC | 3.0 s | 60 rides ≈ 3 min |
| Final clip 30 s, HEVC 10-bit libx265 (CPU) | 22.1 s | 60 rides ≈ 22 min |

Not measured yet: person detection speed on the GPU (no PyTorch installed), 4K HDR sources (no
4K HDR sample on disk), native Windows ffmpeg (not installed).

Also found: `IMG_3106.MP4` (the 45°-left evaluation session) is **not present** in
`OneDrive/Media/trifecta`; it may be online-only or moved. 13 other archive sessions are local.

## R1. Where the backend runs

- **Decision**: Run the backend under Linux in WSL2 (Ubuntu 24.04), managed with uv, started from
  a shell. Provide a Docker image (GPU-enabled, same code) as a reproducible alternative later in
  001; it is not required for development.
- **Rationale**: The measurements remove both risks raised earlier: NVDEC/NVENC work from WSL2
  Linux, and reading video from the Windows drive is ~190 MB/s, far above any video bitrate
  (3.6 Mbps archive; ~100 Mbps 4K HDR at most), so sessions are read in place without copying.
  Linux has first-class CUDA, PyTorch and ffmpeg packages. The browser on Windows reaches a WSL2
  server on `localhost` by default.
- **Alternatives**: Native Windows (would need a separate ffmpeg build, Windows-specific
  CUDA/PyTorch setup; no measured advantage). Docker from day one (adds image rebuilds to every
  dependency change during heavy iteration; GPU-in-container on Docker Desktop not yet tested —
  **Verify in T001**).
- **Constitution**: Principle X allows the backend natively or in Linux under WSL2; this choice is
  backed by the table above (amended to v1.1.1 to say "Linux under WSL2, directly or in a container").

## R2. Decoding and the analysis proxy

- **Decision**: ffmpeg subprocess pipes (raw frames to NumPy) for the low-fps analysis proxy and
  for full-frame-rate boundary refinement windows; `ffprobe` JSON for metadata. CPU decode for
  720p sources; NVDEC for 4K HEVC. HDR sources are tone-mapped to SDR for analysis with
  `zscale` + `tonemap` (hable). Analysis runs at 5 fps at native resolution up to 720p, downscaled
  to 720p height for larger sources.
- **Rationale**: Measured: CPU decode of 720p to 5 fps is ~2 min per hour. ffmpeg handles every
  input codec and HDR transfer, and pipes keep memory flat.
- **Alternatives**: PyAV (finer control, but extra build dependency; keep as an option for exact
  frame seeking if pipes prove imprecise); OpenCV VideoCapture (no HDR handling, weak seeking).
- **Verify in T001**: Ubuntu's ffmpeg build includes `zscale` (libzimg); otherwise use a static
  ffmpeg build.

## R3. Person and board detection

- **Decision**: Pretrained YOLO11 (COCO classes `person`, `surfboard`), size `s` by default, via
  the Ultralytics package on CUDA. Tiled inference (SAHI-style, 2×2 overlap) only in the region of
  the zone where predicted rider height drops below ~60 px at 720p.
- **Rationale**: Pretrained, fast on small GPUs, has both needed classes (constitution VIII).
  Tiling only where needed keeps the time budget.
- **Alternatives**: RT-DETR (Apache-2.0, slower); YOLO11n (faster, weaker on small far riders).
- **Licence note**: Ultralytics is AGPL-3.0. Acceptable for a personal, unpublished tool; revisit
  before any distribution.
- **Verify in T001**: detection throughput on the RTX 2060 for 1 h at 5 fps with tiling; target
  ≤ 15 min so the total stays under SC-006's 30 min.

## R4. Tracking

- **Decision**: ByteTrack (via the `supervision` package or Ultralytics' tracker) on detections at
  5 fps, with track-gap tolerance tuned in seconds. Ride-level joining (acid drops, frame-edge
  exits, epoch boundaries) is done by our own logic on top, not by the tracker.
- **Rationale**: Robust to low-confidence detections at night; no appearance model needed in 001.
- **Alternatives**: BoT-SORT (camera-motion compensation is unnecessary for a static camera);
  DeepSORT (appearance features belong to 002).

## R5. Camera epochs

- **Decision**: At 1 fps, ORB features on a background mask (excluding the zone polygon and person
  boxes) matched against the epoch's reference keyframe; homography with RANSAC; new epoch on a
  sudden jump or cumulative drift > 2% of frame width, or inlier ratio below threshold. Auto re-map
  when inliers are sufficient, otherwise flag for re-confirmation. SIFT as fallback.
- **Rationale**: PRD sample checks found 570–2,080 background matches per pair, including at night.
- **Alternatives**: Optical-flow global motion (drifts); SuperPoint + LightGlue (only if ORB/SIFT
  fail on the evaluation set).

## R6. Zone proposal and pool coordinates

- **Decision**: First pass without a zone collects foot points of tracks with sustained lateral
  motion. The proposal fits a quadrilateral to their density, tries both orientations (camera left
  or right), and picks the deck/water boundary as the strongest edge along the far side. The four
  corners are stored by role (deck-edge pair, wave-end pair). A homography maps image points to pool
  coordinates in [0,1]². Ultra-wide sources are undistorted first only if straight edges visibly bow
  (*should*; parameters estimated from the confirmed deck line).
- **Rationale**: Uses detections the pipeline already needs; sun patches make water texture a weak
  signal (PRD sample findings).
- **Alternatives**: Manual-only (kept as fallback); water-motion segmentation (secondary signal only).

## R7. Ride logic

- **Decision**: A per-track state machine (off → dropping-in → on-wave → off) driven by evidence
  from feet position (pool coordinates), board overlap below the feet, box aspect for stance, and
  lateral speed in pool units/s. Confirmation window 1.5 s; start back-dated along the track to the
  boundary crossing. Acid-drop linking: track ending at the deck edge + on-wave track starting
  within 1 s and within N rider heights. Frame-edge grace 2 s. Minimum length 10 s. All values in
  `config/default.toml`.
- **Rationale**: Directly encodes the spec's FR-010…FR-018; pure Python, easy to unit-test with
  synthetic tracks.
- **Alternatives**: Learned action classifier (needs training data; violates "simple first").

## R8. Boundary refinement

- **Decision**: For each ride, decode ±2 s around start and end at the source's full frame rate,
  run detection on those frames only, and move each boundary to the first/last frame that meets the
  on-wave evidence. Timestamps come from the frame PTS (handles variable frame rate).
- **Rationale**: Meets the < 1 s boundary target cheaply (~4 s × 2 per ride).

## R9. Storage and caching

- **Decision**: One folder per session: `artifacts/<session-id>/`. Session ID = short hash of
  source path + size + mtime. Each stage writes a versioned file (`schema_version` field) plus a
  cache key (hash of inputs + relevant config section + code stage version). Large per-frame data
  (detections, tracks) in Parquet; everything a human or later feature reads (`epochs.json`,
  `rides.json`, `edits.json`) in JSON validated by pydantic models.
- **Rationale**: Constitution VII and FR-022/FR-023; JSON keeps user-facing files inspectable.
- **Alternatives**: SQLite (harder to diff and inspect; unnecessary for one user).

## R10. User edits as hard constraints

- **Decision**: Edits are stored separately in `edits.json` as an append-only log of operations
  (confirm zone, trim, split, merge, delete, add) with stable ride IDs. `rides.json` is rebuilt as
  *detected rides + edits applied*. On re-run, detected rides are matched to edited rides by time
  overlap; edits always win.
- **Rationale**: Re-runs can never overwrite edits because they never write to `edits.json`
  (constitution VI, FR-022).

## R11. Backend API and video delivery

- **Decision**: FastAPI + uvicorn bound to `127.0.0.1` only. Video served with HTTP Range support
  (Starlette `FileResponse`). The pipeline runs in a background worker process; the UI polls job
  status. Exact frames are served as PNG by seeking with ffmpeg.
- **Rationale**: Thin layer over the library (constitution X); localhost-only satisfies FR-025.
- **Verify in T001**: Range requests work for seeking in Chrome/Edge against the WSL2 server.

## R12. Review playback (FR-021, FR-026, SC-009)

- **Decision**: A per-session review copy: 720p H.264 SDR, keyframe every 0.5 s (measured ~5.5 min
  and ~870 MB per hour). Per-ride review segments are cut from it for frame stepping (each fully
  buffered by the browser, ~15 MB for 30 s). Frame stepping uses `requestVideoFrameCallback` to know
  the displayed frame; the backend's exact-frame endpoint is the fallback. A thumbnail sprite strip
  per session for timeline scrubbing.
- **Rationale**: Browser decoders handle H.264 SDR everywhere; short keyframe interval makes seeks
  and backward steps fast.
- **Alternatives**: Play originals directly (4K HEVC HDR seeks are slow and Dolby Vision won't
  play); frame-image-only player (smooth slow motion is impossible).

## R13. Final clip export (FR-020)

- **Decision**: Frame-accurate re-encode with NVENC: HEVC Main10 for HDR sources (copying colour
  primaries, transfer (HLG or PQ) and matrix; HDR10 mastering metadata passed through when present;
  Dolby Vision exported as its HLG base layer); H.264 high quality for SDR sources. libx265/libx264
  CPU fallback. Only new or changed rides are re-encoded (cache key = ride boundaries + source +
  encoder settings).
- **Rationale**: Measured 3 s per 30 s 720p clip on NVENC vs 22 s on CPU.
- **Verify in T001**: an HLG and a PQ test file round-trip with correct metadata (`ffprobe`
  shows the same colour tags), and play as HDR in Windows' Media Player.

## R14. Frontend

- **Decision**: Svelte 5 + TypeScript + Vite, built to static files that the backend serves. Three
  screens: Sessions, Zone editor (canvas over keyframe with draggable role-labelled points), Review
  (ride list + player + timeline).
- **Rationale**: Small, reactive UI with little boilerplate; no runtime server besides the backend.
- **Alternatives**: Plain TypeScript (more manual state handling for the review editor); React
  (heavier for a three-screen tool).

## R15. Evaluation harness (constitution II)

- **Decision**: `surfclip eval` compares `rides.json` with hand labels (`labels/<session>.json`:
  rides with start/end, acid-drop flag, camera-shift times) and reports SC-001…SC-005 per session.
  Hand labels are made with the same review UI in a "label" mode, so P0 labelling needs no extra
  tool. Synthetic shift clips are generated by `surfclip eval make-shifts` (crop/translate/zoom
  transforms written to `artifacts/eval/`).
- **Rationale**: Reuses the UI; metrics reported on every session, not averaged.
- **Open data issue**: `IMG_3106.MP4` must be made local before it can be labelled.

## R16. Testing

- **Decision**: pytest. Unit tests for geometry, state machine and ride joining with synthetic
  tracks (no video). Contract tests validate JSON files and API responses against the schemas in
  `contracts/`. Integration tests run the pipeline on short fixture clips cut from the sample
  sessions into `artifacts/fixtures/` by a script (never committed; sources read-only).
