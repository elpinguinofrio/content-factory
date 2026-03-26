# CLI Transcription Tools for Text-Based Video Editing

Research date: 2026-03-25

## Tool Comparison

| Tool | Engine | Speed | Word timestamps | Diarization | Mac (Apple Silicon) | GPU req |
|------|--------|-------|-----------------|-------------|---------------------|---------|
| whisper (OpenAI) | PyTorch | 1x baseline | yes (--word_timestamps) | no | CPU/MPS | optional |
| whisper.cpp | GGML/C++ | ~4-8x | yes (--max-len 1) | no | Metal accel | no |
| faster-whisper | CTranslate2 | ~4x, less RAM | yes | no | CPU only* | optional |
| whisperX | faster-whisper + wav2vec2 | ~70x (batched) | best (forced alignment) | yes (pyannote) | CUDA preferred | recommended |
| insanely-fast-whisper | HF Transformers + Flash Attn | ~90x | yes | no | MPS (Mac) | CUDA/MPS |
| mlx-whisper | Apple MLX | ~3x faster than whisper.cpp on M1 | yes | no | native MLX | Apple Silicon only |
| stable-ts | Whisper + stabilization | ~1x | yes (improved) | no | same as whisper | optional |
| whisper-timestamped | Whisper + DTW alignment | ~1x | yes (improved) | no | same as whisper | optional |

*faster-whisper: CTranslate2 has limited MPS support; CPU mode works fine on Mac.

## 1. whisper.cpp (Best for: local, lightweight, no Python)

### Install
```bash
# macOS with Homebrew
brew install whisper-cpp

# Or build from source (with Metal support on Mac)
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp && cmake -B build && cmake --build build --config Release

# Download model
./models/download-ggml-model.sh large-v3
```

### CLI Commands
```bash
# Basic transcription → SRT
whisper-cpp -m models/ggml-large-v3.bin -f input.wav -osrt

# VTT output
whisper-cpp -m models/ggml-large-v3.bin -f input.wav -ovtt

# JSON output
whisper-cpp -m models/ggml-large-v3.bin -f input.wav -ojf

# Word-level timestamps (set max segment length to 1 word)
whisper-cpp -m models/ggml-large-v3.bin -f input.wav -ml 1 -osrt

# All formats at once + word timestamps
whisper-cpp -m models/ggml-large-v3.bin -f input.wav -ml 1 -osrt -ovtt -ojf

# With language hint (Russian example)
whisper-cpp -m models/ggml-large-v3.bin -f input.wav -l ru -osrt
```

### Key flags
- `-ml N` / `--max-len N` — max chars per segment (use 1 for word-level)
- `-osrt` — output SRT file
- `-ovtt` — output VTT file
- `-ojf` — output JSON (full, with timestamps)
- `-of NAME` — output file prefix
- `-t N` — number of threads
- `-l LANG` — language code (auto-detect if omitted)
- `--print-colors` — show confidence coloring in terminal

### Note on input format
whisper.cpp requires 16kHz mono WAV. Convert first:
```bash
ffmpeg -i input.mp4 -ar 16000 -ac 1 -c:a pcm_s16le input.wav
```

## 2. faster-whisper (Best for: Python ecosystem, good speed/accuracy balance)

### Install
```bash
pip install faster-whisper
# CLI wrapper compatible with OpenAI whisper CLI:
pip install whisper-ctranslate2
```

### CLI Commands (whisper-ctranslate2)
```bash
# SRT with word-level timestamps
whisper-ctranslate2 input.wav --model large-v3 --output_format srt --word_timestamps true

# JSON output
whisper-ctranslate2 input.wav --model large-v3 --output_format json --word_timestamps true

# All formats
whisper-ctranslate2 input.wav --model large-v3 --output_format all --word_timestamps true

# Specific language
whisper-ctranslate2 input.wav --model large-v3 --language ru --output_format srt
```

### Python one-liner for word-level JSON
```python
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", compute_type="int8")
segments, info = model.transcribe("input.wav", word_timestamps=True)
for seg in segments:
    for word in seg.words:
        print(f"{word.start:.3f} -> {word.end:.3f}: {word.word}")
```

## 3. whisperX (Best for: precise word timestamps + speaker diarization)

