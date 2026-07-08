#!/usr/bin/env bash
set -uo pipefail

# Hard-burn an SRT subtitle file into a video using ffmpeg's `subtitles`
# filter. The video is re-encoded (H.264, yuv420p) — that is intentional
# and is the whole point of the feature. Audio is copied through.
#
# Usage: ./burn-subs.sh <video> <srt> [output_path]
#
# Inputs:
#   $1 — path to an existing video file
#   $2 — path to an existing SRT subtitle file
#   $3 — optional explicit output path. When omitted, output defaults to
#        "<video_basename>_subbed.mp4" next to the input video, where
#        <video_basename> is the input path with its trailing extension
#        stripped. The default output is always .mp4 regardless of input
#        container.
#
# Behavior:
#   - Idempotent: ffmpeg is invoked with `-y` so the output is overwritten
#     on repeat runs.
#   - Errors (missing video, missing SRT) exit non-zero and write a
#     message mentioning the offending path to stderr.

VIDEO="${1:-}"
SRT="${2:-}"
OUTPUT="${3:-}"

if [[ -z "$VIDEO" || -z "$SRT" ]]; then
    echo "Usage: burn-subs.sh <video> <srt> [output_path]" >&2
    exit 1
fi

# --- 1. Validate inputs FIRST (before any tool checks) ---
if [[ ! -f "$VIDEO" ]]; then
    echo "!! Video file not found: $VIDEO" >&2
    exit 1
fi

if [[ ! -f "$SRT" ]]; then
    echo "!! SRT file not found: $SRT" >&2
    exit 1
fi

# --- 2. Resolve default output path ---
if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${VIDEO%.*}_subbed.mp4"
fi

# --- 3. Resolve absolute paths so we can cd into the SRT's directory.
#        This is the simplest robust way to handle SRT paths containing
#        characters (`:`, `'`, `[`, `]`, `,`) that would otherwise need
#        escaping in ffmpeg's filter graph syntax. ---
abs_path() {
    local p="$1"
    if [[ "$p" = /* ]]; then
        echo "$p"
    else
        echo "$PWD/$p"
    fi
}

VIDEO_ABS="$(abs_path "$VIDEO")"
SRT_ABS="$(abs_path "$SRT")"
OUTPUT_ABS="$(abs_path "$OUTPUT")"

SRT_DIR="$(dirname "$SRT_ABS")"
SRT_BASE="$(basename "$SRT_ABS")"

echo ">> Video:  $VIDEO_ABS"
echo ">> SRT:    $SRT_ABS"
echo ">> Output: $OUTPUT_ABS"

# --- 4. Run ffmpeg from the SRT's directory so the filter only needs the
#        bare basename — no colon/path escaping required. ---
(
    cd "$SRT_DIR"
    ffmpeg -y -i "$VIDEO_ABS" \
        -vf "subtitles=${SRT_BASE}" \
        -c:v libx264 -pix_fmt yuv420p \
        -c:a copy \
        "$OUTPUT_ABS" \
        -loglevel error
)

echo ">> Done: $OUTPUT_ABS"
