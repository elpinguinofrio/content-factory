"""Deterministic compatibility scorer.

The LLM extracts ``ProfileFeatures``. This module independently
recomputes the score from the operator's preferences, and if it
disagrees with the LLM's score it overrides.

Matching is case-insensitive substring — good enough for v1. We match
a configured keyword against:

- the profile bio
- interests
- photo_traits (LLM-extracted)
- red_flags (LLM-extracted)

Deal-breakers short-circuit the score to 0.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config_loader import Preferences
from ..vision.schema import Decision, ProfileFeatures


@dataclass
class ScoreBreakdown:
    score: float
    matched_likes: list[str] = field(default_factory=list)
    matched_dislikes: list[str] = field(default_factory=list)
    matched_red_flags: list[str] = field(default_factory=list)
    matched_deal_breakers: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def dealbreaker_hit(self) -> bool:
        return bool(self.matched_deal_breakers)


def _haystack(profile: ProfileFeatures) -> str:
    parts: list[str] = []
    if profile.bio:
        parts.append(profile.bio)
    if profile.occupation:
        parts.append(profile.occupation)
    if profile.location:
        parts.append(profile.location)
    parts.extend(profile.interests)
    parts.extend(profile.photo_traits)
    parts.extend(profile.red_flags)
    return " \n ".join(parts).lower()


def _matches(keywords: list[str], haystack: str) -> list[str]:
    out = []
    for kw in keywords:
        if kw and kw.strip().lower() in haystack:
            out.append(kw)
    return out


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_profile(profile: ProfileFeatures, prefs: Preferences) -> ScoreBreakdown:
    hay = _haystack(profile)

    dealbreakers = _matches(prefs.deal_breakers, hay)
    if dealbreakers:
        return ScoreBreakdown(
            score=0.0,
            matched_deal_breakers=dealbreakers,
            reason=f"deal-breaker match: {', '.join(dealbreakers)}",
        )

    likes = _matches(prefs.likes, hay)
    dislikes = _matches(prefs.dislikes, hay)
    red_flags = _matches(prefs.red_flags, hay)

    w = prefs.weights
    score = 0.5
    score += w.get("likes", 0.1) * len(likes)
    score += w.get("dislikes", -0.1) * len(dislikes)
    score += w.get("red_flags", -0.2) * len(red_flags)
    score = _clip(score)

    bits: list[str] = []
    if likes:
        bits.append(f"likes: {', '.join(likes)}")
    if dislikes:
        bits.append(f"dislikes: {', '.join(dislikes)}")
    if red_flags:
        bits.append(f"red_flags: {', '.join(red_flags)}")
    reason = "; ".join(bits) if bits else "no configured keywords matched"

    return ScoreBreakdown(
        score=score,
        matched_likes=likes,
        matched_dislikes=dislikes,
        matched_red_flags=red_flags,
        reason=reason,
    )


def action_from_score(score: float, prefs: Preferences) -> str:
    threshold = prefs.threshold.get("swipe_right_min_score", 0.55)
    return "swipe_right" if score >= threshold else "swipe_left"


def override_decision(decision: Decision, prefs: Preferences) -> tuple[Decision, ScoreBreakdown | None]:
    """If ``decision`` is a card decision, recompute score deterministically.

    Returns ``(possibly_updated_decision, breakdown or None)``. The
    returned decision has its ``score``, ``score_reason`` and (for
    swipes) ``action`` replaced with deterministic values. The LLM's
    perception of the profile is preserved untouched.
    """
    if decision.screen != "card" or decision.profile is None:
        return decision, None

    breakdown = score_profile(decision.profile, prefs)
    new_action = decision.action
    if decision.action in ("swipe_left", "swipe_right"):
        new_action = action_from_score(breakdown.score, prefs)

    updated = Decision(
        screen=decision.screen,
        confidence=decision.confidence,
        action=new_action,
        reasoning=decision.reasoning,
        profile=decision.profile,
        score=breakdown.score,
        score_reason=breakdown.reason,
        action_args=dict(decision.action_args),
        ambiguity=decision.ambiguity,
        safe_stop_reason=decision.safe_stop_reason,
    )
    return updated, breakdown
