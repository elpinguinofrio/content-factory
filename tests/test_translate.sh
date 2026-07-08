#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# tests/test_translate.sh — TDD red-phase tests for scripts/translate.sh
# ─────────────────────────────────────────────────────────────────────
#
# CONTRACT FOR translate.sh (the BUILDER must implement this):
#
# 1. INVOCATION
#    scripts/translate.sh <basename>.transcript.json [target_lang=es]
#
# 2. INPUTS
#    - $1: path to an existing transcript JSON produced by transcribe.sh.
#          Format: {"segments":[{"start":<sec>,"end":<sec>,"text":"..."}],
#                   "language":"ru", "source":"gemini", ...}
#    - $2 (optional): ISO target language code, default "es".
#
# 3. OUTPUTS (written next to the input file, sharing its basename minus
#    the trailing ".transcript.json" suffix — same convention as
#    transcribe.sh)
#    - <basename>.<lang>.transcript.json   (e.g. sample.es.transcript.json)
#    - <basename>.<lang>.srt               (e.g. sample.es.srt)
#
# 4. INVARIANT (this is THE point of the feature)
#    - Output transcript MUST preserve the input segment count.
#    - Output transcript MUST preserve every segment's "start" and "end"
#      timestamps EXACTLY (no rounding, no shifting).
#    - Only the "text" field is translated.
#    - Output transcript "language" field is the TARGET language code
#      (e.g. "es"), since "language" means "the language of the text"
#      in transcribe.sh's convention.
#
# 5. API KEY LOADING
#    - Same pattern as scripts/transcribe.sh: read GEMINI_API_KEY from
#      env, then walk a list of candidate .env files. If still empty
#      AND mock mode is OFF → exit non-zero with an error mentioning
#      GEMINI_API_KEY.
#
# 6. MOCK MODE CONTRACT  ◀─── KEY FOR TESTING OFFLINE ───▶
#    - Env var name: TRANSLATE_MOCK_RESPONSE_FILE
#    - When set AND non-empty AND points to a readable file, the script
#      MUST skip the live Gemini API call entirely and instead read that
#      file as if it were the raw Gemini API response body
#      (i.e. the JSON envelope with .candidates[0].content.parts[0].text).
#    - In mock mode, GEMINI_API_KEY is NOT required.
#    - This lets tests run hermetically with no network and no key.
#
# 7. ERROR CASES (all exit non-zero)
#    - Missing input file → stderr mentions the missing path.
#    - Missing GEMINI_API_KEY when NOT in mock mode → stderr mentions
#      GEMINI_API_KEY.
#
# ─────────────────────────────────────────────────────────────────────
# Test framework: pure bash. Each test_* function returns 0 on pass,
# 1 on fail. main() runs them all, counts failures, exits non-zero if
# any failed.
# ─────────────────────────────────────────────────────────────────────

set -uo pipefail
# NOTE: deliberately NOT using `set -e` at the top level — individual
# tests need to capture non-zero exits from translate.sh without
# aborting the suite.

# Resolve project root (this script lives in <root>/tests/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

TRANSLATE_SH="$PROJECT_ROOT/scripts/translate.sh"
TRANSLATE_MD="$PROJECT_ROOT/.claude/commands/translate.md"
SAMPLE_INPUT="$FIXTURES_DIR/sample.transcript.json"
MOCK_RESPONSE="$FIXTURES_DIR/mock_gemini_response.json"

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

# Build a tmp working dir per test so output files don't collide
make_workdir() {
    local d
    d=$(mktemp -d -t translate_test.XXXXXX)
    echo "$d"
}

# Copy sample input into workdir under a given basename, return its path
prepare_input() {
    local workdir="$1"
    local name="${2:-sample}"
    local dest="$workdir/${name}.transcript.json"
    cp "$SAMPLE_INPUT" "$dest"
    echo "$dest"
}

# ── tests ────────────────────────────────────────────────────────────

test_script_exists_and_executable() {
    local name="test_script_exists_and_executable"
    if [[ ! -f "$TRANSLATE_SH" ]]; then
        log_fail "$name" "scripts/translate.sh does not exist at $TRANSLATE_SH"
        return 1
    fi
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "scripts/translate.sh exists but is not executable (chmod +x)"
        return 1
    fi
    log_pass "$name"
}

