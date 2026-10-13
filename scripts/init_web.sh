#!/usr/bin/env bash
# One-off: scaffold web/ with Vite + Svelte + TypeScript (T005). Safe to re-run: skips if present.
set -e
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source scripts/wsl-env.sh
if [ -f web/package.json ]; then echo "web/ already initialised"; exit 0; fi
rm -rf web && npm create vite@6.5.0 web -- --template svelte-ts >/dev/null
cd web
npm install --no-fund --no-audit >/dev/null
echo "svelte $(node -p "require('svelte/package.json').version"), vite $(node -p "require('vite/package.json').version")"
