# Text-Based Video Editing & Automated Post-Production via CLI

Research date: 2026-03-25

## 1. Text-Based Editing Workflow (Transcript → Edit Text → Re-assemble Video)

The core idea: transcribe video with word-level timestamps, present the transcript as editable text, delete/rearrange text, and the corresponding video segments are automatically cut/reordered.

### Commercial tools (for reference)
| Tool | Model | Notes |
|------|-------|-------|
| Descript | SaaS, desktop app | The pioneer. Transcribe → edit text → video follows. Exports to Premiere/Resolve/FCP. Overdub (AI voice). |
| Adobe Premiere Pro | Built-in since 2023 | Text-Based Editing panel. Transcript synced to timeline. Delete text = delete clip segment. |
| Clipchamp (Microsoft) | Web/desktop | Highlight transcript text → delete → video splits automatically. |
| CapCut | Mobile/desktop | Similar transcript-based flow. |
| Gling | SaaS | Specifically for YouTubers. Auto-removes bad takes and silences from transcript. |
| OpusClip | SaaS | Auto-clips long videos into shorts using transcript + AI virality scoring. |

### Open-source / CLI alternatives
| Tool | Stack | Status | URL |
|------|-------|--------|-----|
| OpenScript | TypeScript, Whisper, FFmpeg.wasm | Early dev (2025), local-first Descript alternative | https://github.com/preston176/openscript |
| vcut | — | Text-based editor, edit video by editing transcript | https://github.com/msnodderly/vcut |
| videotextcut | — | Auto-trim based on edited transcripts | https://github.com/tanzir71/videotextcut |

### DIY pipeline (Whisper + FFmpeg + Python)
The most practical approach for CLI/scripting:
1. **Transcribe** with Whisper (or faster-whisper) → get word-level timestamps in JSON/SRT
2. **Edit the transcript** in any text editor — delete unwanted sections, note the timestamp ranges to keep
3. **Feed timestamp ranges to FFmpeg** to extract and concatenate segments (see Section 3)

```
video.mp4 → whisper → transcript.json (with word timestamps)
                         ↓
              human/LLM edits transcript, produces keep-ranges.json
                         ↓
              ffmpeg cuts segments → concat → final.mp4
```

---

## 2. auto-editor — Silence Removal & Jump Cuts

**Repo:** https://github.com/WyattBlue/auto-editor (4.1k stars, Public Domain)
**Install:** `pip install auto-editor` or `brew install auto-editor`
**Language:** Nim (rewritten from Python), latest v30.0.0 (Mar 2026)

### Core concept
Analyzes audio loudness (or motion) frame-by-frame, marks segments as "loud" or "silent", removes silent parts, re-renders.

### Key commands
```bash
# Basic silence removal (default threshold 4%)
auto-editor input.mp4

# Adjust silence threshold
auto-editor input.mp4 --edit audio:threshold=0.03
auto-editor input.mp4 --edit audio:-19dB

# Motion-based editing (remove static frames)
auto-editor input.mp4 --edit motion:threshold=0.02

# Combine audio + motion
auto-editor input.mp4 --edit "(or audio:0.03 motion:0.06)"

# Add padding around cuts (feels more natural)
auto-editor input.mp4 --margin 0.2sec
auto-editor input.mp4 --margin 0.3s,1.5sec   # asymmetric: 0.3s before, 1.5s after

# Manual cut ranges
auto-editor input.mp4 --cut-out 0,30sec              # remove first 30s
auto-editor input.mp4 --cut-out -10sec,end            # remove last 10s
auto-editor input.mp4 --add-in 0,30sec                # force-keep first 30s

# Export as NLE timeline (no re-encoding!)
auto-editor input.mp4 --export premiere               # Premiere Pro XML
auto-editor input.mp4 --export resolve                # DaVinci Resolve
auto-editor input.mp4 --export final-cut-pro          # FCP XML
auto-editor input.mp4 --export shotcut
auto-editor input.mp4 --export kdenlive
auto-editor input.mp4 --export clip-sequence          # individual clip files

# Export with custom timeline name
auto-editor input.mp4 --export 'premiere:name="My Edit"'

# Render from an XML timeline
auto-editor myFcp7File.xml -o render.mp4
```

### Other silence removal tools
| Tool | Notes |
|------|-------|
| jumpcutter (carykh) | Python, PyPI. Original viral tool. Inactive/unmaintained. |
| auto-silence-cut | Python. V2 (2025) — 2-4x faster. Outputs DaVinci Resolve-compatible edits. |
| SavvyCut | SaaS. AI "Smart Cut" with speech detection. |
| Recut | macOS app. Drag-and-drop silence removal. |
| TimeBolt | Desktop app. Visual silence/filler-word removal. |

