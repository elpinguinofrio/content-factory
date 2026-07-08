# Existing Open-Source Video Production Pipeline Projects

Research date: 2026-03-26

## Summary

There is NO single open-source project that handles the FULL pipeline (raw video -> transcribe -> AI edit decisions -> cut -> shorts -> subtitles -> dub/translate -> upload). But several projects cover large chunks, and a combination of 2-3 can get close to end-to-end.

---

## Tier 1: Most Complete / Highest Stars

### MoneyPrinterTurbo
- **URL:** https://github.com/harry0703/MoneyPrinterTurbo
- **Stars:** 53,342 | Forks: 7,541
- **Language:** Python
- **Updated:** 2026-03-26 (actively maintained)
- **What it does:** Topic/keyword -> AI script -> stock footage sourcing -> TTS voiceover -> subtitles -> background music -> assembled short video. Web UI + API.
- **Tech:** Python, FFmpeg, supports OpenAI/DeepSeek/Gemini/Ollama for LLM, multiple TTS providers, Pexels/Pixabay for footage
- **Pipeline coverage:** Script generation, footage sourcing, TTS, subtitles, assembly. Does NOT take existing raw video as input -- it generates from scratch.
- **Limitation:** Not for repurposing YOUR footage. It's a "faceless channel" tool that assembles stock clips. No upload to YouTube yet (planned).

### ShortGPT
- **URL:** https://github.com/RayVentura/ShortGPT
- **Stars:** 7,198 | Forks: 1,005
- **Language:** Python
- **Updated:** 2026-03-26 (still maintained)
- **What it does:** AI framework for automating shorts/TikTok creation. LLM-oriented video editing language, script generation, footage sourcing, voiceover synthesis, multi-language dubbing.
- **Tech:** Python, OpenAI GPT, ElevenLabs TTS, Pexels footage, FFmpeg
- **Pipeline coverage:** Script -> footage -> voiceover -> editing -> multi-language dubbing
- **Limitation:** Like MoneyPrinterTurbo, oriented toward generating NEW content from scratch, not repurposing existing long-form video. Voice dubbing is a standout feature.

### MoneyPrinterPlus
- **URL:** https://github.com/ddean2009/MoneyPrinterPlus
- **Stars:** 5,946 | Forks: 1,094
- **Language:** Python
- **Updated:** 2026-03-26 (active)
- **What it does:** Fork/variant of MoneyPrinterTurbo with batch video generation, auto-posting to Douyin/Kuaishou/Xiaohongshu, local TTS (ChatTTS, FasterWhisper, GPTSoVITS), cloud TTS (Azure, Alibaba, Tencent).
- **Pipeline coverage:** Similar to MoneyPrinterTurbo but adds auto-upload to Chinese platforms and local model support.
- **Limitation:** Same -- generates from scratch, not repurposing. Chinese-ecosystem focused.

---

## Tier 2: Best for Repurposing Existing Video (Your Use Case)

### SupoClip (OpusClip alternative)
- **URL:** https://github.com/FujiwaraChoki/supoclip
- **Stars:** 324 | Forks: 125
- **Language:** Python (backend) + Next.js (frontend)
- **Updated:** 2026-03-26 (active)
- **What it does:** Self-described "open-source OpusClip". Takes long-form video -> transcribes (AssemblyAI) -> LLM identifies best clips -> cuts video -> generates clips. Docker-based, web UI.
- **Tech:** Python, Docker, AssemblyAI for transcription, LLM (Google Gemini/OpenAI/Anthropic/Ollama) for clip selection
- **Pipeline coverage:** Transcribe -> AI clip detection -> cut video. No subtitles burning, no dubbing, no upload.
- **BEST FIT for your use case.** Closest to the "take existing video -> make shorts" workflow.

### ClippedAI
- **URL:** https://github.com/Shaarav4795/ClippedAI
- **Stars:** 119 | Forks: 32
- **Language:** Python
- **Updated:** 2026-03-24 (active)
- **What it does:** Open-source OpusClip alternative. Uses ClipsAI library under the hood. Smart clip detection, auto-resize to 9:16, animated subtitles (white text, yellow for numbers), viral title generation, engagement scoring.
- **Tech:** Python, ClipsAI, WhisperX, HuggingFace (free), Groq (free), FFmpeg
- **Pipeline coverage:** Transcribe -> clip detection -> resize 9:16 -> subtitles -> viral titles
- **Notable:** 100% free API keys (HuggingFace + Groq). Works offline except for title generation. Animated subtitles built-in.

