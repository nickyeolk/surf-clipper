#!/usr/bin/env bash
# Run a command from the repo root inside WSL with the project environment, e.g.
#   wsl -d Ubuntu --cd <repo> -- bash scripts/wsl-run.sh uv sync
set -e
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
"$@"
