#!/usr/bin/env bash
# Re-run the (cached) pipeline for evaluation sessions and print one summary line each.
# Detection and tracking come from the cache unless their config or code changed.
# Usage: rerun_rides.sh NAME... (file names without extension)
set -u
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
SRC_DIR="${SURFCLIP_SAMPLES:-/mnt/c/Users/likkhian/OneDrive/Media/trifecta}"
for name in "$@"; do
  src=$(find "$SRC_DIR" -maxdepth 1 -iname "$name.*" | head -1)
  printf "%-22s " "$name"
  uv run --quiet surfclip run "$src" 2>/dev/null | head -1
done
