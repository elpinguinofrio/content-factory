#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# tests/test_burn_subs.sh — TDD red-phase tests for scripts/burn-subs.sh
# ─────────────────────────────────────────────────────────────────────
#
# CONTRACT FOR burn-subs.sh (the BUILDER must implement this):
#
# 1. INVOCATION
#    scripts/burn-subs.sh <video> <srt> [output_path]
#
# 2. INPUTS
#    - $1: path to an existing video file (any container ffmpeg can read).
#    - $2: path to an existing SRT subtitle file.
#    - $3 (optional): explicit output path. When omitted, output defaults
#      to "<video_basename>_subbed.mp4" written next to the input video,
#      where <video_basename> is the input path with its trailing
#      extension stripped (e.g. "/tmp/x/clip.mp4" → "/tmp/x/clip_subbed.mp4",
#      "/tmp/x/clip.mov" → "/tmp/x/clip_subbed.mp4").
#
# 3. BEHAVIOR
#    - Hard-burns the subtitles into the video using ffmpeg's `subtitles`
#      filter (subtitles=<srt>). This re-encodes the video stream — that
#      is intentional and is the whole point of the feature.
#    - Audio stream should be preserved (copy or transcode, both fine —
#      tests only assert presence of a video stream and approximate
#      duration; audio is out of scope here but should not be dropped).
#    - Idempotent: running twice on the same inputs must succeed both
#      times (i.e. ffmpeg invoked with `-y` so the output is overwritten).
#
# 4. ERROR CASES (all exit non-zero, stderr mentions the offending path)
#    - Missing video file → exit non-zero, stderr mentions the path.
#    - Missing SRT file → exit non-zero, stderr mentions the path.
#
# 5. SLASH COMMAND
#    - .claude/commands/burn-subs.md must exist as the user-facing entry
#      point (no contract on its content beyond existence).
#
# ─────────────────────────────────────────────────────────────────────
# Test framework: pure bash, mirroring tests/test_translate.sh.
# Each test_* function returns 0 on pass, 1 on fail. main() runs them
# all, counts failures, exits non-zero if any failed.
# Fixtures (tiny mp4 + tiny srt) are GENERATED at runtime per test in a
# mktemp dir so we don't commit binary blobs and we exercise the full
# ffmpeg path end-to-end. No network, no API key.
# ─────────────────────────────────────────────────────────────────────

set -uo pipefail
# NOTE: deliberately NOT using `set -e` at the top level — individual
# tests need to capture non-zero exits from burn-subs.sh without
# aborting the suite (same pattern as tests/test_translate.sh).

# Resolve project root (this script lives in <root>/tests/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BURN_SUBS_SH="$PROJECT_ROOT/scripts/burn-subs.sh"
BURN_SUBS_MD="$PROJECT_ROOT/.claude/commands/burn-subs.md"

PASS=0
FAIL=0
FAILED_TESTS=()

# ── helpers ──────────────────────────────────────────────────────────
log_pass() { printf "  PASS: %s\n" "$1"; PASS=$((PASS + 1)); }
log_fail() {
    printf "  FAIL: %s\n      %s\n" "$1" "$2"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("$1")
}

make_workdir() {
    local d
    d=$(mktemp -d -t burn_subs_test.XXXXXX)
    echo "$d"
}

# Build a tiny 1-second 320x240 blue mp4 in $1, named $2 (default sample.mp4).
# Returns the absolute path on stdout.
make_sample_video() {
    local workdir="$1"
    local name="${2:-sample.mp4}"
    local out="$workdir/$name"
    ffmpeg -y -f lavfi -i color=blue:size=320x240:duration=1:rate=10 \
        -c:v libx264 -pix_fmt yuv420p "$out" -loglevel error
    echo "$out"
}

# Write a 2-cue SRT spanning 0.0-0.5s and 0.5-1.0s into $1/$2 (default sample.srt).
# Returns the absolute path on stdout.
make_sample_srt() {
    local workdir="$1"
    local name="${2:-sample.srt}"
    local out="$workdir/$name"
    cat > "$out" <<'SRT'
1
00:00:00,000 --> 00:00:00,500
Hello world

2
00:00:00,500 --> 00:00:01,000
Goodbye world
SRT
    echo "$out"
}

# Echo the duration in seconds (float) of a media file using ffprobe.
probe_duration() {
    ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" 2>/dev/null
}

# ── tests ────────────────────────────────────────────────────────────

