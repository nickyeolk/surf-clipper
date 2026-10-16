# Quickstart: Compilations, Stills, Viewer and Packaging

## One-time install

From the repo in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-shortcuts.ps1
```

This builds the web UI and puts **Surf Clipper** and **Stop Surf Clipper** on the Desktop.

## Use

1. Double-click **Surf Clipper**. The browser opens on Sessions within a minute.
2. A banner shows if the GPU or a model is missing; **Download models** fetches the weights.
3. In **Riders**, name yourself, then **Compilation** on your card: one video of your rides, each
   with "me · ride 3 of 12 · 10:42" for its first 3 seconds.
4. **Exports** (from Sessions or Riders) lists compilations, clips per rider and stills. Play at
   full quality, step frames with `,` and `.`, slow down to 0.5x or 0.25x.
5. On a good frame press **Save still** (in Review or Exports): a full-resolution JPEG in
   `clips/stills/`.
6. **Stop** on the Sessions page or **Stop Surf Clipper** on the Desktop.

## Checks

- `ffprobe clips/reel_me.mp4` on an HLG session shows `arib-std-b67` and `bt2020`.
- The still opens in Photos at the source resolution.
