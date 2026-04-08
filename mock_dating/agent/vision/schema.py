"""Schemas for the vision-first mock-dating agent.

Stdlib dataclasses instead of pydantic. Every schema knows how to
round-trip through JSON via ``to_dict`` / ``from_dict``, which is what
the audit logger uses.

The canonical list of screens and actions lives here. Everything else
imports from this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


SCREENS = (
    "boot",
    "discover",
    "card",
    "match_popup",
    "chat_list",
    "chat",
    "settings",
    "popup",
    "unknown",
)

ACTIONS = (
    "swipe_left",
    "swipe_right",
    "tap_chat",
    "type_message",
    "tap_back",
    "tap_dismiss",
    "wait",
    "noop",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProfileFeatures:
    name: str | None = None
    age: int | None = None
    bio: str | None = None
    location: str | None = None
    interests: list[str] = field(default_factory=list)
    occupation: str | None = None
    photo_traits: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProfileFeatures":
        return cls(
            name=d.get("name"),
            age=d.get("age"),
            bio=d.get("bio"),
            location=d.get("location"),
            interests=list(d.get("interests") or []),
            occupation=d.get("occupation"),
            photo_traits=list(d.get("photo_traits") or []),
            red_flags=list(d.get("red_flags") or []),
        )


@dataclass
class Decision:
    screen: str
    confidence: float
    action: str
    reasoning: str
    profile: ProfileFeatures | None = None
    score: float | None = None
    score_reason: str | None = None
    action_args: dict[str, Any] = field(default_factory=dict)
    ambiguity: bool = False
    safe_stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.profile is None:
            d["profile"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Decision":
        prof = d.get("profile")
        return cls(
            screen=d["screen"],
            confidence=float(d["confidence"]),
            action=d["action"],
            reasoning=d.get("reasoning", ""),
            profile=ProfileFeatures.from_dict(prof) if prof else None,
            score=d.get("score"),
            score_reason=d.get("score_reason"),
            action_args=dict(d.get("action_args") or {}),
            ambiguity=bool(d.get("ambiguity", False)),
            safe_stop_reason=d.get("safe_stop_reason"),
        )


@dataclass
class TickEvent:
    tick_id: int
    run_id: str
    ts: str
    screen_hash: str
    decision: Decision
    action_executed: bool
    latency_ms: int
    llm_call_id: str | None = None
    retries: int = 0
    safe_stop: bool = False
    safe_stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick_id": self.tick_id,
            "run_id": self.run_id,
            "ts": self.ts,
            "screen_hash": self.screen_hash,
            "decision": self.decision.to_dict(),
            "action_executed": self.action_executed,
            "latency_ms": self.latency_ms,
            "llm_call_id": self.llm_call_id,
            "retries": self.retries,
            "safe_stop": self.safe_stop,
            "safe_stop_reason": self.safe_stop_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TickEvent":
        return cls(
            tick_id=int(d["tick_id"]),
            run_id=d["run_id"],
            ts=d["ts"],
            screen_hash=d["screen_hash"],
            decision=Decision.from_dict(d["decision"]),
            action_executed=bool(d["action_executed"]),
            latency_ms=int(d["latency_ms"]),
            llm_call_id=d.get("llm_call_id"),
            retries=int(d.get("retries", 0)),
            safe_stop=bool(d.get("safe_stop", False)),
            safe_stop_reason=d.get("safe_stop_reason"),
        )


@dataclass
class ChatTurn:
    turn_id: int
    match_id: str
    ts: str
    role: str  # "them" | "us"
    text: str
    source: str  # "mock_user" | "llm" | "operator" | "approval"
    llm_call_id: str | None = None
    approval_state: str = "n/a"  # "n/a" | "pending" | "approved" | "rejected"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChatTurn":
        return cls(
            turn_id=int(d["turn_id"]),
            match_id=d["match_id"],
            ts=d["ts"],
            role=d["role"],
            text=d["text"],
            source=d["source"],
            llm_call_id=d.get("llm_call_id"),
            approval_state=d.get("approval_state", "n/a"),
        )


def new_decision_stub() -> Decision:
    """A maximally-safe default decision. Used for ambiguous / error paths."""
    return Decision(
        screen="unknown",
        confidence=0.0,
        action="noop",
        reasoning="stub",
        ambiguity=True,
        safe_stop_reason="stub",
    )
