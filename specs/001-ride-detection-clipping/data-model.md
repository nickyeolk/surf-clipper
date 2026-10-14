# Data Model: Ride Detection and Clipping (001)

All times are stored as seconds (float, from the source's presentation timestamps) **and** source
frame indices. All positions used for decisions are in pool coordinates `(u, v)` in [0,1]², where
`u` runs along the wave (from side wall `a` at `u=0` to side wall `b` at `u=1`; riders enter over
the side walls) and `v` runs from the back wall (`v=0`) towards the
camera. Image-space values are kept only for display. Every file carries `schema_version`.

## Session

One source video and everything derived from it. Folder: `artifacts/<session_id>/`.

| Field | Type | Notes |
| --- | --- | --- |
| session_id | str | short hash of source path + size + mtime |
| source_path | str | absolute path; read-only |
| created_at | datetime | |
| config_overrides | dict | per-session values over `config/default.toml` (e.g. `rides.min_length_s`) |
| stages | dict[stage → StageStatus] | status, cache key, output file, finished_at, error |

## SourceInfo (`probe.json`)

codec, profile, width, height, duration_s, frame_count, avg_fps, is_vfr, bit_depth,
color_primaries, color_transfer (bt709 / arib-std-b67 (HLG) / smpte2084 (PQ)), color_space,
hdr_format (none / hlg / hdr10 / dolby_vision), rotation, device metadata hints (optional).

Validation: reject before processing if duration > 1.5 h or codec unsupported (spec edge case).

## CameraEpoch (`epochs.json`)

| Field | Type | Notes |
| --- | --- | --- |
| epoch_id | int | 0-based, time-ordered |
| start_s, end_s | float | contiguous, cover the whole video |
| reference_frame | int | keyframe used for matching and zone display |
| transform_from_prev | 3×3 or null | homography to previous epoch |
| inlier_ratio, inliers | float, int | quality of the transform |
| cause | `start` / `jump` / `drift` | |
| remap | `none` / `auto` / `needs_confirmation` | auto re-maps get a timeline marker |

## Zone (`zones.json`, one per epoch)

| Field | Type | Notes |
| --- | --- | --- |
| epoch_id | int | |
| corners | {back_a, back_b, front_a, front_b} → image point in **source display pixels** (full resolution after rotation; detections are scaled up from the analysis frame before comparison) | by role, never by image side; may lie outside the frame. Side wall `a` = back_a→front_a, `b` = back_b→front_b |
| entry_walls | subset of {side_a, side_b} | walls riders drop in from; default both (riders never enter over the back wall) |
| side_areas | list of polygons (image px) | where people wait on the side walls/decks |
| image_to_pool | 3×3 | derived from corners |
| undistort | params or null | ultra-wide correction (*should*) |
| origin | `proposed` / `auto_remap` | how the candidate was produced |
| proposal_confidence | float | below threshold → "unreliable" label in UI |

Confirmation state lives in `edits.json`, not here, so re-runs can regenerate proposals freely.

## Detection and Track (`detections.parquet`, `tracks.parquet`)

Per analysis frame (5 fps) and refinement window (full rate):
frame, t_s, track_id, class (person/surfboard), bbox (image), score, truncated_edge (none/left/
right/top/bottom), feet_point (image + pool), feet_estimated (bool), box_height_px.

Per track per frame (derived): state (`off` / `dropping_in` / `on_wave`), region (`side_wall`
(on or beside an entry wall), `side_area`, `zone`, `outside`), at_frame_edge (which edge, if any), board_contact (bool), stance (`standing`, `crouched`,
`sitting`, `unknown`), lateral_speed (pool units/s).

State transitions (per track):

```text
off ──(feet cross into water, standing, on board)──▶ dropping_in
dropping_in ──(on-wave evidence held ≥ confirm_window_s)──▶ on_wave   [start back-dated]
dropping_in ──(evidence lost)──▶ off                                   [no ride]
on_wave ──(fall / exit over a side wall / leave zone)──▶ off           [ride ends at last on_wave frame]
on_wave ──(exit via frame edge)──▶ on_wave (grace ≤ frame_edge_grace_s) ──▶ off if not back
```

## Ride (`rides.detected.json` → `rides.json`)

| Field | Type | Notes |
| --- | --- | --- |
| ride_id | str | stable across re-runs (`r` + start frame at creation; edits keep ids) |
| start_s, end_s, start_frame, end_frame | float/int | refined boundaries, no padding |
| clip_start_s, clip_end_s | float | with padding (1 s before, 1.5 s after) |
| confidence | float [0,1] | sorts the review list (lowest first) |
| epochs | list[int] | more than one if it spans a camera move |
| track_ids | list[int] | joined tracks (acid drop, edge exit, epoch join) |
| start_kind | `step_in` / `acid_drop` / `off_frame` / `unknown` | `off_frame`: entry wall not visible, start = first appearance; acid-drop and off-frame boundary errors reported separately |
| state_timeline | list[(t_s, state)] | compressed run-lengths |
| flags | {lesson, truncated, user_edited, user_added} | |
| export | {path, cache_key, exported_at, span} or null | set by on-demand export; kept across re-runs (exports.json) while the clip span is unchanged |

`rides.json` = detected rides with edits applied. **ShortAttempt** has the same shape minus
`export`, stored in `rides.json` under `short_attempts`.

Validation: `end > start`; rides ≥ `min_length_s` unless `user_added` or `user_edited`; overlap allowed only as a
changeover (≤ `changeover_overlap_max_s`).

## UserEdit (`edits.json`, append-only)

| Field | Type | Notes |
| --- | --- | --- |
| edit_id | int | sequence |
| at | datetime | |
| op | `confirm_zone` / `trim` / `split` / `merge` / `delete` / `add` | |
| target | epoch_id or ride_id(s) | |
| payload | op-specific | e.g. zone corners; new start/end; split time |

Rules: pipeline stages never write this file; applying edits is deterministic; after a re-run,
edits are re-attached to detected rides by time overlap (IoU ≥ 0.5) and otherwise kept as
user-added rides, so no edit is ever dropped (SC-007).

## ReviewAssets

`review.mp4` (720p H.264 SDR, keyframe every 0.5 s), `thumbs/` sprite sheets (1 per 10 s),
per-ride `review_segments/<ride_id>.mp4`, `keyframes/<epoch_id>.jpg`.

## Config (`config/default.toml`)

Sections: `analysis` (fps, max_height), `detect` (model, conf, tiling_min_height_px_at_720p),
`track`, `epochs` (match_fps, drift_frac, jump_frac, min_inliers, min_inlier_ratio), `zone`,
`rides` (confirm_window_s = 1.5, acid_link_s = 1.0, acid_link_heights, frame_edge_grace_s = 2.0,
min_length_s = 10, pad_before_s = 1.0, pad_after_s = 1.5, refine_window_s = 2.0,
changeover_overlap_max_s), `export` (encoder, quality), `server` (host = 127.0.0.1, port).
`config_version` is recorded in every stage cache key.
