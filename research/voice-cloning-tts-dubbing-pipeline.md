# Research: Voice Cloning + TTS for Dubbing/Translation Pipeline

Generated: 2026-03-26
Agents: Opus (WebSearch x22)

---

## Executive Summary

For a Russian YouTube video -> English/Spanish dubbed audio pipeline, the best 2026 stack is:

- **ASR**: WhisperX (word-level timestamps + diarization)
- **Translation**: Claude/Gemini API or DeepL API ($25/1M chars)
- **Voice cloning + TTS**: Chatterbox (MIT, best quality) or Fish Speech 1.5 (Apache 2.0, best multilingual) or CosyVoice 3 (best cross-lingual cloning with Russian support)
- **Sync + merge**: pyVideoTrans (all-in-one) or custom ffmpeg pipeline
- **Lip sync** (optional): InfiniteTalk or Linly-Dubbing

Total self-hosted cost: GPU time only (~$0.50-2/hr). No per-minute fees.

---

## 1. Open-Source Voice Cloning + TTS Models

### Tier 1: Best for Dubbing (2026)

| Model | License | Clone Sample | Languages | VRAM | Install | Quality |
|-------|---------|-------------|-----------|------|---------|---------|
| **Chatterbox** (Resemble AI) | MIT | 5s | 23 | ~6GB | `pip install chatterbox-tts` | Beats ElevenLabs 63.75% pref |
| **Fish Speech 1.5** | Apache 2.0 | 10-30s | 30+ | 4GB | `pip install fish-audio-sdk` | #1 TTS-Arena, ELO 1339 |
| **CosyVoice 3** (Alibaba) | Apache 2.0 | 3-10s | 9 + 18 dialects | ~4GB | `pip install cosyvoice` | WER 1.68%, 150ms streaming |
| **Qwen3-TTS** (Alibaba) | Open | 3s | 10 (incl. Russian) | ~4GB | HuggingFace | WER 1.835%, beats ElevenLabs |
| **F5-TTS v1** | CC-BY-NC | few sec | Multi | ~6GB | `pip install f5-tts` | Cross-lingual paper Feb 2026 |
| **IndexTTS-2** | Open | Zero-shot | Multi | ~6GB | GitHub | Best WER (0.2418), duration control |

### Tier 2: Solid Alternatives

| Model | License | Clone Sample | Languages | Notes |
|-------|---------|-------------|-----------|-------|
| **GPT-SoVITS** | MIT | 1 min (best), 5s (zero-shot) | CN/EN/JP | WebUI, training pipeline included. 6GB+ VRAM |
| **OpenVoice v2** (MyShell) | MIT | Short clip | 6 native + cross-lingual | Zero-shot cross-lingual. Lightweight |
| **XTTS v2** (Coqui) | CPML (non-commercial) | 6s | 17 (incl. Russian) | Company dead Dec 2025, community-maintained |
| **Bark** (Suno) | MIT | No native cloning | Multi | Multilingual but no official voice cloning. Community forks exist |
| **Kokoro-82M** | Open | Via KokoClone fork | Multi | Ultra-fast (sub-0.3s), 82M params. No native cloning |
| **Zonos** | Open | N/A | Multi | Best controllability, not focused on cloning |
| **Piper** | MIT | Training required | 30+ | CPU-only, Raspberry Pi. No zero-shot cloning. Use TextyMcSpeechy for voice training |
| **MeloTTS** | MIT | N/A | 6 | Fast CPU inference, no voice cloning |

### Russian Language Support Matrix

| Model | Russian Input | Clone Russian Speaker → English Output | Notes |
|-------|--------------|---------------------------------------|-------|
| Qwen3-TTS | Yes (native) | Yes | Best Russian support in open-source |
| CosyVoice 3 | Yes (native) | Yes | Cross-lingual cloning confirmed |
| XTTS v2 | Yes (native) | Yes | 17 languages including Russian |
| Fish Speech 1.5 | Partial | Yes | 300k hrs EN/CN training, Russian less tested |
| Chatterbox | No (23 langs, unclear on RU) | Yes (output EN/ES) | Check latest model for RU support |
| OpenVoice v2 | Not native | Yes (tone transfer) | Clone voice from RU, generate in EN |

### CLI Usage Examples

**Chatterbox** (simplest):
```python
from chatterbox.tts import ChatterboxTTS
import torchaudio as ta

model = ChatterboxTTS.from_pretrained(device="cuda")
wav = model.generate(
    "Hello, this is a cloned voice speaking English.",
    audio_prompt_path="russian_speaker_sample.wav",
    exaggeration=0.5,    # emotion intensity
    cfg_weight=0.5       # voice similarity strength
)
ta.save("output.wav", wav, model.sr)
```

