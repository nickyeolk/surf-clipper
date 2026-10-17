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

## R6. Comparison playback (rescope 2026-10-17)

Each side is the session's 720p review copy in a container; a CSS transform (scale + translate)
keeps the surfer's crop box (from the keypoints file, smoothed over ~0.5 s so the view doesn't
jitter) filling the panel. The skeleton is drawn on a canvas in the same transformed space, with
keypoints linearly interpolated between the 15 fps analysis frames. Mirror = `scaleX(-1)` on the
container (keypoints mirrored with it). Sync: B's time = B.sync + (A.time - A.sync); A drives the
clock; on each animation frame B is re-seeked if it drifts by more than half a frame (paused) or
its playbackRate is nudged ±3% (playing). Measures under the videos share an x axis of "seconds
from sync".

## R7. Reference clips

An imported clip is a session (`kind = "reference"`) so it reuses probe, review copy, detection
and tracking; zone, rides and riders are skipped. The user clicks the surfer on a frame; the
track whose box contains the click (nearest centre otherwise) at that time is chosen, and nearby
tracks that continue it (001's stitching rules) are joined. The clip's single ride spans the
chosen track.

## R8. Score from stars

Features per analysed ride (data-model.md), standardised over all the user's analysed rides.
Default weights from `[score]` (length 1, clean end 1, compressions 0.5, depth 1, rhythm 0.5,
tricks 0.5, unclear -1). With ≥ 5 starred and ≥ 5 unstarred rides, weights are fitted by
L2-regularised logistic regression (starred = 1), pooled over sessions; the explanation names the
two or three largest positive and negative contributions in words ("long ride, deep turns; fell
at the end"). SC-002 is measured leaving one session out of the fit.
