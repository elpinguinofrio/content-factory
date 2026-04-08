"""Unit tests for vision.schema."""

import unittest

from mock_dating.agent.vision.schema import (
    ACTIONS,
    SCREENS,
    ChatTurn,
    Decision,
    ProfileFeatures,
    TickEvent,
)


class SchemaRoundTripTests(unittest.TestCase):
    def test_profile_features_roundtrip(self) -> None:
        p = ProfileFeatures(
            name="Sam",
            age=29,
            bio="loves dogs and hiking",
            interests=["dogs", "hiking"],
            photo_traits=["outdoors"],
        )
        self.assertEqual(ProfileFeatures.from_dict(p.to_dict()), p)

    def test_decision_roundtrip_card(self) -> None:
        d = Decision(
            screen="card",
            confidence=0.82,
            action="swipe_right",
            reasoning="shared interests",
            profile=ProfileFeatures(name="Sam", age=29, interests=["hiking"]),
            score=0.7,
            score_reason="likes: hiking",
        )
        self.assertEqual(Decision.from_dict(d.to_dict()), d)

    def test_decision_roundtrip_no_profile(self) -> None:
        d = Decision(
            screen="chat",
            confidence=0.9,
            action="type_message",
            reasoning="reply to opener",
            action_args={"text": "hey"},
        )
        round_tripped = Decision.from_dict(d.to_dict())
        self.assertEqual(round_tripped, d)
        self.assertIsNone(round_tripped.profile)

    def test_tick_event_roundtrip(self) -> None:
        d = Decision(screen="card", confidence=0.6, action="swipe_left", reasoning="meh")
        ev = TickEvent(
            tick_id=7,
            run_id="r123",
            ts="2026-04-08T00:00:00+00:00",
            screen_hash="abc",
            decision=d,
            action_executed=True,
            latency_ms=1234,
            llm_call_id="call_x",
        )
        self.assertEqual(TickEvent.from_dict(ev.to_dict()), ev)

    def test_chat_turn_roundtrip(self) -> None:
        t = ChatTurn(
            turn_id=0,
            match_id="m1",
            ts="2026-04-08T00:00:00+00:00",
            role="us",
            text="hi",
            source="llm",
            llm_call_id="c1",
        )
        self.assertEqual(ChatTurn.from_dict(t.to_dict()), t)

    def test_constants_present(self) -> None:
        self.assertIn("card", SCREENS)
        self.assertIn("swipe_right", ACTIONS)
        self.assertIn("noop", ACTIONS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
