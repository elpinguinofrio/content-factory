"""Audit logger.

Writes per-tick directories and an events.jsonl stream under
``runs/<run_id>/``. Every tick produces:

    runs/<run_id>/
      config_snapshot.json
      events.jsonl
      tick_000000/
        screen.png
        prompt.txt
        response.json
        decision.json
        action.json
        meta.json
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..vision.prompt import PromptBundle
from ..vision.schema import Decision, TickEvent


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
        with (self.run_dir / "config_snapshot.json").open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)

    def _tick_dir(self, tick_id: int) -> Path:
        d = self.run_dir / f"tick_{tick_id:06d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_tick(
        self,
        *,
        tick_id: int,
        prompt: PromptBundle,
        image: bytes,
        raw_response: dict,
        decision: Decision,
        action_executed: bool,
        action_args: dict[str, Any] | None,
        latency_ms: int,
        llm_call_id: str | None,
        retries: int,
        safe_stop: bool,
        safe_stop_reason: str | None,
        screen_hash: str,
    ) -> TickEvent:
        tdir = self._tick_dir(tick_id)
        (tdir / "screen.png").write_bytes(image)
        (tdir / "prompt.txt").write_text(
            f"=== SYSTEM ===\n{prompt.system}\n\n=== USER ===\n{prompt.user}\n",
            encoding="utf-8",
        )
        (tdir / "response.json").write_text(
            json.dumps(raw_response, indent=2, sort_keys=True), encoding="utf-8"
        )
        (tdir / "decision.json").write_text(
            json.dumps(decision.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        (tdir / "action.json").write_text(
            json.dumps(
                {
                    "action": decision.action,
                    "action_args": action_args or decision.action_args,
                    "executed": action_executed,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        event = TickEvent(
            tick_id=tick_id,
            run_id=self.run_id,
            ts=datetime.now(timezone.utc).isoformat(),
            screen_hash=screen_hash,
            decision=decision,
            action_executed=action_executed,
            latency_ms=latency_ms,
            llm_call_id=llm_call_id,
            retries=retries,
            safe_stop=safe_stop,
            safe_stop_reason=safe_stop_reason,
        )
        (tdir / "meta.json").write_text(
            json.dumps(
                {
                    "tick_id": tick_id,
                    "run_id": self.run_id,
                    "ts": event.ts,
                    "screen_hash": screen_hash,
                    "latency_ms": latency_ms,
                    "retries": retries,
                    "llm_call_id": llm_call_id,
                    "safe_stop": safe_stop,
                    "safe_stop_reason": safe_stop_reason,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")
        return event

    def write_stop_marker(self, reason: str) -> None:
        path = self.run_dir / "STOPPED"
        path.write_text(
            json.dumps(
                {
                    "reason": reason,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "run_id": self.run_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
