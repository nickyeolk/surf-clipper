# Implementation Plan: Ride Analysis

**Branch**: `004-ride-analysis` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-ride-analysis/spec.md`

## Summary

A new cached **analysis** stage runs after `riders`, only for rides of named riders. For each
ride it decodes the full-resolution source at 15 fps, crops the tracked rider (001 track boxes,
interpolated), runs YOLO11-pose on the crop and keeps the keypoints of the person nearest the
crop centre (spike: 99-100% joint visibility at 85-360 px). From the keypoints and the rider's
path across the pool (001 zone mapping) it derives, per ride: a **compression signal** relative
to the rider's own body, **turns** (direction changes across the wave, usually with a
compression), **pumps** (compress/extend cycles without a direction change), **trimming**
(neither), **unclear** spans, and the **ending** (fall / exit / unclear). User corrections
(ending, turn add/remove) and **trick tags** are append-only edits, as in 001/002.

The Review player gets a skeleton overlay and an analysis strip (compression curve with turns,
pumps, ending, tags). A per-session **Analysis** screen shows the ride table, the
turning/pumping/trimming shares and the **fall comparison** (with back-to-back playback of
pre-fall moments); a **Trends** screen pools sessions by the user-given rider name. A **ride
marks** screen lets the user mark turns and endings for evaluation before tuning.

## Technical Context

**Language/Version**: Python 3.12; TypeScript 5 + Svelte 5

**Primary Dependencies**: as 001-003; pose weights `yolo11s-pose.pt` (or `m`/`x` if R2 says so)
fetched by `surfclip models download`; no new packages (ultralytics, NumPy, SciPy, pyarrow)

**Storage**: per session `artifacts/<session>/analysis/<ride>.parquet` (keypoints: t, 17×(x, y,
conf) in source pixels, crop box) and `analysis.json` (per-ride measures, events, summary; stage
output); corrections and tags in `edits.json`; evaluation marks in
`labels/analysis/<video>.json` (times only, no names: committed like ride labels)

**Testing**: pytest (unit: compression signal, turn/pump/trim segmentation, ending rules,
edit application, trends pooling; contract: routes; integration: stage on a short synthetic
or sample clip); `surfclip eval-analysis` for SC-001..003 per marked session, one session held out

**Target Platform**: as before (RTX 2060, WSL2, Chromium)

**Performance Goals**: ≤ 20 s per ride (SC-004: 30 rides ≤ 10 min); overlay at 1x (SC-005)

**Constraints**: measures relative to the body, never pixels or absolute angles (FR-002); named
riders only (FR-010); keypoints stay in the session folder; cross-session pooling only by the
user-given name, never by appearance (constitution I, 002)

**Scale/Scope**: ~30 analysed rides per session, ~600 frames per ride

## Constitution Check

| # | Principle | How this plan complies | Status |
| --- | --- | --- | --- |
| I | Local-first and personal | Pose runs locally; only named riders analysed; keypoints in the session folder; trends link sessions only by the user's own naming | Pass |
| II | Evaluation before features | Ride-marks screen and `eval-analysis` come first; thresholds tuned on marked rides, one session held out; the compression measure is chosen by the marks (R3) | Pass |
| III | Scale-, perspective-, mirror-invariant | All measures are body-relative ratios; direction changes use pool coordinates; left/right turns treated alike | Pass |
| IV | Assume the camera moves | Handheld follow-cam supported: body ratios are zoom-invariant; pool-coordinate movement is used only when the session has a confirmed zone and no camera motion in that span (epochs), else turns come from compression + image motion of the rider relative to the wave | Pass |
| V | Confirm late, start early | Ending is decided from the whole ride end, not the first dip | Pass |
| VI | Human corrections are ground truth | Ending/turn corrections and trick tags are append-only edits re-attached by ride span | Pass |
| VII | Staged, cached pipeline | `analysis` stage, cache per ride (span + rider + settings + code version) | Pass |
| VIII | Simple first | Rules on two signals (compression, lateral motion); no learned classifier; trick detection deferred | Pass |
| IX | Config, not constants | `[analysis_pose]` section (rate, model, smoothing, thresholds) | Pass |
| X | Engineering standards | Library `surfclip/analysis/`, CLI, thin API, UI without analysis logic | Pass |
| XI | Scope discipline | No absolute angles, no 3D, no trick recognition, no cross-surfer comparison (future) | Pass |

## Project Structure

```text
specs/004-ride-analysis/
├── plan.md  research.md  data-model.md  quickstart.md  tasks.md
├── contracts/{http-api.md, session-files.md, cli.md}
└── checklists/requirements.md

config/default.toml                  # + [analysis_pose]
src/surfclip/analysis/
├── pose.py         # decode ride, crop, YOLO-pose, keypoints parquet
├── signals.py      # compression signal, lateral motion, unclear spans
├── events.py       # turns, pumps, trimming, ending
├── summary.py      # per-ride measures, fall comparison, session shares, trends
├── marks.py        # evaluation marks (labels/analysis) and eval-analysis
└── service.py      # analysis stage: which rides, cache, apply corrections
src/surfclip/stages.py               # AnalysisStage after riders
src/surfclip/store/schemas.py        # RideAnalysis, AnalysisFile, new EditOps
src/surfclip/api/app.py              # analysis, keypoints, marks, tags, trends routes
src/surfclip/cli.py                  # analyse, eval-analysis
web/src/lib/Skeleton.svelte          # overlay canvas on the review video
web/src/lib/AnalysisStrip.svelte     # compression curve + events under the player
web/src/routes/Marks.svelte          # #/marks/<id>: mark turns and endings
web/src/routes/Analysis.svelte       # #/analysis/<id>: rides, shares, fall comparison, tricks
web/src/routes/Trends.svelte         # #/trends/<name>
tests/unit/test_analysis_*.py, tests/contract/test_api_analysis.py
```

## Complexity Tracking

No violations.
