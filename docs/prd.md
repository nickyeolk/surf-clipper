# Surf Session Clipper — PRD (MVP)

Oct 13, 2026 · @lik · Status: Draft v0.5

## Summary and problem

The MVP turns a ~1 hour fixed-camera standing-wave video into one clip per ride, groups the rides by rider after I name one clip per person, and exports a compiled video for any chosen rider. Everything runs locally. Manoeuvre detection and turn counting come later.

**Problem.** A session video is about an hour long, and most of it is waiting and changeovers. Finding my own rides means scrubbing the whole file by hand, and separating several riders' turns takes even longer.

**Why build it.** Venue systems such as Flowstate and Surf Eye clip and group rides automatically, but only at parks that install them, and you pay per session. Nothing does this for footage I film myself at a Citywave-style wave.

**MVP outcome.** I drop in a session video, spend a few minutes naming riders and fixing mistakes, and get one video per rider containing only their rides.

## Target user

The first user is me: a solo surfer at a standing wave who films sessions on a fixed camera and is comfortable running a CLI and local models.

- **Context:** about a 1 hour session; my phone on a stand, framed differently every session, at 1x or 0.5x ultra-wide zoom, and sometimes bumped mid-session; several riders take turns, one on the wave at a time.
- **When:** after the session, on my own computer.
- **What I want:** my rides, quickly, for my own use. Other riders don't receive compilations for now.
- **Later users, not designed for yet:** other riders in my session, coaches, and possibly venues.

## User stories

| ID | As a surfer, I want to… | So that… |
| --- | --- | --- |
| US-1 | give the tool a session video and get every ride as its own clip | I never scrub through waiting time |
| US-2 | confirm an auto-proposed wave zone on one keyframe per upload | setup takes seconds even though framing changes every session |
| US-3 | review detected rides and fix boundaries, delete false rides, add missed ones | the clip list is right before I share it |
| US-4 | name one clip per rider and have the rest labelled for me | grouping an hour of rides takes minutes |
| US-5 | correct wrong assignments and have the tool re-propagate | one fix improves the remaining rides |
| US-6 | export one compiled video of all rides by a chosen rider | I can watch or share my session in one file |
| US-7 | export the ride list with times and rider labels as JSON or CSV | later phases and my own analysis can reuse it |
| US-8 | re-run the pipeline without losing my edits | trying new settings is safe |

## Functional requirements

The pipeline runs in cached stages: ingest → camera epochs and zone → ride detection → review → rider labelling → export. Each stage writes a file the next stage reads. All MVP requirements are must-haves unless marked *should*.

### Wave zone and camera handling

Framing, zoom and position change every session, and the phone can move mid-video. So the zone is set up again for each upload, and each stretch of video with a stable camera (a "camera epoch") gets its own zone.

**Recommendation: auto-propose the zone from riders' positions, then confirm it on one keyframe.**

