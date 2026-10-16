# Contract: Session files added by 002

See [data-model.md](../data-model.md) for field meanings. All files carry `schema_version`.

## `riders.json` (v1.0.0, stage output; reproducible from rides + appearance + edits)

```json
{
  "schema_version": "1.0.0",
  "session_id": "9ac6901941",
  "descriptor": "colour",
  "riders": [
    {"rider_id": "g01", "name": "me", "ignored": false, "kind": "rider",
     "ride_ids": ["r004512", "r009120"], "example_ride_id": "r004512",
     "stills": [{"ride_id": "r004512", "t_s": 152.0}]},
    {"rider_id": "g02", "name": null, "ignored": false, "kind": "rider",
     "ride_ids": ["r006021"], "example_ride_id": "r006021", "stills": []},
    {"rider_id": "lesson", "name": null, "ignored": false, "kind": "lesson",
     "ride_ids": ["r000000"], "example_ride_id": "r000000", "stills": []}
  ],
  "assignments": [
    {"ride_id": "r004512", "rider_id": "g01", "confidence": 0.93, "confirmed": true,
     "queued": false, "low_evidence": false}
  ],
  "join_suggestions": [{"first": "r010020", "second": "r010455", "gap_s": 3.2, "confidence": 0.71}],
  "auto_joined": []
}
```

## `appearance.parquet` (per-session only; never read for another session)

Columns: `ride_id` (str), `span` (str "start-end", for reuse across re-runs), `t_s` (float),
`track_id` (int), `sharpness` (float), `box_height_px` (float), `colour` (list[float]),
`embedding` (list[float] | null), `kind` (`crop` | `ride_mean`).

## Rider edit ops in `edits.json`

```json
{"edit_id": 12, "at": "2026-10-16T09:00:00Z", "op": "rider_name", "target": {},
 "payload": {"name": "me", "rides": {"r004512": [150.4, 171.9], "r009120": [304.0, 331.2]},
             "examples": ["r004512"]}}
{"edit_id": 13, "at": "...", "op": "ride_rider", "target": {},
 "payload": {"ride": ["r012000", 400.0, 431.5], "name": "me"}}
```

Invariants: rider edits never mention group ids; `riders.json` is always recomputable; undo of a
rider edit uses 001's `undo` op.

## `labels/riders/<video>.json` (evaluation)

```json
{"schema_version": "1.0.0", "source": "20240924.MP4", "named": ["me"],
 "rides": [{"label_ride_id": "r015024", "start_s": 500.8, "end_s": 542.6, "rider": "me"}],
 "finalized": true}
```
