# Feature Specification: Ride Detection and Clipping

**Feature Branch**: `001-ride-detection-clipping`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Feature 001: ride detection and clipping for phone-filmed standing-wave sessions." (full prompt from `docs/prd.md` v0.5, section "First specify prompt (feature 001)")

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get every ride from a session video (Priority: P1)

I give the tool an hour-long session video and get back a list of rides (start, end, confidence)
and one clip per ride, without scrubbing through waiting time, changeovers or people sitting at
the entrance.

**Why this priority**: This is the core value of the whole product; every later feature (rider
labelling, compilation) consumes the ride list.

**Independent Test**: Run a labelled evaluation session through the tool with a zone already
confirmed, compare the ride list to the hand labels, and play a few clips.

**Acceptance Scenarios**:

1. **Given** a confirmed zone and a session with several riders taking turns, **When** processing
   finishes, **Then** each ride of at least the minimum length appears once in the ride list with
   start, end and confidence, and has its own clip padded 1 s before and 1.5 s after.
2. **Given** a person sitting at the entrance for several minutes whose image overlaps the wave
   zone, **When** processing finishes, **Then** no ride is produced for them.
3. **Given** a rider who acid-drops from the deck edge, **When** processing finishes, **Then** the
   ride starts at the jump, not when the rider is first seen steady on the wave.
4. **Given** a fall or attempt shorter than the minimum length, **When** processing finishes,
   **Then** it is not in the ride list or clips but is listed as a short attempt.
5. **Given** a changeover where the next rider drops in while the previous one falls, **When**
   processing finishes, **Then** both rides are reported, overlapping in time.
6. **Given** a coached lesson with an instructor in the water holding a beginner, **When**
   processing finishes, **Then** only the beginner on the board produces rides, and those rides are
   flagged "lesson".

---

### User Story 2 - Confirm the wave zone on one keyframe (Priority: P1)

For each upload the tool proposes the wave-zone corners, the deck/water boundary, and the entrance
and side waiting areas on a keyframe. I accept with one action, drag points to adjust, or draw
them by hand when the proposal is poor.

**Why this priority**: Framing differs every session; ride detection cannot be correct without a
correct zone, so this is a prerequisite of Story 1.

**Independent Test**: Load each evaluation session, time how long it takes to accept or fix the
proposal, and compare it with the hand-marked zone.

**Acceptance Scenarios**:

1. **Given** a new session video, **When** the first analysis pass completes, **Then** a keyframe
   is shown with proposed zone corners, deck/water boundary, and entrance and side areas.
2. **Given** a reasonable proposal, **When** I accept it, **Then** it becomes a confirmed zone used
   for that camera epoch, and the step takes under 30 s.
3. **Given** a low-confidence proposal (too few detections, no clear cluster), **When** the keyframe
   is shown, **Then** I am told the proposal is unreliable and can draw the zone by hand.
4. **Given** the camera is filmed from the left, the right or head-on, **When** the proposal is
   made, **Then** it is equally usable in each case (no side is assumed).

---

### User Story 3 - Survive camera bumps and frame-edge exits (Priority: P2)

When the phone gets bumped mid-session, the tool notices, re-maps the zone silently when it can
(with a marker on the timeline), and asks me to re-confirm only when it can't. A ride that spans a
bump, or briefly leaves through the frame edge, stays one ride.

**Why this priority**: Bumps happen a few times per session; an undetected bump silently loses
every later ride.

**Independent Test**: Run the staged bump session and synthetic shift clips; check every shift is
detected, re-maps are marked, unreliable ones prompt, and spanning rides are not split.

**Acceptance Scenarios**:

1. **Given** a sudden camera jump with enough static background visible, **When** processing runs,
   **Then** a new camera epoch starts, the zone is re-mapped automatically, and a marker appears on
   the review timeline.
2. **Given** a large change (e.g. a zoom switch) or too little matching background, **When**
   processing runs, **Then** I am asked to re-confirm the zone on the new epoch's first keyframe.
3. **Given** slow drift that accumulates past the threshold, **When** processing runs, **Then** a
   new epoch is started as for a jump.
4. **Given** a ride that crosses an epoch boundary, **When** processing finishes, **Then** it is
   one ride.
5. **Given** a rider who leaves through a frame edge and returns through the same edge within the
   grace window (default 2 s), **When** processing finishes, **Then** it is one ride.

---

### User Story 4 - Review and correct rides (Priority: P2)

I skim the detected rides (lowest confidence first) with thumbnails, and trim, split, merge, delete
or add a missed ride. My edits survive any re-run.

**Why this priority**: Detection will not be perfect; fast correction gets the list to 100% and
keeps my hands-on time under 5 minutes.

**Independent Test**: Make each kind of edit on a processed session, change a setting and re-run,
and confirm every edit is still present.

**Acceptance Scenarios**:

1. **Given** a processed session, **When** I open review, **Then** rides are listed with thumbnails,
   confidence, any "lesson" flag, camera-shift markers and the short-attempt list.
2. **Given** a ride, **When** I trim, split, merge with a neighbour, or delete it, **Then** the ride
   list and clips reflect the change.
