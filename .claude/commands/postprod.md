# /postprod — Full Auto Post-Production Pipeline

Run the complete post-production pipeline on a video file: transcribe → editorial analysis → assemble → normalize audio.

## Arguments
- `$ARGUMENTS` — path to the video file (required)

## Steps

### 1. Transcribe
Run the transcription script:
```bash
./scripts/transcribe.sh "$ARGUMENTS"
```
This produces `<basename>.transcript.json` (word-level timestamps) and `<basename>.srt`.

### 2. Read Transcript
Read the generated `.transcript.json` file. Understand the full content.

### 3. Editorial Analysis
Analyze the transcript and produce a keep/cut decision for each segment. Criteria:
- **CUT**: filler words (uh, um, э, ну), repeated takes, long pauses already trimmed, off-topic tangents, false starts, self-corrections
- **KEEP**: main points, examples, stories, jokes, hooks, calls to action, natural transitions

Output a JSON array of keep-ranges to a file `<basename>.keep-ranges.json`:
```json
[
  {"start": 5.2, "end": 42.8, "reason": "intro + hook"},
  {"start": 65.0, "end": 118.5, "reason": "main point 1"}
]
```

Write the file using the Write tool. Also summarize what was cut and why.

### 4. Assemble
Run the assembly script with the keep-ranges:
```bash
python scripts/assemble.py "$ARGUMENTS" "<basename>.keep-ranges.json" --fix-audio
```

### 5. Normalize Audio
Run audio normalization on the assembled output:
```bash
./scripts/normalize-audio.sh "<basename>_assembled.mp4"
```

### 6. Report
Summarize results:
- Input duration vs output duration
- What percentage was cut
- List of what was removed and why
- Output file paths (assembled video, SRT for captions, transcript JSON)
