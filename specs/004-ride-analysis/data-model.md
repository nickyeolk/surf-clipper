# Data Model: Ride Analysis (rescoped 2026-10-17)

## Keypoints (`analysis/<ride_id>.parquet`, one row per analysed frame)

`t` (source s), `box` (crop box, source px), `kp` (17 × x, y, confidence; source px),
`other_iou` (overlap with another tracked person).

## RideAnalysis (in `analysis.json`)

| Field | Notes |
| --- | --- |
| ride_id, span, rider, cache_key, keypoints_key, fps, t0 | identity and cache |
| compression, lean, arms, stance | per-frame series, null where unclear (FR-002) |
| lateral | pool `u` where the session has a zone |
| turns, pumps | events: `t`, `depth` |
| shares, ending, summary | as built |
| score | `{value, parts: {feature: contribution}, explanation}` (filled on read) |
| starred | bool (from edits, on read) |
| tricks | user tags: `t`, `name` (from edits, on read) |

Measures: **compression** = hip-ankle / shoulder-hip (or leg straightness); **lean** = angle of
the hip→shoulder line from the image vertical, signed (camera-relative); **arms** = wrist-wrist
distance / torso length; **stance** = ankle-ankle distance / torso length.

## Reference clip

A session (`session.json`, `kind = "reference"`) plus `reference.json`:
`{track_id, start_s, end_s, picked_at: {t, x, y}}`. Its single ride `ref` spans the chosen
track; analysis as for rides; `rider` = the clip's file stem.

## Edits (`edits.json`)

| op | target | payload |
| --- | --- | --- |
| `ride_star` | ride_id | `starred: bool`, `spans` |
| `trick_tag` | ride_id | `t`, `name`, `spans` |

## Score weights (`artifacts/score.json`)

`{features: [..], mean: [..], std: [..], weights: [..], bias, fitted_on: {stars, rides,
sessions}, fitted_at}`; defaults from `[score]` when there are too few stars.

Features: `length_s`, `clean_end` (1 exit, 0 fall, 0.5 unclear), `compressions_per_10s`,
`depth` (1 - mean compression at events), `rhythm` (1 - rhythm_cv, clipped), `tricks`,
`unclear` (negative weight).

## Config

`[analysis_pose]` as built. `[score]`: default weights per feature, `min_stars = 5`,
`l2 = 1.0`.
