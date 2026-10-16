# Research: Compilations, Stills, Viewer and Packaging

## R1. Captions on HDR footage

**Decision**: ffmpeg `drawtext` (libfreetype) in the same encode as the clip, text in neutral grey
at the transfer's reference-white level, a translucent black box behind it, shown with
`enable='lt(t,caption_s)'`. Levels (fraction of full scale): HLG 0.75, PQ 0.58, SDR 0.92.

**Rationale**: neutral greys have the same Y and neutral chroma under every matrix, so the level
does not depend on how drawtext converts RGB to YUV. HLG reference white (203 cd/m²) is 75% of the
signal (ITU-R BT.2408), PQ reference white is 58%; pure white would be drawn at peak brightness
(1000 cd/m² on HLG), the "glaring caption" problem. Spike on PXL_20261014 (HLG 1080p): a 6 s
segment re-encoded with the caption in 2.0 s (NVENC hevc main10), tags kept
(`bt2020/arib-std-b67/bt2020nc`, yuv420p10le); tone-mapped the caption reads as white.

**Alternatives**: overlay a PNG rendered in Python (needs its own HDR conversion; no gain);
burn captions into a short re-encoded head and stream-copy the rest (cuts must fall on keyframes,
so the head length varies per ride and joins get fragile; the full re-encode is fast enough);
subtitle track instead of burned in (the user chose burned in; players hide subtitles by default).

## R2. Compilation structure and caching

**Decision**: each ride of the rider becomes a captioned segment `clips/captioned/<ride>.mp4`,
encoded from the source with exactly the 001 clip settings plus the caption filter. Cache key =
001's clip key + caption text + `[compilation]` settings. The compilation joins the segments with
the concat demuxer and `-c copy` (as 002's reel). Records in `clips/compilations.json` hold the
rides, their offsets in the compilation and the captions, so the viewer can say which ride is
playing and map a compilation time back to the source for stills.

**Rationale**: renaming a rider or a ride count change re-captions every segment of that rider
(the caption text changes), but the source is read once per ride either way; unchanged rides are
never re-encoded (FR-007). Concat copy works because all segments share codec settings.

**Ride number**: position among the rider's rides in time order (1-based), "ride k of n"; session
time = the ride's start in the video as m:ss (h:mm:ss over an hour). The video's wall-clock time
is not reliable across phones and cameras, so it is not used.

## R3. Viewer playback of exported files

**Decision**: the viewer plays the exported files directly (`/media/clips/<ride>.mp4`,
`/media/reel.mp4?rider=`), with a note when `canPlayType` says the browser cannot decode HEVC.

**Rationale**: in the desktop app's Chromium on this laptop, `canPlayType('video/mp4;
codecs="hvc1.2.4.L153.B0"')` is "probably" and a 1080p HLG clip decodes and seeks (measured
2026-10-16). Chrome and Edge on Windows use the same hardware decoder. The display is SDR, so the
browser tone-maps; on an HDR display it shows HDR. A transcoded SDR copy would double storage for
no gain.

**Frame stepping**: ±1 frame = ±1/fps seconds from the session's probe; 0.25x/0.5x/1x via
`playbackRate` (as the Review player).

## R4. Stills

**Decision**: `ffmpeg -ss <t> -i <source> -frames:v 1` with the review copy's tone-map chain (HDR)
or plain conversion (SDR), full source resolution, JPEG quality 2. The requested time is snapped
to the source frame grid (`n = round(t·fps)`, `t = n/fps`) and the still is named by ride and
frame (`r004302_f012345.jpg`); asking again for the same frame returns the existing file.

**Rationale**: input seeking is frame-accurate when decoding (ffmpeg ≥ 2.1). Review-copy times
equal source times (same timestamps, no `-r`), so the Review player's `currentTime` is the source
time. Exact-frame check (SC-004): compare the still, downscaled, with the review copy's frame
`n`, mean absolute difference below a small threshold.

## R5. Starting and stopping without a terminal

**Decision**: `scripts/windows/start.ps1` run by a desktop shortcut with
`powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File`: if `/api/health` answers, open the
browser; otherwise start `wsl -d Ubuntu --cd <repo> -- bash scripts/wsl-run.sh uv run surfclip
serve --log artifacts/logs/server.log` hidden, poll health for up to 60 s, open the browser, or
show a message box with the log path. `stop.ps1` POSTs `/api/shutdown` (falls back to
`wsl pkill -f "surfclip serve"`). The UI also has a Stop button. `install-shortcuts.ps1` builds the
web UI once (`npm run build` in WSL) and creates "Surf Clipper" and "Stop Surf Clipper" on the
Desktop with an icon.

**Shutdown**: `/api/shutdown` cancels queued jobs, asks the running ffmpeg/analysis to stop, and
tells uvicorn to exit. Stage outputs and clips are written to a temporary file and renamed, so an
interrupted job leaves no partial outputs and resumes from the cache.

**Alternatives**: Docker (heavier, Docker Desktop must run; rejected by the user); Windows
service (needs admin); a tray app (needs a GUI toolkit; a Stop button and shortcut suffice).

## R6. Health and model weights

**Decision**: `GET /api/health` returns `{ok, gpu, encoder, models: {detector, embedder},
version}`; `gpu` from `nvidia-smi -L`, `encoder` from a 1-frame NVENC test cached per server
start. The Sessions page shows a banner when the GPU is missing ("processing will be slower") or a
model is missing, with a "Download models" button that runs `models download` as a job.

**Rationale**: the spec's edge case "GPU unavailable at start" and "model downloads do not need a
terminal". Updates of the tool itself stay a developer step (git pull) — out of scope.
