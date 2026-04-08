"""Unit tests for vision.safety."""

import unittest

from mock_dating.agent.config_loader import Runtime
from mock_dating.agent.vision.safety import apply_safety_gate
from mock_dating.agent.vision.schema import Decision, ProfileFeatures


def _runtime(**kw) -> Runtime:
    base = dict(
        mode="auto",
        tick_interval_s=0.0,
        tick_timeout_s=5,
        max_ticks=10,
        min_confidence=0.5,
        ambiguity_safe_stop=True,
    )
    base.update(kw)
    return Runtime(**base)  # type: ignore[arg-type]


def _ok_card() -> Decision:
    return Decision(
        screen="card",
        confidence=0.9,
        action="swipe_right",
        reasoning="ok",
        profile=ProfileFeatures(name="Sam"),
        score=0.8,
    )


class SafetyGateTests(unittest.TestCase):
    def test_valid_decision_passes(self) -> None:
        res = apply_safety_gate(_ok_card(), _runtime())
        self.assertTrue(res.allow)
        self.assertIsNone(res.reason)

    def test_unknown_screen_safe_stops(self) -> None:
        d = _ok_card()
        d.screen = "unknown"
        res = apply_safety_gate(d, _runtime())
        self.assertFalse(res.allow)
        self.assertEqual(res.decision.action, "noop")
        self.assertIn("unknown", (res.reason or "").lower())

    def test_invalid_screen_safe_stops(self) -> None:
        d = _ok_card()
        d.screen = "totally_bogus"  # type: ignore[assignment]
        res = apply_safety_gate(d, _runtime())
        self.assertFalse(res.allow)
        self.assertEqual(res.decision.action, "noop")
        self.assertIn("invalid screen", res.reason or "")

    def test_invalid_action_safe_stops(self) -> None:
        d = _ok_card()
        d.action = "self_destruct"  # type: ignore[assignment]
        res = apply_safety_gate(d, _runtime())
        self.assertFalse(res.allow)
        self.assertIn("invalid action", res.reason or "")

    def test_ambiguity_safe_stops_when_configured(self) -> None:
        d = _ok_card()
        d.ambiguity = True
        d.safe_stop_reason = "llm unsure"
        res = apply_safety_gate(d, _runtime(ambiguity_safe_stop=True))
        self.assertFalse(res.allow)
        self.assertEqual(res.reason, "llm unsure")

    def test_ambiguity_allowed_when_disabled(self) -> None:
        d = _ok_card()
        d.ambiguity = True
        res = apply_safety_gate(d, _runtime(ambiguity_safe_stop=False))
        self.assertTrue(res.allow)

    def test_low_confidence_safe_stops(self) -> None:
        d = _ok_card()
        d.confidence = 0.2
        res = apply_safety_gate(d, _runtime(min_confidence=0.5))
        self.assertFalse(res.allow)
        self.assertIn("confidence", res.reason or "")

    def test_type_message_empty_text_safe_stops(self) -> None:
        d = Decision(
            screen="chat",
            confidence=0.9,
            action="type_message",
            reasoning="reply",
            action_args={"text": "   "},
        )
        res = apply_safety_gate(d, _runtime())
        self.assertFalse(res.allow)
        self.assertIn("empty text", res.reason or "")

    def test_type_message_with_text_allowed(self) -> None:
        d = Decision(
            screen="chat",
            confidence=0.9,
            action="type_message",
            reasoning="reply",
            action_args={"text": "hi there"},
        )
        res = apply_safety_gate(d, _runtime())
        self.assertTrue(res.allow)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
