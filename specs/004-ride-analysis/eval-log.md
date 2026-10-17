# Evaluation log: 004

## 2026-10-17 Pose spike

See research.md R1: 99-100% joint visibility at 85-360 px (handheld 1080p and fixed 720p);
YOLO11s and 11x agree closely. Rider size varies 3x within a fixed-camera ride → body ratios only.

## 2026-10-17 Analysis stage timing (SC-004)

20241004 (720p, 18 named rides): 1.8 min for pose + measures (6 s per ride); re-measuring with
cached keypoints 10 s for all 18.

## 2026-10-17 T017: comparison sync (SC-001)

Browser pane, two 20241004 rides (r007836 vs r013296), playing at 0.5x for 12 s: the gap between
the two sides' "time from sync" stayed 0.000 s (A 5.0326 s, B 5.0327 s past their syncs).
Skeletons sit on the riders after fixing a global `video { max-height }` that shrank the video
under the overlay canvas. Still to check at 0.25x and 1x on a longer stretch.

## 2026-10-17 T021: reference import (SC-003)

60 s cut of 20250206 in a scratch folder: probe → review copy → detect → track 17 s, analysis
5 s (22 s total, target ≤ 3 min). The test picked the longest-visible person automatically
(a bystander: 56% unclear, no turns); in use the surfer is clicked. Still to try with a real
reference clip chosen by the user.