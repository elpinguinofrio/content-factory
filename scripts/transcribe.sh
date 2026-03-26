#!/usr/bin/env bash
set -euo pipefail

# Transcribe video/audio to JSON (segment-level timestamps) + SRT
# Usage: ./transcribe.sh <input_file> [language]
#
# Priority: Gemini API (if GEMINI_API_KEY found) → whisper-cpp → whisper-ctranslate2
# Outputs: <basename>.transcript.json and <basename>.srt

INPUT="${1:?Usage: transcribe.sh <input_file> [language]}"
LANG="${2:-ru}"
BASENAME="${INPUT%.*}"
TMPMP3="/tmp/transcribe_$$.mp3"
TMPWAV="/tmp/transcribe_$$.wav"
TMPJSON="/tmp/transcribe_$$.json"

cleanup() { rm -f "$TMPMP3" "$TMPWAV" "$TMPJSON" /tmp/transcribe_$$_upload_header.tmp /tmp/transcribe_$$_file_info.json; }
trap cleanup EXIT

# --- Load API key from .env ---
GEMINI_API_KEY="${GEMINI_API_KEY:-}"
if [[ -z "$GEMINI_API_KEY" ]]; then
    # Check parent .env (same pattern as diaryOS blackbox)
    for envfile in "$(dirname "$0")/../../.env" "$HOME/dev_local/.env" "../.env" ".env"; do
        if [[ -f "$envfile" ]]; then
            key=$(grep -E '^GEMINI_API_KEY=' "$envfile" 2>/dev/null | head -1 | cut -d= -f2-)
            if [[ -n "$key" ]]; then
                GEMINI_API_KEY="$key"
                break
            fi
        fi
    done
fi

# ═══════════════════════════════════════════════════════
# Method 1: Gemini API (primary)
# ═══════════════════════════════════════════════════════
if [[ -n "$GEMINI_API_KEY" ]]; then
    echo ">> Using Gemini API"
    echo ">> Language: $LANG"

    # Extract audio as MP3 (64k mono 16kHz — matches diaryOS pipeline, small for API)
    echo ">> Extracting audio from: $INPUT"
    ffmpeg -y -i "$INPUT" -ar 16000 -ac 1 -b:a 64k "$TMPMP3" -loglevel warning

    FILE_SIZE=$(wc -c < "$TMPMP3" | tr -d ' ')
    echo ">> Audio file: ${FILE_SIZE} bytes"

    GEMINI_MODEL="gemini-2.5-flash"
    API_BASE="https://generativelanguage.googleapis.com"

    # Prompt for timestamped transcription
    PROMPT="Transcribe the following audio verbatim with timestamps.

Rules:
- Output format: SRT-style segments with timestamps and text
- Timestamp format: [MM:SS] at the start of each segment
- One logical sentence or phrase per segment (3-10 seconds each)
- Transcribe exactly what is said — do not summarize or paraphrase
- Include filler words (uh, um, э, ну, значит, короче, etc.)
- If multiple speakers, label them: Speaker 1, Speaker 2, etc.
- The audio is in ${LANG} language
- If silent or empty, output exactly: [SILENCE]
- Do NOT add commentary. Output ONLY the transcript.

