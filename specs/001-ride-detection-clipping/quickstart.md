# Quickstart & Validation: Ride Detection and Clipping (001)

How to prove the feature works end to end. Commands follow [contracts/cli.md](contracts/cli.md).

## Prerequisites

- Windows 11 with WSL2 Ubuntu 24.04; NVIDIA driver with WSL CUDA support (`nvidia-smi` works in WSL).
- In WSL: ffmpeg ≥ 6.1 with NVENC/NVDEC and zscale; uv; Node 20+ (to build `web/`).
- Sample sessions on the Windows drive, read in place (never modified):
  `/mnt/c/Users/likkhian/OneDrive/Media/trifecta/`.

## Setup

```bash
cd /mnt/c/Users/likkhian/Desktop/code/surf-clipper
uv sync                       # Python deps incl. CUDA PyTorch
(cd web && npm ci && npm run build)
uv run pytest                 # unit + contract tests
uv run python scripts/make_fixtures.py   # short clips into artifacts/fixtures/
uv run pytest tests/integration
```

## Scenario 1 — rides from a session (US1, US2)

```bash
uv run surfclip serve         # open http://localhost:8765
```

1. Add `20250326_1.MP4` (head-on, night LED). Expect a progress bar, then a keyframe with a
   proposed zone (corners, deck line, entrance and side areas).
2. Accept the zone (time it: ≤ 30 s, SC-004). Expect rides to appear, lowest confidence first.
3. Check: no ride for people sitting at the entrance; short attempts listed separately; any
   lesson rides flagged.

## Scenario 2 — review and edits survive re-runs (US4)

1. Trim one ride by stepping frames (←/→) and in slow motion; split one; merge two; delete one;
   add a missed ride. Each step responds within 0.2 s (SC-009).
2. Re-run the ride stage with a different minimum length (UI "Re-run" with min length 15 s, or
   `POST /sessions/{id}/rerun` with `{"from_stage": "rides", "config_overrides":
   {"rides.min_length_s": 15}}`).
3. Expect every edit still present and detection not re-run (stage log shows cache hits).

## Scenario 3 — camera moves (US3)

```bash
uv run surfclip eval make-shifts /mnt/c/.../20241004.MP4 --kinds jump,drift,zoom
```

Process each generated clip: jumps and drift produce a re-map marker and no prompt; the zoom change
prompts for re-confirmation; a ride crossing a shift stays one ride (SC-005).

## Scenario 4 — export (FR-020)

Export all rides. Expect `artifacts/<session>/clips/<ride_id>.mp4` with 1 s / 1.5 s padding;
`ffprobe` shows the same colour primaries/transfer/matrix as the source (HLG/PQ for HDR sources).
Export again after trimming one ride: only that ride is re-encoded.

## Scenario 5 — metrics (constitution II)

```bash
uv run surfclip eval all --labels-dir labels/ --exclude-held-out
```

Pass when, on **every** session: recall ≥ 95%, precision ≥ 90%, boundary error p95 < 1 s and
median < 0.5 s (acid drops reported separately), shifts > 2% of width detected 100%; and a 1 h
session is ready for review in ≤ 30 min (SC-006, printed by `surfclip run --timings`).
