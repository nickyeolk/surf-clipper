# Data Model: Rider Identification (002)

**Date**: 2026-10-16 · **Plan**: [plan.md](plan.md) · Builds on 001's
[data model](../001-ride-detection-clipping/data-model.md).

All files live in the session folder `artifacts/<session_id>/` unless noted, carry a
`schema_version`, and stay inside the session (constitution I: never read across sessions).

## Entities

### RideAppearance (stage output, `appearance.parquet`)

Per crop (one row each): `ride_id`, `t_s`, `track_id`, `sharpness`, `box_height_px`,
`colour` (fixed-length float vector: upper, lower and board histograms), `embedding` (float vector
or null when the embedding is not adopted). Per ride (summary rows): mean descriptors and
`usable_crops`.

Validation: crops < `riders.min_crop_height_px` are dropped; a ride with fewer than
`riders.min_crops` usable crops gets `low_evidence = true` (confidence capped).

### Group / Rider (stage output, `riders.json`)

| Field | Type | Notes |
| --- | --- | --- |
| `rider_id` | string | stable within one computation, e.g. `g01`; never stored in edits |
| `name` | string \| null | from a `rider_name` edit; null = unnamed, shown as "Rider N" |
| `ignored` | bool | from `rider_ignore` |
| `kind` | `rider` \| `lesson` | lesson rides (001 flag) form one `lesson` group |
| `ride_ids` | list[string] | current rides |
| `example_ride_id` | string | clearest ride (largest sharp crops) |
| `stills` | list[{ride_id, t_s}] | up to `riders.stills` moments from different rides |

### Assignment (in `riders.json`, one per ride)

| Field | Type | Notes |
| --- | --- | --- |
| `ride_id` | string | 001 ride id |
| `rider_id` | string | group |
| `confidence` | float 0-1 | margin to the nearest other rider (R5) |
| `confirmed` | bool | fixed by a user edit (`ride_rider`, or shown as an example when naming) |
| `queued` | bool | below `riders.queue_below` and involving a named rider (FR-005) |
| `low_evidence` | bool | too few usable crops |

Plus `join_suggestions: [{first, second, gap_s, confidence}]` and `auto_joined: [[first, second]]`.

### Rider edits (appended to 001's `edits.json`)

All anchored to rides by `ride_id` + span at the time (re-attached by IoU ≥ 0.5 after re-runs,
like 001's ride edits). Ops:

| Op | Payload | Effect |
| --- | --- | --- |
| `rider_name` | `{name, rides: {id: [s, e]}, examples: [id]}` | the rides' group is named; example rides become confirmed |
| `rider_same_as` | `{rides: {id: [s,e]}, other: {id: [s,e]}}` | the two groups (found through their anchor rides) must be one rider |
| `rider_mixed` | `{rides: {id: [s,e]}}` | split that group in two (2-way re-cluster with no must-links across) |
| `rider_ignore` | `{rides: {id: [s,e]}, ignore: bool}` | group ignored (or not) |
| `ride_rider` | `{ride: [id, s, e], name}` or `{..., same_as_ride: id}` | confirm or reassign one ride (fixed) |
| `rider_unjoin` | `{first: [id,s,e], second: [id,s,e]}` | never auto-join this pair again |
| `undo` | `{edit_id}` | 001's undo applies to rider edits too |

Automatic frame-edge joins are 001 `merge` edits with `how: "auto_join"`.

State transitions of a group: proposed → named / ignored; any → merged (same as) or split
(mixed); a ride: assigned → queued → confirmed (or reassigned → confirmed).

### RiderLabels (evaluation, `labels/riders/<video>.json`)

`{source, rides: [{label_ride_id, start_s, end_s, rider}], named: [rider...], finalized}`:
every labelled ride of 001's label file gets the true rider's name; `named` lists the riders the
user would name in normal use (at least "me"), used by SC-002.

### Manifest (export, `clips/manifest.json` and `.csv`)

`[{ride_id, start_s, end_s, rider, confidence, confirmed, clip}]`; rider is the name, "Rider N",
"ignored" or "lesson".

## Stage and cache

`riders` stage: depends on `rides` (and `review_copy`); config section `riders`; extra inputs:
the rider edits (hash of the rider ops in `edits.json`). Re-running rides (e.g. new minimum
length) re-runs riders; descriptors of unchanged rides are reused from `appearance.parquet`
(keyed by ride span), so only new rides are cropped and described.

## Config (`config/default.toml`, `[riders]`)

`crops_per_ride` 12, `keep_sharpest` 8, `min_crop_height_px` 48, `min_crops` 3, `descriptor`
(`colour` | `embedding` | `both`, set by the spike), `cluster_threshold`, `changeover_overlap_s`
(from `[rides]`), `queue_below` 0.5, `stills` 6, `join_gap_s` 6.0, `join_confidence` 0.8,
`lighting_change_window_s` 30.
