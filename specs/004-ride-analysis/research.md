# Research: Ride Analysis

## R1. Pose on this footage (spike, 2026-10-17)

`scripts/spikes/ride_pose.py`, YOLO11s-pose and YOLO11x-pose on full-resolution crops (rider box
+30%, 384 px input), 15 fps:

| Session | Camera | Rider height px (p10/median/p90) | Joints conf ≥ 0.5 (s and x) |
| --- | --- | --- | --- |
| PXL_20261014 | handheld follow, 1080p HLG | 237 / 311 / 363 | shoulders, hips, knees, ankles 99-100% |
| 20241004 | fixed, 720p | 98 / 152 / 230 | 99-100% |

Other sessions (`rider_sizes.py`): 720p fixed 145-152 px median, 1080p 311-355 px. By eye: the
skeleton is right standing, trimming and in turns; in the deepest crouch left and right legs
sometimes swap (hip height still right); falls are obvious. s and x curves nearly coincide.

**Decision**: YOLO11s-pose by default (fast), `m`/`x` configurable; re-check on the marks (R3).

## R2. Scale: why pixels fail

Within one fixed-camera ride the rider's box height ranges 85-295 px with distance from the
camera; the handheld camera zooms to follow. A curve normalised by the ride's own maximum
height in pixels mostly measures distance.

**Decision**: every measure is a ratio of body segments in the same frame, or a quantity in
pool coordinates.

## R3. Compression signal (decided on the marks)

Candidates, each smoothed (Savitzky-Golay, ~0.3 s) and normalised by its own ride median:

1. **Leg/torso**: |mid-hip → mid-ankle| / |mid-shoulder → mid-hip|. Zoom-invariant; torso
   foreshortens when leaning toward the camera.
2. **Leg straightness**: |mid-hip → mid-ankle| / (hip→knee + knee→ankle), averaged over both
   legs: 1 = straight; unaffected by torso lean (2026-10-17: replaces "height/torso", which in
   one frame reduces to 1 + leg/torso).
3. **Height / expected height** (not implemented): shoulder-ankle length over the standing
   height expected at the rider's pool position. Needs the zone and fails on handheld spans;
   built only if 1 and 2 both miss SC-001.

**Decision**: implement 1 and 2 in `signals.py`; choose by SC-001 (turns within 0.5 s) on the
marked rides, held-out session excluded. Record in "R3 results".

## R4. Turns, pumps, trimming

- **Lateral motion**: the rider's feet in pool coordinates (`u` across the wave) where the zone
  is confirmed and the camera still (001 epochs); on handheld sessions the rider's horizontal
  motion relative to the wave can't be separated from panning, so turns there come from the
  compression signal plus torso rotation (shoulder-line angle change).
- **Turn**: a direction change of lateral velocity (sign change with speed above a threshold on
  both sides) within ±0.7 s of a compression minimum; time = the compression minimum.
- **Pump**: a compression minimum deeper than a threshold without a direction change.
- **Trimming**: clear riding time not within any turn (±0.6 s) or pump (±0.4 s) window.
- **Unclear**: frames with hip/ankle confidence below 0.3 or the crop overlapping another person
  (IoU > 0.3 with another track): excluded from measures and shares.

## R5. Endings

- **Fall**: in the last 1.5 s the compression signal collapses below a threshold and/or the
  body's long axis tilts > 50° from the board-normal estimate, and the track ends in the wave
  area (zone face band) rather than at a side wall or the flats; or the rider is seen in the
  water (sitting/lying, 001 stance) right after.
- **Exit**: track ends crossing a side wall or the flats with the body upright, or a kick-out
  (board leaves the feet while the body stays upright).
- **Unclear**: otherwise. The user can correct (edit `ride_ending`).

## R6. Fall comparison

For each fall, the window [end - 3 s, end - 0.5 s]; for each clean exit, the same window
before the exit. Measures: mean and minimum compression, time since last turn, turn rate,
lateral position on the wave (pool `u`, where available), depth on the face (pool `v`). Shown
as two columns with the per-ride values as dots, plus a playlist of the windows (fall moments
back to back in the review copy).

## R7. Trends

`GET /api/trends?name=me` scans every session's `analysis.json` and riders, takes rides whose
rider's user-given name equals the query (case-insensitive) and returns one point per session
(date from the session's creation or the file's recording time) per measure. No appearance data
is read; only names the user typed.

## R8. Evaluation marks

`labels/analysis/<video>.json`: per ride (start/end in seconds, to re-attach): turn times,
ending (fall/exit/unclear), and optional pump/trim spans. Marked in the Marks screen with keys
(t = turn at playhead, f/e = fall/exit). `surfclip eval-analysis` reports SC-001..003 per
session; PXL and 20241004 are the first two marked sessions, a third is held out.