### ClipsAI (library, not app)
- **URL:** https://github.com/ClipsAI/clipsai
- **Stars:** 459 | Forks: ~50
- **Language:** Python
- **Updated:** 2026-03-25 (active)
- **What it does:** Python library (pip install) for automatically converting long videos into clips. Transcript-based clip finding + speaker-aware resizing (16:9 -> 9:16).
- **Tech:** Python, WhisperX, Pyannote (speaker diarization), FFmpeg
- **Pipeline coverage:** Transcribe -> find clips -> resize with speaker tracking. Library only -- you build the pipeline around it.
- **Key building block.** This is what ClippedAI wraps. Most composable option for custom pipelines.

### video-clipper (Vizard AI replica)
- **URL:** https://github.com/kirat11X/video--clipper-vizard-AI-replica-automatic-short-form-clip-generator-
- **Stars:** 9 | Forks: 2
- **Language:** Python
- **Updated:** 2026-03-24 (active)
- **What it does:** End-to-end, fully local. YouTube URL -> download (yt-dlp) -> audio extraction -> Whisper transcription -> multimodal signal analysis (audio energy, semantic NLP, visual/face detection) -> clip scoring with NMS -> 9:16 vertical rendering with blur background + burned-in captions.
- **Tech:** Python, yt-dlp, faster-whisper, librosa, OpenCV, MediaPipe, FFmpeg NVENC
- **Pipeline coverage:** Download -> transcribe -> multimodal analysis -> clip selection -> render with captions. Fully local, no API keys needed.
- **Notable:** Most sophisticated scoring (audio + semantic + visual signals). Low stars but technically impressive architecture. No LLM dependency -- pure signal analysis.

---

## Tier 3: Useful Building Blocks

### auto-editor
- **URL:** https://github.com/WyattBlue/auto-editor
- **Stars:** 4,070 | Forks: 524
- **Language:** Nim
- **Updated:** 2026-03-26 (very active)
- **What it does:** Automatic silence removal and "effort-free" video editing. Detects silent/boring sections and cuts them out. Exports to Premiere/Resolve/Final Cut timelines.
- **Pipeline coverage:** Silence detection -> cut. One piece of the puzzle (the "remove dead air" step).

### videogrep
- **URL:** https://github.com/antiboredom/videogrep
- **Stars:** 3,453 | Forks: 262
- **Language:** Python
- **Updated:** 2026-03-15
- **What it does:** "Automatic video supercuts" -- search transcripts for words/phrases, automatically cut and concatenate matching segments.
- **Pipeline coverage:** Transcript search -> supercut assembly. Useful for "find all mentions of X and make a compilation."

### jumpcutter
- **URL:** https://github.com/carykh/jumpcutter
- **Stars:** 3,146 | Forks: 537
- **Language:** Python
- **Updated:** 2026-03-26
- **What it does:** Automatically removes silent parts from video, speeds up quiet sections.
- **Pipeline coverage:** Silence removal only. Original inspiration for auto-editor.

### Dubbie (AI dubbing)
- **URL:** https://github.com/DubbieHQ/dubbie
- **Stars:** 202 | Forks: ~20
- **Language:** TypeScript (Next.js + Node.js)
- **Updated:** 2026-03-23 (active)
- **What it does:** Open-source AI dubbing studio. Upload video -> Whisper transcription -> LLM sentence segmentation -> LLM translation -> TTS in target language. $0.10/min vs $2/min for ElevenLabs.
- **Tech:** Next.js, Node.js, Prisma/Postgres, Whisper, OpenRouter (LLM), Azure/OpenAI TTS
- **Pipeline coverage:** Transcribe -> translate -> dub. The translation/dubbing piece of the pipeline.

### Auto-Subtitled-Video-Generator
- **URL:** https://github.com/BatuhanYilmaz26/Auto-Subtitled-Video-Generator
- **Stars:** 126 | Forks: 34
- **Language:** Python
- **Updated:** 2026-03-23
- **What it does:** Input YouTube link or video file -> Whisper transcription -> burn subtitles into video. Streamlit web UI.
- **Pipeline coverage:** Transcribe -> subtitle overlay. Simple but solid.