**Fish Speech** (API):
```python
from fish_audio_sdk import Session, TTSRequest, ReferenceAudio

session = Session("your-api-key")
with open("russian_speaker.wav", "rb") as f:
    ref = ReferenceAudio(audio=f.read(), text="Transcript of the reference audio")

for chunk in session.tts(TTSRequest(
    text="Hello, this is the translated text.",
    references=[ref]
)):
    # write chunk to file
    pass
```

**CosyVoice 3** (local):
```python
from cosyvoice.cli.cosyvoice import CosyVoice

model = CosyVoice('pretrained_models/Fun-CosyVoice3-0.5B')
for chunk in model.inference_zero_shot(
    "Hello, this is translated text in English.",
    prompt_text="Transcript of the Russian reference audio",
    prompt_speech="russian_speaker_sample.wav"
):
    # save chunk
    pass
```

**F5-TTS** (CLI):
```bash
f5-tts_infer-cli \
  --model F5TTS_v1_Base \
  --ref_audio "russian_speaker.wav" \
  --ref_text "Transcript of the reference" \
  --gen_text "Hello, this is the translated English text."
```

**GPT-SoVITS** (WebUI):
```bash
# Windows: download integrated package, run go-webui.bat
# Linux/Mac:
git clone https://github.com/RVC-Boss/GPT-SoVITS.git
cd GPT-SoVITS
pip install -r requirements.txt
python webui.py
# Upload 1-min voice sample, train, then synthesize via API
```

---

## 2. Cheap APIs for Voice Cloning + Multilingual TTS

| Service | Pricing | Voice Clone | Languages | Dubbing | Notes |
|---------|---------|-------------|-----------|---------|-------|
| **Fish Audio** | $15/1M UTF-8 bytes (~$0.04-0.08/min) | 15s sample | 80+ | Via API | Cheapest. Open-source model also available |
| **ElevenLabs** | $22-99/mo plans, ~$0.20-0.60/min dubbing | Instant or Professional | 29 dubbing | Dubbing Studio | Best quality, most expensive. Pro plan min for API |
| **Resemble AI** | $0.036/min pay-as-you-go, $30/mo Creator | Few seconds | 23+ | Via API | Also provides Chatterbox open-source |
| **Rask AI** | $60/mo for 25 min (~$2.40/min) | Yes | 135 | Full pipeline | Lip-sync extra ($3/min). Expensive |
| **HeyGen** | $24/mo Creator | Yes | 175+ | Full pipeline + lip sync | Best for video dubbing. Credits double with lip sync |
| **Play.ht** | **DEAD** — acquired by Meta, shut down Dec 2025 | N/A | N/A | N/A | Do not use |

### Cost Comparison: 10-min Russian Video → English Dub

| Approach | Cost | Quality |
|----------|------|---------|
| **Self-hosted** (Chatterbox/CosyVoice + WhisperX + Claude translation) | ~$0.50-1 GPU time + ~$0.10 translation | High |
| **Fish Audio API** | ~$0.40-0.80 | High |
| **ElevenLabs Pro** | ~$2-6 | Highest |
| **Rask AI** | ~$24+ | High (with lip sync) |
| **HeyGen** | ~$5-10 | High (with lip sync) |

---

## 3. Translation Pipeline

### Option A: LLM Translation (Best for Dubbing)

Use Claude or Gemini for context-aware translation that preserves:
- Natural sentence length (critical for sync)
- Idiomatic expressions
- Speaker style/register
- Segment boundaries matching original timestamps

```python
# Example: translate SRT segments with Claude
import anthropic

client = anthropic.Anthropic()

def translate_segments(segments, source_lang="ru", target_lang="en"):
    prompt = f"""Translate these video subtitle segments from {source_lang} to {target_lang}.
Rules:
- Keep translations similar length to originals (for dubbing sync)
- Preserve natural speech patterns, not literary translation
- Keep segment boundaries as-is
- Output format: same numbered segments with translated text

Segments:
{segments}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
```

### Option B: DeepL API

- **Free tier**: 500K chars/month
- **API Pro**: $5.49/mo + $25/1M chars
- Russian, English, Spanish all supported
- Best machine translation quality, but less control over length

### Option C: Local LLM

- Use Qwen2.5 or similar multilingual model
- Free but lower quality for RU→EN than Claude/DeepL
- Good for offline/private workflows

### Preserving Timing/Sync

The key challenge: translated text in another language often has different word count/duration.