---

## 3. FFmpeg Commands for Cutting & Concatenating by Timestamps

### Cut a single segment
```bash
# Fast copy (keyframe-aligned, not frame-accurate)
ffmpeg -ss 00:01:30 -to 00:02:45 -i input.mp4 -c copy segment.mp4

# Frame-accurate (re-encodes, slower)
ffmpeg -i input.mp4 -ss 00:01:30 -to 00:02:45 -c:v libx264 -c:a aac segment.mp4
```
Note: `-ss` before `-i` = fast seek (keyframe). `-ss` after `-i` = slow seek (frame-accurate).

### Cut multiple segments and concatenate
**Method 1: Concat demuxer (fast, stream-copy)**
```bash
# 1. Cut segments
ffmpeg -ss 00:00:10 -to 00:00:45 -i input.mp4 -c copy seg1.mp4
ffmpeg -ss 00:01:20 -to 00:02:00 -i input.mp4 -c copy seg2.mp4
ffmpeg -ss 00:03:10 -to 00:04:30 -i input.mp4 -c copy seg3.mp4

# 2. Create file list
echo "file 'seg1.mp4'
file 'seg2.mp4'
file 'seg3.mp4'" > segments.txt

# 3. Concatenate
ffmpeg -f concat -safe 0 -i segments.txt -c copy final.mp4
```

**Method 2: Complex filter (single pass, frame-accurate, slower)**
```bash
ffmpeg -i input.mp4 -filter_complex \
  "[0:v]trim=start=10:end=45,setpts=PTS-STARTPTS[v0]; \
   [0:a]atrim=start=10:end=45,asetpts=PTS-STARTPTS[a0]; \
   [0:v]trim=start=80:end=120,setpts=PTS-STARTPTS[v1]; \
   [0:a]atrim=start=80:end=120,asetpts=PTS-STARTPTS[a1]; \
   [v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]" \
  -map "[outv]" -map "[outa]" final.mp4
```

**Method 3: Bash script from timestamp file**
```bash
#!/bin/bash
# timestamps.txt format: start end
# 00:00:10 00:00:45
# 00:01:20 00:02:00
INPUT="input.mp4"
i=0
while read start end; do
  ffmpeg -ss "$start" -to "$end" -i "$INPUT" -c copy "seg_${i}.mp4"
  echo "file 'seg_${i}.mp4'" >> segments.txt
  ((i++))
done < timestamps.txt
ffmpeg -f concat -safe 0 -i segments.txt -c copy final.mp4
```

### Important: keyframe vs frame-accurate
- `-c copy` = fast but cuts only at keyframes (GOP boundaries, typically every 2-5 seconds)
- Re-encoding = slow but frame-accurate at any point
- Hybrid approach: re-encode only the first/last few frames of each segment, stream-copy the middle

---

## 4. Programmatic Video Assembly (Python / CLI)

### MoviePy (Python)
**Repo:** https://github.com/Zulko/moviepy (12k+ stars)
**Install:** `pip install moviepy`
**Version:** 2.0+ (major rewrite, breaking changes from v1)

```python
from moviepy import VideoFileClip, concatenate_videoclips

video = VideoFileClip("input.mp4")
# Extract segments by timestamp (seconds)
segments = [
    video.subclipped(10, 45),
    video.subclipped(80, 120),
    video.subclipped(190, 260),
]
final = concatenate_videoclips(segments)
final.write_videofile("output.mp4")
```

MoviePy can also: add text overlays, transitions, speed changes, resize, composite multiple clips, add audio tracks.

### Editly (Node.js)
**Repo:** https://github.com/mifi/editly
**Install:** `npm i -g editly`

Declarative JSON spec for video assembly:
```json
{
  "outPath": "output.mp4",
  "width": 1920, "height": 1080, "fps": 30,
  "clips": [
    { "layers": [{ "type": "video", "path": "clip1.mov", "cutFrom": 10, "cutTo": 45 }] },
    { "layers": [{ "type": "title", "text": "Chapter 2" }], "duration": 3 },
    { "layers": [{ "type": "video", "path": "clip1.mov", "cutFrom": 80, "cutTo": 120 }] }
  ],
  "audioTracks": [{ "path": "music.mp3", "mixVolume": 0.3 }]
}
```

Supports: transitions (GL-transitions library), text/title layers, images, custom Canvas/WebGL, audio mixing.

### Remotion (React/TypeScript)
**Site:** https://remotion.dev
Creates videos as React components. Each frame rendered programmatically. Claude Code has official Remotion agent skills. Best for motion graphics / explainer videos rather than cutting raw footage.