### montage-ai
- **URL:** https://github.com/mfahsold/montage-ai
- **Stars:** 21 | Forks: 1
- **Language:** Python
- **Updated:** 2026-03-25 (active)
- **What it does:** Local-first AI video editor. Transcript-based editing, beat-synced cuts, exports to OTIO/EDL (professional NLE interchange formats). CLI + web UI, Docker.
- **Pipeline coverage:** Transcribe -> AI rough-cut -> export timeline. Interesting for professional workflow integration (can export to Premiere/Resolve).

---

## Tier 4: Faceless / Text-to-Video Generators (NOT repurposing)

These generate videos from scratch -- different use case but worth knowing:

| Project | Stars | What it does |
|---------|-------|-------------|
| YumCut (app.yumcut.com) | 662 | Prompt -> script -> voice -> visuals -> captions -> final 9:16 video. TypeScript. Multi-language. |
| YASGU | 72 | Subject+language -> GPT script -> CoquiTTS voice -> DALL-E images -> assembled short -> YouTube upload via Selenium. |
| ShortFactory | 10 | ShortGPT fork with style transfer, multi-platform support. |
| yt-shoorts-automation | 50 | Node.js. GPT-4 script -> Google Cloud TTS -> FFmpeg editing -> CapCut subtitles. |

---

## Tier 5: YouTube Upload Automation

No great standalone open-source YouTube uploader exists. Options:
- **YouTube Data API v3** directly (Python google-api-python-client)
- **youtubeuploader** (Go CLI, used by MARCELO bot): https://github.com/porjo/youtubeuploader
- **Selenium-based upload** (YASGU approach -- fragile)
- **yt-upload-automation** (58 stars) -- downloads TikTok -> edits -> compiles -> uploads to YouTube

---

## Recommended Stack for YOUR Use Case

"Raw video -> transcribe -> AI edit -> cut -> shorts -> subtitles -> dub -> upload"

| Pipeline Step | Best Tool | Alternative |
|---------------|-----------|-------------|
| 1. Transcribe | ClipsAI (WhisperX) or faster-whisper directly | AssemblyAI (paid, used by SupoClip) |
| 2. AI clip selection | SupoClip (LLM-based) or video-clipper (signal-based) | ClipsAI find_clips() |
| 3. Cut video | FFmpeg (all tools use it) | auto-editor for silence removal |
| 4. Resize 9:16 | ClipsAI resize() with speaker tracking | Simple FFmpeg crop+blur |
| 5. Subtitles | ClippedAI (animated subs) or whisper_autosrt | Auto-Subtitled-Video-Generator |
| 6. Dubbing/Translation | Dubbie ($0.10/min) | ShortGPT dubbing engine |
| 7. Upload | YouTube Data API v3 / youtubeuploader | Selenium (fragile) |

### Most practical approaches:

**Option A: SupoClip as base** (most complete single project)
- Fork SupoClip, add subtitle burning + dubbing (via Dubbie or custom) + YouTube upload
- Already has: transcription, LLM clip selection, video cutting, Docker, web UI

**Option B: ClipsAI as library + custom pipeline**
- Use ClipsAI for transcription + clip finding + speaker-aware resizing
- Add: LLM for clip scoring, subtitle burning, Dubbie for translation, YouTube API for upload
- Most flexible, most coding required

**Option C: video-clipper for fully local**
- No API keys needed (except optional). Multimodal analysis (audio+text+visual)
- Add: subtitle burning (already has basic captions), Dubbie for translation, upload
- Best for privacy/cost, but less polished

---

## Key Takeaway

You are NOT fully reinventing the wheel, but no single project does everything you need. The closest are:
1. **SupoClip** (324 stars) -- covers transcribe + AI clip selection + cutting, missing subtitles/dub/upload
2. **ClippedAI** (119 stars) -- covers transcribe + clips + subtitles + resize, missing dub/upload
3. **video-clipper** (9 stars) -- covers the most steps locally but small/new

The gap in the ecosystem is specifically: **taking YOUR raw long-form video and producing upload-ready shorts with subtitles and optional dubbing**. The 50k+ star projects (MoneyPrinterTurbo) all generate from scratch using stock footage. The repurposing tools are 100-300 star range and still maturing.
