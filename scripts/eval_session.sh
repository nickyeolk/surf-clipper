#!/usr/bin/env bash
# Re-run the cached pipeline for a session, score it against its labels, list large errors.
# Usage: eval_session.sh NAME (file name without extension)
set -u
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
SRC_DIR="${SURFCLIP_SAMPLES:-/mnt/c/Users/likkhian/OneDrive/Media/trifecta}"
src=$(find "$SRC_DIR" -maxdepth 1 -iname "$1.*" | head -1)
uv run --quiet surfclip run "$src" --timings 2>&1 | grep -E "^  (track|rides) |rides,"
uv run --quiet surfclip eval "$src"
echo "--- rides with >= 1 s boundary error, and false rides"
uv run --quiet python scripts/eval_details.py "$src" | grep -v MISSED
