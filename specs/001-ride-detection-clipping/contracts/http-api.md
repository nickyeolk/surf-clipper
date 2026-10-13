# Contract: Backend HTTP API (001)

Base URL `http://127.0.0.1:8765/api`. JSON bodies; errors as
`{"error": {"code": str, "message": str}}` with 4xx/5xx. The server binds to 127.0.0.1 only
(FR-025). Schemas referenced are defined in [session-files.md](session-files.md).

## Sessions and jobs

| Method & path | Body / query | Response |
| --- | --- | --- |
| `GET /sessions` | | `[{session_id, source_path, duration_s, stages, ride_count}]` |
| `POST /sessions` | `{source_path, min_length_s?}` | `{session_id}`; starts ingest + analyse job |
| `GET /sessions/{id}` | | Session + SourceInfo |
| `POST /sessions/{id}/rerun` | `{from_stage, config_overrides?}` | `{job_id}` (never touches edits) |
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
| `POST /sessions/{id}/edits` | `{op, target, payload}` (`trim`, `split`, `merge`, `delete`, `add`) | updated affected rides |
| `GET /sessions/{id}/edits` | | edit log |
| `POST /sessions/{id}/export` | `{rides?: [id], all?: bool}` | `{job_id}`; only new/changed rides re-encoded |

## Media (all support HTTP Range)

| Method & path | Response |
| --- | --- |
| `GET /sessions/{id}/media/review.mp4` | 720p review copy |
| `GET /sessions/{id}/media/rides/{ride_id}/review.mp4` | per-ride review segment (padded) |
| `GET /sessions/{id}/media/thumbs/{n}.jpg` + `GET .../thumbs/index.json` | sprite sheets + timing |
| `GET /sessions/{id}/media/frame?t=S` or `?frame=N` | exact frame as PNG (SDR) |

Performance expectations: seeks into `review.mp4` start playback ≤ 1 s; ride segments fully
buffered so frame steps ≤ 0.2 s (SC-009).
