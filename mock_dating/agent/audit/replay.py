"""Offline replay of recorded ticks.

Takes a tick directory, loads the screen.png and prompt.txt, and runs
them through a given ``VisionClient``. Returns the new ``Decision``
alongside the old one so callers can diff them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..vision.client import VisionClient
from ..vision.prompt import PromptBundle
from ..vision.schema import Decision


@dataclass
class ReplayResult:
    tick_dir: Path
    original: Decision
    replayed: Decision
    structurally_compatible: bool
    diff: dict


def _load_original(tick_dir: Path) -> tuple[Decision, PromptBundle]:
    decision = Decision.from_dict(
        json.loads((tick_dir / "decision.json").read_text(encoding="utf-8"))
    )
    image = (tick_dir / "screen.png").read_bytes()
    prompt_text = (tick_dir / "prompt.txt").read_text(encoding="utf-8")

    # prompt.txt is "=== SYSTEM ===\n...\n\n=== USER ===\n...\n"
    if "=== SYSTEM ===" in prompt_text and "=== USER ===" in prompt_text:
        _, rest = prompt_text.split("=== SYSTEM ===\n", 1)
        system, user = rest.split("\n=== USER ===\n", 1)
    else:
        system, user = "", prompt_text
    return decision, PromptBundle(system=system.rstrip(), user=user.rstrip(), image_bytes=image)


def _structurally_compatible(a: Decision, b: Decision, score_tolerance: float = 0.1) -> bool:
    if a.screen != b.screen:
        return False
    if a.action != b.action:
        return False
    if a.score is not None and b.score is not None:
        if abs(a.score - b.score) > score_tolerance:
            return False
    return True


def _diff(a: Decision, b: Decision) -> dict:
    return {
        "screen": [a.screen, b.screen],
        "action": [a.action, b.action],
        "score": [a.score, b.score],
        "confidence": [a.confidence, b.confidence],
    }


def replay_tick(tick_dir: Path, client: VisionClient) -> ReplayResult:
    original, prompt = _load_original(Path(tick_dir))
    response = client.decide(prompt)
    compatible = _structurally_compatible(original, response.decision)
    return ReplayResult(
        tick_dir=Path(tick_dir),
        original=original,
        replayed=response.decision,
        structurally_compatible=compatible,
        diff=_diff(original, response.decision),
    )
