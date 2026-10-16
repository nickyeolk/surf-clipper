# Data Model: Compilations, Stills, Viewer and Packaging

## Caption

Text burned into the first `caption_s` seconds of a ride in a compilation.

| Field | Type | Notes |
| --- | --- | --- |
| rider | str | the rider's name, else "Rider N" (002 `rider_names`) |
| index | int | 1-based position among the rider's rides in time order |
| count | int | number of the rider's rides in the compilation |
| at_s | float | ride start in the video (`Ride.start_s`) |
| text | str | `"{rider} · ride {index} of {count} · {clock(at_s)}"` |

## CaptionedSegment (per ride, cached)

| Field | Type | Notes |
| --- | --- | --- |
| ride_id | str | |
| path | str | `clips/captioned/<ride_id>.mp4` |
| cache_key | str | sha256 of 001 clip key + caption text + `[compilation]` settings |
| span | (float, float) | clip span, as `ExportRecord.span` |
| duration_s | float | measured after encoding (for offsets) |

## Compilation (`clips/compilations.json`, one record per rider)

| Field | Type | Notes |
| --- | --- | --- |
| rider_id | str | 002 rider id |
| rider | str | display name at export time |
| path | str | `clips/reel_<slug>.mp4` |
| made_at | datetime | |
| rides | list[CompilationRide] | in order |

`CompilationRide`: `ride_id`, `offset_s` (start in the compilation), `duration_s`,
`clip_start_s` (source time of the segment's first frame), `caption` (text).

A compilation is current when every listed ride's segment key still matches and the rider's
ride list is unchanged; the viewer shows "out of date" otherwise.

## Still (`clips/stills.json`)

| Field | Type | Notes |
| --- | --- | --- |
| name | str | `<ride_id or "t">_f<frame:06d>.jpg` |
| path | str | `clips/stills/<name>` |
| t_s | float | source time, snapped to `frame / fps` |
| frame | int | source frame number |
| ride_id | str or null | ride containing `t_s`, if any |
| rider | str or null | that ride's rider label at save time |
| width, height | int | full source resolution |
| saved_at | datetime | |

## Health (`GET /api/health`)

`ok: bool`, `version: str`, `gpu: bool`, `encoder: "nvenc" | "cpu"`,
`models: {detector: bool, embedder: bool}`.

## Config: `[compilation]`

| Key | Default | Meaning |
| --- | --- | --- |
| caption_s | 3.0 | seconds the caption shows at the start of each ride |
| font | "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" | |
| size_frac | 0.055 | text height as a fraction of the shorter frame side |
| position | "bottom_left" | `bottom_left` \| `bottom_right` \| `top_left` \| `top_right` |
| margin_frac | 0.04 | margin as a fraction of the shorter frame side |
| box_opacity | 0.45 | black box behind the text |
| level_sdr | 0.92 | text grey level (fraction of full scale) per transfer |
| level_hlg | 0.75 | HLG reference white (BT.2408) |
| level_pq | 0.58 | PQ reference white (203 cd/m²) |
| still_quality | 2 | JPEG quality (ffmpeg `-q:v`, 2 = best) |
