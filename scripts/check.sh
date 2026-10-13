#!/usr/bin/env bash
# Format, lint, type-check and test. Usage (from Windows):
#   wsl -d Ubuntu --cd <repo> -- bash scripts/check.sh [pytest args]
set -u
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
echo "== ruff";    uv run ruff format src tests scripts | tail -1; uv run ruff check src tests --fix | tail -3
echo "== pyright"; uv run pyright 2>&1 | grep -E " error: |[0-9]+ errors?," | cut -c1-200 | tail -15
echo "== pytest";  uv run pytest -q "$@" 2>&1 | tail -15
