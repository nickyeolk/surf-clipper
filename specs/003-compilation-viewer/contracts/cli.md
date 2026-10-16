# CLI (003 additions)

```text
surfclip export SESSION --reel --rider NAME     # now the captioned compilation
surfclip still SESSION --at 2:30.4              # save the frame at that source time
surfclip serve [--log PATH]                     # --log: write server output to a file
```

`--at` takes seconds or m:ss(.f). Prints the still's path. Exit 1 when outside the video.
