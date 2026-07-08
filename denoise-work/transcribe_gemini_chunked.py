#!/usr/bin/env python3
"""Transcribe audio via Gemini 3.5 Flash on Vertex AI, chunking into N-second segments.

Splits input WAV into chunks, transcribes each, concatenates with timestamps.
Fixes the truncation Gemini does on multi-minute audio.
"""
import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path

VERTEX_KEY = "/Users/elpinguino/dev_local/temp/google300/vertex-key.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = VERTEX_KEY

from google import genai
from google.genai import types
import json

PROJECT_ID = json.load(open(VERTEX_KEY))["project_id"]

PROMPT = """Transcribe this Russian-language audio chunk verbatim.

Rules:
- Output ONLY the Russian text spoken in this chunk
- Do not translate, summarize, or add commentary
- Preserve fillers ("эм", "ну", "вот"), stutters, repetitions
- For unintelligible parts write [unclear]
- If chunk is silent or only background noise, output [silence]
- Do not add scoring or metadata - just the transcript

Now transcribe:"""


def get_duration(path: str) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", path
    ]).decode().strip()
    return float(out)


def chunk_audio(path: str, chunk_s: int, work_dir: Path) -> list[tuple[float, str]]:
    duration = get_duration(path)
    chunks = []
    n = int(duration // chunk_s) + (1 if duration % chunk_s else 0)
    for i in range(n):
        start = i * chunk_s
        out = work_dir / f"chunk_{i:03d}.wav"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start), "-t", str(chunk_s),
            "-i", path, "-ac", "1", "-ar", "16000",
            str(out)
        ], check=True)
        chunks.append((start, str(out)))
    return chunks


def transcribe_chunk(client, path: str) -> str:
    audio_bytes = Path(path).read_bytes()
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                ),
            )
            return (resp.text or "[empty]").strip()
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = (attempt + 1) * 45
                print(f"  rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            return f"[ERROR: {e}]"
    return "[ERROR: rate-limited after 4 attempts]"


def main():
    if len(sys.argv) < 3:
        print("Usage: transcribe_gemini_chunked.py <audio_file> <out_file> [chunk_seconds=45]", file=sys.stderr)
        sys.exit(2)
    audio = sys.argv[1]
    out = sys.argv[2]
    chunk_s = int(sys.argv[3]) if len(sys.argv) > 3 else 45

    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    duration = get_duration(audio)
    print(f"[chunking {audio} ({duration:.0f}s) into {chunk_s}s segments]", file=sys.stderr)

    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        chunks = chunk_audio(audio, chunk_s, work_dir)
        print(f"[{len(chunks)} chunks]", file=sys.stderr)

        lines = [f"=== {Path(audio).name} | chunked {chunk_s}s | {len(chunks)} chunks ==="]
        for start, cpath in chunks:
            t0 = time.time()
            text = transcribe_chunk(client, cpath)
            elapsed = time.time() - t0
            mm, ss = divmod(int(start), 60)
            line = f"[{mm:02d}:{ss:02d}] {text}"
            print(line + f"  ({elapsed:.1f}s)", file=sys.stderr)
            lines.append(line)
            time.sleep(3)

    Path(out).write_text("\n".join(lines))
    print(f"\n[wrote {out}]", file=sys.stderr)


if __name__ == "__main__":
    main()