Example output format:
[00:00] Привет, сегодня мы поговорим о важной теме.
[00:05] Э, значит, первое что нужно сказать...
[00:12] Speaker 2: Да, я согласен с этим."

    if [[ "$FILE_SIZE" -gt 15000000 ]]; then
        # Large file: use File API (upload first, then reference)
        echo ">> Large file — using File API upload"

        MIME_TYPE="audio/mpeg"
        UPLOAD_HEADER="/tmp/transcribe_$$_upload_header.tmp"
        FILE_INFO="/tmp/transcribe_$$_file_info.json"

        # Step 1: Start resumable upload
        curl -s "${API_BASE}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
            -D "$UPLOAD_HEADER" \
            -H "X-Goog-Upload-Protocol: resumable" \
            -H "X-Goog-Upload-Command: start" \
            -H "X-Goog-Upload-Header-Content-Length: ${FILE_SIZE}" \
            -H "X-Goog-Upload-Header-Content-Type: ${MIME_TYPE}" \
            -H "Content-Type: application/json" \
            -d '{"file": {"display_name": "transcribe_audio"}}' \
            -o /dev/null

        UPLOAD_URL=$(grep -i "x-goog-upload-url: " "$UPLOAD_HEADER" | cut -d" " -f2 | tr -d "\r")

        if [[ -z "$UPLOAD_URL" ]]; then
            echo "!! Failed to get upload URL from File API"
            echo "!! Falling back to local transcription..."
        else
            # Step 2: Upload bytes
            curl -s "$UPLOAD_URL" \
                -H "Content-Length: ${FILE_SIZE}" \
                -H "X-Goog-Upload-Offset: 0" \
                -H "X-Goog-Upload-Command: upload, finalize" \
                --data-binary "@${TMPMP3}" > "$FILE_INFO"

            FILE_URI=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['file']['uri'])" "$FILE_INFO" 2>/dev/null || echo "")

            if [[ -z "$FILE_URI" ]]; then
                echo "!! Failed to upload file. Response:"
                cat "$FILE_INFO"
                echo "!! Falling back to local transcription..."
            else
                echo ">> Uploaded: $FILE_URI"

                # Step 3: Generate content with file reference
                curl -s "${API_BASE}/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}" \
                    -H "Content-Type: application/json" \
                    -X POST \
                    -d "$(python3 -c "
import json
payload = {
    'contents': [{'parts': [
        {'text': $(python3 -c "import json; print(json.dumps('$PROMPT'))" 2>/dev/null || echo '"Transcribe with timestamps"')},
        {'file_data': {'mime_type': 'audio/mpeg', 'file_uri': '$FILE_URI'}}
    ]}],
    'generationConfig': {'temperature': 1.0, 'topP': 0.95, 'topK': 40}
}
print(json.dumps(payload))
")" > "$TMPJSON"
            fi
        fi
    else
        # Small file: inline base64
        echo ">> Inline base64 upload"
        AUDIO_B64=$(base64 < "$TMPMP3")

        python3 -c "
import json, sys

prompt = '''$PROMPT'''

payload = {
    'contents': [{'parts': [
        {'text': prompt},
        {'inline_data': {'mime_type': 'audio/mpeg', 'data': '$AUDIO_B64'}}
    ]}],
    'generationConfig': {'temperature': 1.0, 'topP': 0.95, 'topK': 40}
}
print(json.dumps(payload))
" > /tmp/transcribe_$$_payload.json

        echo ">> Sending to Gemini API (model: $GEMINI_MODEL)..."
        curl -s "${API_BASE}/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}" \
            -H "Content-Type: application/json" \
            -X POST \
            -d @/tmp/transcribe_$$_payload.json > "$TMPJSON"

        rm -f /tmp/transcribe_$$_payload.json
    fi

    # Parse Gemini response if we got one
    if [[ -f "$TMPJSON" ]] && python3 -c "import json; json.load(open('$TMPJSON'))['candidates']" 2>/dev/null; then
        echo ">> Parsing Gemini response..."

        python3 << 'PYEOF'
import json, re, sys, os

tmpjson = os.environ.get("TMPJSON", sys.argv[1] if len(sys.argv) > 1 else "")
basename = os.environ.get("BASENAME", sys.argv[2] if len(sys.argv) > 2 else "output")

with open(tmpjson) as f:
    resp = json.load(f)

text = resp["candidates"][0]["content"]["parts"][0]["text"]

# Parse [MM:SS] lines into segments
segments = []
pattern = re.compile(r'\[(\d{1,2}):(\d{2})\]\s*(.*)')
lines = text.strip().split('\n')

for line in lines:
    line = line.strip()
    if not line:
        continue
    m = pattern.match(line)
    if m:
        mins, secs, content = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        start = mins * 60 + secs
        segments.append({"start": start, "text": content})

# Calculate end times (each segment ends when next begins; last segment +5s)
for i in range(len(segments)):
    if i + 1 < len(segments):
        segments[i]["end"] = segments[i + 1]["start"]
    else:
        segments[i]["end"] = segments[i]["start"] + 5

# Write JSON
transcript = {
    "segments": segments,
    "language": os.environ.get("LANG", "ru"),
    "source": "gemini",
    "raw_text": text,
}
json_path = f"{basename}.transcript.json"
with open(json_path, "w") as f:
    json.dump(transcript, f, ensure_ascii=False, indent=2)
print(f">> Output: {json_path}")

