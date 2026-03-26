#!/usr/bin/env python3
"""
Assemble video from keep-ranges JSON + source video using ffmpeg.

Usage:
    python assemble.py <video> <ranges.json> [-o output.mp4] [--frame-accurate] [--fix-audio]

ranges.json format:
    [{"start": 5.2, "end": 42.8}, {"start": 65.0, "end": 118.5}]

Options:
    --frame-accurate  Re-encode for precise cuts (slower, but no keyframe drift)
    --fix-audio       Final audio-only re-encode pass (fixes pops at concat joints)
    -o, --output      Output file path (default: <video>_assembled.mp4)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def run(cmd, **kwargs):
    print(f">> {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"!! ffmpeg exited with code {result.returncode}", file=sys.stderr)
        sys.exit(1)
    return result


def assemble_concat_demuxer(video, ranges, output):
    """Fast assembly using concat demuxer (stream copy, keyframe-aligned)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for r in ranges:
            f.write(f"file '{os.path.abspath(video)}'\n")
            f.write(f"inpoint {r['start']}\n")
            f.write(f"outpoint {r['end']}\n\n")
        concat_file = f.name

    try:
        run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output,
        ])
    finally:
        os.unlink(concat_file)


def assemble_frame_accurate(video, ranges, output):
    """Frame-accurate assembly using filter_complex (re-encodes)."""
    n = len(ranges)
    filters = []
    streams = []

    for i, r in enumerate(ranges):
        filters.append(
            f"[0:v]trim=start={r['start']}:end={r['end']},setpts=PTS-STARTPTS[v{i}]"
        )
        filters.append(
            f"[0:a]atrim=start={r['start']}:end={r['end']},asetpts=PTS-STARTPTS[a{i}]"
        )
        streams.append(f"[v{i}][a{i}]")

    filter_str = "; ".join(filters)
    filter_str += f"; {''.join(streams)}concat=n={n}:v=1:a=1[outv][outa]"

    run([
        "ffmpeg", "-y",
        "-i", video,
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        output,
    ])


def fix_audio_pops(video, output):
    """Re-encode audio only to fix pops at concat joints."""
    tmp = output + ".tmp.mp4"
    os.rename(output, tmp)
    try:
        run([
            "ffmpeg", "-y",
            "-i", tmp,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            output,
        ])
    finally:
        os.unlink(tmp)


def get_duration(video):
    """Get video duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Assemble video from keep-ranges JSON")
    parser.add_argument("video", help="Source video file")
    parser.add_argument("ranges", help="JSON file with keep-ranges")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--frame-accurate", action="store_true",
                        help="Re-encode for precise cuts (slower)")
    parser.add_argument("--fix-audio", action="store_true",
                        help="Re-encode audio to fix pops at concat joints")
    args = parser.parse_args()

    if not os.path.isfile(args.video):
        print(f"!! Video not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    with open(args.ranges) as f:
        ranges = json.load(f)

    if not ranges:
        print("!! No keep-ranges in JSON", file=sys.stderr)
        sys.exit(1)

    # Sort by start time
    ranges.sort(key=lambda r: r["start"])

    output = args.output or f"{os.path.splitext(args.video)[0]}_assembled.mp4"

    print(f">> Source: {args.video}")
    print(f">> Ranges: {len(ranges)} segments")
    print(f">> Output: {output}")
    print(f">> Mode: {'frame-accurate (re-encode)' if args.frame_accurate else 'stream copy (fast)'}")

    if args.frame_accurate:
        assemble_frame_accurate(args.video, ranges, output)
    else:
        assemble_concat_demuxer(args.video, ranges, output)

    if args.fix_audio:
        print(">> Fixing audio pops at concat joints...")
        fix_audio_pops(args.video, output)

    # Report
    input_dur = get_duration(args.video)
    output_dur = get_duration(output)
    kept = sum(r["end"] - r["start"] for r in ranges)

    print(f"\n>> Done: {output}")
    if input_dur:
        print(f"   Input:  {input_dur:.1f}s")
    if output_dur:
        print(f"   Output: {output_dur:.1f}s")
    print(f"   Kept:   {kept:.1f}s across {len(ranges)} segments")
    if input_dur:
        print(f"   Cut:    {input_dur - kept:.1f}s ({(1 - kept / input_dur) * 100:.0f}%)")


if __name__ == "__main__":
    main()
