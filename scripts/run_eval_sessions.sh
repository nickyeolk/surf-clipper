#!/usr/bin/env bash
# Process evaluation sessions one after another (GPU work is not run in parallel).
# Confirms each session's zone from labels/zones/<name>.json, then runs the pipeline.
# Usage: run_eval_sessions.sh NAME... (file names without extension)
set -u
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
SRC_DIR="${SURFCLIP_SAMPLES:-/mnt/c/Users/likkhian/OneDrive/Media/trifecta}"
for name in "$@"; do
  src=$(find "$SRC_DIR" -maxdepth 1 -iname "$name.*" | head -1)
  echo "=== $name ($src) $(date +%H:%M)"
  uv run --quiet surfclip zone "$src" --from-file "labels/zones/$name.json"
  uv run --quiet surfclip run "$src" --timings 2>&1 | grep -v -E "FutureWarning|sv.ByteTrack|tracker = "
done
echo "=== all done $(date +%H:%M)"
