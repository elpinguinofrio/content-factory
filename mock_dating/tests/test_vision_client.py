"""Unit tests for vision.client response parsing + the fake client."""

import json
import unittest

from mock_dating.agent.config_loader import Persona, Preferences, Runtime, Config
from mock_dating.agent.vision.client import (
    FakeVisionClient,
    VisionClientError,
    parse_decision,
)
from mock_dating.agent.vision.prompt import build_decision_prompt
from mock_dating.agent.vision.schema import Decision, ProfileFeatures


def _config() -> Config:
    return Config(
        persona=Persona(display_name="Alex", voice={}, goals=[], hard_rules=[]),
        preferences=Preferences(
            likes=["dogs"], dislikes=[], red_flags=[], deal_breakers=[],
            weights={}, threshold={"swipe_right_min_score": 0.5},
        ),
        runtime=Runtime(),
    )


class ParseDecisionTests(unittest.TestCase):
    def test_parse_clean_json(self) -> None:
        text = json.dumps(
            {
                "screen": "card",
                "confidence": 0.8,
                "action": "swipe_right",
                "reasoning": "likes dogs",
                "profile": {"name": "Sam", "age": 29, "interests": ["dogs"]},
                "score": 0.7,
            }
        )
        d = parse_decision(text)
        self.assertEqual(d.screen, "card")
        self.assertEqual(d.action, "swipe_right")
        self.assertIsNotNone(d.profile)
        assert d.profile is not None
        self.assertEqual(d.profile.name, "Sam")

    def test_parse_fenced_json(self) -> None:
        text = "```json\n" + json.dumps(
            {"screen": "chat", "confidence": 0.9, "action": "noop", "reasoning": "idle"}
        ) + "\n```"
        d = parse_decision(text)
        self.assertEqual(d.screen, "chat")
        self.assertEqual(d.action, "noop")

    def test_parse_rejects_non_json(self) -> None:
        with self.assertRaises(VisionClientError):
            parse_decision("not json")

    def test_parse_rejects_unknown_screen(self) -> None:
        with self.assertRaises(VisionClientError):
            parse_decision(json.dumps(
                {"screen": "bogus", "confidence": 0.5, "action": "noop", "reasoning": ""}
            ))

    def test_parse_rejects_unknown_action(self) -> None:
        with self.assertRaises(VisionClientError):
            parse_decision(json.dumps(
                {"screen": "card", "confidence": 0.5, "action": "teleport", "reasoning": ""}
            ))

    def test_parse_rejects_out_of_range_confidence(self) -> None:
        with self.assertRaises(VisionClientError):
            parse_decision(json.dumps(
                {"screen": "card", "confidence": 1.5, "action": "noop", "reasoning": ""}
            ))


class FakeVisionClientTests(unittest.TestCase):
    def test_default_decision_is_ambiguous(self) -> None:
        client = FakeVisionClient()
        prompt = build_decision_prompt(
            config=_config(),
            tick_id=0,
            image=b"\x89PNG",
            curr_hash="h0",
            prev_hash=None,
            recent_actions=[],
        )
        resp = client.decide(prompt)
        self.assertTrue(resp.decision.ambiguity)
        self.assertEqual(resp.decision.action, "noop")

    def test_rule_matches_and_wins(self) -> None:
        def rule(prompt):
            if "tick 5" in prompt.user:
                return Decision(
                    screen="card",
                    confidence=0.9,
                    action="swipe_right",
                    reasoning="rule match",
                    profile=ProfileFeatures(name="Sam", interests=["dogs"]),
                    score=0.8,
                )
            return None

        client = FakeVisionClient(rules=[rule])
        prompt = build_decision_prompt(
            config=_config(),
            tick_id=5,
            image=b"\x89PNG",
            curr_hash="h5",
            prev_hash="h4",
            recent_actions=["noop"],
        )
        resp = client.decide(prompt)
        self.assertEqual(resp.decision.screen, "card")
        self.assertEqual(resp.decision.action, "swipe_right")

    def test_calls_recorded(self) -> None:
        client = FakeVisionClient()
        p = build_decision_prompt(
            config=_config(),
            tick_id=0,
            image=b"\x89PNG",
            curr_hash="h",
            prev_hash=None,
            recent_actions=[],
        )
        client.decide(p)
        client.decide(p)
        self.assertEqual(len(client.calls), 2)


class PromptBuilderTests(unittest.TestCase):
    def test_prompt_includes_persona_and_prefs(self) -> None:
        p = build_decision_prompt(
            config=_config(),
            tick_id=0,
            image=b"\x89PNG",
            curr_hash="h",
            prev_hash=None,
            recent_actions=[],
        )
        self.assertIn("Alex", p.system)
        self.assertIn("dogs", p.system)
        self.assertIn("tick 0", p.user)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
