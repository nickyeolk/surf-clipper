# Feature Specification: Ride Analysis

**Feature Branch**: `004-ride-analysis`

**Created**: 2026-10-17

**Status**: Draft (rescoped 2026-10-17)

**Input**: User description: "Analyse my rides so I can improve my surfing, in flow (aesthetics)
and tricks." Rescoped after discussion: "If I see someone with great style, I can place it side
by side and try to understand how I can position my body better to do tricks or to match the
style" and "some indicator of how fancy a ride was so I can clip it." Builds on 001 (rides,
tracks), 002 (riders, names) and 003 (viewer, compilations).

## Context

A spike on the user's footage (2026-10-17, `scripts/spikes/ride_pose.py`) found 2D pose usable:
shoulders, hips, knees and ankles are found in 99-100% of frames for riders 85-360 px tall,
handheld 1080p and fixed 720p alike. A compress/extend signal follows bottom turns and trims;
falls are obvious. Limits: absolute joint angles from one camera are unreliable, and a rider's
size in the image changes 3x within a ride, so measures are ratios of the rider's own body.

Counting turns per ride describes a ride but does not tell the rider how to ride better, so the
feature is built around two things the user will act on: **comparing their body position with a
surfer whose style they like**, and **finding their best rides**. Turn and compression signals are
ingredients of both, not reports of their own.

## Clarifications

### Session 2026-10-17

- Q: Tricks in the first version? → A: The user tags trick moments; tags make attempts easy to
  find and compare. No automatic trick recognition yet.
- Q: Which riders are analysed? → A: Named riders only (in sessions), plus imported clips.
- Q: Comparison or best-rides score first? → A: Both, in this feature.
- Q: Where does the reference surfer's footage come from? → A: Both: a rider the user names in
  their own sessions, and video clips the user imports.
- Q: Fall comparison and session trends? → A: Dropped for now.
- Q: Evaluation labels? → A: The user stars their favourite rides (seconds per ride) instead of
  marking turns; the best-rides score is tuned to rank starred rides first.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Side by side with a stylish surfer (Priority: P1)

The user picks one of their rides (or a tagged trick attempt) and a reference: a ride of a
surfer they named in one of their sessions, or an imported clip. The two play side by side,
each cropped to the surfer, with skeletons drawn on. The user sets a sync point in each (e.g. the
bottom of the same turn, the take-off of a trick) and both play from there together, at 1x or
slowed down, frame-steppable. Under the videos, a few body measures for both, on one time axis:
how low (compression), torso lean, arm spread, stance width.

**Why this priority**: the most direct help for body positioning, style and tricks.

**Independent Test**: compare a ride of the user with a reference ride; set sync points; both
play in step with skeletons and both measure curves aligned at the sync point.

**Acceptance Scenarios**:

1. **Given** an analysed ride of the user and an analysed reference, **When** the user opens the
   comparison and sets a sync point in each, **Then** both play together from the sync points,
   at the same speed, and frame steps move both by one frame.
2. **Given** the comparison, **When** it plays, **Then** each surfer's skeleton follows them and
   the measure curves of both are drawn on one time axis aligned at the sync point.
3. **Given** a sync point at a turn in one ride, **When** the user asks to align on the nearest
   turn in the other, **Then** the other's sync point snaps to its nearest detected turn.

---

### User Story 2 - Bring in a reference clip (Priority: P1)

