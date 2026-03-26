# /transcribe — Transcribe Video with Word-Level Timestamps

Transcribe a video file to JSON (word-level timestamps) and SRT.

## Arguments
- `$ARGUMENTS` — path to the video file (required)

## Steps

### 1. Run Transcription
```bash
./scripts/transcribe.sh "$ARGUMENTS"
```

### 2. Verify Output
Read the generated `.transcript.json` and confirm:
- Word-level timestamps are present
- Language detection is correct
- No obviously broken segments

### 3. Report
Show:
- Output file paths
- Detected language
- Total duration
- Number of segments
- First few lines of transcript as preview
