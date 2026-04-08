"""Vision LLM client.

Two implementations:

- ``AnthropicVisionClient``: calls the Anthropic Messages API over
  ``urllib.request``. Used at runtime when ``ANTHROPIC_API_KEY`` is set.
- ``FakeVisionClient``: returns canned ``Decision`` objects keyed by
  screen-hash prefix or by a registered rule. Used by tests.

Both implementations produce a ``VisionResponse`` (raw response dict +
a validated ``Decision``). The safety gate in ``safety.py`` runs on
top of the response.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .prompt import PromptBundle
from .schema import ACTIONS, SCREENS, Decision, ProfileFeatures


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class VisionClientError(RuntimeError):
    pass


@dataclass
class VisionResponse:
    call_id: str
    raw: dict
    decision: Decision


class VisionClient(Protocol):
    def decide(self, prompt: PromptBundle) -> VisionResponse: ...


# ---------------------------------------------------------------------------
# Response parsing (shared by real and fake clients)
# ---------------------------------------------------------------------------


def parse_decision(raw_text: str) -> Decision:
    """Parse a JSON blob into a ``Decision``.

    Accepts either pure JSON or JSON wrapped in a ```json ...``` fence.
    Raises ``VisionClientError`` on any schema violation.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        # Strip leading ``` and optional "json" language tag.
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise VisionClientError(f"response was not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise VisionClientError("top-level JSON was not an object")

    try:
        screen = data["screen"]
        action = data["action"]
        confidence = float(data.get("confidence", 0.0))
        reasoning = str(data.get("reasoning", ""))
    except KeyError as e:
        raise VisionClientError(f"missing required field: {e}") from e

    if screen not in SCREENS:
        raise VisionClientError(f"unknown screen: {screen!r}")
    if action not in ACTIONS:
        raise VisionClientError(f"unknown action: {action!r}")
    if not (0.0 <= confidence <= 1.0):
        raise VisionClientError(f"confidence out of range: {confidence}")

    profile = data.get("profile")
    if profile is not None and not isinstance(profile, dict):
        raise VisionClientError("profile must be an object or null")

    score = data.get("score")
    if score is not None:
        try:
            score_f: float | None = float(score)
        except (TypeError, ValueError) as e:
            raise VisionClientError(f"score not a number: {score!r}") from e
        if not (0.0 <= score_f <= 1.0):
            raise VisionClientError(f"score out of range: {score_f}")
    else:
        score_f = None

    return Decision(
        screen=screen,
        confidence=confidence,
        action=action,
        reasoning=reasoning,
        profile=ProfileFeatures.from_dict(profile) if profile else None,
        score=score_f,
        score_reason=data.get("score_reason"),
        action_args=dict(data.get("action_args") or {}),
        ambiguity=bool(data.get("ambiguity", False)),
        safe_stop_reason=data.get("safe_stop_reason"),
    )


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class AnthropicVisionClient:
    api_key: str
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024
    timeout_s: float = 30.0

    def _post(self, body: dict) -> dict:
        import urllib.error
        import urllib.request

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=data,
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "replace") if e.fp else ""
            raise VisionClientError(f"HTTP {e.code}: {body_text}") from e
        except urllib.error.URLError as e:
            raise VisionClientError(f"network error: {e}") from e
        return json.loads(payload)

    def decide(self, prompt: PromptBundle) -> VisionResponse:
        image_b64 = base64.standard_b64encode(prompt.image_bytes).decode("ascii")
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": prompt.system,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt.user},
                    ],
                }
            ],
        }
        raw = self._post(body)

        text_parts = []
        for block in raw.get("content", []) or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        text = "\n".join(text_parts).strip()
        if not text:
            raise VisionClientError("empty response from model")

        decision = parse_decision(text)
        call_id = raw.get("id") or f"anth_{uuid.uuid4().hex[:12]}"
        return VisionResponse(call_id=call_id, raw=raw, decision=decision)


# ---------------------------------------------------------------------------
# Fake client (tests, offline dev)
# ---------------------------------------------------------------------------


FakeRule = Callable[[PromptBundle], Decision]


@dataclass
class FakeVisionClient:
    """Returns canned decisions driven by a list of rules.

    The first rule that returns a non-None value wins. If no rule
    matches, ``default`` is used.
    """

    rules: list[FakeRule] = field(default_factory=list)
    default: Decision | None = None
    calls: list[PromptBundle] = field(default_factory=list)

    def decide(self, prompt: PromptBundle) -> VisionResponse:
        self.calls.append(prompt)
        for rule in self.rules:
            out = rule(prompt)
            if out is not None:
                decision = out
                break
        else:
            decision = self.default or Decision(
                screen="unknown",
                confidence=0.0,
                action="noop",
                reasoning="fake default",
                ambiguity=True,
                safe_stop_reason="no rule matched",
            )
        return VisionResponse(
            call_id=f"fake_{uuid.uuid4().hex[:8]}",
            raw={"content": [{"type": "text", "text": json.dumps(decision.to_dict())}]},
            decision=decision,
        )
