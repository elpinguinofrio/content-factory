# LLM + Video Editing Automation: Research Notes

_Date: 2026-03-25_

---

## 1. Core Pattern: Transcript → LLM → Cut List → FFmpeg

The dominant workflow emerging across projects:

1. **Transcribe** raw video with Whisper (local) → get word-level timestamps (SRT/JSON)
2. **Feed transcript + prompt** to LLM (Claude/GPT) asking for editorial decisions
3. **LLM returns** structured output: timestamps, segment labels, or FFmpeg commands
4. **Execute cuts** via FFmpeg concat demuxer, filter_complex, or moviepy

This avoids GUI editing entirely. The LLM acts as the "editor brain" deciding what stays, what goes, and what gets emphasis.

---

## 2. Claude Code Skills Approach (chrislema/videoeditor)

Chris Lema's pipeline: **8 markdown skill files**, each describing one post-production step. Claude Code reads and executes them sequentially. Dependencies: only ffmpeg + local whisper.

| Step | What it does |
|------|-------------|
| 1. Silence trim | Detect pauses >0.5s, reduce to 0.3s via ffmpeg |
| 2. Transcription | Whisper → timed transcript sections |
| 3. Editorial categorization | LLM labels sections: "normal" / "emphasis" / "critical" (40/35/25% distribution, 3-7s segments) |
| 4. Dynamic zoom | OpenCV face detection → zoom levels per category (1x / 1.25x / 1.6x) |
| 5. Color correction | Warm-punch preset for indoor talking-head |
| 6. Audio mastering | Highpass, presence EQ, compression, loudness normalization |
| 7. Caption burning | Styled subtitles baked into video |
| 8. Resolution scaling | 4K → HD output |

Key insight: expertise encoded as markdown files = portable. Any AI agent can execute the same professional workflow.

- Source: https://chrislema.com/claude-code-skills-for-video-editing
- Repo: https://github.com/chrislema/videoeditor

---

## 3. digitalsamba/claude-code-video-toolkit

A more ambitious toolkit with 11 slash commands and 17 Python tools. Oriented toward **generating** videos (not just editing existing footage).

**Skills:** Remotion, ElevenLabs, FFmpeg, Playwright Recording, Frontend Design, Qwen Edit, ACEStep (AI music), RunPod (cloud GPU)

**Pipeline:** Script → Assets → Scene Review → Design → Audio → Config → Preview → Render

**Key commands:** `/video` (create project from template), `/record-demo` (browser recording), `/generate-voiceover`, `/voice-clone`

- Repo: https://github.com/digitalsamba/claude-code-video-toolkit

---

## 4. Proof-of-Concept: LLM Rough Cuts (mitch7w/ai-video-editor)

Simplest demo of the pattern. Places input videos in a folder, LLM (Claude 3.5 Sonnet) analyzes transcripts, outputs cut decisions, ffmpeg/moviepy assembles the result.

- Limitation: only works with dialogue-heavy video
- Rough output — still includes some pauses/mistakes
- Repo: https://github.com/mitch7w/ai-video-editor

---

## 5. CLI Tools for Automated Cutting

### auto-editor (4.1k stars) — the standout
Best-in-class CLI for silence/motion-based editing. No LLM needed for basic cuts.

```
auto-editor input.mp4 --edit audio:threshold=0.04
auto-editor input.mp4 --edit motion:threshold=0.02
auto-editor input.mp4 --margin 0.2s
auto-editor input.mp4 --export premiere  # or resolve, fcpxml, shotcut, kdenlive
```

Exports to: Premiere Pro XML, DaVinci Resolve, Final Cut Pro, ShotCut, Kdenlive, clip-sequence.

- Repo: https://github.com/WyattBlue/auto-editor

### Other silence removers
| Tool | Stars | Notes |
|------|-------|-------|
| unsilence | ~600 | pip install, speed-based approach |
| jumpcutter | ~400 | Python + ffmpeg wrapper |
| auto-silence-cut | ~100 | Outputs DaVinci Resolve timeline |

---

## 6. Declarative Video Assembly (JSON/JS spec → video)

### editly (Node.js)
Declarative NLE via JSON spec. Define clips, transitions, layers, audio in a JSON5 file → renders via ffmpeg streaming (no temp files).

```json
{
  "outPath": "out.mp4",
  "clips": [
    { "layers": [{ "type": "video", "path": "clip1.mp4" }] },
    { "transition": { "name": "crossfade" }, "layers": [{ "type": "title", "text": "Hello" }] }
  ]
}
```

- Repo: https://github.com/mifi/editly

### Remotion (React → video)
Each frame = React component. Claude Code has official Remotion Skills integration (Jan 2026). Best for templated/generated content (intros, data viz, social media).

```
npx create-video@latest
# Claude Code writes React components → renders to MP4
```

- Docs: https://www.remotion.dev/docs/ai/claude-code

### Shotstack (cloud API)
JSON template → REST API → rendered video. SDKs for Python and Node.js. Merge fields for dynamic content (like mail merge for video). Pay-per-render.

