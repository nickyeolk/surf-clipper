# Session files (003 additions)

Under `artifacts/<session>/clips/` (all reproducible from rides, riders and the source, except
stills, which are the user's own picks):

```text
clips/
├── <ride>.mp4                 # 001 clip (unchanged, never captioned)
├── <rider>/                   # 002 per-rider folder (unchanged)
├── manifest.json / .csv       # 002 (unchanged)
├── reel.mp4                   # plain join of all rides (unchanged)
├── reel_<rider>.mp4           # 003: captioned compilation of one rider
├── captioned/<ride>.mp4       # 003: captioned segments (cache)
├── compilations.json          # 003
├── stills/<ride>_f<frame>.jpg # 003
└── stills.json                # 003
```

## `compilations.json`

```json
{
  "schema_version": "1.0.0",
  "segments": {
    "r004302": {"path": "clips/captioned/r004302.mp4", "cache_key": "a1b2c3d4e5f60718",
                "span": [143.4, 177.5], "duration_s": 34.1}
  },
  "compilations": {
    "me": {"rider": "me", "path": "clips/reel_me.mp4",
           "made_at": "2026-10-16T10:00:00Z",
           "rides": [{"ride_id": "r004302", "offset_s": 0.0, "duration_s": 34.1,
                      "clip_start_s": 143.4, "caption": "me · ride 1 of 12 · 2:23"}]}
  }
}
```

## `stills.json`

```json
{
  "schema_version": "1.0.0",
  "stills": [
    {"name": "r004302_f004512.jpg", "path": "clips/stills/r004302_f004512.jpg", "t_s": 150.4,
     "frame": 4512, "ride_id": "r004302", "rider": "me", "width": 1920, "height": 1080,
     "saved_at": "2026-10-16T10:05:00Z"}
  ]
}
```

Rider names appear in these files and in file names; they stay in `artifacts/` (gitignored), as
in 002.
