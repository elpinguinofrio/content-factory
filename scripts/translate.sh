#!/usr/bin/env bash
set -uo pipefail

# Translate a transcript JSON (produced by transcribe.sh) into another
# language while preserving every segment's start/end timestamps exactly.
#
# Usage: ./translate.sh <basename>.transcript.json [target_lang=es]
#
# Outputs (next to input, with the trailing ".transcript.json" stripped
# from the basename — same convention as transcribe.sh):
#   <basename>.<lang>.transcript.json
#   <basename>.<lang>.srt
#
# Mock mode: when TRANSLATE_MOCK_RESPONSE_FILE is set, non-empty, and
# points to a readable file, the live Gemini API call is skipped and the
# file is read as the raw Gemini response envelope. GEMINI_API_KEY is
# NOT required in mock mode.

INPUT="${1:?Usage: translate.sh <basename>.transcript.json [target_lang=es]}"
LANG="${2:-es}"

# Strip the trailing ".transcript.json" suffix to get the basename used
# for sibling outputs. If the input doesn't end in ".transcript.json"
# (defensive), fall back to stripping the last extension.
if [[ "$INPUT" == *.transcript.json ]]; then
    BASENAME="${INPUT%.transcript.json}"
else
    BASENAME="${INPUT%.*}"
fi

OUT_JSON="${BASENAME}.${LANG}.transcript.json"
OUT_SRT="${BASENAME}.${LANG}.srt"

TMPRESP="/tmp/translate_$$.json"
TMPPAYLOAD="/tmp/translate_$$_payload.json"

cleanup() { rm -f "$TMPRESP" "$TMPPAYLOAD"; }
trap cleanup EXIT

# --- 1. Validate input existence FIRST (before any API/key checks) ---
if [[ ! -f "$INPUT" ]]; then
    echo "!! Input file not found: $INPUT" >&2
    exit 1
fi

# --- 2. Decide mode: mock vs live ---
MOCK_FILE="${TRANSLATE_MOCK_RESPONSE_FILE:-}"
USE_MOCK=0
if [[ -n "$MOCK_FILE" && -r "$MOCK_FILE" ]]; then
    USE_MOCK=1
fi

# --- 3. Load API key (only required in live mode) ---
GEMINI_API_KEY="${GEMINI_API_KEY:-}"
if [[ -z "$GEMINI_API_KEY" ]]; then
    # Walk a list of candidate .env files. Paths are evaluated relative
    # to the current working directory so a HOME-isolated, repo-isolated
    # cwd can opt out (see test_missing_api_key_errors).
    for envfile in "../../.env" "$HOME/dev_local/.env" "../.env" ".env"; do
        if [[ -f "$envfile" ]]; then
            key=$(grep -E '^GEMINI_API_KEY=' "$envfile" 2>/dev/null | head -1 | cut -d= -f2-)
            if [[ -n "$key" ]]; then
                GEMINI_API_KEY="$key"
                break
            fi
        fi
    done
fi

if [[ "$USE_MOCK" -eq 0 && -z "$GEMINI_API_KEY" ]]; then
    echo "!! GEMINI_API_KEY is not set. Provide it in the environment or in a .env file." >&2
    echo "   (Or set TRANSLATE_MOCK_RESPONSE_FILE for offline mock mode.)" >&2
    exit 1
fi

# --- 4. Either read mock response, or call Gemini API ---
if [[ "$USE_MOCK" -eq 1 ]]; then
    echo ">> Mock mode: reading Gemini response from $MOCK_FILE"
    cp "$MOCK_FILE" "$TMPRESP"
else
    echo ">> Using Gemini API"
    echo ">> Target language: $LANG"

    GEMINI_MODEL="gemini-2.5-flash"
    API_BASE="https://generativelanguage.googleapis.com"

    # Build a [MM:SS] text block from the input segments, then ask Gemini
    # to translate each line and emit the same [MM:SS] format back. This
    # mirrors transcribe.sh's prompt style so parsing is symmetric.
    INPUT_BLOCK=$(python3 - "$INPUT" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
lines = []
for seg in data.get("segments", []):
    s = int(seg.get("start", 0))
    mins, secs = s // 60, s % 60
    text = (seg.get("text") or "").replace("\n", " ").strip()
    lines.append(f"[{mins:02d}:{secs:02d}] {text}")
print("\n".join(lines))
PYEOF
    )

    PROMPT="Translate each of the following timestamped lines into ${LANG}.

