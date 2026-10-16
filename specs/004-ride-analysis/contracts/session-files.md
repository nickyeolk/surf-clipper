# Session files (004)

```text
artifacts/<session>/
├── analysis/<ride_id>.parquet   # keypoints (stage cache, named riders' rides only)
└── analysis.json                # per-ride analysis (stage output, no corrections)
labels/analysis/<video>.json     # evaluation marks (times only; committed)
```

`analysis.json`:

```json
{
  "schema_version": "1.0.0",
  "session_id": "9ac6901941",
  "settings": {"fps": 15, "signal": "leg_torso"},
  "rides": [
    {"ride_id": "r059094a", "span": [196.8, 235.2], "rider": "me", "cache_key": "…", "fps": 15,
     "compression": [1.02, 0.98, null], "lateral": [0.41, 0.42, null],
     "turns": [{"t": 207.3, "depth": 0.52, "side": null}], "pumps": [{"t": 201.1, "depth": 0.8}],
     "shares": {"turning": 0.41, "pumping": 0.18, "trimming": 0.36, "unclear": 0.05},
     "ending": "fall", "ending_auto": "fall",
     "summary": {"length_s": 38.4, "turns": 6, "pumps": 3, "turn_rate_per_10s": 1.6,
                 "rhythm_cv": 0.31, "mean_depth": 0.71}}
  ]
}
```

Keypoints and analysis hold body data of named riders only and stay in `artifacts/`
(gitignored). Marks hold times only.