test_command_file_exists() {
    local name="test_command_file_exists"
    if [[ ! -f "$TRANSLATE_MD" ]]; then
        log_fail "$name" ".claude/commands/translate.md does not exist at $TRANSLATE_MD"
        return 1
    fi
    log_pass "$name"
}

test_missing_input_file_errors() {
    local name="test_missing_input_file_errors"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local bogus="$workdir/does_not_exist.transcript.json"
    local stderr_file="$workdir/stderr.txt"

    # Even in mock mode the script should validate input existence first.
    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$bogus" 2>"$stderr_file" >/dev/null
    local rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log_fail "$name" "expected non-zero exit for missing input, got 0"
        rm -rf "$workdir"
        return 1
    fi
    if ! grep -qF "$bogus" "$stderr_file" && ! grep -qiE 'not found|no such|missing|does not exist' "$stderr_file"; then
        log_fail "$name" "stderr did not mention the missing path. stderr was: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_missing_api_key_errors() {
    local name="test_missing_api_key_errors"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")
    local stderr_file="$workdir/stderr.txt"

    # Run from a HOME-isolated, repo-isolated working directory so the
    # script's .env walk (../../.env, $HOME/dev_local/.env, ../.env, .env)
    # cannot find any GEMINI_API_KEY. Explicitly leave mock mode OFF so
    # this test exercises the live-API path's error branch.
    set +e
    (
        cd "$workdir"
        env -i \
            HOME="$workdir" \
            PATH="$PATH" \
            GEMINI_API_KEY="" \
            "$TRANSLATE_SH" "$input" 2>"$stderr_file" >/dev/null
    )
    local rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        log_fail "$name" "expected non-zero exit when GEMINI_API_KEY missing, got 0. stderr: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    if ! grep -qE 'GEMINI_API_KEY' "$stderr_file"; then
        log_fail "$name" "stderr did not mention GEMINI_API_KEY. stderr was: $(cat "$stderr_file")"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_output_files_created() {
    local name="test_output_files_created"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")

    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$input" >/dev/null 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "translate.sh exited $rc in mock mode. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local out_json="$workdir/sample.es.transcript.json"
    local out_srt="$workdir/sample.es.srt"

    if [[ ! -f "$out_json" ]]; then
        log_fail "$name" "expected output JSON not found: $out_json (workdir contents: $(ls "$workdir"))"
        rm -rf "$workdir"
        return 1
    fi
    if [[ ! -f "$out_srt" ]]; then
        log_fail "$name" "expected output SRT not found: $out_srt (workdir contents: $(ls "$workdir"))"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_segment_count_preserved() {
    local name="test_segment_count_preserved"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")

    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$input" >/dev/null 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "translate.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local out_json="$workdir/sample.es.transcript.json"
    if [[ ! -f "$out_json" ]]; then
        log_fail "$name" "output JSON missing: $out_json"
        rm -rf "$workdir"
        return 1
    fi

    local in_count out_count
    in_count=$(jq '.segments | length' "$input")
    out_count=$(jq '.segments | length' "$out_json")
    if [[ "$in_count" != "$out_count" ]]; then
        log_fail "$name" "segment count mismatch: input=$in_count output=$out_count"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_timestamps_preserved() {
    local name="test_timestamps_preserved"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")

    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$input" >/dev/null 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "translate.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local out_json="$workdir/sample.es.transcript.json"
    if [[ ! -f "$out_json" ]]; then
        log_fail "$name" "output JSON missing: $out_json"
        rm -rf "$workdir"
        return 1
    fi

    local in_starts out_starts in_ends out_ends
    in_starts=$(jq -c '[.segments[].start]' "$input")
    out_starts=$(jq -c '[.segments[].start]' "$out_json")
    in_ends=$(jq -c '[.segments[].end]' "$input")
    out_ends=$(jq -c '[.segments[].end]' "$out_json")

    if [[ "$in_starts" != "$out_starts" ]]; then
        log_fail "$name" "start timestamps differ. input=$in_starts output=$out_starts"
        rm -rf "$workdir"
        return 1
    fi
    if [[ "$in_ends" != "$out_ends" ]]; then
        log_fail "$name" "end timestamps differ. input=$in_ends output=$out_ends"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_text_was_translated() {
    local name="test_text_was_translated"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")

    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$input" >/dev/null 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "translate.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local out_json="$workdir/sample.es.transcript.json"
    local count i in_text out_text any_empty=0 any_same=0
    count=$(jq '.segments | length' "$out_json")

    if [[ "$count" -eq 0 ]]; then
        log_fail "$name" "output has zero segments"
        rm -rf "$workdir"
        return 1
    fi

    for ((i = 0; i < count; i++)); do
        in_text=$(jq -r ".segments[$i].text" "$input")
        out_text=$(jq -r ".segments[$i].text" "$out_json")
        if [[ -z "$out_text" || "$out_text" == "null" ]]; then
            any_empty=1
            log_fail "$name" "segment $i has empty/null text in output"
            break
        fi
        if [[ "$in_text" == "$out_text" ]]; then
            any_same=1
            log_fail "$name" "segment $i text not translated: input='$in_text' output='$out_text'"
            break
        fi
    done

    if [[ $any_empty -eq 1 || $any_same -eq 1 ]]; then
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_srt_structure_valid() {
    local name="test_srt_structure_valid"
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")

    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$input" >/dev/null 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "translate.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local out_srt="$workdir/sample.es.srt"
    if [[ ! -f "$out_srt" ]]; then
        log_fail "$name" "output SRT missing: $out_srt"
        rm -rf "$workdir"
        return 1
    fi

    # Count SRT cues by counting timestamp lines (HH:MM:SS,mmm --> HH:MM:SS,mmm)
    local cue_count expected_count
    cue_count=$(grep -cE '^[0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3} --> [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3}$' "$out_srt" || true)
    expected_count=$(jq '.segments | length' "$input")

    if [[ "$cue_count" != "$expected_count" ]]; then
        log_fail "$name" "SRT cue count $cue_count != expected $expected_count. SRT was:
$(cat "$out_srt")"
        rm -rf "$workdir"
        return 1
    fi

    # Also verify the very first cue starts with "1" on its own line — basic SRT shape.
    if ! head -1 "$out_srt" | grep -qE '^1$'; then
        log_fail "$name" "SRT does not start with '1' on first line. First line: $(head -1 "$out_srt")"
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

test_default_target_language_is_spanish() {
    local name="test_default_target_language_is_spanish"
    # CONTRACT NOTE: output JSON's "language" field is set to the TARGET
    # language code (default "es"), matching transcribe.sh's convention
    # where "language" describes the language of the text in segments.
    if [[ ! -x "$TRANSLATE_SH" ]]; then
        log_fail "$name" "translate.sh missing/not executable — cannot test"
        return 1
    fi

    local workdir; workdir=$(make_workdir)
    local input; input=$(prepare_input "$workdir" "sample")

    set +e
    TRANSLATE_MOCK_RESPONSE_FILE="$MOCK_RESPONSE" \
        "$TRANSLATE_SH" "$input" >/dev/null 2>"$workdir/stderr.txt"
    local rc=$?
    set -e

    if [[ $rc -ne 0 ]]; then
        log_fail "$name" "translate.sh exited $rc. stderr: $(cat "$workdir/stderr.txt")"
        rm -rf "$workdir"
        return 1
    fi

    local out_json="$workdir/sample.es.transcript.json"
    local lang
    lang=$(jq -r '.language' "$out_json")
    if [[ "$lang" != "es" ]]; then
        log_fail "$name" "expected .language == \"es\", got: \"$lang\""
        rm -rf "$workdir"
        return 1
    fi
    rm -rf "$workdir"
    log_pass "$name"
}

# ── runner ───────────────────────────────────────────────────────────
main() {
    echo "============================================================"
    echo "TDD red-phase tests for scripts/translate.sh"
    echo "Project root: $PROJECT_ROOT"
    echo "============================================================"
    echo ""

    # Sanity: fixtures must exist (these are OUR responsibility, not the
    # builder's — fail loudly if they're missing).
    for f in "$SAMPLE_INPUT" "$MOCK_RESPONSE"; do
        if [[ ! -f "$f" ]]; then
            echo "FATAL: fixture missing: $f" >&2
            exit 2
        fi
    done

    test_script_exists_and_executable
    test_command_file_exists
    test_missing_input_file_errors
    test_missing_api_key_errors
    test_output_files_created
    test_segment_count_preserved
    test_timestamps_preserved
    test_text_was_translated
    test_srt_structure_valid
    test_default_target_language_is_spanish

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