test_script_exists_and_executable() {
    local name="test_script_exists_and_executable"
    if [[ ! -f "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "scripts/burn-subs.sh does not exist at $BURN_SUBS_SH"
        return 1
    fi
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "scripts/burn-subs.sh exists but is not executable (chmod +x)"
        return 1
    fi
    log_pass "$name"
}

test_command_file_exists() {
    local name="test_command_file_exists"
    if [[ ! -f "$BURN_SUBS_MD" ]]; then
        log_fail "$name" ".claude/commands/burn-subs.md does not exist at $BURN_SUBS_MD"
        return 1
    fi
    log_pass "$name"
}

test_missing_video_file_errors() {
    local name="test_missing_video_file_errors"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local srt; srt=$(make_sample_srt "$workdir")
    local bogus="$workdir/does_not_exist.mp4"
    local stderr_file="$workdir/stderr.txt"

    set +e
    "$BURN_SUBS_SH" "$bogus" "$srt" 2>"$stderr_file" >/dev/null
    local rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log_fail "$name" "expected non-zero exit for missing video, got 0. stderr: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    if ! grep -qF "$bogus" "$stderr_file" && ! grep -qiE 'not found|no such|missing|does not exist' "$stderr_file"; then
        log_fail "$name" "stderr did not mention the missing video path. stderr was: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_missing_srt_file_errors() {
    local name="test_missing_srt_file_errors"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir")
    local bogus="$workdir/does_not_exist.srt"
    local stderr_file="$workdir/stderr.txt"

    set +e
    "$BURN_SUBS_SH" "$video" "$bogus" 2>"$stderr_file" >/dev/null
    local rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log_fail "$name" "expected non-zero exit for missing SRT, got 0. stderr: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    if ! grep -qF "$bogus" "$stderr_file" && ! grep -qiE 'not found|no such|missing|does not exist' "$stderr_file"; then
        log_fail "$name" "stderr did not mention the missing SRT path. stderr was: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_default_output_path() {
    local name="test_default_output_path"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir" "sample.mp4")
    local srt; srt=$(make_sample_srt "$workdir" "sample.srt")
    local expected="$workdir/sample_subbed.mp4"

    set +e
    "$BURN_SUBS_SH" "$video" "$srt" >"$workdir/stdout.txt" 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "burn-subs.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi
    if [[ ! -f "$expected" ]]; then
        log_fail "$name" "expected default output not found: $expected (workdir contents: $(ls "$workdir"))"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_explicit_output_path() {
    local name="test_explicit_output_path"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir")
    local srt; srt=$(make_sample_srt "$workdir")
    local explicit="$workdir/custom_named_output.mp4"

    set +e
    "$BURN_SUBS_SH" "$video" "$srt" "$explicit" >"$workdir/stdout.txt" 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "burn-subs.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi
    if [[ ! -f "$explicit" ]]; then
        log_fail "$name" "explicit output not found: $explicit (workdir contents: $(ls "$workdir"))"
        rm -rf "$workdir"
        return 1
    fi
    # Default-named output must NOT exist when explicit was given.
    if [[ -f "$workdir/sample_subbed.mp4" ]]; then
        log_fail "$name" "default-named output also created when explicit path given (workdir: $(ls "$workdir"))"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_output_is_valid_video() {
    local name="test_output_is_valid_video"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir")
    local srt; srt=$(make_sample_srt "$workdir")
    local out="$workdir/sample_subbed.mp4"

    set +e
    "$BURN_SUBS_SH" "$video" "$srt" >"$workdir/stdout.txt" 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "burn-subs.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi
    if [[ ! -s "$out" ]]; then
        log_fail "$name" "output file missing or empty: $out"
        rm -rf "$workdir"
        return 1
    fi
    if ! ffprobe -v error -show_streams "$out" 2>/dev/null | grep -q '^codec_type=video$'; then
        log_fail "$name" "output has no video stream. ffprobe streams: $(ffprobe -v error -show_streams "$out" 2>/dev/null)"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_output_duration_matches_input() {
    local name="test_output_duration_matches_input"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir")
    local srt; srt=$(make_sample_srt "$workdir")
    local out="$workdir/sample_subbed.mp4"

    set +e
    "$BURN_SUBS_SH" "$video" "$srt" >"$workdir/stdout.txt" 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "burn-subs.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi
    if [[ ! -f "$out" ]]; then
        log_fail "$name" "output missing: $out"
        rm -rf "$workdir"
        return 1
    fi

    local in_dur out_dur
    in_dur=$(probe_duration "$video")
    out_dur=$(probe_duration "$out")
    if [[ -z "$in_dur" || -z "$out_dur" ]]; then
        log_fail "$name" "could not probe duration. in='$in_dur' out='$out_dur'"
        rm -rf "$workdir"
        return 1
    fi
    # |out_dur - in_dur| <= 0.5
    local within
    within=$(awk -v a="$in_dur" -v b="$out_dur" 'BEGIN { d = a - b; if (d < 0) d = -d; print (d <= 0.5) ? "yes" : "no" }')
    if [[ "$within" != "yes" ]]; then
        log_fail "$name" "duration drift > 0.5s. input=$in_dur output=$out_dur"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_subtitles_visible_in_video() {
    local name="test_subtitles_visible_in_video"
    # SMOKE TEST (not OCR): we extract one frame at t=0.7s from the
    # subtitled output and one frame from a plain re-encode of the same
    # source (no subtitles filter). Both go through libx264 with the
    # same params, so the only intentional pixel difference is the
    # rendered subtitle text. We compare PNG file sizes; if they're
    # identical, no overlay was rendered.
    # BLIND SPOT: this does not verify which text was rendered, only
    # that *something* was drawn. OCR is out of scope.
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir")
    local srt; srt=$(make_sample_srt "$workdir")
    local subbed="$workdir/sample_subbed.mp4"
    local control="$workdir/control.mp4"

    # Build a control video: same source, no subs, but re-encoded so its
    # codec/params line up with what burn-subs.sh produces.
    ffmpeg -y -i "$video" -c:v libx264 -pix_fmt yuv420p "$control" -loglevel error

    set +e
    "$BURN_SUBS_SH" "$video" "$srt" "$subbed" >"$workdir/stdout.txt" 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "burn-subs.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local frame_subbed="$workdir/frame_subbed.png"
    local frame_control="$workdir/frame_control.png"
    ffmpeg -y -ss 0.7 -i "$subbed"  -vframes 1 "$frame_subbed"  -loglevel error
    ffmpeg -y -ss 0.7 -i "$control" -vframes 1 "$frame_control" -loglevel error

    if [[ ! -s "$frame_subbed" || ! -s "$frame_control" ]]; then
        log_fail "$name" "could not extract comparison frames"
        rm -rf "$workdir"
        return 1
    fi

    local size_subbed size_control
    size_subbed=$(wc -c < "$frame_subbed" | tr -d ' ')
    size_control=$(wc -c < "$frame_control" | tr -d ' ')

    if [[ "$size_subbed" == "$size_control" ]]; then
        log_fail "$name" "subbed and control frames are identical size ($size_subbed bytes); subtitles likely not burned in"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_idempotent_overwrite() {
    local name="test_idempotent_overwrite"
    if [[ ! -x "$BURN_SUBS_SH" ]]; then
        log_fail "$name" "burn-subs.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local video; video=$(make_sample_video "$workdir")
    local srt; srt=$(make_sample_srt "$workdir")
    local out="$workdir/sample_subbed.mp4"

    set +e
    "$BURN_SUBS_SH" "$video" "$srt" >"$workdir/stdout1.txt" 2>"$workdir/stderr1.txt"
    local rc1=$?
    "$BURN_SUBS_SH" "$video" "$srt" >"$workdir/stdout2.txt" 2>"$workdir/stderr2.txt"
    local rc2=$?
    set -e

    if [[ $rc1 -ne 0 ]]; then
        log_fail "$name" "first run exited $rc1. stderr: $(cat "$workdir/stderr1.txt")"
        rm -rf "$workdir"
        return 1
    fi
    if [[ $rc2 -ne 0 ]]; then
        log_fail "$name" "second run exited $rc2 (must overwrite cleanly with -y). stderr: $(cat "$workdir/stderr2.txt")"
        rm -rf "$workdir"
        return 1
    fi
    if [[ ! -s "$out" ]]; then
        log_fail "$name" "output missing/empty after second run: $out"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

# ── runner ───────────────────────────────────────────────────────────
main() {
    echo "============================================================"
    echo "TDD red-phase tests for scripts/burn-subs.sh"
    echo "Project root: $PROJECT_ROOT"
    echo "============================================================"
    echo ""

    # Skip gracefully if ffmpeg/ffprobe aren't on PATH. The /research
    # of this machine confirmed both are present at /opt/homebrew/bin,
    # so on the user's box the suite WILL exercise.
    if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
        echo "SKIP: ffmpeg or ffprobe not on PATH; cannot run end-to-end tests."
        exit 0
    fi

    test_script_exists_and_executable
    test_command_file_exists
    test_missing_video_file_errors
    test_missing_srt_file_errors
    test_default_output_path
    test_explicit_output_path
    test_output_is_valid_video
    test_output_duration_matches_input
    test_subtitles_visible_in_video
    test_idempotent_overwrite

    echo ""
    echo "============================================================"
    echo "Results: $PASS passed, $FAIL failed"
    if [[ $FAIL -gt 0 ]]; then
        echo "Failed tests:"
        for t in "${FAILED_TESTS[@]}"; do
            echo "  - $t"
        done
        echo "============================================================"
        exit 1
    fi
    echo "============================================================"
    exit 0
}

main "$@"
