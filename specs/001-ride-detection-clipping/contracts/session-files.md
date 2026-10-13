# Contract: Session Folder Layout and Files (001)

Feature 002 (riders) and 003 (compilation, viewer) read these files, so their shapes are a
contract. Every JSON file has `schema_version` (semver); breaking changes bump the major version.
Field details are in [../data-model.md](../data-model.md).

```text
artifacts/<session_id>/
├── session.json            # Session (stages, cache keys, config overrides)
├── probe.json              # SourceInfo
├── proxy/                  # analysis frames index (internal)
├── detections.parquet      # internal
├── tracks.parquet          # internal
├── epochs.json             # CameraEpoch[]
├── zones.json              # Zone per epoch (proposals / auto re-maps)
├── edits.json              # UserEdit[] — written ONLY by user actions
├── rides.detected.json     # pipeline output before edits (internal)
├── rides.json              # PUBLIC: rides with edits applied + short attempts
├── review.mp4              # review copy
├── review_segments/<ride_id>.mp4
├── thumbs/                 # sprite sheets + index.json
├── keyframes/<epoch_id>.jpg
└── clips/<ride_id>.mp4     # final-quality exports (on demand)
```

## `rides.json` (public, v1.0.0)

```json
{
  "schema_version": "1.0.0",
  "session_id": "a1b2c3d4",
  "source": {"path": "...", "fps": 30.0, "hdr_format": "none"},
  "settings": {"min_length_s": 10, "pad_before_s": 1.0, "pad_after_s": 1.5},
  "rides": [
    {
      "ride_id": "r004512",
      "start_s": 150.4, "end_s": 171.9,
      "start_frame": 4512, "end_frame": 5157,
      "clip_start_s": 149.4, "clip_end_s": 173.4,
      "confidence": 0.87,
      "epochs": [0],
      "track_ids": [17],
      "start_kind": "acid_drop",
      "state_timeline": [[148.9, "dropping_in"], [150.4, "on_wave"], [171.9, "off"]],
      "flags": {"lesson": false, "truncated": true, "user_edited": false, "user_added": false},
      "export": null
    }
  ],
  "short_attempts": [
    {"ride_id": "s006021", "start_s": 200.7, "end_s": 205.1, "confidence": 0.71}
  ],
  "markers": [{"t_s": 1834.2, "kind": "remap", "epoch_id": 1}]
}
```

## `edits.json` (v1.0.0)

```json
{
  "schema_version": "1.0.0",
  "edits": [
    {"edit_id": 1, "at": "2026-10-13T11:02:00Z", "op": "confirm_zone", "target": {"epoch_id": 0},
     "payload": {"corners": {"deck_a": [102, 233], "deck_b": [1180, 241],
                 "wave_end_a": [40, 690], "wave_end_b": [1265, 702]}, "how": "accepted"}},
    {"edit_id": 2, "at": "2026-10-13T11:05:10Z", "op": "trim", "target": {"ride_id": "r004512"},
     "payload": {"start_s": 150.1}}
  ]
}
```

Invariants: `edits.json` is append-only; `rides.json` is always reproducible from
`rides.detected.json` + `edits.json`; source files are never written.
