#!/usr/bin/env bash
# Probe the evaluation sessions (read-only). Usage: probe_samples.sh NAME... (without extension)
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
SRC_DIR="${SURFCLIP_SAMPLES:-/mnt/c/Users/likkhian/OneDrive/Media/trifecta}"
for name in "$@"; do
  match=$(find "$SRC_DIR" -maxdepth 1 -iname "$name.*" | head -1)
  if [ -z "$match" ]; then echo "$name: NOT FOUND"; continue; fi
  printf "%s (%s): " "$(basename "$match")" "$(du -h "$match" | cut -f1)"
  uv run --quiet surfclip probe "$match" 2>&1 | tail -1
done
