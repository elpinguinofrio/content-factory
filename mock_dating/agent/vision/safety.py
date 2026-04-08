"""Safety gate.

Takes a ``Decision`` and the runtime config, and decides whether the
action is allowed to execute. If not, returns a safe-stop ``Decision``
with a concrete reason. Pure function, trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config_loader import Runtime
from .schema import ACTIONS, SCREENS, Decision


@dataclass
class SafetyResult:
    allow: bool
    decision: Decision
    reason: str | None = None


def _safe_stop(reason: str, base: Decision) -> Decision:
    return Decision(
        screen=base.screen if base.screen in SCREENS else "unknown",
        confidence=base.confidence,
        action="noop",
        reasoning=base.reasoning,
        profile=base.profile,
        score=base.score,
        score_reason=base.score_reason,
        action_args={},
        ambiguity=True,
        safe_stop_reason=reason,
    )


def apply_safety_gate(decision: Decision, runtime: Runtime) -> SafetyResult:
    # 1) Invalid action vocabulary.
    if decision.action not in ACTIONS:
        reason = f"invalid action: {decision.action!r}"
        return SafetyResult(False, _safe_stop(reason, decision), reason)

    # 2) Invalid screen.
    if decision.screen not in SCREENS:
        reason = f"invalid screen: {decision.screen!r}"
        return SafetyResult(False, _safe_stop(reason, decision), reason)

    # 3) Unknown screen → safe-stop.
    if decision.screen == "unknown":
        reason = "screen classified as unknown"
        return SafetyResult(False, _safe_stop(reason, decision), reason)

    # 4) Ambiguity → safe-stop (if configured).
    if runtime.ambiguity_safe_stop and decision.ambiguity:
        reason = decision.safe_stop_reason or "ambiguity flag set"
        return SafetyResult(False, _safe_stop(reason, decision), reason)

    # 5) Confidence below threshold → safe-stop.
    if decision.confidence < runtime.min_confidence:
        reason = (
            f"confidence {decision.confidence:.2f} below "
            f"min_confidence {runtime.min_confidence:.2f}"
        )
        return SafetyResult(False, _safe_stop(reason, decision), reason)

    # 6) type_message without any text is not executable.
    if decision.action == "type_message":
        text = str(decision.action_args.get("text", ""))
        if not text.strip():
            reason = "type_message with empty text"
            return SafetyResult(False, _safe_stop(reason, decision), reason)

    return SafetyResult(True, decision, None)
