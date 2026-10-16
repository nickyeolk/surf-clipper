# Feature Specification: Ride Analysis

**Feature Branch**: `004-ride-analysis`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Analyse my rides so I can improve my surfing, in flow (aesthetics)
and tricks. Useful questions: what am I doing differently on rides where I fall, and how much of
each ride am I actually turning or pumping." Builds on 001 (rides, tracks, wave zone), 002
(riders, names) and 003 (viewer, compilations).

## Context

A spike on the user's footage (2026-10-17, `scripts/spikes/ride_pose.py`) found 2D pose usable:
shoulders, hips, knees and ankles are found in 99-100% of frames for riders 85-360 px tall,
both on the handheld 1080p session and the fixed 720p camera. A compress/extend signal follows
the rider's bottom turns and trims, and falls are obvious. Two limits shape this feature:
absolute joint angles from one camera are unreliable (viewpoint, wave-face slope, legs swapping
in a deep crouch), and a rider's size in the image changes 3x within a ride with distance from
the camera, so every measure must be relative to the rider's own body, not to pixels.

## Clarifications

### Session 2026-10-17

- Q: Tricks in the first version? → A: The user tags trick moments; they are listed and become
  examples for a later detector. No automatic trick recognition yet.
- Q: Compare across sessions? → A: Yes, pooled by the name the user gives in each session
  (e.g. "me"), never by matching appearance across sessions.
- Q: Which riders are analysed? → A: Named riders only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See how I move on each ride (Priority: P1)

The user plays one of their rides and sees their skeleton drawn over it (toggle) and, under the
player, a timeline of how compressed or extended they are, with turns and pumps marked. A short
summary says how long the ride was, how many turns and pumps, how regular the rhythm was and how
the ride ended.

**Why this priority**: it is what everything else builds on, and seeing the rhythm next to the
video is useful on its own for "flow".

**Independent Test**: analyse a named rider's rides in one session; on 5 rides the user has
marked turns and endings, the marked turns and endings match within the success criteria.

**Acceptance Scenarios**:

1. **Given** a session with a named rider, **When** analysis has run, **Then** each of that
   rider's rides has a compression timeline, turns and pumps marked, and a summary.
2. **Given** a ride in the player, **When** the user turns the skeleton on, **Then** the
   skeleton follows the rider at full frame rate without visible lag.
3. **Given** a ride that ends in a fall, **When** analysed, **Then** its ending is "fall";
   a ride ending by stepping or kicking off is "exit".

---

### User Story 2 - What do I do differently before I fall? (Priority: P2)

For a named rider, the tool compares the seconds before each fall with the same stretch of rides
that ended cleanly: compression depth, rhythm, time since the last turn, position on the wave,
and shows the falls side by side so the user can watch them in a row.

**Why this priority**: the user's own question; turns a pile of rides into a lesson.

**Independent Test**: on a session with at least 3 falls and 3 clean exits, the comparison lists
every fall and every clean ride correctly and plays the pre-fall moments back to back.

**Acceptance Scenarios**:

1. **Given** a session with falls and clean exits, **When** the user opens the comparison,
   **Then** they see each measure for "before falls" vs "before clean exits", and can play all
   pre-fall moments in a row.

---

### User Story 3 - Turning, pumping or just standing? (Priority: P2)

Per ride and per session, the share of riding time spent turning, pumping and trimming
(standing without much movement), and how that changes across sessions for the same name.

**Why this priority**: the user's second question; the session trend is how they see improvement.

**Independent Test**: the shares on the user's marked rides match the marked time within the
success criteria; a second session with the same name shows up in the trend.

**Acceptance Scenarios**:

1. **Given** analysed rides, **When** the user opens a session report, **Then** it shows the
   turning/pumping/trimming shares per ride and for the session.
2. **Given** two sessions where the user named themselves "me", **When** they open the trend,
   **Then** each session is one point per measure, in date order.

---

### User Story 4 - Tag tricks (Priority: P3)

While watching, the user marks a moment as a trick with a name they choose (e.g. "floater",
"360", "shove-it"). Tagged tricks are listed per session and across sessions by name and can be
played back to back.