### VidPy (Python, MLT-based)
**Repo:** https://github.com/antiboredom/vidpy
Alpha-stage, wraps the MLT framework. Requires melt binary (comes with Shotcut).

### FFmpeg-python
```python
import ffmpeg
# Cut and concatenate using ffmpeg-python bindings
in1 = ffmpeg.input('input.mp4', ss=10, to=45)
in2 = ffmpeg.input('input.mp4', ss=80, to=120)
(ffmpeg
    .concat(in1.video, in1.audio, in2.video, in2.audio, v=1, a=1)
    .output('final.mp4')
    .run())
```

### Python script: Whisper transcript → keep-ranges → FFmpeg assembly
```python
"""
Full pipeline: transcribe → LLM selects ranges → ffmpeg assembles
"""
import json, subprocess

# Step 1: Transcribe with faster-whisper
# (assumes you've already run: faster-whisper input.mp4 --output_format json > transcript.json)
with open("transcript.json") as f:
    transcript = json.load(f)

# Step 2: Define keep ranges (manually or via LLM - see Section 5)
keep_ranges = [
    {"start": 5.2, "end": 42.8},
    {"start": 65.0, "end": 118.5},
    {"start": 145.3, "end": 210.0},
]

# Step 3: Cut segments with FFmpeg
segment_files = []
for i, r in enumerate(keep_ranges):
    seg = f"seg_{i:03d}.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(r["start"]),
        "-to", str(r["end"]),
        "-i", "input.mp4",
        "-c:v", "libx264", "-c:a", "aac",  # re-encode for frame accuracy
        seg
    ])
    segment_files.append(seg)

# Step 4: Concatenate
with open("segments.txt", "w") as f:
    for seg in segment_files:
        f.write(f"file '{seg}'\n")

subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", "segments.txt",
    "-c", "copy",
    "final.mp4"
])
```

---

## 5. LLM-Assisted Video Editing (Emerging, 2024-2026)

### The concept
Feed a timestamped transcript to an LLM (Claude, GPT), ask it to decide what to cut/keep based on editorial criteria, get back timestamp ranges, then auto-assemble with FFmpeg.

### Claude Code Skills for Video Post-Production
**Source:** Chris Lema (2025), Karen Spinner (2025)
**How it works:** 8 markdown skill files that instruct Claude Code to run a full pipeline:

| Step | What it does | Tool |
|------|-------------|------|
| 1. Silence removal | Detect pauses >0.5s, reduce to 0.3s | FFmpeg |
| 2. Transcription | Word-level timestamps | Whisper (local) |
| 3. Editorial analysis | LLM categorizes content: normal/emphasis/critical (40/35/25%) | Claude |
| 4. Dynamic zoom | Face-centered crop at 1.0x / 1.25x / 1.6x per category | OpenCV + FFmpeg |
| 5. Color correction | Warm-punch preset for indoor talking-head | FFmpeg |
| 6. Audio mastering | Highpass, presence EQ, compression, loudness normalization | FFmpeg |
| 7. Captioning | Burn-in styled captions | FFmpeg |

**Repo (related):** https://github.com/digitalsamba/claude-code-video-toolkit — AI-native video production workspace. Uses Remotion + ElevenLabs + FFmpeg + Playwright. Focused on explainer video creation rather than post-production of raw footage.

### LLM as editorial decision-maker (DIY approach)
```
Prompt to Claude/GPT:
"Here is a transcript of a 20-minute talking-head video.
Mark each segment as KEEP or CUT based on these criteria:
- CUT: filler words, repeated takes, off-topic tangents, ums/ahs
- KEEP: main points, examples, jokes, calls to action
Output JSON: [{start: float, end: float, action: 'keep'|'cut', reason: string}]"

[paste transcript with timestamps]
```

Then feed the KEEP ranges to the FFmpeg pipeline from Section 4.

### Practical lessons learned (from Karen Spinner's 2025 post-mortem)
- **Conversational > structured CLI**: Telling Claude "that fade is too long" worked better than building a rigid CLI tool with all params
- **Stream copy is critical**: Re-encoding every clip = 55min assembly. Transport stream concat = 30 seconds.
- **AI chapter detection failed**: LLM consistently guessed chapter breaks wrong. Simple file naming (01-intro.mov) was more reliable.
- **Audio pops at concat joints**: Solution = final audio-only re-encode pass
- **AI video generation (Veo, Runway, Pika) not production-ready** for reliable pipelines — 30-120s/clip with unpredictable quality

### Research papers (2024-2025)
- **LAVE** (2024): LLM-Powered Agent Assistance and Language Augmentation for Video Editing — arxiv.org/html/2402.10294v1
- **"From Shots to Stories"** (2025): LLM-Assisted Video Editing with Unified Language Representations — arxiv.org/html/2505.12237v1
- **awesome-video-editing** paper list: https://github.com/wentianli/awesome-video-editing

