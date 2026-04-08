"""Chat reply engine.

Builds a chat prompt from the persona + memory, calls a ``ChatClient``
to produce a reply, and returns a ``ChatTurn``. Like the vision
client, ``ChatClient`` is a protocol with real and fake
implementations so tests can run offline.

The real implementation reuses the Anthropic Messages API over
``urllib.request``, no SDK dependency.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .._util import strip_json_fence, utcnow_iso
from ..config_loader import Config
from ..vision.client import extract_text
from ..vision.schema import ChatTurn, ProfileFeatures


CHAT_SYSTEM_PROMPT = """\
You are {display_name}, the operator persona below, replying in a MOCK
dating app's chat. This is a test environment. The other party is a simulated
user. Stay in character per the persona, follow the hard rules, and respect
the message length limit.

Persona: {persona_json}
Goals: {goals_json}
Hard rules: {rules_json}

Match profile snapshot (may be partial):
{profile_json}

Conversation memory so far (oldest first):
{memory_json}

You MUST reply with a single JSON object of this shape (no prose outside JSON):
{{"text": "...", "ambiguity": false, "notes": "..."}}

If you are uncertain how to reply (e.g. message is offensive, asks for
personal info you must not share, off-topic in a confusing way), set
ambiguity: true and text: "". The harness will safe-stop or escalate.
"""


class ChatClient(Protocol):
    def reply(self, system: str, last_their_message: str) -> dict: ...


class ChatEngineError(RuntimeError):
    pass


@dataclass
class ReplyResult:
    turn: ChatTurn
    raw: dict
    ambiguous: bool
    notes: str = ""


def build_chat_prompt(
    *,
    config: Config,
    profile: ProfileFeatures | None,
    memory: list[ChatTurn],
) -> str:
    return CHAT_SYSTEM_PROMPT.format(
        display_name=config.persona.display_name,
        persona_json=json.dumps(config.persona.voice, sort_keys=True),
        goals_json=json.dumps(config.persona.goals),
        rules_json=json.dumps(config.persona.hard_rules),
        profile_json=json.dumps(profile.to_dict() if profile else None, indent=2),
        memory_json=json.dumps(
            [
                {"role": t.role, "text": t.text}
                for t in memory
            ],
            indent=2,
        ),
    )


def _parse_reply_json(text: str) -> dict:
    try:
        data = json.loads(strip_json_fence(text))
    except json.JSONDecodeError as e:
        raise ChatEngineError(f"reply was not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ChatEngineError("reply JSON was not an object")
    if "text" not in data:
        raise ChatEngineError("reply JSON missing 'text'")
    return data


def generate_reply(
    *,
    client: ChatClient,
    config: Config,
    match_id: str,
    profile: ProfileFeatures | None,
    memory: list[ChatTurn],
    last_their_message: str,
) -> ReplyResult:
    system = build_chat_prompt(config=config, profile=profile, memory=memory)
    raw = client.reply(system=system, last_their_message=last_their_message)

    text = extract_text(raw)
    if not text:
        raise ChatEngineError("empty chat response")

    data = _parse_reply_json(text)
    ambiguous = bool(data.get("ambiguity", False))
    reply_text = str(data.get("text", "")).strip()
    if not ambiguous and not reply_text:
        raise ChatEngineError("non-ambiguous reply with empty text")

    turn = ChatTurn(
        turn_id=len(memory),
        match_id=match_id,
        ts=utcnow_iso(),
        role="us",
        text=reply_text,
        source="llm",
        llm_call_id=raw.get("id"),
    )
    return ReplyResult(
        turn=turn,
        raw=raw,
        ambiguous=ambiguous,
        notes=str(data.get("notes", "")),
    )


# ---------------------------------------------------------------------------
# Fake + real clients
# ---------------------------------------------------------------------------


FakeReplyRule = Callable[[str, str], dict | None]


@dataclass
class FakeChatClient:
    rules: list[FakeReplyRule] = field(default_factory=list)
    default: dict | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def reply(self, system: str, last_their_message: str) -> dict:
        self.calls.append((system, last_their_message))
        for rule in self.rules:
            out = rule(system, last_their_message)
            if out is not None:
                return out
        default = self.default or {
            "text": json.dumps({"text": "hey! how's your week going?", "ambiguity": False})
        }
        return {
            "id": f"fake_chat_{uuid.uuid4().hex[:8]}",
            "content": [{"type": "text", "text": default["text"]}],
        }
