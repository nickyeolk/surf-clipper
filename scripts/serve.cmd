@echo off
rem Double-click to start Surf Session Clipper, then open http://localhost:8765 in Chrome or Edge.
rem The server runs in WSL and listens on this laptop only. Close this window to stop it.
cd /d "%~dp0.."
start "" http://localhost:8765
wsl -d Ubuntu --cd "%CD%" -- bash scripts/wsl-run.sh uv run surfclip serve
