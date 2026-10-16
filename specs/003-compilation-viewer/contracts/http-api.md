# HTTP API (003 additions and changes)

All routes on loopback, JSON unless noted; errors as in 001
(`{"error": {"code": "...", "message": "..."}}`).

## Changed

### `POST /api/sessions/{id}/export`

Body adds nothing new: `{"reel": true, "rider": "<rider label>"}` now produces the captioned
compilation (`clips/reel_<slug>.mp4`) instead of a plain join. `{"reel": true}` without a rider
stays the plain join of all rides (no captions). Returns a job as before.

### `GET /api/sessions/{id}/media/reel.mp4?rider=<label>`

Unchanged; serves the compilation.

## New

### `GET /api/sessions/{id}/exports`

What the viewer lists.

```json
{
  "fps": 30.0,
  "compilations": [
    {"rider": "me", "url": "/api/sessions/9ac6901941/media/reel.mp4?rider=me",
     "current": true, "made_at": "2026-10-16T10:00:00Z",
     "rides": [{"ride_id": "r004302", "offset_s": 0.0, "duration_s": 34.1,
                "clip_start_s": 143.4, "caption": "me · ride 1 of 12 · 2:23"}]}
  ],
  "riders": [
    {"rider": "me", "clips": [
      {"ride_id": "r004302", "url": "/api/sessions/9ac6901941/media/clips/r004302.mp4",
       "clip_start_s": 143.4, "duration_s": 34.1}]}
  ],
  "unassigned": [],
  "stills": [
    {"name": "r004302_f004512.jpg", "url": "/api/sessions/9ac6901941/media/stills/r004302_f004512.jpg",
     "t_s": 150.4, "frame": 4512, "ride_id": "r004302", "rider": "me", "width": 1920, "height": 1080}
  ]
}
```

`riders` lists only rides with a current export; ignored riders are left out.

### `POST /api/sessions/{id}/stills`

Body `{"t_s": 150.41}` (source time, e.g. the Review player's `currentTime`, or a clip's
`clip_start_s + currentTime`). Snaps to the frame grid; returns the Still (as in `exports.stills`),
201 when new, 200 when that frame was already saved. 400 when outside the video.

### `GET /api/sessions/{id}/media/stills/{name}.jpg`

The still (image/jpeg). `?download=1` adds `Content-Disposition: attachment`.

### `DELETE /api/sessions/{id}/stills/{name}`

Removes a still the user saved (it is the user's own output, not source data). 204.

### `GET /api/health`

```json
{"ok": true, "version": "0.3.0", "gpu": true, "encoder": "nvenc",
 "models": {"detector": true, "embedder": true}}
```

### `POST /api/models/download`

Starts a job downloading missing weights. Returns `{"job_id": "..."}`; 409 if one is running.

### `POST /api/shutdown`

Cancels queued jobs, stops the running one, and exits the server after the response.
`{"stopping": true}`. Only from loopback (as every route).
