"""Audit logger.

Writes per-tick directories and an ``events.jsonl`` stream under
``runs/<run_id>/``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .._util import append_jsonl, utcnow_iso, write_json
from ..vision.prompt import PromptBundle
from ..vision.schema import TickEvent


def new_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}_{uuid.uuid4().hex[:6]}"


@dataclass
class AuditLogger:
    root: Path
    run_id: str = field(default_factory=new_run_id)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def run_dir(self) -> Path:
        return self.root / self.run_id

    @property
    def events_path(self) -> Path:
        return self.run_dir / "events.jsonl"

    def snapshot_config(self, snapshot: dict[str, Any]) -> None:
        write_json(self.run_dir / "config_snapshot.json", snapshot)

    def _tick_dir(self, tick_id: int) -> Path:
        d = self.run_dir / f"tick_{tick_id:06d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_tick(
        self,
        event: TickEvent,
        *,
        prompt: PromptBundle,
        image: bytes,
        raw_response: dict,
        action_args: dict[str, Any] | None = None,
    ) -> TickEvent:
        tdir = self._tick_dir(event.tick_id)
        (tdir / "screen.png").write_bytes(image)
        write_json(tdir / "prompt.json", {"system": prompt.system, "user": prompt.user})
        write_json(tdir / "response.json", raw_response)
        write_json(tdir / "decision.json", event.decision.to_dict())
        write_json(
            tdir / "action.json",
            {
                "action": event.decision.action,
                "action_args": action_args if action_args is not None else event.decision.action_args,
                "executed": event.action_executed,
            },
        )
        write_json(
            tdir / "meta.json",
            {
                "tick_id": event.tick_id,
                "run_id": event.run_id,
                "ts": event.ts,
                "screen_hash": event.screen_hash,
                "latency_ms": event.latency_ms,
                "retries": event.retries,
                "llm_call_id": event.llm_call_id,
                "safe_stop": event.safe_stop,
                "safe_stop_reason": event.safe_stop_reason,
            },
        )
        append_jsonl(self.events_path, event.to_dict())
        return event

    def write_stop_marker(self, reason: str) -> None:
        write_json(
            self.run_dir / "STOPPED",
            {"reason": reason, "ts": utcnow_iso(), "run_id": self.run_id},
        )