### Install
```bash
pip install whisperx
```

### CLI Commands
```bash
# Basic with word-level timestamps (default)
whisperx input.wav --model large-v3 --output_format json

# With speaker diarization (requires HuggingFace token)
whisperx input.wav --model large-v3 --diarize --hf_token YOUR_HF_TOKEN

# SRT output
whisperx input.wav --model large-v3 --output_format srt

# Specific language + output dir
whisperx input.wav --model large-v3 --language ru --output_dir ./transcripts

# Align only (if you already have a transcript)
whisperx input.wav --model large-v3 --align_model WAV2VEC2_MODEL
```

### Why whisperX for text-based editing
- Uses forced alignment (wav2vec2) for genuinely accurate word boundaries
- Standard Whisper word timestamps are approximate; whisperX corrects them
- Speaker labels let you filter/edit by speaker
- JSON output includes per-word `start`, `end`, `score` fields

## 4. insanely-fast-whisper (Best for: raw speed on GPU)

### Install & Run
```bash
pip install insanely-fast-whisper
# or run without install:
pipx run insanely-fast-whisper --file-name input.wav
```

### CLI Commands
```bash
# Basic (outputs JSON to stdout)
insanely-fast-whisper --file-name input.wav --model-name openai/whisper-large-v3

# With word timestamps + specific output file
insanely-fast-whisper --file-name input.wav --transcript-path output.json --timestamp word

# Batch size for speed (GPU memory dependent)
insanely-fast-whisper --file-name input.wav --batch-size 24 --timestamp word
```

Performance: ~150 min audio in <98 seconds on NVIDIA GPU. Works on Mac MPS too (slower).

## 5. mlx-whisper (Best for: Apple Silicon Macs)

### Install
```bash
pip install mlx-whisper
```

### Usage (Python, no standalone CLI)
```python
import mlx_whisper
result = mlx_whisper.transcribe(
    "input.wav",
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    word_timestamps=True
)
# result["segments"][i]["words"] → [{word, start, end}, ...]
```

### Wrapper script for CLI use
```bash
python -c "
import mlx_whisper, json, sys
result = mlx_whisper.transcribe(sys.argv[1], path_or_hf_repo='mlx-community/whisper-large-v3-turbo', word_timestamps=True)
print(json.dumps(result, ensure_ascii=False, indent=2))
" input.wav > output.json
```

~3x faster than whisper.cpp on M1 Max. lightning-whisper-mlx claims 10x over whisper.cpp.

## 6. stable-ts (Best for: improved timestamp accuracy with any Whisper backend)

### Install
```bash
pip install stable-ts
```

### CLI Commands
```bash
# Transcribe with stabilized timestamps
stable-ts input.wav --model large-v3 --output audio.srt

# Word-level SRT
stable-ts input.wav --model large-v3 --word_level true --output audio.srt

# Use faster-whisper backend for speed
stable-ts input.wav --model large-v3 --output audio.json --backend faster-whisper
```

### Output format: word-level VTT example
```
00:00:07.760 --> 00:00:09.900
But<00:00:07.860> when<00:00:08.040> you<00:00:08.280> arrived<00:00:08.580> at<00:00:08.800> that<00:00:09.000> distant<00:00:09.400> world
```

### SRT word-level (one word per cue)
```
1
00:00:07,760 --> 00:00:07,860
But

2
00:00:07,860 --> 00:00:08,040
when
```

## Output Format Examples

### SRT (SubRip)
```
1
00:00:00,000 --> 00:00:03,520
This is the first segment of speech.

2
00:00:03,520 --> 00:00:07,040
And this is the second segment.
```

### VTT (WebVTT)
```
WEBVTT

00:00:00.000 --> 00:00:03.520
This is the first segment of speech.

00:00:03.520 --> 00:00:07.040
And this is the second segment.
```

