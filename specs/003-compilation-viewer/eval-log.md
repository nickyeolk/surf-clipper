# Evaluation log: 003

## 2026-10-16 T008: compilation on PXL_20261014 (HLG 1080p30, 28 rides, one rider)

- `surfclip export … --reel --rider "Rider 1"`: 348 s for 28 rides (12.4 s per ride, NVENC;
  the 1080p HEVC 10-bit decode dominates). 20 rides ≈ 4.1 min → **SC-001 processing ≤ 5 min: pass**.
- Output: hevc yuv420p10le, `bt2020 / arib-std-b67 / bt2020nc`, 918.23 s = sum of the 28 segment
  durations (918.21 s) → **SC-003 tags: pass**.
- Captions: ride 2 reads "Rider 1 · ride 2 of 28 · 4:45" at offset 34.13 s (ride 1's length);
  tone-mapped frame 1 s in shows the caption, 4 s in shows none → **SC-002: pass** on this
  session (numbering and times checked in `compilations.json` against `rides.json`).
- Caption level: on a synthetic HLG source the caption's Y max is 719-733 (10 bit) against HLG
  reference white 721 (integration test). With the default bitrate cap a pure-black test source
  rang to 891 because its bitrate is tiny; real footage is unaffected (test lifts the cap).

## 2026-10-16 T014: start and stop on the laptop

- `install-shortcuts.ps1`: built the UI and created "Surf Clipper" / "Stop Surf Clipper" on the
  Desktop (hidden PowerShell running `scripts\windows\start.ps1` / `stop.ps1`, wave icon).
- `start.ps1` from a stopped server to `/api/health` answering: 9.4 s and 8.9 s → **SC-005
  (≤ 60 s): pass**. Health on this laptop: GPU yes, encoder nvenc, both models present.
- `stop.ps1` → `/api/shutdown`: the server process exits (checked with `pgrep`); against the old
  server without that route, the `pkill` fallback stopped it.
- Found and fixed: Windows PowerShell's `Invoke-RestMethod` tries `localhost` as IPv6 `::1`
  first, which WSL does not forward, so health checks hung; the scripts now call `127.0.0.1`
  (the browser still uses `localhost`, which Chromium resolves fine).
- Left for the user: double-clicking the shortcuts themselves (they open the browser).

## 2026-10-16 T022: viewer in the browser pane (PXL, HLG)

- The 918 s HEVC Main10 HLG compilation plays at 1920×1080; caption visible at the start of
  ride 1; `]` jumps to ride 2 at 34.13 s, `.` steps one frame (+0.0333 s); the ride bar fits.
- Save still from the compilation at 0:00 saved frame 4257 (source 141.91 s = ride 1's clip
  start), 1920×1080 JPEG. It was named `t_…` because snapping put it half a frame before the
  clip start; ride lookup now allows half a frame. Test still deleted afterwards.
- Stills are converted to BT.601 full range explicitly (JPEG's convention): without it the HLG
  still's colours were off (mean error 9.3 vs < 4 after, integration test).
