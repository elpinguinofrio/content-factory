# /edit-transcript — Analyze Transcript and Produce Keep-Ranges

Read an existing transcript JSON and make editorial decisions about what to keep and cut.

## Arguments
- `$ARGUMENTS` — path to the `.transcript.json` file (required)

## Steps

### 1. Read Transcript
Read the transcript JSON file. Understand the full content, noting timestamps.

### 2. Editorial Analysis
Analyze each segment and decide keep or cut. Criteria:
- **CUT**: filler words (uh, um, э, ну, значит, короче), repeated takes, long silences, off-topic tangents, false starts, self-corrections, mumbling
- **KEEP**: main points, examples, stories, emotional moments, jokes, hooks, calls to action, natural transitions between topics

Consider the content as a whole — preserve narrative flow. Don't create jarring jumps.

### 3. Output Keep-Ranges
Write a JSON file `<basename>.keep-ranges.json` next to the transcript:
```json
[
  {"start": 5.2, "end": 42.8, "reason": "intro + hook"},
  {"start": 65.0, "end": 118.5, "reason": "main point 1 with example"}
]
```

### 4. Summary
Present a table:
| Segment | Time | Duration | Action | Reason |
Show estimated output duration vs input, and percentage cut.

Ask the user if they want to adjust any decisions before assembling.
