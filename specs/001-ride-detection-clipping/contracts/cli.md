# Contract: `surfclip` CLI (001)

All commands accept `--artifacts DIR` (default `./artifacts`) and `--config FILE` (default
`config/default.toml`). Exit code 0 on success, 2 on invalid input, 1 on processing error.
`--json` prints machine-readable output to stdout; logs go to stderr.

| Command | Purpose | Key options | Output |
| --- | --- | --- | --- |
| `surfclip probe VIDEO` | Read metadata; validate input | | SourceInfo |
| `surfclip ingest VIDEO` | Create session; build analysis proxy, review copy, thumbnails | `--min-length S` | session_id |
| `surfclip analyse SESSION` | Detection, tracking, epochs, zone proposals | `--cpu` | stage summary |
| `surfclip zone SESSION --accept EPOCH` | Confirm proposed zone (CLI alternative to UI) | `--from-file zone.json` | edit appended |
| `surfclip rides SESSION` | State machine, linking, refinement → `rides.json` | | ride count, short attempts |
| `surfclip run VIDEO` | ingest → analyse → (wait for zone confirmations) → rides | `--min-length S` | session_id |
| `surfclip export SESSION` | Export final clips for new/changed rides | `--all`, `--rides ID,...`, `--cpu` | list of clip paths |
| `surfclip serve` | Start backend + UI on 127.0.0.1 | `--port 8765` | URL |
| `surfclip eval SESSION --labels FILE` | Metrics SC-001…SC-005 for one session | | metrics JSON |
| `surfclip eval all --labels-dir DIR` | Metrics for every labelled session, per session | `--exclude-held-out` | table |
| `surfclip eval make-shifts VIDEO` | Generate synthetic shift test clips | `--kinds jump,drift,zoom` | clip paths |

Invariants:
- No command writes outside `--artifacts` except `export --out DIR` if given.
- No command opens the source video for writing.
- Re-running any command never modifies `edits.json`.