1. A first detection pass runs over the whole video before any zone exists.
2. The ride zone is proposed from where people persist and move fastest. Waiting surfers sit still at the edges; riders hold position on the wave face while moving laterally.
3. A motion-variance map of the water (the standing wave's constant churn) is a secondary signal to tighten the polygon.
4. The user sees the proposal on a keyframe: the wave-zone corners, the deck/water boundary, and the entrance and side areas. They accept it with one click or drag the points. Target: under 30 s.

**Fallback:** if the proposal has low confidence (too few detections, or no clear cluster), the user draws the polygon by hand on the keyframe.

Why this route over the others:

- **Manual zone only:** reliable, but costs effort on every upload.
- **Water texture or motion only:** fragile with glare, spray, floodlights and wide-angle distortion.
- **Riders' positions:** uses the same detections the pipeline already needs, and lands where rides actually happen.

**Camera-shift handling:**

1. Pick a reference keyframe. At about 1 fps, match features on static background against it (ORB or SIFT; SuperPoint + LightGlue if those prove weak), masking out the water and people.
2. Fit a homography with RANSAC and track the inlier ratio and how far the frame has moved.
3. A sudden jump, or slow drift past a threshold, starts a new camera epoch. Thresholds are in fractions of frame size, not pixels.
4. If the homography is reliable, re-map the zone into the new epoch and apply it silently, with a marker on the review timeline.
5. If not (too few inliers, or a large change such as a zoom switch), prompt the user to re-confirm the zone on the new epoch's first keyframe.
6. A ride that crosses an epoch boundary is joined back into one ride.

### Scene geometry: head-on to 45° oblique

The camera sits anywhere from head-on (at the downstream end, facing the wave) to about 45° to the left or right. The pool therefore appears as a skewed quadrilateral, and riders shrink with distance. All position logic runs in pool coordinates, not raw pixels.

- **Pool plane.** At zone confirmation the user accepts four corners of the wave area. A homography maps image points to a top-down pool plane, normalised to 0–1 across and along the wave. Lateral movement, distance to the deck and zone membership are all measured there. At 0.5x, points are undistorted first (*should*).
- **Local scale.** Near riders look several times larger than far ones. Size-based thresholds therefore use the rider's current box height, not a session median.
- **Deck/water boundary.** The deck and entrance run along the back edge of the pool, which is the far edge of the quadrilateral. It is proposed automatically from the strong edge between deck and water, and confirmed with the zone.
- **Regions.** The keyframe step also marks the entrance strip and the side waiting areas. At this angle, a person sitting at the entrance can overlap the wave zone in pixels. Region membership therefore uses the feet point mapped to the pool plane, not box overlap.
- **Hidden feet.** Whitewater often hides the feet. The feet point is then estimated from the board detection, or from the top of the box plus the rider's usual height.

**Mirror-agnostic.** The camera can be on either side of the wave, so no logic may assume a side:

- **Pool-plane corners:** ordered by role (deck edge first, then the wave's two ends), never by image left or right.
- **Directions:** nothing assumes riders move left to right, or that the entrance and waiting areas sit on a particular side.
- **Zone proposal:** tries both orientations and keeps the better fit.
- **Evaluation:** the set includes sessions filmed from both sides.

### On/off-wave logic

Each tracked person gets a state in every frame: **off** (deck, entrance, side, or in the water after a fall), **dropping in**, or **on the wave**. A ride is one track's continuous run of on-wave frames.

| Evidence | On the wave | Waiting at the entrance or side |
| --- | --- | --- |
| Feet point vs the deck/water boundary | Water side, inside the wave zone | Deck side, entrance strip or side area |
| Board contact | Board detected under the feet (pretrained "surfboard" class) | No board, board held, or board lying beside them |
| Stance | Standing or crouched (box shape; optional pose keypoints) | Sitting, or standing still |
| Sustained motion | Lateral movement in pool coordinates for at least 1.5 s | Little or no movement |

1. **Confirm late, start early.** A ride is confirmed only after on-wave evidence holds for a confirmation window (default 1.5 s), so sitters and brief splashes don't trigger one. The start is then back-dated along the track to the moment the rider crossed the deck/water boundary or left the deck edge.
2. **Acid drops.** A drop-in from the deck edge is fast and blurred, so the track often breaks. A person last seen at the deck edge is linked to an on-wave track that appears within 1 s and nearby, measured in rider heights. The ride starts at the jump, not when the track resumes.
3. **Entrance sitters.** Someone sitting at the entrance stays off however long they sit, even if their box overlaps the wave zone in the image. They become a candidate only when their feet point crosses into the water with a standing stance. People standing in the water without riding a board stay off too, such as an instructor or someone waiting at the back entrance. While a lesson runs, only the person standing on a board is the rider. Lesson stretches are clipped as the beginner's rides and flagged "lesson" in review.
4. **Two-pass boundaries.** Detection runs at about 5 fps. Each ride's start and end are then refined at full frame rate within ±2 s, to meet the 1 s boundary target on sudden drop-ins and falls.
5. **Ride end.** The ride ends on its last on-wave frame:
   - a fall (stance lost, rider gone into the whitewater, or board separated);
   - an exit to the side or deck; or
   - leaving the zone.

   A changeover overlap, where the next rider drops in while the previous one falls, is allowed.
6. **Minimum length.** Rides shorter than the minimum length are dropped from the output but listed in review as "short attempts". The minimum defaults to 10 s and is set by the user before processing.

### Rider partly out of frame

At this angle, close rides on the near side can carry the rider past the frame edge, as in the 12 Oct sample frame.

- **Truncated boxes:** a box touching a frame edge is marked truncated. The rider still counts as present, but the box isn't used for scale estimates or rider crops.
- **Grace window:** a rider who leaves through a frame edge and returns through the same edge within 2 s (default) continues the same ride.
- **Ride end:** a frame-edge exit ends the ride only if the rider doesn't return within the window, or reappears off the wave.
- **Zone past the edge:** the proposed zone may extend beyond the frame edge. It is clipped for display, but positions near the edge stay valid.

### Scale-invariant thresholds

No threshold depends on fixed pixel sizes or frame counts:

- **Distances and movements:** in pool-plane coordinates (0–1 across and along the wave) or in units of the rider's current box height, never in raw pixels.
- **Times:** in seconds, not frames, because frame rate varies (30, 60 or 120 fps).
- **Zone membership:** the feet point (or board) mapped to the pool plane, not box overlap. This holds up under the 45° angle and 0.5x distortion.
- **Rider size range:** riders range from small (far side, 0.5x) to very large (near side, close to the camera, as in the 12 Oct sample). The detector must handle both: a higher input resolution or tiling (SAHI) when riders are small, and no assumed maximum size. In the samples, rider height runs from about 30 to 320 px at 720p (4% to 45% of frame height). Tiled inference switches on when far riders drop below about 60 px.

### Requirements

| ID | Requirement |
| --- | --- |
| FR-1 | Accept local MP4 or MOV phone video: H.264 or HEVC, 8-bit SDR or 10-bit HDR, 720p to 4K. Accept both the phone's original files (e.g. iPhone HEVC, with HDR as HLG or Dolby Vision) and exports such as the 720p30 H.264 SDR archive. Frame rates of 30 to 120 fps, up to 1.5 h long |
| FR-2 | Decode a low-fps, low-resolution SDR proxy for analysis, tone-mapping HDR footage; keep the original for export. Use lens, zoom and HDR metadata as hints when present; never require them |
| FR-3 | Split the video into camera epochs by background feature matching and homography |
| FR-4 | For each epoch, propose the wave-zone corners (pool plane), the deck/water boundary, and the entrance and side areas, from rider positions and scene edges |
| FR-5 | Show the proposal on a keyframe for one-click accept, edit, or manual draw (fallback) |
| FR-6 | Re-map zones across reliable shifts automatically and silently, marked on the review timeline; prompt only when a re-map is unreliable |
| FR-7 | Track people and give each a state per frame (off, dropping in, on the wave) from boundary position, board contact, stance and sustained motion |
| FR-8 | Confirm a ride after the confirmation window (default 1.5 s), and back-date its start to the boundary crossing or drop-in |
| FR-9 | Link deck-edge tracks to on-wave tracks for acid drops; join rides split by an epoch boundary or a brief frame-edge exit |
| FR-10 | Refine each ride's start and end at full frame rate within ±2 s |
| FR-11 | Apply the minimum ride length (default 10 s, set before processing) and padding (1 s before, 1.5 s after); list dropped short attempts in review |
| FR-12 | Write `rides.json`: ride ID, start/end (seconds and frames), confidence, epoch, state timeline, truncation flags, lesson flag, rider crops |
| FR-13 | Review UI: list rides with thumbnails and a "lesson" flag; play, trim, split, merge, delete, add a missed ride |
| FR-14 | Export clips with frame-accurate re-encoding, keeping HDR (10-bit, colour metadata) in every clip and compilation, matching the source: HLG, HDR10, or Dolby Vision's HLG base layer when re-encoding; *should* offer a fast stream-copy mode |
| FR-15 | Compute a per-ride appearance descriptor from sharp, untruncated crops, normalised for size and colour |
| FR-16 | Cluster rides into candidate riders (up to 10 per session), with the count unknown or set by the user |
| FR-17 | Run the naming step and propagate labels (see the human-in-the-loop flow below) |
| FR-18 | Treat confirmed zones, edited boundaries and rider labels as hard constraints that re-runs never overwrite |
| FR-19 | Export a compiled MP4 per rider in time order, with hard cuts and overlays for rider name, ride number and session time |
| FR-20 | Export a per-rider clip folder and a session manifest (JSON and CSV) |
| FR-21 | Ship as a Windows desktop app over a local pipeline library with a CLI; run on a laptop with a small GPU, with a CPU fallback |
| FR-22 | Cache each stage so an edit never forces detection to run again |

## Human-in-the-loop flow

The user steps in at three points (zone, rides, riders), and every confirmation becomes a hard constraint. Target: no more than 5 minutes of my time per 1 hour session.

1. **Confirm the zone.** Accept or adjust the proposed polygon on the keyframe. Repeat only for camera epochs whose zone could not be re-mapped automatically.
2. **Review rides** (optional). Skim the thumbnails, then trim, delete or add rides. The lowest-confidence rides are listed first.
3. **Name riders.** For each candidate cluster, show its most typical ride. The user then:
   - types a name;
   - marks it "same as" another cluster (merge);
   - marks it "mixed" (split it, then show both halves); or
   - marks it "ignore" (staff, or someone not riding).
4. **Propagate.** Each ride goes to the nearest named rider. Its confidence is the margin to the second-nearest rider, and the session's usual turn order is only a soft prior, because rotation is common but not fixed.
5. **Work the review queue.** Rides below the confidence threshold are shown lowest first. Each confirm or reassign is added as a constraint, and step 4 runs again, so later rides improve. Loop until the queue is empty or I stop.
6. **Export** per-rider clips, compilations and the manifest.

### Rider re-ID under changing zoom and lighting

- **Across sessions:** zoom, framing and lighting change, so appearance does not carry over reliably. The MVP clusters within a single session only. Remembering riders across sessions is not wanted for now.
- **Small riders at 0.5x:** crops are low-resolution, so deep re-ID embeddings (OSNet, DINOv2) lose detail. Mitigations:
  - add colour descriptors (clothing, board) that survive low resolution;
  - resize crops to a fixed height before embedding;
  - average over many frames per ride.
- **Coloured LED lighting at night:** LED hues shift the colour of clothing and boards. They usually stay fixed for a session. Mitigations:
  - estimate one colour correction per session (per camera epoch) from the static background, falling back to per-frame correction if the background colour drifts past a threshold;
  - down-weight colour features when the light is strongly tinted;
  - lean on deep embeddings and the board's shape and pattern instead.
- **Lighting drift in a session** (dusk, floodlights switching on): rides near a lighting change are weighted towards their neighbours and sent to the review queue.
- **Motion blur:** close, fast rides blur the rider. Only the sharpest crops of each ride, ranked by a blur score, feed the descriptor and the representative clip.
- **Clothing varies** (wetsuit, boardshorts, rash vest): a mid-session change (hood off, top on, board swap) splits a rider into two clusters, which the "same as" merge in step 3 handles.
- **Camera bump mid-session:** apparent size and angle shift slightly, so crops are size-normalised and descriptors avoid pixel-size features.

## Success metrics

The MVP ships when every target holds on each evaluation session, including the 0.5x and bumped sessions, not only on average. The processing-time target is a proposal until it has been measured on the sample videos.

| Metric | Definition | Proposed MVP target |
| --- | --- | --- |
| Ride recall | Hand-labelled rides at or above the minimum length, matched by a detected ride (time IoU ≥ 0.5) | ≥ 95% |
| Ride precision | Detected rides that match a hand-labelled ride | ≥ 90% |
| Clip boundary error | Absolute start and end error in seconds, on matched rides; acid-drop starts reported separately | 95th percentile < 1 s; median < 0.5 s |
| Rider-assignment accuracy | Rides assigned to the correct rider straight after the naming step, before the review queue | ≥ 85% |
| Review effort | Corrections needed to reach 100% correct assignment | ≤ 10 per session |
| Zone setup effort | Time to confirm or fix the zone, including re-confirmations after shifts | ≤ 30 s per epoch |
| Shift detection | Real camera shifts caught (synthetic plus real bumps) | 100% of shifts larger than 2% of frame width |
| Processing time | Wall-clock time per 1 h video on my Windows laptop with a small GPU, from upload to ready for review | ≤ 30 min; CPU-only fallback ≤ 90 min |
| User time | My total hands-on time per session | ≤ 5 min |

### Evaluation set

At least 5 hand-labelled sessions, each with ride start/end times, rider IDs and camera-shift times. One is held out and never used for tuning.

- [ ] `20241004.MP4`: about 45° to the right, close to the near wall, daylight, riders often cut off at the frame edge, a lesson at the start
- [ ] `IMG_3106.MP4`: about 45° to the left, elevated, daylight with moving sun patches
- [ ] `20250326_1.MP4`: head-on, ultra-wide, night LED, small far riders
- [ ] 12 Oct 2026 night session: HDR, coloured LED, heavy motion blur on close rides; the only HDR session
- [ ] New staged session with a deliberate mid-video bump, filmed from a new position. This one is held out from tuning, except for shift detection.
- [ ] Synthetic shift tests: clean sessions with injected jumps, slow drift and zoom changes, for shift-detection regression tests
- [ ] Edge cases tagged across all sessions:
  - acid-drop starts
  - people sitting or standing at the entrance or side for long stretches
  - lessons with several people on the wave
  - a rider partly out of frame at the near edge
  - people walking close to the camera
  - heavily blurred close rides
  - falls and attempts under 10 s
  - changeover overlaps

## Non-goals

The MVP finds, cuts, groups and compiles rides. It does not judge what happens inside a ride.

- **Manoeuvre detection and classification** (turns, cutbacks, carves, 360s): future phase F3
- **Turn counting:** future phase F1
- **Pose estimation:** future phase F2
- **Scoring or judging rides**
- **Remembering riders across sessions:** future phase F4
- **Several riders on the wave at once, ocean surf, or a camera that pans or follows the rider**
- **Multiple cameras, or one session split across files** (a should-have to consider later)
- **Real-time or live processing; cloud hosting; accounts; a mobile app**
- **Face recognition:** never planned

## Assumptions and constraints

**Assumptions:**

- **Camera:** a phone on a stand, anywhere from head-on to about 45° to the left or right of the wave. It stays still between bumps, with no panning or zooming during recording. A bump or re-position may happen a few times per session.
- **Framing:** differs every session, so nothing is reused from earlier sessions. Zoom is 1x or 0.5x ultra-wide.
- **Scene:** the wave and whitewater fill the lower part of the frame, and the deck and entrance run along the back edge of the pool. Waiting riders may sit on the side or at the entrance, in or out of frame.
- **Rides:** Normally one rider is on the wave at a time, with up to 10 riders per session. Coached lessons are the exception: an instructor may stand in the water holding a beginner on a pole, and pairs may practise together. Rotation is usual but not fixed. A ride starts from the entrance or with an acid drop from the deck edge.
- **Framing of riders:** riders can be very close and large, and partly out of frame at the near edge.
- **Light:** daylight, or night under coloured LED lighting; HDR recording is common.
- **Session:** one continuous file of up to 1.5 h. The input may be the phone's original file or an export; the archive exports are one file per session.

**Constraints:**

- **Hardware:** a Windows laptop with a small GPU, plus a CPU fallback.
- **Local processing first:** footage and rider data stay on my machine, with no cloud calls in the pipeline.
- **Personal use:** compilations are for me, not shared with other riders. Appearance descriptors are kept for the current session only, and there is no face recognition.
- **Stack:** a Python and ffmpeg pipeline (with HDR tone-mapping) as a library with a CLI, wrapped by a Windows desktop app. Pretrained detectors and trackers only; no custom model training for the MVP.
- **Scale-invariant thresholds:** see Functional requirements.

## Risks

The biggest risks come from three sources. First, the phone camera: unknown framing, angles from head-on to 45°, ultra-wide zoom, bumps. Second, crowded scenes: waiting riders beside the wave, lessons. Third, night sessions: LED colour, HDR, motion blur. Each has an evaluation case that tests it.

| Risk | Impact | Mitigation | Evaluation case |
| --- | --- | --- | --- |
| Riders sitting or standing at the entrance or side are taken for riders | False rides | Feet point in the pool plane vs the deck/water boundary; stance; board contact; sustained motion; 1.5 s confirmation window | Tagged entrance and side waiters (all sessions) |
| Lessons put several people on the wave | False rides, split rides, or the wrong person labelled | Only a person standing on a board counts as the rider; people in the water without a board stay off; lesson stretches clipped as the beginner's rides and flagged in review | `20241004.MP4` lesson segment |
| Acid-drop starts are clipped late | Clips miss the drop-in | Back-dated starts; linking deck-edge tracks to on-wave tracks; full-frame-rate refinement | Tagged acid drops; separate boundary error for drop-ins |
| Camera angle varies from head-on to 45° either side | Missed or false rides; wrong scale | Pool-plane homography; local rider scale; feet-point membership; no assumed side | `20241004.MP4` (right), `IMG_3106.MP4` (left), `20250326_1.MP4` (head-on) |
| Proposed zone or boundary is wrong (odd framing, waiting riders, staff, sun patches) | False or missed rides | Rider positions as the primary signal; one-click confirm or edit; manual-draw fallback | All sessions; zone setup time |
| Mid-session bump goes undetected | The zone no longer matches, and rides are lost | Homography-based camera epochs (570 to 2,080 background matches per frame pair in the samples); inlier-ratio alarm; prompt to re-confirm | Staged bump session; synthetic jump and drift tests |
| A silent automatic re-map is wrong | The zone is offset, unnoticed | Mask out water when matching; minimum inlier count; timeline marker at every re-map | Synthetic shift tests at 1x and ultra-wide |
| Night LED lighting and sensor noise | Missed detections; colour re-ID fails | Lower detection thresholds bridged by tracking; colour correction per session with a per-frame fallback; down-weight colour | `20250326_1.MP4`; 12 Oct session |
| HDR (10-bit) footage from new recordings | Washed-out analysis frames; exports with wrong colour; slower decode | Tone-mapped SDR proxy; HDR kept in every export with its metadata (Dolby Vision's dynamic metadata survives only stream-copy, so re-encoded clips keep its HLG base layer); overlays rendered at HDR reference white; check playback on Windows | 12 Oct session |
| Motion blur on close, fast rides | Missed detections; weak stance and re-ID signals | Tolerance for track gaps; sharpest-crop selection; full-frame-rate boundary refinement | 12 Oct session; tagged blurred rides |
| Rider partly out of frame | A ride split, or ended early | Truncation flags; frame-edge grace window | `20241004.MP4` near-wall rides |
| Small far riders (about 30 px at 720p) are missed | Ride recall drops | Tiled inference below about 60 px; thresholds relative to rider height | `20250326_1.MP4` |
| Riders look alike; low-resolution crops | Rider assignment below 85% | Colour and deep descriptors; soft turn-order prior; review queue sorted by confidence | All sessions; assignment metric |
| Laptop GPU too slow for 4K HDR | Processing-time target missed on new recordings | Small detector (e.g. YOLO11n/s); low-fps proxy; hardware decode; stage caching | Timing on the 12 Oct file and a 720p archive file |
| Windows desktop packaging (GPU runtime, ffmpeg) | P3 slips | Pipeline stays a library with a CLI; the app is a thin shell | Not applicable |
| Clips cut on keyframes are off by up to about 1 s | Clip boundary error exceeds 1 s | Frame-accurate re-encode by default | Boundary error metric |
| Tuning to my own sessions only | Fails at a new position or framing | Held-out staged session; synthetic tests | Staged bump session |
| Scope creep into manoeuvres | The MVP slips | Constitution and non-goals; future phases on the roadmap | Not applicable |

## Phased roadmap

_Roadmap diagram (text version):_

| Phase | Scope | Effort (focused weeks) | Exit gate |
| --- | --- | --- | --- |
| P0 Eval set | Label 5 sessions; synthetic shift test clips | 1 to 2 | |
| P1 Rides (001) | Detection, zone, camera epochs | 4 to 5 | Gate A: ride recall 95%+, boundary error under 1 s, including the 0.5x and bump sessions |
| P2 Riders (002) | Clustering, naming, review queue | 2 to 3 | Gate B: rider assignment 85%+ before the review queue |
| P3 Export (003) | Clips, compilation, desktop app, overlays | 2 to 3 | MVP release: all targets on every evaluation session |

Future phases, after the MVP gate: F1 turn counting (lateral reversals) · F2 pose (keypoints per ride) · F3 manoeuvres (classify and count) · F4 cross-session riders (remember riders).

The MVP is now about 9 to 13 focused weeks, up from 7 to 10. Two phases grew:

- **P1, 4 to 5 weeks (was 3 to 4):** the on/off-wave state machine, acid-drop starts, pool-plane geometry for the 45° angle, frame-edge handling, and HDR and blur robustness.
- **P3, 2 to 3 weeks (was 1):** a Windows desktop app instead of a CLI with a local web UI, overlays, and HDR-preserving export.

P0 and P2 are unchanged. Part-time, expect roughly double the calendar time.

## Next step: Spec Kit

The MVP goes into Spec Kit as three features, each with its own specify → clarify → plan → tasks → implement cycle. They are not one big spec.

- **001:** ride detection, camera epochs and zone
- **002:** rider labelling
- **003:** compilation, export and the desktop app

To get there:

1. Run `specify init --ai claude`.
2. Paste the constitution below into `/speckit.constitution`.
3. Run the 001 prompt through `/speckit.specify`, then `/speckit.clarify`.

Command names vary by Spec Kit version, so check the installed README.

### Draft constitution

```markdown
# Surf Session Clipper — Constitution

1. Local-first and personal. Footage and rider data never leave the machine. No face recognition. No telemetry. Descriptors live for one session only.
2. Evaluation before features. Every detection, zone, shift, on/off-wave or re-ID component reports its metric on the labelled evaluation set, including the 0.5x, bumped, night-HDR and held-out sessions. No change merges if it regresses an agreed metric.
3. Scale-, perspective- and mirror-invariant by design, with the camera to the left or right of the wave. No threshold in raw pixels or frames: use pool-plane coordinates, the rider's current height, and seconds.
4. Assume the camera moves. Every spatial artefact (zone, boundary, positions) belongs to a camera epoch; nothing assumes one fixed frame for a whole video.
5. Confirm late, start early. Ride decisions may wait for evidence, but timestamps are back-dated to the true onset.
6. Human corrections are ground truth. Confirmed zones, boundaries and rider labels are hard constraints; re-runs never overwrite them.
7. Staged, cached pipeline. Each stage reads and writes versioned files (epochs.json, rides.json, labels.json) and can be re-run on its own.
8. Simple first. Heuristics and pretrained models before any training; a new model must beat the baseline on the evaluation set, within the laptop's GPU budget.
9. Config, not constants. Thresholds live in a versioned config file; the user can set minimum ride length before processing.
10. Engineering. Python 3.11+, uv, typed (pyright), ruff, pytest; ffmpeg for media, HDR-aware. Must run on Windows. The pipeline is a library with a CLI; the desktop app is a thin shell over it.
11. Scope discipline. Manoeuvres, turn counting, pose analysis and cross-session identity are out of scope until their roadmap phase opens.
```

### First specify prompt (feature 001)

```text
Feature 001: ride detection and clipping for phone-filmed standing-wave sessions.

I film ~1 hour surf sessions at a standing wave with my phone on a stand, anywhere from head-on to about 45 degrees left or right of the wave; nothing may assume a side. Archive files are 720p30 H.264 SDR (about 1 h, 1.6 GB); new recordings may be 4K HDR. Framing differs every session, zoom is 1x or 0.5x ultra-wide, and the phone sometimes gets bumped mid-session. Sessions may be at night under coloured LED lighting, recorded in HDR, with heavy motion blur on close, fast rides. The deck and entrance run along the back edge of the pool. Up to 10 riders take turns; exactly one is on the wave at a time. Others wait on the side or sit at the entrance, in or out of frame. A ride starts either from the entrance or with an acid drop (jumping in from the deck edge).

I want to give the tool a session video and get back every ride as its own clip plus a ride list (start, end, confidence), so I never scrub through waiting time.

- The tool proposes the wave zone, the deck/water boundary and the entrance/side areas; I confirm or adjust them on one keyframe in under 30 seconds, or draw them by hand.
- Someone sitting at the entrance or on the side is never counted as riding. A rider is on the wave when they are on the water side of the deck boundary, on their board, standing, and moving along the wave.
- Acid-drop starts must not be clipped late: the ride starts at the jump.
- The tool detects camera moves, re-maps the zone silently when it can (with a marker on the timeline) and asks me only when it can't. A ride crossing a camera move, or briefly leaving the frame edge, stays one ride.
- Nothing depends on fixed pixel sizes or frame counts; it must work at 1x and 0.5x, at 30-120 fps, and from an oblique angle.
- Rides shorter than a minimum length (default 10 s, which I set before processing) are left out but listed as short attempts. Clips get 1 s of padding before and 1.5 s after.
- I can review rides, trim, split, merge, delete and add missed ones; my edits survive re-runs.
- Success: >=95% ride recall, >=90% precision, clip boundary error <1 s at the 95th percentile (acid drops reported separately), on every labelled session including the 0.5x, bumped and night HDR sessions; a 1 h video processed in <=30 min on my Windows laptop with a small GPU.

Out of scope: rider identification (002), compilation and the desktop app (003), manoeuvres. Everything runs locally.
```

## Sample footage findings

The three archive sessions I checked are all 720p, 30 fps, H.264, standard (non-HDR) video of about an hour each, and none of them has a camera bump. They also contradict two assumptions: the camera can face the wave head-on, and coached lessons put several people on the wave at once. All three were read only, never modified or moved.

| File | Recorded | Format | Duration, size | Camera position | Light | Rider height at 720p |
| --- | --- | --- | --- | --- | --- | --- |
| `IMG_3106.MP4` | 14 Nov 2025 | H.264 High, 1280×720, 29.97 fps (slightly variable), 8-bit BT.709 SDR, 3.6 Mbps | 58.9 min, 1.58 GB | About 45° to the left, elevated, normal width | Daylight, moving sun patches on the water | About 80–215 px (11–30% of frame height) |
| `20250326_1.MP4` | 26 Mar 2025 | H.264 High, 1280×720, 30 fps, 8-bit BT.709 SDR, 3.6 Mbps | 60.4 min, 1.62 GB | Head-on from the downstream end; looks ultra-wide (straight edges bow) | Night, steady purple-blue LED | About 30–120 px (4–17%) |
| `20241004.MP4` | 4 Oct 2024 | H.264 High, 1280×720, 30 fps, 8-bit BT.709 SDR, 3.6 Mbps | 62.7 min, 1.69 GB | About 45° to the right, close to the near wall | Daylight | About 85–320 px (12–45%); often cut off at the right edge |

What this means for the MVP:

- **Format:**
  - **Archive:** every file is an iPhone recording (Apple Core Media metadata tracks) exported as 720p SDR. One file per session; nothing splits.
  - **HDR:** none of the archive is HDR. HDR comes only from new recordings, such as the 12 Oct night session.
  - **Processing:** decoding 720p30 is light, so the processing-time target looks comfortable.
- **Rider size:** about 30 to 320 px tall at 720p, roughly a tenfold range.
  - Native 720p is enough for most frames.
  - Tiling is needed only for far riders in ultra-wide, head-on framing.
  - People waiting in the water at the back entrance are about 45–55 px tall, the same size as far riders. Size can't separate them; position and stance must.
- **Camera position:** left 45°, right 45° and head-on all occur. The head-on view shows the whole wave face, with waiting riders on both side decks right next to the wave.
- **Camera shifts:** none in any of the three sessions. Matching frames 5 minutes apart moved under 0.5% of frame width.
  - The matcher found 570 to 2,080 matching background points per pair, even at night under LED lighting, which supports the shift-detection design.
  - The bump test case must still be staged.
- **More than one person on the wave:** the first minutes of `20241004.MP4` show a lesson.
  - An instructor stands in the water holding a beginner by a pole while another pair practises behind them.
  - Separately, people often stand in the flat water at the back entrance while someone rides.
- **People near the camera:** people walk past close to the camera carrying boards, appearing large in frame. Pool-plane membership screens them out.
- **Daylight sun patches:** patches of sun drift across the water during the day. That makes water motion a weaker signal for proposing the zone, which supports making rider positions the primary signal.

## Open questions

All 19 questions are decided and folded into the doc. None remain open before Spec Kit.

| Question | Decision | Applied in |
| --- | --- | --- |
| Phone video format | Archive: iPhone footage as 720p30 H.264 SDR, about 1 h and 1.6 GB per file, one file per session. New recordings may be 4K HDR. | Sample footage findings, FR-1, evaluation set |
| Rider size range | About 30 to 320 px at 720p (4–45% of frame height); tile below about 60 px | Scale-invariant thresholds, risks |
| Camera side | Head-on to about 45° left or right; no logic may assume a side | Scene geometry, constitution, evaluation set |
| LED lighting | Colours usually fixed per session: one correction per session, with a per-frame fallback | Rider re-ID, risks |
| HDR in exports | Keep HDR in every clip and compilation | FR-14, risks |
| Hardware | Windows laptop with a small GPU | Constraints, FR-21, processing-time target |
| Riders | Up to 10 per session; rotation usual but not fixed | FR-16; turn order is a soft prior |
| Falls | Minimum ride length 10 s by default, set before processing | On/off-wave logic, FR-11 |
| Clip padding | 1 s before, 1.5 s after | FR-11 |
| Camera shifts | Apply re-mapped zones automatically | FR-6 |
| Interface | Desktop app | FR-21, roadmap P3 |
| Compilation | Hard cuts, with overlays | FR-19 |
| Sharing and consent | Compilations are not shared with other riders | Constraints |
| Riders across sessions | Not for now | Non-goals (F4) |
| Labelling budget | Yes: 5 sessions, including a staged bump | Evaluation set |
| Long term | Personal tool for now | Constraints |
| Lessons | Clip lesson stretches as the beginner's rides and flag them "lesson" in review | On/off-wave logic, FR-12, FR-13, risks |
| Originals or exports | Either; metadata is a hint, never required | FR-1, FR-2, FR-14, assumptions, risks |

## Changelog

| Version | Area | Change |
| --- | --- | --- |
| v0.5 | Lessons (FR-12, FR-13) | Lesson stretches clipped as the beginner's rides, with a "lesson" flag in rides.json and the review UI (was proposed only) |
| v0.5 | Input files (FR-1, FR-2, FR-14) | Accepts phone originals and exports. Metadata is used as a hint, never required. Re-encoded Dolby Vision clips keep the HLG base layer; only stream-copy keeps its dynamic metadata. |
| v0.5 | Open questions and effort | All 19 questions decided; none remain. Effort unchanged at 9 to 13 weeks. |
| v0.4 | Sample footage | New section with format, camera position, light and rider sizes for three archive sessions |
| v0.4 | Format (FR-1) | Adds 720p30 H.264 SDR, the archive format (was 1080p to 4K) |
| v0.4 | Camera angle | Head-on to 45° left or right (was 45° left or right only) |
| v0.4 | Rider size | Measured 30 to 320 px at 720p; tiled inference below about 60 px (was untested) |
| v0.4 | Lessons | New exception to the one-rider rule: only the person standing on a board counts as the rider, and lesson stretches are flagged; new risk and evaluation case |
| v0.4 | Evaluation set | Names the actual sessions: `20241004.MP4`, `IMG_3106.MP4`, `20250326_1.MP4`, the 12 Oct session, and a new staged bump session held out from tuning |
| v0.4 | Effort | Unchanged at 9 to 13 weeks. Lesson handling is small, and 720p archive footage makes P1 tuning cheaper. |
| v0.3 | Camera side | Supports the camera to the left or right of the wave: corners ordered by role, no assumed direction, both orientations tried, and both sides in the evaluation set (was left only) |
| v0.3 | LED colour correction | One correction per session (per camera epoch), with a per-frame fallback if the colour drifts (was per frame) |
| v0.3 | HDR export (FR-14) | HDR kept in every clip and compilation; SDR conversion dropped; overlays rendered at HDR reference white (was HDR by default, SDR optional) |
| v0.3 | Effort | Unchanged: these decisions fit inside the existing P1, P2 and P3 estimates |
| v0.2 | Zone setup (FR-4, FR-5) | Adds the deck/water boundary, the entrance and side areas, and four corners for pool-plane coordinates (was a polygon only) |
| v0.2 | On/off-wave logic (FR-7 to FR-10) | New per-frame state machine, back-dated starts, linking for acid drops, and boundary refinement at full frame rate (was zone membership plus movement) |
| v0.2 | Rider out of frame | New truncation flags and a 2 s frame-edge grace window |
| v0.2 | Scale | Uses the rider's current height and pool-plane coordinates (was the session's median rider height) |
| v0.2 | Shift re-maps (FR-6) | Applied silently with a timeline marker (was flagged for a glance) |
| v0.2 | Minimum ride and padding (FR-11) | 10 s default, set before processing; padding of 1 s and 1.5 s confirmed |
| v0.2 | HDR (FR-1, FR-2, FR-14) | Tone-mapped proxy for analysis; HDR kept on export (was SDR assumed) |
| v0.2 | Re-ID (FR-15, FR-16) | Colour normalisation, sharpest crops, up to 10 riders, turn order as a soft prior only |
| v0.2 | Overlays (FR-19) | Now a must-have (was a should-have) |
| v0.2 | Interface (FR-21) | Windows desktop app over a library with a CLI (was a CLI plus a local web UI) |
| v0.2 | Processing time | ≤ 30 min on the laptop, ≤ 90 min CPU-only (was ≤ 20 min with a GPU, ≤ 60 min CPU-only) |
| v0.2 | Evaluation set | The night LED HDR session replaces the generic lighting-change session; new tagged edge cases |
| v0.2 | Effort | P1 4 to 5 weeks (was 3 to 4); P3 2 to 3 weeks (was 1); MVP 9 to 13 weeks (was 7 to 10) |
| v0.2 | Spec Kit | Constitution gains "confirm late, start early" and the Windows and HDR rules; the 001 prompt is updated |
| v0.1 | Whole doc | First draft, including the phone-camera changes: a zone confirmed per upload, camera epochs and scale-invariant thresholds |
