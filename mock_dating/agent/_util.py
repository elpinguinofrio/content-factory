"""Small shared utilities: timestamps, JSON helpers, fenced-JSON parsing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def strip_json_fence(text: str) -> str:
    """Strip an optional ```json ... ``` wrapper around a JSON blob."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = text.lstrip("`")
    if text.lower().startswith("json"):
        text = text[4:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
