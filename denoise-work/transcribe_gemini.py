#!/usr/bin/env python3
"""Transcribe an audio file via Gemini 3.5 Flash on Vertex AI (Russian)."""
import os
import sys
import time
from pathlib import Path

VERTEX_KEY = "/Users/elpinguino/dev_local/temp/google300/vertex-key.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = VERTEX_KEY

from google import genai
from google.genai import types
import json

PROJECT_ID = json.load(open(VERTEX_KEY))["project_id"]

PROMPT = """You are a transcription engine. Transcribe the speech in this audio recording.

The speaker is a native Russian speaker. Output ONLY the verbatim Russian text. Do not translate. Do not summarize. Do not add commentary. Preserve filler words ("эм", "ну", "вот"), stutters, and repetitions. Use proper Russian punctuation and capitalization. If a segment is unintelligible, write [unclear] in its place.

After the full transcript, on a new line, write three lines:
COHERENCE_SCORE: <integer 0-10, your judgement of how coherent the speech is - 10=perfectly clear, 5=mostly understandable with gaps, 0=mostly garbled>
NOISE_LEVEL: <integer 0-10, how much background noise interferes - 0=clean studio, 10=overwhelming>
UNCLEAR_SEGMENT_COUNT: <number of [unclear] tokens you emitted>
"""


def transcribe(path: str) -> tuple[str, float]:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    audio_bytes = Path(path).read_bytes()
    mime = "audio/wav" if path.lower().endswith(".wav") else "audio/mp4"
    t0 = time.time()
    resp = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=8192,
        ),
    )
    elapsed = time.time() - t0
    return resp.text, elapsed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: transcribe_gemini.py <audio_file> [<out_file>]", file=sys.stderr)
        sys.exit(2)
    audio = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    text, elapsed = transcribe(audio)
    text = text or "[EMPTY_RESPONSE_FROM_MODEL]"
    header = f"=== {Path(audio).name} | {elapsed:.1f}s ===\n"
    print(header)
    print(text)
    if out:
        Path(out).write_text(header + text)
        print(f"\n[wrote {out}]", file=sys.stderr)
