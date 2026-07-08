# /burn-subs — Hard-Burn Subtitles Into Video

Hard-burn an SRT subtitle file into a video using ffmpeg's `subtitles` filter. The video is re-encoded (H.264, yuv420p); audio is copied through.

## Arguments
- `$ARGUMENTS` — path to the video file, path to the SRT file, and optionally an explicit output path.

## Steps

### 1. Run Burn-In
```bash
./scripts/burn-subs.sh "$ARGUMENTS"
```

By default this writes `<video_basename>_subbed.mp4` next to the input video (always `.mp4`, regardless of input container). Pass a third argument to override the output path.

### 2. Verify Output
- Output file exists and is non-empty.
- ffprobe reports a video stream and a duration within ~0.5s of the input.
- Spot-check a frame mid-clip to confirm the rendered subtitle text is visible.

### 3. Report
Show:
- Output file path
- Input vs output duration
- Codec/pixel-format of the output (`libx264` / `yuv420p`)
