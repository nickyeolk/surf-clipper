# Data Model: Ride Analysis

## Keypoints (`analysis/<ride_id>.parquet`, one row per analysed frame)

| Column | Type | Notes |
| --- | --- | --- |
| t | float | source seconds |
| box | 4×float | crop box in source pixels |
| kp | 17×3 float | COCO keypoints (x, y in source pixels; confidence) |
| other_iou | float | max IoU of the crop with another tracked person |

## RideAnalysis (in `analysis.json`)

| Field | Type | Notes |
| --- | --- | --- |
| ride_id | str | |
| span | (float, float) | ride start/end it was computed for |
| rider | str | user-given name at analysis time |
| cache_key | str | span + rider + `[analysis_pose]` + code version |
| fps | float | analysis rate |
| compression | list[float \| null] | per frame, 1.0 = ride median; null = unclear |
| lateral | list[float \| null] | pool `u` per frame where available |
| turns | list[Event] | `t`, `depth` (compression at the minimum), `side` (frontside/backside if known) |
| pumps | list[Event] | |
| shares | {turning, pumping, trimming, unclear} | fractions of ride time |
| ending | "fall" \| "exit" \| "unclear" | after corrections |
| ending_auto | same | before corrections |
| summary | {length_s, turns, pumps, turn_rate_per_10s, rhythm_cv, mean_depth} | |

`rhythm_cv`: coefficient of variation of intervals between consecutive turns/pumps (lower =
steadier rhythm, a "flow" proxy).

## AnalysisFile (`analysis.json`)

`schema_version`, `session_id`, `rides: list[RideAnalysis]`, `settings`.

## Edits (new ops in `edits.json`)

| op | target | payload |
| --- | --- | --- |
| `ride_ending` | ride_id | `ending`, `spans` |
| `turn_add` | ride_id | `t`, `spans` |
| `turn_remove` | ride_id | `t` (nearest turn within 0.5 s), `spans` |
| `trick_tag` | ride_id | `t`, `name`, `spans` |

Tags are deleted with the existing `undo`.

## Marks (`labels/analysis/<video>.json`)

`source`, `rides: [{start_s, end_s, turns: [t], ending, pumps?: [t]}]`, `final: bool`.

## Trend point

`session_id`, `video`, `date`, `rides`, `shares`, `turn_rate_per_10s`, `rhythm_cv`,
`falls`, `exits`, `mean_depth`.

## Config `[analysis_pose]`

`fps = 15`, `model = "artifacts/models/yolo11s-pose.pt"`, `imgsz = 384`, `crop_margin = 0.3`,
`min_conf = 0.3`, `smooth_s = 0.3`, `signal = "leg_torso" | "leg_straightness"` (R3),
`turn_speed_pool_per_s`,
`turn_window_s = 0.7`, `pump_depth = 0.85`, `fall_window_s = 1.5`,
`fall_depth = 0.6`, `compare_window_s = [3.0, 0.5]`, `other_iou_max = 0.3`.
