# /translate — Translate Transcript Preserving Timestamps

Translate a transcript JSON (produced by `/transcribe`) into another language while keeping every segment's `start`/`end` timestamps exactly intact, and emit a sibling SRT for captions.

## Arguments
- `$ARGUMENTS` — path to a `<basename>.transcript.json` file (required), and optionally a target language code (default `es`).

## Steps

### 1. Run Translation
```bash
./scripts/translate.sh "$ARGUMENTS"
```

This produces, next to the input:
- `<basename>.<lang>.transcript.json` — same segment count, same `start`/`end`, translated `text`.
- `<basename>.<lang>.srt` — SRT cues using the preserved timestamps.

### 2. Verify Output
Read the generated `.<lang>.transcript.json` and confirm:
- Segment count matches the input transcript
- Every `start` / `end` is identical to the input (no rounding, no shifting)
- `language` field equals the target language code
- No empty `text` fields and no segments left in the source language

### 3. Report
Show:
- Output file paths
- Target language
- Number of segments
- First few translated lines as preview
