"""Prompt assembly for the master vision decision call.

Mirrors the templates in ``mock_dating/design.md``. Prompts are pure
strings so they can be snapshotted and diffed across versions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..config_loader import Config
from .schema import ACTIONS, SCREENS


DECISION_SCHEMA_DESCRIPTION = {
    "screen": f"one of: {list(SCREENS)}",
    "confidence": "float in [0, 1] — your self-rated confidence",
    "action": f"one of: {list(ACTIONS)}",
    "action_args": "object, e.g. {'text': '...'} for type_message",
    "profile": "ProfileFeatures when screen == 'card', else null",
    "score": "float in [0, 1] when screen == 'card', else null",
    "score_reason": "string citing specific prefs when screen == 'card'",
    "reasoning": "one-paragraph rationale for the chosen action",
    "ambiguity": "bool: true if you are uncertain",
    "safe_stop_reason": "string: only set when ambiguity is true",
}

PROFILE_FEATURES_DESCRIPTION = {
    "name": "string or null",
    "age": "int or null",
    "bio": "string or null",
    "location": "string or null",
    "interests": "list of strings",
    "occupation": "string or null",
    "photo_traits": "list of strings (e.g. 'outdoors', 'with dog')",
    "red_flags": "list of strings observed in the profile",
}


SYSTEM_PROMPT_TEMPLATE = """\
You are an automation agent driving a MOCK Android dating app inside an emulator.
This is a TEST environment. There are NO real users. Your job is to look at one
screenshot and return a single structured decision.

You must:
- Identify the current screen.
- If the screen is a profile card, extract structured features and rate the
  profile against the operator's preferences.
- Choose exactly ONE action from the allowed vocabulary.
- Be honest about uncertainty. If you are not confident, set `ambiguity` to
  true and choose `action: "noop"`. The harness will safe-stop. Do NOT guess.

Allowed actions: {actions}
Allowed screens: {screens}

Respond with a single JSON object matching this shape (no prose outside JSON):
{decision_schema}

ProfileFeatures shape (used inside `profile`):
{profile_schema}

Operator persona:
{persona}

Operator preferences:
{preferences}

Scoring rule to apply when screen == "card":

  Any `deal_breakers` overlap forces score = 0.0 and action = "swipe_left".
  Otherwise:
    score = clip(
      0.5
      + weights.likes       * (#likes_matched)
      + weights.dislikes    * (#dislikes_matched)
      + weights.red_flags   * (#red_flags_matched),
      0.0, 1.0
    )
    action = "swipe_right" if score >= threshold.swipe_right_min_score
             else "swipe_left"

  Return BOTH the score and a score_reason that cites the specific configured
  likes / dislikes / red flags / deal breakers that influenced the score.

Safety: if the screen is unrecognised, or if the right action is not obvious,
set ambiguity=true and action="noop". The operator will review.
"""


USER_PROMPT_TEMPLATE = """\
This is tick {tick_id}. The previous screen hash was {prev_hash}; the current
screen hash is {curr_hash}. They are {same_or_different}.

Recent actions (oldest first): {recent_actions}

Return exactly one Decision JSON object.
"""


@dataclass
class PromptBundle:
    system: str
    user: str
    image_bytes: bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "user": self.user,
            "image_size_bytes": len(self.image_bytes),
        }


def build_system_prompt(config: Config) -> str:
    """Build the system prompt. Config is immutable per run, so callers
    should cache the result and reuse it across ticks."""
    persona_yaml = json.dumps(
        {
            "display_name": config.persona.display_name,
            "voice": config.persona.voice,
            "goals": config.persona.goals,
            "hard_rules": config.persona.hard_rules,
        },
        indent=2,
        sort_keys=True,
    )
    prefs_yaml = json.dumps(
        {
            "likes": config.preferences.likes,
            "dislikes": config.preferences.dislikes,
            "red_flags": config.preferences.red_flags,
            "deal_breakers": config.preferences.deal_breakers,
            "weights": config.preferences.weights,
            "threshold": config.preferences.threshold,
        },
        indent=2,
        sort_keys=True,
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        actions=", ".join(ACTIONS),
        screens=", ".join(SCREENS),
        decision_schema=json.dumps(DECISION_SCHEMA_DESCRIPTION, indent=2),
        profile_schema=json.dumps(PROFILE_FEATURES_DESCRIPTION, indent=2),
        persona=persona_yaml,
        preferences=prefs_yaml,
    )


def build_user_prompt(
    *,
    tick_id: int,
    curr_hash: str,
    prev_hash: str | None,
    recent_actions: list[str],
) -> str:
    return USER_PROMPT_TEMPLATE.format(
        tick_id=tick_id,
        prev_hash=prev_hash or "(none)",
        curr_hash=curr_hash,
        same_or_different="SAME" if prev_hash == curr_hash else "DIFFERENT",
        recent_actions=json.dumps(recent_actions),
    )


def build_decision_prompt(
    *,
    config: Config,
    tick_id: int,
    image: bytes,
    curr_hash: str,
    prev_hash: str | None,
    recent_actions: list[str],
) -> PromptBundle:
    """Build a full ``PromptBundle``. Prefer caching the system prompt via
    ``build_system_prompt`` and calling ``build_user_prompt`` per tick."""
    return PromptBundle(
        system=build_system_prompt(config),
        user=build_user_prompt(
            tick_id=tick_id,
            curr_hash=curr_hash,
            prev_hash=prev_hash,
            recent_actions=recent_actions,
        ),
        image_bytes=image,
    )
