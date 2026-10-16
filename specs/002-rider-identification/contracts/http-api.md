# Contract: Backend HTTP API additions (002)

Base URL and error format as in [001](../../001-ride-detection-clipping/contracts/http-api.md).
Schemas in [session-files.md](session-files.md).

## Riders

| Method & path | Body / query | Response |
| --- | --- | --- |
| `GET /sessions/{id}/riders` | | `riders.json`: groups (name, ignored, kind, ride_ids, example, stills), assignments, queue, join suggestions; 404 `not_ready` until the riders stage has run |
| `POST /sessions/{id}/rider-edits` | `{op, payload}` with `op` in `rider_name`, `rider_same_as`, `rider_mixed`, `rider_ignore`, `ride_rider`, `rider_unjoin` (the client sends ride ids; the server records spans) | `{edit, riders}` after re-assignment (≤ 2 s); 400 `invalid_edit`, 404 `ride_not_found` |
| `POST /sessions/{id}/joins` | `{first, second}` | applies a suggested join (a 001 `merge` edit) and returns `{rides, riders}` |
| `GET /sessions/{id}/media/rider-still.jpg?ride=ID&t=S` | | 160 px crop of the ride's rider at time t (cached) |

Undo uses 001's `POST /sessions/{id}/edits {op: "undo", payload: {edit_id}}`; the riders are
recomputed after any ride or rider edit.

## Review and export (changes)

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /sessions/{id}/rides` | `?rider=NAME_OR_ID` | 001 response filtered to that rider's rides; each ride gains `rider` and `rider_confidence` |
| `POST /sessions/{id}/export` | `{rides?, reel?, rider?, per_rider?: bool, manifest?: bool}` | Job; `rider` restricts to one rider (`reel` → `clips/reel_<rider>.mp4`); `per_rider` writes `clips/<rider>/` folders; `manifest` writes `clips/manifest.json` and `.csv` |
| `GET /sessions/{id}/media/reel.mp4` | `?rider=NAME` | that rider's reel |

## Rider labels (evaluation; never change rides or rider edits)

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /sessions/{id}/rider-labels` | | label work: every labelled ride (001 labels) with the proposed rider from the current groups and the user's answer so far |
| `PUT /sessions/{id}/rider-labels` | label work | saved to `labels/riders/<video>.work.json` |
| `POST /sessions/{id}/rider-labels/finalize` | | writes `labels/riders/<video>.json`; 409 while any ride has no rider |
