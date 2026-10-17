# HTTP API (004, rescoped)

Errors as before: `{"error": {"code": "...", "message": "..."}}`.

| Route | Purpose |
| --- | --- |
| `GET /api/sessions/{id}/analysis` | `analysis.json` with stars, tags and scores applied; 404 before the stage ran |
| `POST /api/sessions/{id}/analysis` | run/refresh the stage as a job; `{"job_id"}` |
| `GET /api/sessions/{id}/analysis/{ride}/keypoints` | `{fps, width, height, frames: [{t, box: [x0,y0,x1,y1], kp: [[x,y,c]*17]}]}` in review-copy pixels |
| `POST /api/sessions/{id}/stars` | `{ride_id, starred}` → the ride's analysis |
| `POST /api/sessions/{id}/tricks` | `{ride_id, t, name}` → the tag (delete with the existing undo) |
| `GET /api/tricks?name=` | tags across sessions: `[{session_id, video, ride_id, t, name, rider}]` |
| `GET /api/references` | `[{session_id, video, status, surfer_picked, analysed}]` |
| `POST /api/references` | `{source_path}` → import job (probe, review copy, detect, track) |
| `GET /api/references/{id}/people?t=` | people boxes at t (review-copy px) to click on |
| `POST /api/references/{id}/surfer` | `{t, x, y}` → choose the track, analyse (job) |