# Write SRT
srt_path = f"{basename}.srt"
with open(srt_path, "w") as f:
    for i, seg in enumerate(segments, 1):
        s_h, s_m, s_s = seg["start"] // 3600, (seg["start"] % 3600) // 60, seg["start"] % 60
        e_h, e_m, e_s = seg["end"] // 3600, (seg["end"] % 3600) // 60, seg["end"] % 60
        f.write(f"{i}\n")
        f.write(f"{s_h:02d}:{s_m:02d}:{s_s:02d},000 --> {e_h:02d}:{e_m:02d}:{e_s:02d},000\n")
        f.write(f"{seg['text']}\n\n")
print(f">> Output: {srt_path}")
print(f">> Segments: {len(segments)}")
PYEOF

        exit 0
    elif [[ -f "$TMPJSON" ]]; then
        echo "!! Gemini API error:"
        python3 -c "import json; d=json.load(open('$TMPJSON')); print(json.dumps(d.get('error', d), indent=2))" 2>/dev/null || cat "$TMPJSON"
        echo ""
        echo "!! Falling back to local transcription..."
    fi
fi

# ═══════════════════════════════════════════════════════
# Method 2: whisper-cpp (local fallback)
# ═══════════════════════════════════════════════════════
echo ">> Extracting audio from: $INPUT"
ffmpeg -y -i "$INPUT" -ar 16000 -ac 1 -c:a pcm_s16le "$TMPWAV" -loglevel warning

if command -v whisper-cpp &>/dev/null; then
    echo ">> Using whisper-cpp (local)"

    MODEL=""
    for candidate in \
        "$HOME/.local/share/whisper-cpp/ggml-large-v3.bin" \
        "$HOME/models/ggml-large-v3.bin" \
        "$(brew --prefix 2>/dev/null)/share/whisper-cpp/models/ggml-large-v3.bin" \
        "$HOME/.local/share/whisper-cpp/ggml-medium.bin" \
        "$(brew --prefix 2>/dev/null)/share/whisper-cpp/models/ggml-medium.bin" \
        "$HOME/.local/share/whisper-cpp/ggml-base.bin" \
        "$(brew --prefix 2>/dev/null)/share/whisper-cpp/models/ggml-base.bin"; do
        [[ -f "$candidate" ]] && MODEL="$candidate" && break
    done

    if [[ -n "$MODEL" ]]; then
        echo ">> Model: $MODEL"
        echo ">> Language: $LANG"
        whisper-cpp -m "$MODEL" -f "$TMPWAV" -l "$LANG" -ml 1 -ojf -osrt -of "$BASENAME"
        [[ -f "${BASENAME}.json" ]] && mv "${BASENAME}.json" "${BASENAME}.transcript.json"
        echo ">> Output: ${BASENAME}.transcript.json"
        echo ">> Output: ${BASENAME}.srt"
        exit 0
    fi
fi

# ═══════════════════════════════════════════════════════
# Method 3: whisper-ctranslate2 (Python fallback)
# ═══════════════════════════════════════════════════════
if command -v whisper-ctranslate2 &>/dev/null; then
    echo ">> Using whisper-ctranslate2 (faster-whisper)"
    echo ">> Language: $LANG"

    OUTDIR="$(dirname "$BASENAME")"
    whisper-ctranslate2 "$TMPWAV" --model large-v3 --language "$LANG" --output_format json --word_timestamps true --output_dir "$OUTDIR"

    WAVBASE="$(basename "$TMPWAV" .wav)"
    [[ -f "${OUTDIR}/${WAVBASE}.json" ]] && mv "${OUTDIR}/${WAVBASE}.json" "${BASENAME}.transcript.json"

    whisper-ctranslate2 "$TMPWAV" --model large-v3 --language "$LANG" --output_format srt --word_timestamps true --output_dir "$OUTDIR"
    [[ -f "${OUTDIR}/${WAVBASE}.srt" ]] && mv "${OUTDIR}/${WAVBASE}.srt" "${BASENAME}.srt"

    echo ">> Output: ${BASENAME}.transcript.json"
    echo ">> Output: ${BASENAME}.srt"
    exit 0
fi

echo "!! No transcription method available."
echo "   Set GEMINI_API_KEY in .env, or install:"
echo "   brew install whisper-cpp"
echo "   pip install whisper-ctranslate2"
exit 1
