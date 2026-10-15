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

## 2026-10-15 — first labelled evaluation, all four sessions

Labels: proposed by the tool, validated by the user in the label screen (miss scan: 20240924
whole hour; 20241004 to 17 min; 20260928_IMG_1652 to 27 min; 20261012 to 45 min, so recall
beyond those points is unproven). Lesson rides count as rides (user decision B); the 20241004
lesson labels (0:00-2:35) are unverified tool proposals. SC-003 now measures clip completeness
(>= 95% of rides inside their padded clip) and tightness (<= 3 s overhang at p95).

| Session | Recall | Precision | Complete | Tightness |
| --- | --- | --- | --- | --- |
| 20240924 | 100% | 100% | 93.7% | 1.50 s |
| 20241004 | 96.4% | 97.6% | 91.6% | 1.50 s |
| 20260928_IMG_1652 | 96.2% | 91.1% | 77.4% | 1.90 s |
| 20261012_110549566 | 100% | 98.9% | 89.7% | 1.92 s |

Fixes driven by the labels (20240924 complete/end error before -> after where measured):
wall touches and stalls no longer split rides (end error p95 11.7 -> 1.0 s); identity
switches mid-ride joined; riders cut off at a side edge continue their ride; lesson riders are
not merged by the label containment rule; wall holds up to 10 s.

Open: portrait session rides split (starts 11-23 s late, ends 7-13 s early); three rides
cut 10-23 s short (20240924 28:04, 20261012 27:08 and 53:22, 20241004 56:03).

## 2026-10-15 - lessons as one ride; portrait framing accepted as a limitation

User decision: a lesson is one ride (FR-014). `_merge_lessons` joins overlapping rides when
either is a lesson; the 20241004 labels were merged the same way (`merge_lesson_labels.py`,
lesson ride r000000, 0:00-2:35.6 from 9 items).

| Session | Recall | Precision | Complete | Tightness |
| --- | --- | --- | --- | --- |
| 20240924 | 100% | 100% | 93.7% | 1.50 s |
| 20241004 | 100% | 98.7% | 96.0% | 1.50 s |
| 20260928_IMG_1652 (not gating) | 96.2% | 91.1% | 77.4% | 1.90 s |
| 20261012_110549566 | 100% | 100% | 89.7% | 2.54 s |

Portrait session: riders leave the frame mid-ride, so rides split. Accepted as an edge case
(spec Edge Cases); not gating; rider identification (002) may rejoin them.
Framing indicators tried (`scripts/edge_report.py`, riding frames cut off by the frame edge):
20240924 0%, 20241004 0%, portrait 8.8%, night HDR 22.2%. The HDR session is cut off more
often yet completes 89.7%, and visible wave-face share (portrait 92.9%, HDR 79.6%) did not
separate them either, so no automatic framing warning yet.

## 2026-10-15 - wall returns; padding 1.5 s / 2 s

* Wall returns (`_merge_wall_returns`, `rides.wall_return_max_s` = 4 s): a ride ending at a side
  wall continues when a new track appears there within 4 s, close by, and rides back out.
  Fixes 20240924 28:04 (end -11.7 s -> -1.9 s). A first version allowing 10 s merged two riders
  on 20241004 (9:13, 6.4 s apart) and was tightened.
* Padding: `scripts/pad_sweep.py` over before {1, 1.5, 2} x after {1.5, 2, 2.5, 3}. Chose
  1.5 s / 2 s: SC-003 then holds on both archive sessions with 2.0 s p95 overhang.

| Session | Recall | Precision | Complete | Tightness |
| --- | --- | --- | --- | --- |
| 20240924 | 100% | 100% | 96.2% | 2.00 s |
| 20241004 | 100% | 98.7% | 96.0% | 2.00 s |
| 20260928_IMG_1652 (not gating) | 96.2% | 91.1% | 79.2% | 2.40 s |
| 20261012_110549566 | 100% | 100% | 90.8% | 3.04 s |

Open: the night HDR session misses completeness (8 cut rides: 27:08 and 53:22 end ~11 s early,
the rest are 1.5-5 s start or end errors) and is 0.04 s over the tightness target.
## 2026-10-15 - first held-out session: PXL_20261014_100546073

New footage (Pixel, 1080p HLG, 55.7 min, front-deck view; left wall partly out of frame),
labelled by the user, scored with no tuning.

| Session | Recall | Precision | Complete | Tightness |
| --- | --- | --- | --- | --- |
| PXL_20261014_100546073 (held out) | 86.5% | 95.1% | 86.5% | 2.00 s |

* 8 rides missed outright (the user added them).
* 4 detected rides each join two consecutive labelled rides 7-10 s apart (00:41, 14:08, 23:07,
  24:26; two tracks each). Likely the wall-stall bridge (a rider resting at the wall keeps the
  ride open up to 10 s) followed by the cross-track wall return picking up the next rider. This
  is the over-fitting risk discussed earlier; fix with more held-out data, not on this session.
* Start error p95 3.5 s, end error p95 0.5 s.

User verdict: segments are good enough for now; move on to zone proposal (US2).