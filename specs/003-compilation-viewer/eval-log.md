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
