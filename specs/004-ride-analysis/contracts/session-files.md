# Session files (004)

```text
artifacts/<session>/
├── analysis/<ride_id>.parquet   # keypoints (named riders' rides, or the reference's ride)
├── analysis.json                # stage output (no stars/tags; those are edits)
└── reference.json               # reference clips only: chosen track and span
artifacts/score.json             # score weights fitted to the user's stars
```

`analysis.json` per ride: `ride_id`, `span`, `rider`, `cache_key`, `keypoints_key`, `fps`,
`t0`, series `compression`, `lean`, `arms`, `stance`, `lateral` (null = unclear), `turns`,
`pumps`, `shares`, `ending`, `ending_auto`, `summary`. All stay in `artifacts/` (gitignored).