The user imports a video of a surfer whose style they like (from the footage folder: a pro clip
they downloaded, a friend's phone video). The tool finds the surfer, runs the same analysis and
offers it as a reference. If several people are in it, the user picks which one.

**Why this priority**: the best reference is often not in the user's own sessions.

**Independent Test**: import a 30-60 s clip of one surfer; it appears as a reference with
skeletons; import one with two people and pick the second.

**Acceptance Scenarios**:

1. **Given** a clip in the footage folder, **When** the user imports it as a reference, **Then**
   within a few minutes it is analysed and listed as a reference with its surfer.
2. **Given** a clip with several people, **When** imported, **Then** the user picks the surfer by
   clicking them, and the analysis follows that person.

---

### User Story 3 - Find my best rides (Priority: P2)

Each of the user's rides gets a score of how good it was (style, flow, commitment), and the
user's rides can be sorted by it, with the top rides one click from a compilation. The user stars
rides they love; the score learns from the stars which rides they consider best.

**Why this priority**: finding rides worth clipping and seeing which attempts were good.

**Independent Test**: on sessions where the user starred rides, starred rides rank near the top.

**Acceptance Scenarios**:

1. **Given** analysed rides, **When** the user sorts by score, **Then** the rides are listed best
   first, with the score and what it was made of (e.g. "long, deep turns, steady rhythm, no fall").
2. **Given** starred rides, **When** the score is refreshed, **Then** starred rides rank higher
   than they did before, without the user ordering every ride.
3. **Given** the top rides, **When** the user picks "compilation of these", **Then** 003's
   captioned compilation is made of exactly those rides.

---

### User Story 4 - Tag tricks (Priority: P3)

While watching, the user marks a moment as a trick with a name they choose ("floater", "360").
Tags are listed per session and across sessions, play back to back, and are one click from the
comparison (e.g. "my 360 vs the reference 360").

**Why this priority**: makes practice attempts easy to find and compare.

**Independent Test**: tag 3 tricks of 2 kinds; list them by kind; open one in the comparison.

**Acceptance Scenarios**:

1. **Given** a ride in the player, **When** the user tags the current moment as "floater",
   **Then** it appears in the trick list and plays from a second before it.
2. **Given** a tag, **When** the user opens it in the comparison, **Then** its sync point is the
   tagged moment.

---

### Edge Cases

- The surfer is hidden by spray or leaves the frame: those moments show no skeleton and gaps in
  the curves rather than guesses.
- Two people overlap (changeover, a crowded reference clip): the skeleton stays on the chosen
  person; overlapping moments are marked unclear.
- Reference and user filmed from different angles or distances: measures are body ratios, so
  they compare; the view note says "as seen by each camera" for lean.
- Mirror stance (regular vs goofy, or a left vs right turn): the comparison can mirror one video.
- Different frame rates: both play in real time; frame steps follow each clip's own frames.
- A ride edited after analysis: its analysis is refreshed for the new span only.
- Imported clip in HDR or portrait: handled as sessions are.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST estimate body keypoints through each ride of named riders and through
  imported reference clips, from the full-resolution source (default 15 per second).
- **FR-002**: Measures MUST be ratios of the surfer's own body (compression, arm spread, stance
  width) or angles in the image labelled as camera-relative (lean); never absolute pixel sizes.
- **FR-003**: Users MUST be able to play two analysed clips side by side, each cropped to its
  surfer, with skeletons, a sync point per clip, shared play/pause/speed/frame-step, and an
  optional mirror of either clip.
- **FR-004**: The comparison MUST show the body measures of both clips on one time axis aligned
  at the sync points.
- **FR-005**: The comparison MUST offer snapping a sync point to the nearest detected turn or to a
  trick tag.
- **FR-006**: Users MUST be able to import a video from the footage folder as a reference clip,
  pick the surfer when several people are visible, and have it analysed like a ride.
- **FR-007**: System MUST compute a score per analysed ride from its measures (length, ending,
  depth and number of compressions, rhythm regularity, tagged tricks) and explain it in words.
- **FR-008**: Users MUST be able to star and unstar rides; the score's weights MUST be fitted to
  the user's stars (across their sessions) and fall back to defaults with too few stars.
- **FR-009**: Users MUST be able to sort their rides by score and make a 003 compilation of
  chosen rides.
- **FR-010**: Users MUST be able to tag a moment as a trick with a free-text name, list and play
  tags per session and across sessions, delete tags, and open a tag in the comparison.
- **FR-011**: Analysis MUST run only for named riders and imported references; nothing about
  other people is stored.
- **FR-012**: Analysis MUST be cached per ride (and per reference clip) and recomputed only when
  the span, the surfer choice or the settings change.
- **FR-013**: Thresholds and score defaults MUST be configurable.

### Key Entities

- **Ride analysis**: per ride or reference clip: keypoints over time, measures, turns, ending,
  score and its parts.
- **Reference clip**: an imported video, the chosen surfer (track), its analysis.
- **Star**: a ride the user loves (an edit, like other user corrections).
- **Trick tag**: ride or clip, time, name.
- **Comparison**: two clips and their sync points (may be saved to reopen).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the comparison, both clips stay in sync within one frame over 30 s of playback
  at 1x and 0.25x, and the skeletons keep up at 1x on the laptop.
- **SC-002**: With at least 10 starred rides over 2 sessions, the median starred ride ranks in the
  top 25% of its session by score (held-out session included in the report, not in fitting).
- **SC-003**: Importing a 60 s reference clip to "ready to compare" takes at most 3 minutes.
- **SC-004**: Analysing a session's named-rider rides takes at most 10 minutes per hour of footage
  with about 30 such rides.
- **SC-005**: From picking two clips to watching them synced takes the user at most 1 minute.

## Future directions (not in this feature)

- Automatic trick recognition, trained on the user's trick tags.
- Automatic sync on matching movement (aligning two turns by their compression curves).
- Fall comparison and session trends (dropped from this feature 2026-10-17).

## Assumptions

- References are for the user's own study; imported clips stay on the laptop.
- One camera per clip; no multi-camera 3D.
- Trick names are free text; no fixed list.
- Body data (keypoints) stays in the session or reference folder; only named riders and
  references are analysed.
