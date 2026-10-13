#!/usr/bin/env bash
# T001 (d) prep: full-length review copy (720p H.264 SDR, keyframe every 0.5 s, faststart).
# Reads the source only; writes to artifacts/spikes/t001/.
set -e
SRC="${1:?source video}"
OUT="${2:-artifacts/spikes/t001/review.mp4}"
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 "$SRC")
GOP=$(python3 -c "from fractions import Fraction as F; print(max(1, round(F('$FPS') / 2)))")
start=$(date +%s)
ffmpeg -hide_banner -loglevel error -y -hwaccel cuda -i "$SRC" -an \
  -vf "scale=-2:'min(720,ih)'" -c:v h264_nvenc -preset p4 -g "$GOP" -bf 0 \
  -movflags +faststart "$OUT"
echo "review copy: $(du -h "$OUT" | cut -f1) in $(( $(date +%s) - start ))s (GOP $GOP frames)"