Rules:
- Output exactly one line per input line, in the same order.
- Keep the leading [MM:SS] timestamp tag unchanged.
- Translate ONLY the text after the timestamp.
- Do not add commentary, headers, or extra blank lines.

Input:
${INPUT_BLOCK}"

    python3 - "$PROMPT" > "$TMPPAYLOAD" <<'PYEOF'
import json, sys
prompt = sys.argv[1]
payload = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"temperature": 0.2, "topP": 0.95, "topK": 40},
}
print(json.dumps(payload))
PYEOF

    echo ">> Sending to Gemini API (model: $GEMINI_MODEL)..."
    curl -s "${API_BASE}/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}" \
        -H "Content-Type: application/json" \
        -X POST \
        -d @"$TMPPAYLOAD" > "$TMPRESP"

    if ! python3 -c "import json; json.load(open('$TMPRESP'))['candidates']" 2>/dev/null; then
        echo "!! Gemini API error:" >&2
        python3 -c "import json; d=json.load(open('$TMPRESP')); print(json.dumps(d.get('error', d), indent=2))" 2>/dev/null >&2 || cat "$TMPRESP" >&2
        exit 1
    fi
fi

# --- 5. Parse the Gemini response and zip translated lines onto input
#        segments, preserving start/end timestamps exactly. ---
INPUT="$INPUT" OUT_JSON="$OUT_JSON" OUT_SRT="$OUT_SRT" \
    LANG="$LANG" TMPRESP="$TMPRESP" \
python3 <<'PYEOF'
import json, os, re, sys

input_path = os.environ["INPUT"]
out_json = os.environ["OUT_JSON"]
out_srt = os.environ["OUT_SRT"]
lang = os.environ["LANG"]
tmpresp = os.environ["TMPRESP"]

with open(input_path) as f:
    src = json.load(f)

with open(tmpresp) as f:
    resp = json.load(f)

try:
    text = resp["candidates"][0]["content"]["parts"][0]["text"]
except (KeyError, IndexError, TypeError) as e:
    print(f"!! Could not extract translated text from Gemini response: {e}",
          file=sys.stderr)
    sys.exit(1)

# Pull the lines that match [MM:SS] ...; strip the timestamp tag.
pattern = re.compile(r'^\s*\[(\d{1,2}):(\d{2})\]\s*(.*)$')
translated = []
for raw in text.strip().split("\n"):
    line = raw.strip()
    if not line:
        continue
    m = pattern.match(line)
    if m:
        translated.append(m.group(3).strip())
    else:
        # Non-tagged line: keep as-is (best-effort fallback)
        translated.append(line)

src_segments = src.get("segments", [])
if len(translated) < len(src_segments):
    print(f"!! Translated line count ({len(translated)}) is less than input "
          f"segment count ({len(src_segments)}). Cannot map 1:1.",
          file=sys.stderr)
    sys.exit(1)

# Zip translated text onto input segments, preserving start/end exactly.
out_segments = []
for i, seg in enumerate(src_segments):
    out_segments.append({
        "start": seg["start"],
        "end": seg["end"],
        "text": translated[i],
    })

out_doc = {
    "segments": out_segments,
    "language": lang,
    "source": "gemini",
    "raw_text": text,
}
with open(out_json, "w") as f:
    json.dump(out_doc, f, ensure_ascii=False, indent=2)
print(f">> Output: {out_json}")

# SRT
def fmt(t):
    # Accept int or float seconds; emit HH:MM:SS,mmm
    total_ms = int(round(float(t) * 1000))
    h = total_ms // 3_600_000
    m = (total_ms % 3_600_000) // 60_000
    s = (total_ms % 60_000) // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

with open(out_srt, "w") as f:
    for i, seg in enumerate(out_segments, 1):
        f.write(f"{i}\n")
        f.write(f"{fmt(seg['start'])} --> {fmt(seg['end'])}\n")
        f.write(f"{seg['text']}\n\n")
print(f">> Output: {out_srt}")
print(f">> Segments: {len(out_segments)}")
PYEOF
