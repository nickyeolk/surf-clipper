# Feature Specification: Rider Identification

**Feature Branch**: `002-rider-identification`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Clip out the videos of me: group a session's rides by rider, let me
name riders once, and play, review and export rides by rider. Builds on 001 (rides, review,
play-all and one-video export). PRD: roadmap P2 'Riders (002)': clustering, naming, review queue;
human-in-the-loop steps 3-6; rider re-ID under changing zoom and lighting."

## Context

Feature 001 finds every ride in a session and lets the user review, play and export them. To get
"just my rides" today the user must watch every ride and delete everyone else's. This feature
groups rides by the person riding, so the user names each rider once and then works with one
rider's rides: play them back to back, export them as clips or as one video.

Within a session, riders take turns on one wave; usually 3-15 people share an hour. Their
appearance (wetsuit or boardshorts, rash vest colour, helmet, board colour and shape, build)
mostly stays the same within the session but differs between sessions, and footage ranges from
close, blurred riders to small far riders at 0.5x zoom, in daylight or coloured LED light.

## Clarifications

### Session 2026-10-16

- Q: Should rider names carry over between sessions? → A: No, per session only; nothing about
  riders is kept between sessions (FR-009).
- Q: What must the tool sort out in each session? → A: Everyone is grouped; naming is optional
  (e.g. only "me"); unnamed groups are usable riders (FR-010).
- Q: If only some riders are named, which rides does the review queue show? → A: Only rides that
  might belong to a named rider; uncertainty between unnamed riders is never queued (FR-005).
- Q: Which sessions get rider labels for measuring accuracy? → A: Every ride's rider on all five
  labelled sessions of 001 (about 400 rides), picked from the tool's proposed groups (FR-014).
- Q: Should rides split by the rider leaving the frame be joined? → A: Automatically when both
  halves are confidently the same rider and the gap at the frame edge is short; otherwise a
  one-click suggestion (FR-011).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get my rides from a session (Priority: P1)

After a session's rides are found, the tool groups them by rider. The user sees the groups, each
shown with its clearest ride and a few stills, largest group first. They name the group that is
them (and any others they care about), merge groups that are the same person, split a group that
mixes two people, and mark staff or non-riders "ignore". Every ride then belongs to a rider, and
the user picks a rider to play all of that rider's rides back to back or export them as one
video.

**Why this priority**: it is the reason for the feature: "clip out the videos of me" without
watching and deleting everyone else's rides.

**Independent Test**: on a labelled session, name the user's own group (plus at most a few
merges/splits), then play and export that rider's rides; compare the result with the hand-labelled
rider of each ride.

**Acceptance Scenarios**:

1. **Given** a session with rides found, **When** grouping finishes, **Then** every ride (not
   short attempts) is in exactly one group, and each group shows its clearest ride, a few stills
   and its number of rides.
2. **Given** the groups, **When** the user names a group, **Then** all its rides carry that name
   and the group is listed under that name.
3. **Given** two groups that are the same person (e.g. a hood taken off mid-session), **When** the
   user marks one "same as" the other, **Then** they become one rider.
4. **Given** a group that mixes two people, **When** the user marks it "mixed", **Then** it is split
   in two and both halves are shown for naming.
5. **Given** a named rider, **When** the user chooses "play all" or "export as one video" for that
   rider, **Then** only that rider's rides are played or exported, in time order.

---

### User Story 2 - Fix uncertain assignments quickly (Priority: P2)

Each ride is assigned to the most similar named rider with a confidence. Rides the tool is unsure
about are listed first in a review queue. The user confirms or reassigns each with one action;
every answer is used to improve the remaining uncertain rides, so the queue shrinks faster than
one ride per answer.

**Why this priority**: grouping will not be perfect on blurred, far or LED-lit rides; a short
targeted queue is what makes the result trustworthy without rewatching everything.

**Independent Test**: on a labelled session, count the corrections needed to make every ride's
rider right, working the queue lowest confidence first.

**Acceptance Scenarios**:

