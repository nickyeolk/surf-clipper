#!/usr/bin/env bash
# Extract one still per session for zone drafting. Usage: keyframes.sh SECONDS NAME...
# NAME is the file name without extension. Reads the sample folder only; writes to
# artifacts/review/. HDR sources are tone-mapped so the still looks like the scene.
set -e
cd "$(dirname "$0")/.."
SRC_DIR="${SURFCLIP_SAMPLES:-/mnt/c/Users/likkhian/OneDrive/Media/trifecta}"
T="$1"; shift
mkdir -p artifacts/review
for name in "$@"; do
  src=$(find "$SRC_DIR" -maxdepth 1 -iname "$name.*" | head -1)
  trc=$(ffprobe -v error -select_streams v:0 -show_entries stream=color_transfer -of csv=p=0 "$src")
  vf="null"
  if [ "$trc" = "arib-std-b67" ] || [ "$trc" = "smpte2084" ]; then
    vf="zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
  fi
  out="artifacts/review/key_${name}_${T}.jpg"
  ffmpeg -v error -y -ss "$T" -i "$src" -frames:v 1 -vf "$vf" "$out"
  rot=$(ffprobe -v error -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 "$src" | head -1)
  echo "$out (rotation: ${rot:-none})"
done
