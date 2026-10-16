# Feature Specification: Compilations, Stills, Viewer and Packaging

**Feature Branch**: `003-compilation-viewer`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Feature 003 from the PRD (roadmap P3 'Export'): compiled videos
per rider with overlays (rider name, ride number, session time), stills and a full-quality viewer
(deferred here from 001), and packaging so the tool runs on the laptop without a developer.
Builds on 001 (rides, clips, one-video join) and 002 (riders, per-rider folders, manifest)."

## Context

001 and 002 already deliver final-quality clips (HDR kept), a per-rider folder and manifest, and
"export as one video" (clips joined end to end, no overlays). What is missing is the finished
product the user watches and keeps: a compilation that says who is riding and when, frames to
save as photos, a way to watch the full-quality result inside the tool, and a way to start the
tool on the laptop without a developer running commands.

## Clarifications

### Session 2026-10-16

- Q: How should the overlay appear? → A: At the start of each ride (first few seconds), burned in.
- Q: Still format for HDR sessions? → A: SDR JPEG (tone-mapped).
- Q: How should the tool start without a terminal? → A: A Windows desktop shortcut that starts
  the existing setup (WSL) quietly and opens the browser.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A finished compilation of my rides (Priority: P1)

The user picks a rider (usually themselves) and exports a compilation: all of that rider's
rides in time order, hard cuts between rides, each ride with an overlay showing the rider's
name, the ride number and the time in the session. The compilation keeps the source's quality
and HDR.

**Why this priority**: it is the PRD's main output ("my rides, quickly, for my own use") and the
must-have overlay requirement (FR-19).

**Independent Test**: export a compilation for a named rider on a labelled session and check
that it contains exactly that rider's rides in order, each with a correct overlay, at source
quality with HDR preserved.

**Acceptance Scenarios**:

1. **Given** a session with a named rider, **When** the user exports that rider's compilation,
   **Then** one video file contains every ride of that rider in time order with hard cuts.
2. **Given** the compilation, **When** it plays, **Then** each ride shows the rider's name, its
   number ("ride 3 of 12") and the session time it started, legible on a phone screen and not
   covering the rider.
3. **Given** an HDR session, **When** the compilation is exported, **Then** it stays HDR with the
   same transfer and colour as the clips, and the overlay is not washed out or overly bright.

---

### User Story 2 - Save a frame as a photo (Priority: P2)

While watching a ride, the user steps to the best frame and saves it as a full-resolution still.

**Why this priority**: the best moment of a ride is often worth keeping as a photo; deferred from
001 to this feature by the user.

**Independent Test**: step to a frame in the player, save the still, and compare it with the
source frame at that time (resolution, framing, colour).

**Acceptance Scenarios**:

1. **Given** a ride in the player, **When** the user saves a still at the current frame, **Then**
   an image of that exact frame at the source's full resolution is saved in the session's export
   folder and can be opened from the tool.

---

### User Story 3 - Watch the full-quality result in the tool (Priority: P2)

The user watches exported clips and compilations at full quality inside the tool, with frame
stepping and slow motion, instead of finding files on disk.

**Why this priority**: the review player uses a 720p preview copy; the user wants to see the
final result as it will be kept.

**Independent Test**: open an exported compilation in the viewer and step through it frame by
frame at full resolution.

**Acceptance Scenarios**:

1. **Given** exported clips and compilations, **When** the user opens the viewer, **Then** they
   are listed per rider and play at full resolution with frame stepping and 0.25x/0.5x.

---

### User Story 4 - Start the tool without a developer (Priority: P1)

The user starts the tool from Windows with one action, the browser opens on the Sessions page,
and processing works as today (GPU used when present). Updates and model downloads do not need
a terminal.

**Why this priority**: today every start requires running commands in WSL; the tool is not
usable on its own without that.

**Independent Test**: on the laptop, from a fresh login, start the tool with one action, add a
video and export a compilation without opening a terminal.

**Acceptance Scenarios**:

1. **Given** the tool is installed, **When** the user starts it, **Then** the Sessions page opens
   in the browser within a minute and shows the existing sessions.
2. **Given** the tool is running, **When** the user stops it (or closes it), **Then** running
   processing is stopped cleanly and resumes from its cache next time.

---

### Edge Cases

- A rider with one ride: the compilation is that ride with its overlay.
- Rides of a rider that were never exported: exported first, then compiled.
- Very long compilations (e.g. 40 rides): progress is shown; the result plays smoothly.
- Mixed recordings in one compilation (different resolution or frame rate within a session):
  not possible within one session (one source file per session).
- An unnamed rider: overlay says "Rider 3" (the card's label).
- Joined rides (002): one ride, one overlay.
- A still requested at a frame between analysis frames: the exact source frame is used.
- The GPU is unavailable at start: the tool starts and says processing will be slower.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST export a per-rider compilation: the rider's rides in time order, each
  ride's padded clip, hard cuts, as one video file.
- **FR-002**: Each ride in a compilation MUST carry an overlay with the rider's name (or "Rider
  N"), the ride's number among that rider's rides ("ride 3 of 12") and the session time it
  started, burned into the video for the first few seconds of each ride (configurable, default
  3 s) and then gone, so the riding itself is clean.
- **FR-003**: Compilations MUST keep the source's dynamic range and colour (as 001's clips);
  overlays on HDR footage MUST be rendered at reference white, not peak brightness.
- **FR-004**: Users MUST be able to save the current player frame as a full-resolution still of
  the exact source frame, saved as an SDR JPEG (HDR sessions tone-mapped as in the review copy)
  so it opens and shares everywhere.
- **FR-005**: The tool MUST list a session's exported clips, compilations and stills, and play
  clips and compilations at full resolution with frame stepping and 0.25x/0.5x.
- **FR-006**: Users MUST be able to start and stop the tool from Windows with one action, without
  a terminal; the browser opens on the Sessions page. Starting is a Windows desktop shortcut that
  runs the existing setup quietly in the background; stopping is a button in the tool (and a
  second shortcut).
- **FR-007**: Exports MUST NOT re-encode what is already exported unless its span or settings
  changed (as 001).
- **FR-008**: Compilation layout settings (overlay position, size, duration) MUST be
  configurable.

### Key Entities

- **Compilation**: one video per rider per session: ordered rides, overlay text per ride, the
  file and the settings it was made with.
- **Still**: a saved frame: session, ride, source time and frame number, file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From "riders named" to "compilation of my rides with overlays on disk" takes at most
  2 minutes of the user's time and at most 5 minutes of processing for 20 rides.
- **SC-002**: In 100% of compilations, every ride's overlay shows the right rider, ride number and
  session time, and the rides are exactly the rider's rides in time order.
- **SC-003**: HDR compilations keep their HDR transfer and colour tags, and overlay text is at
  most reference white (checked on the HDR session).
- **SC-004**: A saved still matches the source frame at that time (same frame, full resolution).
- **SC-005**: Starting the tool takes one action and at most 1 minute until the Sessions page
  shows, on the laptop; no terminal is opened by the user.

## Assumptions

- One rider's compilation per session; compilations across sessions are not part of this
  feature (cross-session identity is out of scope).
- The user's laptop keeps WSL2 and the NVIDIA driver as set up during 001.
- The browser UI from 001/002 is kept (the PRD's "Windows desktop app" was replaced by a backend
  and browser UI in 001); packaging starts it, it does not replace it.
- Compilations are for the user's own use, not shared with other riders (PRD).