Strategies:
1. **Length-constrained translation**: Prompt LLM to keep translations similar length
2. **TTS speed adjustment**: Stretch/compress TTS output to match original segment duration (ffmpeg atempo)
3. **Duration-aware TTS**: IndexTTS-2 and CosyVoice support explicit duration control
4. **Post-processing**: Use rubberband/ffmpeg to time-stretch without pitch artifacts

```bash
# Adjust TTS audio speed to match original segment duration
# If original segment = 3.2s but TTS output = 4.0s:
ffmpeg -i tts_output.wav -filter:a "atempo=1.25" -vn synced_output.wav
```

---

## 4. Full Dubbing Pipeline Tools

### All-in-One Open Source Solutions

#### pyVideoTrans (Best All-in-One)
- **Repo**: [github.com/jianchang512/pyvideotrans](https://github.com/jianchang512/pyvideotrans)
- **License**: GPL-v3
- **Pipeline**: ASR → translate → TTS → video merge (one click)
- **TTS integrations**: F5-TTS, CosyVoice, GPT-SoVITS, plus cloud APIs
- **Install**: Windows .exe package, or Python. No environment setup needed for Windows
- **Languages**: 16+, batch processing, speaker diarization

#### KrillinAI / Klic Studio
- **Repo**: [github.com/krillinai/KrillinAI](https://github.com/krillinai/KrillinAI)
- **License**: Open source (Go language)
- **Pipeline**: Whisper ASR → LLM translation → GPT-SoVITS/CosyVoice TTS → merge
- **Features**: 100 languages, YouTube/TikTok format optimization, desktop app
- **Voice cloning**: Integrates GPT-SoVITS and CosyVoice

#### Linly-Dubbing
- **Repo**: [github.com/Kedreamix/Linly-Dubbing](https://github.com/Kedreamix/Linly-Dubbing)
- **License**: Open source
- **Features**: Translation + voice cloning + lip sync (via Linly-Talker)
- **Extras**: Background music insertion, volume/speed adjustment, subtitle overlay

#### Auto-Synced-Translated-Dubs (ThioJoe)
- **Repo**: [github.com/ThioJoe/Auto-Synced-Translated-Dubs](https://github.com/ThioJoe/Auto-Synced-Translated-Dubs)
- **Pipeline**: SRT file → translate (Google/DeepL) → TTS (Google/Azure/ElevenLabs) → time-stretch to match original → merge
- **Bonus tools**: TrackAdder (multi-language audio tracks), TitleTranslator (YouTube metadata)
- **Best for**: YouTube creators who already have SRT files

#### Gladia
- **Features**: Translation + dubbing + lip sync
- **Type**: Open-source developer app

### Custom Pipeline (Recommended for Control)

```
Input: Russian YouTube video
  │
  ├─ [yt-dlp] ──────────────────── download video + audio
  │
  ├─ [WhisperX] ─────────────────── transcribe Russian → SRT with word timestamps
  │     --model large-v3
  │     --language ru
  │     --diarize (if multi-speaker)
  │
  ├─ [Claude API / DeepL] ──────── translate segments RU → EN/ES
  │     (length-constrained prompting)
  │
  ├─ [Chatterbox / CosyVoice 3] ── clone voice + synthesize each segment
  │     reference: original speaker audio
  │     text: translated segment
  │
  ├─ [ffmpeg atempo] ───────────── stretch/compress each TTS clip
  │     to match original segment duration
  │
  ├─ [ffmpeg concat + merge] ──── assemble clips, mix with original BGM
  │     -filter_complex "[0:a]volume=0.1[bg];[1:a][bg]amix"
  │
  └─ Output: dubbed video with cloned voice
```

### Sync Algorithm (Pseudocode)

```python
for segment in srt_segments:
    original_duration = segment.end - segment.start

    # Generate TTS for translated text
    tts_audio = voice_clone_tts(
        text=segment.translated_text,
        reference_audio=speaker_sample,
        target_language="en"
    )
    tts_duration = get_duration(tts_audio)

    # Speed-adjust to match original timing
    speed_factor = tts_duration / original_duration
    if 0.75 < speed_factor < 1.5:  # acceptable range
        adjusted = ffmpeg_atempo(tts_audio, speed_factor)
    else:
        # Re-translate with length constraint or use silence padding
        adjusted = handle_extreme_mismatch(segment, tts_audio)

    # Place at correct timestamp
    timeline.add(adjusted, offset=segment.start)
```

---

## 5. Recommendations by Use Case

### Cheapest Self-Hosted (No API Costs)
**Stack**: WhisperX + local Qwen2.5 translation + Chatterbox/CosyVoice 3 + ffmpeg
**Requires**: NVIDIA GPU with 8GB+ VRAM
**Cost**: Electricity only

### Best Quality Self-Hosted
**Stack**: WhisperX + Claude API translation + CosyVoice 3 (Russian support) + IndexTTS-2 (duration control) + ffmpeg
**Cost**: ~$0.10-0.20/video for translation API

### Easiest Setup (No Coding)
**Tool**: pyVideoTrans (Windows .exe, one-click pipeline)
**Or**: KrillinAI (desktop app, cross-platform)

### Best API-Based (Minimal Infrastructure)
**Stack**: Fish Audio API ($15/1M bytes) + DeepL API ($25/1M chars) + WhisperX
**Cost**: ~$0.50-1/video

### For Russian → English Specifically
**Best TTS models**: CosyVoice 3 or Qwen3-TTS (both have native Russian support from Alibaba)
**Alternative**: XTTS v2 (17 languages including Russian, but non-commercial license)
**Translation**: Claude API (best RU→EN quality) or DeepL (cheaper, still excellent)

---

## Sources

### Open-Source Repositories
- [Chatterbox](https://github.com/resemble-ai/chatterbox) — MIT, 23 languages, emotion control
- [Fish Speech](https://github.com/fishaudio/fish-speech) — Apache 2.0, #1 TTS-Arena
- [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) — Apache 2.0, 9 langs + 18 dialects
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) — 10 languages, 3s cloning
- [F5-TTS](https://github.com/SWivid/F5-TTS) — flow matching, cross-lingual paper
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) — MIT, 1-min voice training
- [OpenVoice v2](https://github.com/myshell-ai/OpenVoice) — MIT, cross-lingual cloning
- [XTTS v2 / Coqui TTS](https://github.com/coqui-ai/TTS) — community-maintained
- [IndexTTS](https://index-tts.github.io/) — best WER, duration control
- [Piper](https://github.com/rhasspy/piper) — lightweight CPU TTS
- [Bark](https://github.com/suno-ai/bark) — multilingual but no native cloning
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — ultra-fast, lightweight
- [KokoClone](https://github.com/Ashish-Patnaik/kokoclone) — voice cloning for Kokoro

### Pipeline Tools
- [pyVideoTrans](https://github.com/jianchang512/pyvideotrans) — GPL-v3, all-in-one dubbing
- [KrillinAI](https://github.com/krillinai/KrillinAI) — Go, 100 languages, desktop app
- [Linly-Dubbing](https://github.com/Kedreamix/Linly-Dubbing) — dubbing + lip sync
- [Auto-Synced-Translated-Dubs](https://github.com/ThioJoe/Auto-Synced-Translated-Dubs) — SRT-based dubbing
- [InfiniteTalk](https://www.blog.brightcoding.dev/2025/09/23/infinitetalk-unlimited-length-audio-driven-video-dubbing-with-pixel-perfect-lip-sync/) — pixel-perfect lip sync

### API Services
- [Fish Audio Pricing](https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits) — $15/1M UTF-8 bytes
- [ElevenLabs Pricing](https://elevenlabs.io/pricing) — $22-99+/mo plans
- [Resemble AI Pricing](https://www.resemble.ai/pricing/) — $0.036/min pay-as-you-go
- [DeepL API](https://support.deepl.com/hc/en-us/articles/360021200939-DeepL-API-plans) — $25/1M chars
- [Rask AI](https://www.rask.ai/pricing) — $60/mo for 25 min
- [HeyGen](https://www.heygen.com/translate/ai-dubbing) — $24/mo Creator plan

### Comparison & Benchmark Articles
- [SiliconFlow: Best Open Source Voice Cloning 2026](https://www.siliconflow.com/articles/en/best-open-source-models-for-voice-cloning)
- [SiliconFlow: Best Open Source Dubbing Models 2026](https://www.siliconflow.com/articles/en/best-open-source-AI-models-for-dubbing)
- [BentoML: Best Open Source TTS 2026](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
- [Inferless: 12 TTS Models Compared](https://www.inferless.com/learn/comparing-different-text-to-speech---tts--models-part-2)
- [Resemble AI: Best Open Source Voice Cloning 2026](https://www.resemble.ai/best-open-source-ai-voice-cloning-tools/)
- [Pinch: Dubbing API Pricing Comparison 2026](https://startpinch.com/guides/dubbing-api-pricing-comparison)
- [Qwen3-TTS Announcement](https://qwen.ai/blog?id=qwen3tts-0115)
- [CosyVoice 3 Guide](https://stable-learn.com/en/cosyvoice3-tech-guide/)
