# Bus Station Recording — Denoising Comparison Report

**Source:** `/Volumes/My Shared Files/Recordings/20260429 161623-C4A0CF04.m4a`
**Duration:** 6:38 (398s)
**Speaker language:** Russian (with brief English at hotel check-in)
**Noise profile:** outdoor / transit area, mean -18.7 dB raw (very noisy throughout)
**Transcriber:** Gemini 3.5 Flash on Vertex AI (`location=global`)

---

## Result

**Winner: ffmpeg `highpass=200Hz` + `loudnorm=-16 LUFS` — NO neural denoiser.**

Why: neural denoisers (DeepFilterNet 3 at three settings, ffmpeg afftdn) all over-suppressed Russian speech phonemes and confused Gemini. Simple 200Hz high-pass removes engine/bus rumble (~30–200Hz) without touching speech (300Hz+), preserves consonants, and lets Gemini's noise-robust ASR do its job. The deepest noisy chunk (04:30) went from `[silence]` to a full transcribed conversation.

**Files for verification:**
- Clean audio (listen): `final_clean_48k.wav` (12 MB)
- Clean audio (ASR feed): `final_clean_16k.wav` (12 MB)
- Final transcript: `final_transcript.txt`

---

## Per-chunk transcript comparison (45-second chunks)

| Time | Loudnorm (HP80) baseline | DFN3 (-pf) | DFN3 gentle (-a 20) | afftdn | **HP200 + loudnorm (WINNER)** |
|---|---|---|---|---|---|
| 00:00 | "Билетики продают" ✓ | "гренки продаются" ✗ | "Английский продаётся" ✗ | "Билетики продают" ✓ (+ added bad text) | "Билетики продают" ✓ (longest, richest) |
| 00:45 | "сосед с какашкой, который ремонт делает болгаркой" ✓ | hallucinated "сейчас по башке тебе дам" ✗ | "папа скажет" ✗ | "сейчас покажет" ✗ | "сосед с какашкой ... болгаркой" ✓ |
| 01:30 | [silence] | "И" | [silence] | [silence] | [silence] |
| 02:15 | [silence] | "Да" | [silence] | [silence] | "Мама" (new content) |
| 03:00 | "А у вас какой" | [silence] | "Ой, а я" | "А у нас, а у нас" | "А у тебя папа уехал? Да..." ✓ (full sentence) |
| 03:45 | "Здравствуйте" ✓ | "И" ✗ | [silence] | [silence] | "Здравствуйте" ✓ |
| 04:30 | [silence] | [silence] | [silence] | English check-in ✓ | English check-in ✓ (full, 11s of audio) |
| 05:15 | English: "Outpost living 26" ✓ | "Output leaving 26" ✗ | "Eat out first ... Outpost" ✓ | [silence] | [silence] |
| 06:00 | [silence] | [silence] | "Ой, блин" | [silence] | [silence] |

**Scoring:** HP200 wins 6 chunks, baseline wins 2 (chunk 05:15 English check-in — afftdn/HP200 placed it in chunk 04:30 instead, so the content is preserved either way), DFN3 wins 0.

---

## Pipeline (canonical command)

```bash
ffmpeg -y -i input.m4a -ac 1 -ar 16000 \
  -af "highpass=f=200,loudnorm=I=-16:LRA=11:tp=-1.5" \
  output_clean_16k.wav
```

**For long files**, transcribe in 45-second chunks via Gemini 3.5 Flash on Vertex AI (`location="global"`). Single-shot calls on multi-minute audio cause Gemini to truncate. The chunker is at `transcribe_gemini_chunked.py`.

---

## What was tried and rejected

1. **DeepFilterNet 3** (full attenuation, post-filter) — Codex's #1 pick. Cut noise -13 dB but corrupted Russian phonemes. "Билетики" → "гренки". REJECTED.
2. **DeepFilterNet 3 gentle (-a 20)** — softer attenuation cap. Still corrupted phonemes. REJECTED.
3. **DeepFilterNet 3 mid (-a 30, +postfilter)** — similar to default. REJECTED.
4. **ffmpeg afftdn** (classical FFT denoiser) — lost some Russian text, gained hallucinations. REJECTED.
5. **HP 80Hz baseline** — original Codex-recommended cutoff. Good but missed chunk 04:30 conversation. SUPERSEDED by HP200.

## What was NOT tried (next options if HP200 isn't enough)

- ClearVoice MossFormerGAN_SE (Codex's #2) — would need Python venv setup, ~20 min, similar over-suppression risk
- ElevenLabs Voice Isolator — paid API, no Russian benchmark, would need API key
- Adobe Enhance Speech — paid cloud, manual upload only
- Whisper large-v3 (local) as second-opinion ASR — not installed; would let us cross-check Gemini's "[silence]" verdicts

## Key insight (from Codex deep research)

> "Denoising can HURT ASR. Whisper-large-v3 [and Gemini 3.5 Flash] are already noise-robust, so always run a raw baseline before applying neural enhancement."

Confirmed on this recording. A simple 200Hz high-pass + loudness normalization beat every neural denoiser tried.
