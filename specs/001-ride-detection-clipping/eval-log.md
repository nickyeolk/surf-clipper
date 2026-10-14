# Evaluation Log: Ride Detection and Clipping (001)

Per-session results against the success criteria (constitution II). Accuracy metrics
(SC-001..SC-003) need validated labels (`labels/rides/<session>.json`); until then only counts
and timings are recorded.

## 2026-10-14 — first end-to-end runs (no labels yet)

Laptop: i7-9750H, RTX 2060 6 GB, WSL2 Ubuntu 24.04. Analysis at 5 fps, YOLO11s full frame +
2x2 tiles, ByteTrack with 2.5x association boxes, track stitching, evidence gap 1.5 s.

| Session | Format | Length | Detect | Track | Rides | Short attempts |
| --- | --- | --- | --- | --- | --- | --- |
| `20240924.MP4` | 720p30 H.264 SDR, 45° right, day | 60.3 min | 10.9 min | 0.3 min | 83 | 24 |
| `20241004.MP4` | 720p30 H.264 SDR, 45° right, day, group lesson at start | 62.7 min | 13.3 min | 0.3 min | 90 | 32 |
| `20260928_IMG_1652.MOV` | 960x1280 portrait H.264 SDR, night | 40.1 min | 8.7 min | 0.2 min | 57 | 26 |
| `20261012_110549566.mp4` | 1080p HEVC 10-bit HLG, VFR ~25.7 fps, upside down, night, close | 55.8 min | 22.4 min | 0.2 min | 91 | 67 |

SC-006 (ready for review in <= 30 min per hour on GPU): all four pass on processing time
(longest: HDR session, 22.6 min for 55.8 min of video, i.e. ~24 min per hour; HDR tone-mapping
runs on the CPU).

### What changed between runs (20241004 unless noted)

| Change | Rides | Short attempts |
| --- | --- | --- |
| First run | 9 | 530 |
| Stitch track fragments (gap <= 1.5 s, distance in rider heights) | 41 | 386 |
| Association boxes 2.5x for ByteTrack (fast carving riders) | 88 | 56 |
| Zone compared in source pixels (portrait 0 -> 39 rides; HDR 0 -> 21) | 89 | 48 |
| Bottom-truncated riders count without a visible board; wall band only outside the pool (HDR 21 -> 55) | 89 | 48 |
| Evidence gap 0.6 -> 1.5 s (HDR 55 -> 91 rides, 256 -> 67 short) | 90 | 32 |

### Open observations to check with labels

- 20241004 ride `r046158` (25:38, 54 s) may contain two riders (changeover merged).
- Some mid-session rides are flagged `lesson` while only one rider is visible (e.g. 22:54).
- Group lesson at 0:00-2:35: four beginners on one pole give four overlapping rides; check
  whether that matches how the user wants lessons clipped.
- Zones for the two night sessions have off-frame corners estimated by eye; u/v accuracy there is
  unknown.

### Next

User validates `labels/rides/<session>.csv` (proposed by the tool), then
`surfclip labels import` and `surfclip eval` give SC-001..SC-003 per session.
