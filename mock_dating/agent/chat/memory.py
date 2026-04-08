"""Per-conversation memory store.

One JSONL file per match_id. Append-only. Tiny on purpose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..vision.schema import ChatTurn


@dataclass
class ChatMemory:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, match_id: str) -> Path:
        return self.root / match_id / "memory.jsonl"

    def load(self, match_id: str) -> list[ChatTurn]:
        path = self._path(match_id)
        if not path.exists():
            return []
        turns: list[ChatTurn] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                turns.append(ChatTurn.from_dict(json.loads(line)))
        return turns

    def append(self, turn: ChatTurn) -> None:
        path = self._path(turn.match_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict()) + "\n")

    def next_turn_id(self, match_id: str) -> int:
        existing = self.load(match_id)
        return len(existing)