**Why this priority**: builds the examples a future trick detector needs; useful now as a library.

**Independent Test**: tag 3 tricks of 2 kinds; the list shows them by kind and plays each.

**Acceptance Scenarios**:

1. **Given** a ride in the player, **When** the user tags the current moment as "floater",
   **Then** it appears in the trick list with its time and plays from a second before it.
2. **Given** tags in two sessions under the same rider name, **When** the user filters by
   "floater", **Then** both sessions' floaters are listed.

---

### Edge Cases

- The rider is partly hidden by spray or leaves the frame: those moments are marked as unclear
  and not counted, rather than guessed.
- Another person overlaps the rider (changeover, staff): the analysed skeleton stays on the
  tracked rider.
- Joined rides (002): analysed as one ride.
- Very short rides (under the minimum length): not analysed.
- A ride edited after analysis (trim, split): its analysis is refreshed for the new span only.
- Portrait or handheld footage where the camera follows the rider: measures stay relative to
  the rider's body, so zoom does not change them.
- A renamed rider: their analysis and tags follow the rides, not the old name.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST estimate the rider's body keypoints through each ride of named riders,
  from the full-resolution source, at a configurable rate (default 15 per second).
- **FR-002**: Measures MUST be relative to the rider's own body (proportions), never absolute
  pixel sizes or absolute joint angles.
- **FR-003**: System MUST derive a compression signal per ride and detect turns and pumps from it
  and from the rider's movement across the wave.
- **FR-004**: System MUST classify how each ride ended: fall, exit (stepped or kicked off), or
  unclear.
- **FR-005**: The player MUST be able to draw the skeleton over the ride and show the compression
  timeline with turns, pumps and the ending marked.
- **FR-006**: System MUST compare the seconds before falls with the same stretch before clean
  exits for a rider in a session, and play the pre-fall moments back to back.
- **FR-007**: System MUST report turning, pumping and trimming shares per ride and per session,
  and a trend across sessions for riders with the same user-given name.
- **FR-008**: Users MUST be able to tag a moment as a trick with a free-text name, list and play
  tags per session and across sessions by name, and delete tags.
- **FR-009**: Moments where the body is not seen well enough MUST be marked unclear and left out
  of measures.
- **FR-010**: Analysis MUST run only for named riders; nothing about other people is stored.
- **FR-011**: Analysis MUST be cached per ride and recomputed only when the ride's span, the
  rider or the settings change.
- **FR-012**: Users MUST be able to correct an ending (fall/exit) and add or remove a turn mark;
  corrections are kept like other edits and win over the automatic result.
- **FR-013**: Thresholds (rates, signal smoothing, turn and pump detection, unclear limits) MUST
  be configurable.

### Key Entities

- **Ride analysis**: per ride: keypoints over time, compression signal, turns, pumps, ending,
  unclear spans, summary measures; settings it was made with.
- **Trick tag**: session, ride, time, name; created by the user.
- **Rider trend**: per user-given name, per session: the summary measures.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the user's marked rides (at least 10 rides over 2 sessions, one handheld and one
  fixed camera), at least 80% of marked turns are detected within 0.5 s, with at most 20% of
  detected turns unmarked.
- **SC-002**: Ride endings are classified correctly for at least 90% of the marked rides.
- **SC-003**: Turning/pumping/trimming shares per ride are within 15 percentage points of the
  marked shares on average.
- **SC-004**: Analysing a session's named-rider rides takes at most 10 minutes per hour of
  footage containing about 30 rides of that rider.
- **SC-005**: The skeleton overlay keeps up with playback at 1x on the laptop.
- **SC-006**: From "rides named" to "see the fall comparison" takes the user at most 2 minutes.

## Assumptions

- Evaluation labels: the user marks turns and endings on at least 10 of their rides (about 5
  minutes per ride) before thresholds are tuned; one session is held out from tuning.
- One camera per session; no multi-camera 3D.
- "Pump" = a compress/extend cycle without a direction change; "turn" = a direction change
  across the wave, usually with a compression; definitions are refined with the user's labels.
- Trick names are free text; no fixed list.
- Body data (keypoints) stays in the session folder like other session data; it is about named
  riders only.
