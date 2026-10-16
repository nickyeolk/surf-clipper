# scripts/

Helpers around the `surfclip` CLI. Python scripts run in the WSL venv:
`wsl -d Ubuntu --cd <repo> -- bash scripts/wsl-run.sh uv run python scripts/<name>.py ...`.
Each script's header has its usage.

## Environment and server

| Script | What it does |
| --- | --- |
| `wsl-env.sh`, `wsl-run.sh` | WSL environment (venv location, Node/IPv4 settings); run a command in it |
| `check.sh` | ruff format/lint, pyright, pytest |
| `serve.cmd` | Windows launcher for `surfclip serve` with a console window (fallback) |
| `windows/install-shortcuts.ps1` | One-time: build the UI, put "Surf Clipper" / "Stop Surf Clipper" on the Desktop |
| `windows/start.ps1`, `windows/stop.ps1` | Hidden start (waits for `/api/health`, opens the browser; log in `artifacts/logs/server.log`) and stop (`/api/shutdown`) |

## Running and scoring sessions

| Script | What it does |
| --- | --- |
| `run_eval_sessions.sh` | confirm each session's zone from `labels/zones/` and run the pipeline |
| `rerun_rides.sh` | re-run the cached pipeline, one summary line per session |
| `eval_session.sh` | re-run one session, score it against its labels, list cut and false rides |
| `eval_details.py` | per-ride boundary errors: CUT, FALSE and MISSED |
| `pad_sweep.py` | completeness and tightness for a grid of clip paddings |
| `label_summary.py` | verdict counts in a label work file |

## Diagnostics

| Script | What it does |
| --- | --- |
| `probe_samples.sh`, `keyframes.sh`, `contact_sheet.sh` | probe sources, extract stills, contact sheets |
| `inspect_session.py` | tracks, evidence and short attempts of a session |
| `trace_window.py` | every observation and its evidence in a time window |
| `draw_tracks.py` | tracked people and the zone drawn on frames |
| `draw_zone.py`, `feet_map.py` | a zone, or riders' feet, drawn over a keyframe |
| `feet_vs_zone.py` | spread of moving riders' feet in pool coordinates (zone proposal design) |
| `face_band_stats.py` | wave-face depth distribution per session |
| `edge_report.py` | share of riding frames cut off by the frame edge |