- API: https://shotstack.io/docs/api/
- Python SDK: https://github.com/shotstack/shotstack-sdk-python
- Node SDK: https://github.com/shotstack/shotstack-sdk-node

---

## 7. Transcript → FFmpeg: The Plumbing

### Concat demuxer approach (no re-encode)
LLM outputs a list of `{start, end}` timestamps. Convert to concat file:

```
# segments.txt
file 'input.mp4'
inpoint 10.5
outpoint 25.3

file 'input.mp4'
inpoint 30.0
outpoint 45.7
```

```bash
ffmpeg -f concat -safe 0 -i segments.txt -c copy output.mp4
```

### filter_complex approach (with re-encode, more flexible)
LLM generates trim + concat filter chains:

```bash
ffmpeg -i input.mp4 \
  -filter_complex "[0:v]trim=10.5:25.3,setpts=PTS-STARTPTS[v0]; \
                    [0:v]trim=30.0:45.7,setpts=PTS-STARTPTS[v1]; \
                    [v0][v1]concat=n=2:v=1:a=0[outv]" \
  -map "[outv]" output.mp4
```

### Python bridge libraries
| Library | Language | Use case |
|---------|----------|----------|
| moviepy 2.0 | Python | Cuts, concat, compositing, effects. New v2 API (v1 deprecated) |
| pydub | Python | Audio manipulation (silence detection, splitting) |
| vidpy | Python | High-level wrapper around MLT framework |
| ffmpeg-python | Python | Pythonic ffmpeg command builder |

---

## 8. AI Video Search & Indexing

### VideoDB / PromptClip
Indexes video by transcript + visual content. Query with natural language ("show funny moments") → returns clips with timestamps. Uses any LLM (Claude, GPT, Gemini). Free tier: 50 uploads.

- Repo: https://github.com/video-db/PromptClip
- Docs: https://docs.videodb.io/promptclip-use-power-of-llm-to-create-clips-52

---

## 9. Open-Source Text-Based Editors (Descript alternatives)

| Project | Stars | Tech | Notes |
|---------|-------|------|-------|
| CutScript | ~46 | Electron + React + FastAPI | Edit video by editing transcript text. Local-first |
| montage-ai | ~21 | Python + Docker | Beat-synced editing, transcript-based, exports EDL/OTIO/CSV, 7 style templates, vertical reframe |
| Audapolis | ~300 | Electron | Free, open-source, text-based audio editing |

CutScript repo: https://github.com/DataAnts-AI/CutScript
montage-ai repo: https://github.com/mfahsold/montage-ai

---

## 10. Academic: L-Storyboard (arxiv 2505.12237)

Converts video shots → structured markdown tables (shot ID, visual description, cinematic attributes, audio/subtitles, timestamps). Feeds these to LLMs for:
- Shot attribute classification
- Next-shot selection
- Sequence ordering (StoryFlow: generate candidates at varying temperatures, pick best)

Key idea: LLMs can't watch video, but they can reason about structured text descriptions of shots.

- Paper: https://arxiv.org/html/2505.12237v1

---

## 11. Practical Architecture for Terminal/Claude Code

**Minimal viable pipeline (what you can build today):**

```
raw_video.mp4
    │
    ├─ whisper --model large-v3 --output_format json → transcript.json
    │
    ├─ Claude/GPT: "Given this transcript, return JSON array of
    │   {start, end, label, reason} for segments to keep/cut/emphasize"
    │
    ├─ Python script: parse LLM output → generate ffmpeg concat file
    │   OR filter_complex command
    │
    ├─ auto-editor: silence removal pass (pre or post LLM cuts)
    │
    └─ ffmpeg: final assembly + audio normalization + captions
```

**Dependencies:** whisper (or whisper.cpp), ffmpeg, auto-editor, Python, Claude API key.

**What works well today:** silence removal, transcript-based rough cuts, template video generation (Remotion), caption burning.

**What's still rough:** LLM-generated ffmpeg filter_complex commands (LLMs struggle with complex filter syntax details), semantic scene analysis without multimodal input, maintaining A/V sync through complex edit chains.

---

## Sources

- https://chrislema.com/claude-code-skills-for-video-editing
- https://github.com/digitalsamba/claude-code-video-toolkit
- https://github.com/mitch7w/ai-video-editor
- https://github.com/WyattBlue/auto-editor
- https://github.com/mifi/editly
- https://www.remotion.dev/docs/ai/claude-code
- https://shotstack.io/docs/api/
- https://github.com/video-db/PromptClip
- https://github.com/DataAnts-AI/CutScript
- https://github.com/mfahsold/montage-ai
- https://arxiv.org/html/2505.12237v1
- https://github.com/Winston-503/automatic_video_editing
- https://towardsdatascience.com/automate-video-chaptering-with-llms-and-tf-idf-f6569fd4d32b/
- https://wonderingaboutai.substack.com/p/i-built-a-video-post-production-pipeline
