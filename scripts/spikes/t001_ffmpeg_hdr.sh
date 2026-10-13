#!/usr/bin/env bash
# T001 (a) + (c): ffmpeg filter support and HDR colour-tag round-trip through hevc_nvenc.
# Generates synthetic 10 s HDR sources; never touches sample footage.
set -u
OUT="${1:-artifacts/spikes/t001}"
mkdir -p "$OUT"

echo "== tools"
for t in uv node npm docker; do printf "%-7s %s\n" "$t" "$(command -v "$t" || echo missing)"; done

echo "== (a) filters"
for f in zscale tonemap tonemap_cuda scale_cuda; do
  if ffmpeg -hide_banner -filters 2>/dev/null | grep -qw "$f"; then echo "$f: yes"; else echo "$f: NO"; fi
done

tags() { ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,profile,pix_fmt,color_primaries,color_transfer,color_space \
  -of compact=p=0 "$1"; }

make_src() {  # $1 name, $2 transfer
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 10 \
    -pix_fmt yuv420p10le -c:v libx265 -preset ultrafast -x265-params log-level=error \
    -color_primaries bt2020 -color_trc "$2" -colorspace bt2020nc "$OUT/src_$1.mp4"
}

reencode() {  # copy tags from probe of source onto an NVENC main10 encode of a 4 s cut
  local src="$1" dst="$2" trc
  trc=$(ffprobe -v error -select_streams v:0 -show_entries stream=color_transfer -of csv=p=0 "$src")
  ffmpeg -hide_banner -loglevel error -y -ss 3 -i "$src" -t 4 -an \
    -c:v hevc_nvenc -profile:v main10 -pix_fmt p010le -preset p5 \
    -color_primaries bt2020 -color_trc "$trc" -colorspace bt2020nc "$dst"
}

echo "== (c) HDR round-trip"
for kind in hlg:arib-std-b67 pq:smpte2084; do
  name=${kind%%:*}; trc=${kind#*:}
  make_src "$name" "$trc"
  reencode "$OUT/src_$name.mp4" "$OUT/clip_$name.mp4"
  echo "source $name: $(tags "$OUT/src_$name.mp4")"
  echo "clip   $name: $(tags "$OUT/clip_$name.mp4")"
done
