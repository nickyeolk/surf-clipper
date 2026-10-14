#!/usr/bin/env bash
# One contact sheet per clip: a frame every STEP seconds, 6 per row, with timestamps.
# Usage: contact_sheet.sh STEP CLIP... ; writes CLIP.sheet.jpg next to each clip.
set -e
STEP="$1"; shift
for clip in "$@"; do
  ffmpeg -v error -y -i "$clip" -vf \
    "fps=1/$STEP,scale=320:-2,drawtext=text='%{pts\:hms}':x=6:y=6:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.5,tile=6x3" \
    -frames:v 1 "${clip%.mp4}.sheet.jpg"
  echo "${clip%.mp4}.sheet.jpg"
done
