# Contract: Backend HTTP API (001)

Base URL `http://127.0.0.1:8765/api`. JSON bodies; errors as
`{"error": {"code": str, "message": str}}` with 4xx/5xx. The server binds to 127.0.0.1 only
(FR-025). Schemas referenced are defined in [session-files.md](session-files.md).

## Sessions and jobs

| Method & path | Body / query | Response |
| --- | --- | --- |
| `GET /sessions` | | `[{session_id, source_path, duration_s, stages, ride_count}]` |
| `GET /sources` | | `[{path, name, size_bytes, session_id}]`: videos in `server.source_dirs` (implemented) |
| `POST /sessions` | `{source_path, min_length_s?}` | `{session_id, job}`; source must be a video in `server.source_dirs` (400 `source_not_allowed`); the job analyses it, finds rides when a zone is confirmed, and precomputes the zone proposal (implemented) |
| `GET /sessions` | | adds `analysed`, `zone_confirmed`, `exported` and the running `job` per session (implemented) |
| `GET /sessions/{id}` | | Session + SourceInfo |
| `POST /sessions/{id}/rerun` | `{min_length_s}` | Job: re-finds rides with the setting (stored in the session's overrides); detection cached, edits kept; 409 `zone_not_confirmed`, 400 `invalid_setting` (implemented) |
| `GET /jobs/{job_id}` | | `{stage, progress 0–1, eta_s, status, error?}` |

## Zones

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /sessions/{id}/epochs` | | `epochs.json` content + per-epoch zone status (`proposed`, `confirmed`, `auto_remap`, `needs_confirmation`) |
| `GET /sessions/{id}/epochs/{e}/keyframe.jpg` | | JPEG |
| `GET /sessions/{id}/epochs/{e}/zone` | | Zone (proposal or confirmed) + `proposal_confidence`, `unreliable` |
| `PUT /sessions/{id}/epochs/{e}/zone` | Zone (accepted, edited or drawn) | appends `confirm_zone` edit; triggers ride stages |

## Rides and edits

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /sessions/{id}/rides` | `?sort=confidence` | `{rides: [Ride], short_attempts: [...], markers: [{t_s, kind: "remap"}]}` |
| `POST /sessions/{id}/edits` | `{op, target, payload}` (`trim`, `split`, `merge`, `delete`, `add`, `undo`) | `{edit, rides}` (the recorded edit, incl. target `spans`, and the rebuilt rides.json); 400 `invalid_edit`, 404 `ride_not_found` |
| `GET /sessions/{id}/edits` | | edit log |
| `POST /sessions/{id}/export` | `{rides?: [id], reel?: bool}` (omitted: all rides) | Job; only new/changed rides re-encoded; with `reel` the clips are also joined (no re-encode) into `clips/reel.mp4`; returns the running job if one exists |
| `GET /jobs/{job_id}` | | `{job_id, kind, status: queued/running/done/failed, progress, message, result: {exported, up_to_date, folder}, error}` |

## Labels (ground truth; never changes rides or edits)

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /sessions/{id}/activity` | | `{bin_s, values: [0..1]}` share of analysed frames per bin with someone riding |
| `GET /sessions/{id}/labels` | | label work: `{source, items: [{id, start_s, end_s, verdict: ?/ok/fix/no/add, acid_drop, detected_as, proposed_start_s, proposed_end_s, confidence, notes}], scanned_to_s, finalized}`; created from rides.json on first call |
| `PUT /sessions/{id}/labels` | label work | saved to `labels/rides/<name>.work.json` |
| `POST /sessions/{id}/labels/finalize` | | `{rides, path}`; writes `labels/rides/<name>.json`; 409 `labels_incomplete` while any verdict is `?` |

## Media (all support HTTP Range)

| Method & path | Response |
| --- | --- |
| `GET /sessions/{id}/media/review.mp4` | 720p H.264 SDR review copy, keyframe every 0.5 s, ≤ 2.5 Mbps (implemented) |
| `GET /sessions/{id}/media/rides/{ride_id}/review.mp4` | per-ride review segment (padded) |
| `GET /sessions/{id}/media/thumbs/{n}.jpg` + `GET .../thumbs/index.json` | sprite sheets + timing |
| `GET /sessions/{id}/media/frame?t=S` or `?frame=N` | exact frame as PNG (SDR) |
| `GET /sessions/{id}/media/clips/{ride_id}.mp4` | exported full-quality clip (implemented) |
| `GET /sessions/{id}/media/reel.mp4` | the rides joined into one video (implemented) |
| `GET /sessions/{id}/media/thumb.jpg?t=S` | 320 px still from the review copy, cached per 0.5 s (implemented) |

Performance expectations: seeks into `review.mp4` start playback ≤ 1 s; ride segments fully
buffered so frame steps ≤ 0.2 s (SC-009).