### JSON with word-level timestamps (whisperX style)
```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 3.52,
      "text": "This is the first segment of speech.",
      "words": [
        {"word": "This", "start": 0.0, "end": 0.28, "score": 0.99},
        {"word": "is", "start": 0.28, "end": 0.42, "score": 0.98},
        {"word": "the", "start": 0.42, "end": 0.56, "score": 0.97},
        {"word": "first", "start": 0.56, "end": 0.92, "score": 0.99},
        {"word": "segment", "start": 0.92, "end": 1.34, "score": 0.95},
        {"word": "of", "start": 1.34, "end": 1.48, "score": 0.98},
        {"word": "speech.", "start": 1.48, "end": 1.88, "score": 0.96}
      ]
    }
  ],
  "language": "en"
}
```

## Text-Based Editing Workflow (CLI-only)

### Step 1: Extract audio
```bash
ffmpeg -i video.mp4 -ar 16000 -ac 1 -c:a pcm_s16le audio.wav
```

### Step 2: Transcribe with word-level timestamps
```bash
# Pick one:
whisperx audio.wav --model large-v3 --output_format json --output_dir ./
# or
whisper-ctranslate2 audio.wav --model large-v3 --output_format json --word_timestamps true
```

### Step 3: Edit the transcript (text-based editing)
Edit the JSON/SRT — delete words, segments, or sections you don't want. The timestamps tell you exactly where to cut the video.

### Step 4: Generate EDL / cut video with ffmpeg
```bash
# Example: extract specific time ranges from the edited transcript
ffmpeg -i video.mp4 -ss 00:00:05.200 -to 00:00:12.800 -c copy segment1.mp4
ffmpeg -i video.mp4 -ss 00:00:15.100 -to 00:00:28.400 -c copy segment2.mp4

# Concatenate kept segments
echo "file 'segment1.mp4'" > filelist.txt
echo "file 'segment2.mp4'" >> filelist.txt
ffmpeg -f concat -safe 0 -i filelist.txt -c copy output.mp4
```

### Automated silence removal (complementary)
```bash
# auto-editor: audio-level based silence removal
pip install auto-editor
auto-editor video.mp4 --margin 0.2s --export premiere  # or --export resolve

# Or purely ffmpeg-based silence detection
ffmpeg -i video.mp4 -af silencedetect=noise=-30dB:d=0.5 -f null - 2>&1 | grep silence
```

## Recommendation for Content Factory

For a solo creator workflow on Mac:

1. **Primary tool: whisperX** — best word-level accuracy via forced alignment, speaker diarization if needed, JSON output perfect for scripting
2. **Fallback/fast: whisper.cpp** — no Python dependencies, Metal-accelerated on Mac, good for quick SRT generation
3. **Apple Silicon optimization: mlx-whisper** — fastest on M-series Macs, but requires a Python wrapper script
4. **Silence removal: auto-editor** — complements transcription-based editing for rough cuts

Pipeline: `ffmpeg (extract audio)` → `whisperX (transcribe + align)` → `jq/python (filter JSON)` → `ffmpeg (cut + concat)`

## Sources
- [whisper.cpp GitHub](https://github.com/ggml-org/whisper.cpp)
- [whisper.cpp CLI README](https://github.com/ggml-org/whisper.cpp/tree/master/examples/cli)
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper)
- [whisperX GitHub](https://github.com/m-bain/whisperX)
- [insanely-fast-whisper GitHub](https://github.com/Vaibhavs10/insanely-fast-whisper)
- [mlx-whisper PyPI](https://pypi.org/project/mlx-whisper/)
- [lightning-whisper-mlx GitHub](https://github.com/mustafaaljadery/lightning-whisper-mlx)
- [stable-ts GitHub](https://github.com/jianfch/stable-ts)
- [whisper-timestamped GitHub](https://github.com/linto-ai/whisper-timestamped)
- [Choosing between Whisper variants (Modal blog)](https://modal.com/blog/choosing-whisper-variants)
- [auto-editor PyPI](https://pypi.org/project/auto-editor/)
- [whisply — batch transcription tool](https://github.com/tsmdt/whisply)
- [Sacha Chua: WhisperX for word-level timestamps](https://sachachua.com/blog/2024/09/using-whisperx-to-get-word-level-timestamps-for-audio-editing-with-emacs-and-subed-record/)
- [MarkTechPost: WhisperX pipeline tutorial (2025)](https://www.marktechpost.com/2025/10/02/how-to-build-an-advanced-voice-ai-pipeline-with-whisperx-for-transcription-alignment-analysis-and-export/)
