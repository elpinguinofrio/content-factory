"""Unit tests for scoring.scorer."""

import unittest

from mock_dating.agent.config_loader import Preferences
from mock_dating.agent.scoring.scorer import (
    action_from_score,
    override_decision,
    score_profile,
)
from mock_dating.agent.vision.schema import Decision, ProfileFeatures


def _prefs() -> Preferences:
    return Preferences(
        likes=["dogs", "hiking", "cooking"],
        dislikes=["smoking"],
        red_flags=["negative bio energy"],
        deal_breakers=["explicit drug references"],
        weights={"likes": 0.1, "dislikes": -0.1, "red_flags": -0.2, "deal_breakers": -10.0},
        threshold={"swipe_right_min_score": 0.55},
    )


class ScorerTests(unittest.TestCase):
    def test_empty_profile_neutral(self) -> None:
        b = score_profile(ProfileFeatures(), _prefs())
        self.assertEqual(b.score, 0.5)
        self.assertEqual(b.matched_likes, [])
        self.assertFalse(b.dealbreaker_hit)

    def test_single_like_raises_score(self) -> None:
        p = ProfileFeatures(bio="I love dogs", interests=[])
        b = score_profile(p, _prefs())
        self.assertGreater(b.score, 0.5)
        self.assertEqual(b.matched_likes, ["dogs"])

    def test_multiple_likes_cap_at_one(self) -> None:
        p = ProfileFeatures(
            bio="dogs, hiking, cooking, dogs, hiking",
            interests=["dogs", "hiking", "cooking"],
            photo_traits=["with dog"],
        )
        b = score_profile(p, _prefs())
        self.assertLessEqual(b.score, 1.0)
        self.assertGreaterEqual(b.score, 0.5)

    def test_dealbreaker_forces_zero(self) -> None:
        p = ProfileFeatures(
            bio="I love dogs and hiking and explicit drug references lol",
            interests=["dogs", "hiking", "cooking"],
        )
        b = score_profile(p, _prefs())
        self.assertEqual(b.score, 0.0)
        self.assertTrue(b.dealbreaker_hit)

    def test_dislike_lowers_score(self) -> None:
        p = ProfileFeatures(bio="casual smoking", interests=[])
        b = score_profile(p, _prefs())
        self.assertLess(b.score, 0.5)

    def test_action_from_score(self) -> None:
        self.assertEqual(action_from_score(0.8, _prefs()), "swipe_right")
        self.assertEqual(action_from_score(0.4, _prefs()), "swipe_left")
        # Boundary is inclusive of the threshold.
        self.assertEqual(action_from_score(0.55, _prefs()), "swipe_right")

    def test_determinism(self) -> None:
        p = ProfileFeatures(bio="dogs hiking", interests=["dogs", "hiking"])
        a = score_profile(p, _prefs()).score
        b = score_profile(p, _prefs()).score
        self.assertEqual(a, b)


class OverrideDecisionTests(unittest.TestCase):
    def test_override_card_with_good_profile(self) -> None:
        dec = Decision(
            screen="card",
            confidence=0.9,
            action="swipe_left",  # LLM was wrong
            reasoning="n/a",
            profile=ProfileFeatures(
                bio="loves dogs and hiking",
                interests=["dogs", "hiking"],
            ),
            score=0.2,
        )
        updated, breakdown = override_decision(dec, _prefs())
        self.assertIsNotNone(breakdown)
        self.assertEqual(updated.action, "swipe_right")
        self.assertGreaterEqual(updated.score or 0.0, 0.55)
        # Features preserved
        self.assertEqual(updated.profile, dec.profile)

    def test_override_preserves_non_card(self) -> None:
        dec = Decision(
            screen="chat",
            confidence=0.9,
            action="type_message",
            reasoning="",
        )
        updated, breakdown = override_decision(dec, _prefs())
        self.assertIsNone(breakdown)
        self.assertEqual(updated, dec)

    def test_override_respects_dealbreaker(self) -> None:
        dec = Decision(
            screen="card",
            confidence=0.9,
            action="swipe_right",  # LLM was wrong
            reasoning="",
            profile=ProfileFeatures(bio="explicit drug references and dogs"),
            score=0.99,
        )
        updated, _ = override_decision(dec, _prefs())
        self.assertEqual(updated.action, "swipe_left")
        self.assertEqual(updated.score, 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
