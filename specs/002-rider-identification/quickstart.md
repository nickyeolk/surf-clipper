# Quickstart & Validation: Rider Identification (002)

**Plan**: [plan.md](plan.md) · Prerequisites and setup as in
[001's quickstart](../001-ride-detection-clipping/quickstart.md); a session processed through
rides (zone confirmed or proposed).

## Scenario 1 — my rides from a session (US1)

1. `surfclip run VIDEO` (or add the video in the browser): the riders stage runs after rides.
2. Open **Riders** for the session: groups are listed largest first with an example ride and
   stills; every ride (not short attempts) is in exactly one group; lesson rides are in "Lesson".
3. Name your group "me"; merge a split of yourself with "same as"; mark staff "ignore".
4. In **Review**, filter to "me": play all, then "export as one video".
   Expected: only your rides, in time order; `clips/reel_me.mp4`.

## Scenario 2 — the review queue (US2)

1. With only "me" named, open the queue: only rides that might or might not be yours are listed,
   lowest confidence first.
2. Answer them; after each answer the remaining confidences change (fewer queued rides).
   Expected: the queue empties in ≤ 10 answers on the labelled sessions (SC-002).

## Scenario 3 — labels survive changes (US3)

1. Name riders and confirm some rides; note the counts.
2. In Review change "min ride" and re-run. Expected: every remaining ride keeps its rider; new
   rides are assigned automatically (SC-005).
3. Split a ride of "me": both parts stay "me". Undo the naming: the group is unnamed again.

## Scenario 4 — exports and manifest (US4)

`surfclip export VIDEO --per-rider --manifest`. Expected: `clips/<rider>/` per named or numbered
rider (ignored riders absent), `clips/manifest.json` and `.csv` listing every ride.

## Scenario 5 — metrics (constitution II)

1. Label riders for each evaluation session in the rider-labelling screen (accept or correct the
   proposed groups), then finalize.
2. `surfclip eval riders VIDEO` on each: SC-001 ≥ 85% and SC-002 ≤ 10 per session; PXL is held
   out from tuning.
3. Time the riders stage on a 1 h session: ≤ 5 min (SC-006).
