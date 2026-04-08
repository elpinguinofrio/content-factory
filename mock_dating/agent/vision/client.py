"""Vision LLM client.

Two implementations:

- ``AnthropicVisionClient``: calls the Anthropic Messages API over
  ``urllib.request``. Used at runtime when ``ANTHROPIC_API_KEY`` is set.
- ``FakeVisionClient``: returns canned ``Decision`` objects keyed by
  rules. Used by tests.

``anthropic_post`` and ``extract_text`` are shared with ``chat.engine``.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .._util import strip_json_fence
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
# HTTP + response plumbing (shared with chat.engine)
# ---------------------------------------------------------------------------


def anthropic_post(api_key: str, body: dict, timeout_s: float = 30.0) -> dict:
    """POST to the Anthropic Messages API. Stdlib-only, raises on any error."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", "replace") if e.fp else ""
        raise VisionClientError(f"HTTP {e.code}: {body_text}") from e
    except urllib.error.URLError as e:
        raise VisionClientError(f"network error: {e}") from e
    return json.loads(payload)


def extract_text(raw: dict) -> str:
    """Join all text blocks from an Anthropic Messages API response."""
    parts = [
        block.get("text", "")
        for block in (raw.get("content") or [])
        if block.get("type") == "text"
    ]
    return "\n".join(parts).strip()


def parse_decision(raw_text: str) -> Decision:
    """Parse a JSON blob (optionally fenced) into a validated ``Decision``."""
    text = strip_json_fence(raw_text)
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
        reasoning=str(data.get("reasoning", "")),
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
        raw = anthropic_post(self.api_key, body, self.timeout_s)
        text = extract_text(raw)
        if not text:
            raise VisionClientError("empty response from model")
        decision = parse_decision(text)
        call_id = raw.get("id") or f"anth_{uuid.uuid4().hex[:12]}"
        return VisionResponse(call_id=call_id, raw=raw, decision=decision)


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


FakeRule = Callable[[PromptBundle], Decision]


@dataclass
class FakeVisionClient:
    """Returns canned decisions driven by a list of rules.

    The first rule that returns a non-None value wins; otherwise ``default``
    (or a safe-stop stub) is used.
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