1. **Given** assigned rides and at least one named rider, **When** the user opens the queue,
   **Then** the rides that might or might not belong to a named rider (below the confidence
   threshold) are listed lowest confidence first, each playable with that rider's stills beside
   it; rides only in doubt between unnamed riders are not listed.
2. **Given** a queued ride, **When** the user confirms or reassigns it, **Then** it becomes a fixed
   assignment and the remaining assignments and confidences are recomputed.
3. **Given** the user stops early, **When** they export, **Then** unconfirmed rides keep their best
   guess and are marked as unconfirmed.

---

### User Story 3 - Rider labels survive changes (Priority: P2)

Names, merges, splits, ignores and per-ride confirmations are the user's corrections. They are
kept when rides are edited (trimmed, split, merged, added), when ride finding is re-run with other
settings and when the zone is changed.

**Why this priority**: constitution VI: the user's minutes of review must never be lost or
repeated.

**Independent Test**: name riders and confirm some rides, re-run ride finding with another minimum
length, and check every label is still attached to the same ride.

**Acceptance Scenarios**:

1. **Given** named riders and confirmed rides, **When** ride finding is re-run, **Then** each ride
   that still exists (matched by time overlap) keeps its rider, and newly found rides are assigned
   automatically.
2. **Given** a ride assigned to a rider, **When** the user splits it, **Then** both parts keep the
   rider; **When** they merge two rides of different riders, **Then** the merged ride is queued for
   review.

---

### User Story 4 - Per-rider export and session manifest (Priority: P3)

The user exports one folder of clips per rider (or one video per rider) and a session manifest
listing every ride with its times, rider and confidence, in JSON and CSV.

**Why this priority**: useful for sharing a rider's clips with that person and for keeping a
record, but "my rides" (US1) delivers most of the value.

**Independent Test**: export a session with three named riders and check the folders, videos and
manifest against the ride list.

**Acceptance Scenarios**:

1. **Given** named riders, **When** the user exports per rider, **Then** each named rider gets a
   folder of their clips (or one video), named after the rider, and ignored rides are left out.
2. **Given** a session, **When** the manifest is exported, **Then** it lists every ride with id,
   start, end, rider (or "unassigned"/"ignored"), confidence and clip file.

---

### Edge Cases

- **Clothing or board change mid-session** (hood off, top on, board swap): the rider splits into
  two groups; the user merges them with "same as".
- **Two riders who look alike** (same club rash vests, rental wetsuits): one mixed group; the user
  splits it; turn order helps separate them.
- **Lessons**: a lesson ride contains several people (001 merges a lesson into one ride). Lesson
  rides are kept in a separate "Lesson" group rather than assigned to one person.
