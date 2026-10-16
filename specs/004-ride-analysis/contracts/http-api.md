# HTTP API (004)

Errors as before: `{"error": {"code": "...", "message": "..."}}`.

| Route | Purpose |
| --- | --- |
| `GET /api/sessions/{id}/analysis` | `analysis.json` (corrections applied); 404 before the stage ran |
| `POST /api/sessions/{id}/analysis` | run/refresh the stage as a job (named riders only); `{"job_id"}` |
| `GET /api/sessions/{id}/analysis/{ride}/keypoints?from=&to=` | keypoints for the overlay, scaled to review-copy pixels: `{fps, frames: [{t, kp: [[x,y,c]*17]}]}` |
| `POST /api/sessions/{id}/analysis-edits` | `{op: ride_ending\|turn_add\|turn_remove\|trick_tag, ride_id, t?, ending?, name?}` → updated ride analysis |
| `GET /api/sessions/{id}/falls` | fall comparison: `{measures: [{name, falls: [..], exits: [..]}], moments: [{ride_id, from_s, to_s, kind}]}` |
| `GET /api/tricks?name=&rider=` | trick tags across sessions: `[{session_id, video, ride_id, t, name, rider}]` |
| `GET /api/trends?rider=me` | `[{session_id, video, date, ...TrendPoint}]` in date order |
| `GET /api/sessions/{id}/marks` / `PUT` / `POST .../marks/finalize` | evaluation marks (as rider labels in 002) |
