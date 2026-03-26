#!/usr/bin/env bash
set -euo pipefail

# Normalize audio loudness (EBU R128, -16 LUFS for YouTube)
# Usage: ./normalize-audio.sh <input.mp4> [-o output.mp4] [--eq]
#
# Options:
#   -o FILE   Output path (default: <input>_normalized.mp4)
#   --eq      Apply presence boost (2-4kHz) + highpass (80Hz) + light compression

INPUT=""
OUTPUT=""
EQ=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o) OUTPUT="$2"; shift 2 ;;
        --eq) EQ=true; shift ;;
        *) INPUT="$1"; shift ;;
    esac
done

if [[ -z "$INPUT" ]]; then
    echo "Usage: normalize-audio.sh <input.mp4> [-o output.mp4] [--eq]"
    exit 1
fi

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${INPUT%.*}_normalized.mp4"
fi

echo ">> Input:  $INPUT"
echo ">> Output: $OUTPUT"

if $EQ; then
    echo ">> Mode: loudness normalization + EQ + compression"
    # Chain: highpass → presence boost → compression → loudness normalization
    AUDIO_FILTER="highpass=f=80,equalizer=f=3000:t=q:w=1.5:g=3,acompressor=threshold=-20dB:ratio=3:attack=5:release=50,loudnorm=I=-16:TP=-1.5:LRA=11"
else
    echo ">> Mode: loudness normalization only"
    AUDIO_FILTER="loudnorm=I=-16:TP=-1.5:LRA=11"
fi

ffmpeg -y -i "$INPUT" \
    -c:v copy \
    -af "$AUDIO_FILTER" \
    -c:a aac -b:a 192k \
    "$OUTPUT" \
    -loglevel warning

# Report loudness
echo ">> Done: $OUTPUT"
echo ">> Checking output loudness..."
ffmpeg -i "$OUTPUT" -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=summary" -f null - 2>&1 | grep -E "Input Integrated|Input True Peak|Input LRA" || true