3. **Given** a missed ride, **When** I mark its start and end, **Then** it is added to the ride list.
4. **Given** edited rides and confirmed zones, **When** I re-run processing with different settings,
   **Then** none of my edits or confirmed zones is overwritten, and detection is not re-run just
   because I edited something.

---

### Edge Cases

- People standing in the flat water at the back entrance while someone rides (same size as far
  riders): never counted as riding unless standing on a board and moving along the wave.
- People walking past close to the camera carrying boards, appearing very large: not counted.
- Rider partly out of frame at the near edge: still counted as present; the truncated view is not
  used for size estimates.
- Feet hidden by whitewater: on-wave position is still determined (from the board or the rider's
  usual height).
- Night sessions under coloured LED lighting, and HDR recordings: analysis is not degraded by
  washed-out or tinted frames; clips keep the source's HDR.
- Heavy motion blur on close, fast rides: the ride is not broken into pieces.
- Far riders as small as about 30 px tall at 720p (0.5x, head-on): still detected.
- Frame rates of 30, 60 or 120 fps, including slightly variable frame rate: timing stays correct.
- Video longer than 1.5 h, or an unsupported format: rejected with a clear message before
  processing starts.
- No rides found at all (e.g. wrong zone): reported clearly, with a prompt to check the zone.

## Requirements *(mandatory)*

### Functional Requirements

**Input and analysis**

- **FR-001**: System MUST accept local MP4 or MOV phone video (H.264 or HEVC, 8-bit SDR or 10-bit
  HDR including HLG and Dolby Vision, 720p to 4K, 30–120 fps, up to 1.5 h), both phone originals
  and exports.
- **FR-002**: System MUST analyse a reduced, tone-mapped proxy of the video while keeping the
  original untouched for clip export. Lens, zoom and HDR metadata MAY be used as hints but MUST NOT
  be required.
- **FR-003**: System MUST never modify, move or overwrite the source video.

**Zone and scene geometry**

- **FR-004**: System MUST propose, per camera epoch, the four wave-zone corners, the deck/water
  boundary, and the entrance and side areas, primarily from where people persist and move on the
  wave.
- **FR-005**: Users MUST be able to accept the proposal in one action, adjust its points, or draw
  it by hand; a low-confidence proposal MUST be labelled as such.
- **FR-006**: System MUST measure positions, movement and region membership in normalised pool
  coordinates derived from the confirmed corners, using each person's feet point (estimated when
  hidden), never box overlap in the image.
- **FR-007**: System MUST NOT assume which side the camera, entrance or waiting areas are on, or
  which direction riders move; corners are identified by role (deck edge, wave ends).

**Camera epochs**

- **FR-008**: System MUST detect camera jumps and accumulated drift by matching static background
  (excluding water and people) and split the video into camera epochs.
- **FR-009**: System MUST re-map the confirmed zone into a new epoch automatically when the match is
  reliable, mark each re-map on the review timeline, and prompt for re-confirmation only when it is
  not.

**On/off-wave and rides**

- **FR-010**: System MUST give each tracked person a state over time (off, dropping in, on the
  wave) from feet position relative to the deck/water boundary, board contact, stance and sustained
  movement along the wave.
- **FR-011**: System MUST confirm a ride only after on-wave evidence holds for a confirmation
  window (default 1.5 s), then back-date its start to the boundary crossing or deck-edge departure.
- **FR-012**: System MUST link a person last seen at the deck edge to an on-wave track that appears
  shortly after nearby (default within 1 s), so acid-drop rides start at the jump.
- **FR-013**: System MUST keep people sitting or standing at the entrance or sides, and people in
  the water not riding a board, in the off state regardless of how long they stay.
- **FR-014**: During lessons, System MUST treat only the person standing on a board as the rider
  and flag those rides "lesson".
- **FR-015**: System MUST end a ride on its last on-wave frame (fall, exit to side or deck, or
  leaving the zone), allow changeover overlaps, and treat a same-edge frame-edge exit and return
  within the grace window (default 2 s) as one ride.
- **FR-016**: System MUST join a ride split by a camera-epoch boundary back into one ride.
- **FR-017**: System MUST refine each ride's start and end at the source's full frame rate.
- **FR-018**: System MUST drop rides shorter than the minimum length (default 10 s, set by the user
  before processing) from the ride list and clips, and list them as short attempts.

**Outputs and review**

- **FR-019**: System MUST write a ride list containing, per ride: ID, start and end (seconds and
  frames), confidence, camera epoch, state timeline, truncation flags and lesson flag.
- **FR-020**: System MUST export one clip per ride with 1 s of padding before and 1.5 s after,
  frame-accurate, at final quality: each clip MUST keep the source's dynamic range and colour
  metadata (SDR stays SDR; HLG and HDR10 stay as they are; Dolby Vision keeps its HLG base layer
  when re-encoded). Clips are exported on demand after review, not automatically after processing:
  one action exports all rides; on later exports only rides that are new or changed since their last
  export are re-encoded.