---

## 6. FFmpeg 8.0 + Native Whisper Integration (Aug 2025)

FFmpeg 8.0 merged a native `whisper` audio filter powered by whisper.cpp. This is a game-changer for single-command transcription pipelines.

**Build requirement:** `./configure --enable-whisper` (needs whisper.cpp installed)

**Capabilities:**
- Transcribe directly within FFmpeg (no separate Whisper step)
- Output formats: text, SRT, JSON
- Works on pre-recorded files AND live streams
- Optional VAD (Voice Activity Detection) for better accuracy
- GPU acceleration supported
- Can burn subtitles in a single pipeline command

This enables single-command flows like: `input.mp4 → whisper filter → SRT → subtitle burn-in → output.mp4`

---

## 7. Recommended Toolchain for a Micro-Creator

For a solo YouTuber (~350 subs) wanting CLI-based automated post-production:

### Minimal pipeline
```
1. Record raw footage → input.mp4
2. auto-editor input.mp4 --margin 0.2sec → removes silence, outputs edited.mp4
3. Done (for basic jump-cut style)
```

### Full pipeline (transcript-based)
```
1. Record → input.mp4
2. auto-editor input.mp4 --margin 0.2sec -o desilenced.mp4
3. whisper desilenced.mp4 --model medium --output_format json → transcript
4. LLM reviews transcript, outputs keep-ranges
5. Python/bash script: ffmpeg cuts + concat → rough_cut.mp4
6. ffmpeg audio normalization + color LUT → final.mp4
```

### Tool stack
| Need | Tool | Install |
|------|------|---------|
| Silence removal | auto-editor | `pip install auto-editor` |
| Transcription | faster-whisper | `pip install faster-whisper` |
| Editorial decisions | Claude API / manual | — |
| Cutting/concat | ffmpeg | `brew install ffmpeg` |
| Scripting glue | Python + ffmpeg-python | `pip install ffmpeg-python` |
| Captions/subs | ffmpeg subtitles filter | built-in |
| Programmatic assembly | moviepy (optional) | `pip install moviepy` |
| NLE export | auto-editor --export | built-in |

---

## Sources

- [auto-editor (WyattBlue)](https://github.com/WyattBlue/auto-editor)
- [auto-editor on PyPI](https://pypi.org/project/auto-editor/)
- [MoviePy](https://github.com/Zulko/moviepy)
- [Editly](https://github.com/mifi/editly)
- [OpenScript](https://github.com/preston176/openscript)
- [Claude Code Video Toolkit](https://github.com/digitalsamba/claude-code-video-toolkit)
- [Claude Code skills for video editing (Chris Lema)](https://chrislema.com/claude-code-skills-for-video-editing)
- [Video post-production pipeline with Claude Code (Karen Spinner)](https://wonderingaboutai.substack.com/p/i-built-a-video-post-production-pipeline)
- [Remotion + Claude Code](https://www.remotion.dev/docs/ai/claude-code)
- [FFmpeg trim guide (Shotstack)](https://shotstack.io/learn/use-ffmpeg-to-trim-video/)
- [FFmpeg cut and concat (Mark Heath)](https://markheath.net/post/cut-and-concatenate-with-ffmpeg)
- [FFmpeg clip extraction (Mux)](https://www.mux.com/articles/clip-sections-of-a-video-with-ffmpeg)
- [FFmpeg 8.0 Whisper filter (Phoronix)](https://www.phoronix.com/news/FFmpeg-Lands-Whisper)
- [FFmpeg Whisper filter (Neowin)](https://www.neowin.net/news/a-powerful-new-whisper-audio-filter-brings-ai-transcription-to-ffmpeg/)
- [FFmpeg 8 Whisper subtitles (The Register)](https://www.theregister.com/2025/08/28/ffmpeg_8_huffman/)
- [Whisper + FFmpeg + Python tutorial (DigitalOcean)](https://www.digitalocean.com/community/tutorials/how-to-generate-and-add-subtitles-to-videos-using-python-openai-whisper-and-ffmpeg)
- [jumpcutter (carykh)](https://github.com/carykh/jumpcutter)
- [auto-silence-cut](https://github.com/YourAverageMo/auto-silence-cut)
- [LAVE paper](https://arxiv.org/html/2402.10294v1)
- [From Shots to Stories paper](https://arxiv.org/html/2505.12237v1)
- [VidPy](https://github.com/antiboredom/vidpy)
- [Descript review 2025](https://aitoolanalysis.com/descript-review-2025-text-based-video-editing/)
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