- **Rides split by leaving the frame** (001's known limitation): two consecutive rides by the same
  rider separated by a short gap at the frame edge are joined automatically when confident,
  otherwise offered as a one-click join (FR-011).
- **Very few frames of the rider** (blurred, far, partly out of frame): low confidence; the ride
  goes to the queue instead of being guessed confidently.
- **Coloured LED lighting** at night, and lighting changes within a session (dusk, floodlights):
  colour is less reliable; rides near a lighting change go to the queue.
- **Only one rider** in the session: one group; naming it labels every ride.
- **Staff, instructors, people walking past**: marked "ignore"; their rides are left out of
  exports.
- **Rides added by hand** in review (no tracked person): assigned from the frames of their time
  span if a person is found there, otherwise unassigned and queued.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST group a session's rides by the person riding them, using only that
  person's appearance in the ride (clothing, board, build and colours) and the session's turn
  order as a soft hint. Face recognition MUST NOT be used.
- **FR-002**: System MUST show each group with its clearest ride (least blurred, largest), a few
  stills from different rides, and its number of rides, largest group first.
- **FR-003**: Users MUST be able to name a group, mark it "same as" another group, mark it
  "mixed" (split into two, both shown again), and mark it "ignore".
- **FR-004**: System MUST assign every ride to the most similar named rider, with a confidence
  that reflects the margin to the second most similar rider.
- **FR-005**: System MUST list in a review queue, lowest confidence first, the rides whose
  assignment to or away from a *named* rider is below a configurable confidence threshold (e.g.
  with only "me" named: rides that might or might not be the user's); uncertainty between unnamed
  riders MUST NOT be queued. Users MUST be able to confirm or reassign each with one action, and
  every answer MUST be applied as a fixed assignment before the remaining rides are re-assigned.
- **FR-006**: Rider names, merges, splits, ignores and confirmations MUST be stored as user edits
  and survive ride edits, re-runs (rides re-matched by time overlap) and zone changes; re-runs MUST
  never overwrite them.
- **FR-007**: The Review screen MUST let the user filter rides by rider and play all of a rider's
  rides back to back or export them as clips or as one video.
- **FR-008**: System MUST export per-rider clip folders or videos, and a session manifest (JSON
  and CSV) with ride id, start, end, rider, confidence, confirmed or not, and clip file.
- **FR-009**: Appearance information and rider names MUST live within one session only and MUST
  NOT be stored or compared across sessions; the user names riders afresh in each session.
- **FR-010**: System MUST group every rider in the session; naming is optional. Unnamed groups
  are riders too (shown as "Rider 1", "Rider 2", … largest first) and can be played and exported
  like named ones. Rides are assigned among all groups, named or not, except ignored ones.
- **FR-011**: Two consecutive rides by the same rider separated by a short gap where the rider
  left and re-entered at a frame edge (rides split by leaving the frame) MUST be joined
  automatically when both halves are assigned to that rider with high confidence and the gap is
  within a configurable limit; otherwise the system MUST offer the join as a one-click suggestion.
  Automatic joins are recorded like user merges, so they can be undone, and are not repeated after
  an undo.
- **FR-012**: Lesson rides MUST be grouped as "Lesson" and not assigned to a single rider unless
  the user does so.
- **FR-013**: Grouping MUST use the stored analysis of 001 (no second pass of person detection)
  and MUST run automatically after rides are found; changes after naming (queue answers, merges)
  MUST update assignments within a few seconds.
- **FR-014**: Users MUST be able to record the true rider of every ride on evaluation sessions
  (rider labels), quickly, by accepting or correcting the tool's proposed groups, so that rider
  assignment can be measured (constitution II). Rider labels are evaluation data: they never
  change the session's rides or rider edits.
- **FR-015**: All thresholds (confidence threshold, number of stills, merge-suggestion gap) MUST
  be configurable.

### Key Entities

- **Rider**: a person in one session, with a user-given name or "ignore"; owns rides.
- **Group (candidate rider)**: the tool's proposal of rides by one person, before or after
  naming; can be merged into another or split.
- **Assignment**: a ride's rider, confidence and whether the user confirmed it.
- **Rider edit**: a name, same-as, mixed, ignore, confirm or reassign action by the user; a hard
  constraint.
- **Manifest**: the per-session list of rides with riders and clip files.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Straight after naming (before the review queue), at least 85% of rides are in the
  group of their true rider (every ride, named riders or not), on each labelled evaluation session
  (including night LED and 0.5x).
- **SC-002**: At most 10 corrections per session are needed to make every ride of the riders the
  user named exactly right (none of theirs missing, none of anyone else's included).
- **SC-003**: Naming the riders and working the queue takes the user at most 3 minutes per hour
  of footage.
- **SC-004**: From "rides found" to playing or exporting only the user's rides takes under
  1 minute when the user's group is correct.
- **SC-005**: 100% of rider edits survive a re-run of ride finding with different settings (for
  rides that still exist).
- **SC-006**: Grouping a 1 h session takes at most 5 minutes on the laptop, after rides are
  found.

## Assumptions

- Rides come from 001 (detected and reviewed); short attempts are not grouped unless kept as rides.
- Evaluation: the user labels the rider of every ride on the five labelled sessions of 001 (about
  80 rides each, picking from groups); PXL_20261014_100546073 stays held out from tuning.
- Exports reuse 001's clip export and one-video join; HDR is kept as in 001.
- Riders can change position in the turn order; turn order is a hint, never a rule.
- Cross-session identity by appearance is out of scope (constitution I and XI); the PRD says
  remembering riders across sessions is not wanted for now.
- The browser UI from 001 is extended; the user works on the laptop.