- **FR-021**: Users MUST be able to review rides with thumbnails, ordered lowest confidence first,
  and play, trim, split, merge, delete and add rides. Zone confirmation and ride review happen in a
  browser UI served by the local backend; this is the product's permanent UI, which later features
  extend. Playback MUST support stepping one frame forward or back and slow motion, so boundaries
  can be trimmed to the frame. Saving still images and the full-resolution ride viewer are out of
  scope for 001 (feature 003).
- **FR-022**: System MUST treat confirmed zones and edited rides as hard constraints that re-runs
  never overwrite.
- **FR-023**: System MUST cache each processing stage so that edits and setting changes downstream
  of detection do not force detection to run again.
- **FR-024**: All thresholds MUST be expressed in seconds, pool coordinates or rider heights (never
  raw pixels or frame counts) and MUST be configurable.
- **FR-025**: All processing MUST run locally with no network calls. The browser UI MUST be
  reachable only from this laptop; access from other devices is deferred to 003.
- **FR-026**: Review playback MUST stream video on demand rather than loading whole files into the
  browser, and MUST stay responsive for a 1 h session (see SC-009).

### Key Entities

- **Session**: one source video plus its processing settings (minimum ride length, padding,
  thresholds) and outputs.
- **Camera epoch**: a time span with a stable camera; owns a confirmed zone and records how it was
  confirmed (accepted, edited, drawn, auto re-mapped) and its re-map reliability.
- **Zone**: four role-ordered wave-zone corners, the deck/water boundary, and entrance and side
  areas, defining pool coordinates for one epoch.
- **Track**: one person followed over time, with per-moment state (off, dropping in, on the wave),
  feet point, truncation and board-contact evidence.
- **Ride**: a confirmed on-wave span of one track: ID, start/end, confidence, epoch(s), state
  timeline, flags (lesson, truncated, user-edited) and its clip.
- **Short attempt**: an on-wave span below the minimum length, listed but not clipped.
- **User edit**: a zone confirmation or ride change kept as a hard constraint across re-runs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

All targets must hold on **each** labelled evaluation session (including the 0.5x, bumped, night
HDR and held-out sessions), not only on average.

- **SC-001**: At least 95% of hand-labelled rides at or above the minimum length are found
  (matched at time overlap IoU ≥ 0.5).
- **SC-002**: At least 90% of detected rides match a hand-labelled ride.
- **SC-003**: Ride start and end errors are under 1 s at the 95th percentile and under 0.5 s at the
  median; acid-drop starts are reported separately.
- **SC-004**: Confirming or fixing the zone takes 30 s or less per camera epoch.
- **SC-005**: 100% of real and synthetic camera shifts larger than 2% of frame width are detected.
- **SC-006**: A 1 h video is ready for review in 30 min or less on the user's Windows laptop with a
  small GPU, and 90 min or less on CPU only. Clip export happens after review and is not included
  in this time.
- **SC-007**: No user edit or confirmed zone is lost across re-runs (0 regressions in a re-run test).
- **SC-008**: The user's total hands-on time for zone setup and ride review is 5 min or less per
  1 h session.
- **SC-009**: In review, jumping to any point in a 1 h session starts playback within 1 s, and
  stepping one frame forward or back within a ride shows the new frame within 0.2 s.

## Assumptions

- One rider is normally on the wave at a time; lessons are the stated exception.
- The camera is a phone on a stand, head-on to about 45° left or right, 1x or 0.5x zoom, with no
  panning or zooming during recording other than occasional bumps or re-positioning.
- The deck and entrance run along the back (far) edge of the pool as seen from the camera.
- One continuous file per session; multi-file sessions are out of scope.
- Everything the tool produces for a session (review copies, stage outputs, ride list, user edits,
  clips) is stored in a per-session folder under the project's `artifacts/` folder, never next to
  the source video. `artifacts/` is not version-controlled.
- The labelled evaluation set (PRD phase P0: five sessions plus synthetic shift clips) is built
  before or alongside this feature and is required to verify the success criteria.
- Pretrained person and board detection is sufficient; no custom model training.
- Rider identification (002), compilation, overlays, the full-resolution ride viewer with still
  capture, and packaging (003), manoeuvres, turn counting and pose analysis are out of scope. HDR-preserving per-ride clip export is in scope for
  001 and is reused by 003's compilation.

## Clarifications

### Session 2026-10-13

- Q: Does 001 deliver final-quality HDR-preserving per-ride clips, or preview clips only? → A:
  Final-quality clips that keep the source's HDR and colour metadata (FR-020).
- Q: What interface does 001 provide for zone confirmation and ride review? → A: A browser UI
  served by a local backend. Initially chosen as temporary; then adopted as the permanent
  architecture in place of a packaged desktop app (FR-021).
- Q: Are per-ride clips exported automatically after processing, or on demand after review? → A: On
  demand after review; only new or changed rides are re-encoded on later exports (FR-020, SC-006).
- Q: Does 001's review screen include the full-resolution ride viewer? → A: No. 001 has frame
  stepping and slow motion (needed for trimming); still capture and the full viewer come in 003
  (FR-021).
- Q: Is the browser UI reachable from other devices (phone, tablet)? → A: Laptop only until the
  basics work; phone access considered in 003 (FR-025).
