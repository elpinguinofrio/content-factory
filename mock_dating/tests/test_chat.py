"""Unit tests for chat.memory and chat.engine."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from mock_dating.agent.chat.engine import (
    ChatEngineError,
    FakeChatClient,
    generate_reply,
)
from mock_dating.agent.chat.memory import ChatMemory
from mock_dating.agent.config_loader import Config, Persona, Preferences, Runtime
from mock_dating.agent.vision.schema import ChatTurn, ProfileFeatures


def _config() -> Config:
    return Config(
        persona=Persona(
            display_name="Alex",
            voice={"tone": "warm"},
            goals=["be curious"],
            hard_rules=["never share contact info"],
        ),
        preferences=Preferences(),
        runtime=Runtime(),
    )


class ChatMemoryTests(unittest.TestCase):
    def test_append_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem = ChatMemory(root=Path(tmp))
            t1 = ChatTurn(
                turn_id=0,
                match_id="m1",
                ts="2026-04-08T00:00:00+00:00",
                role="them",
                text="hi",
                source="mock_user",
            )
            t2 = ChatTurn(
                turn_id=1,
                match_id="m1",
                ts="2026-04-08T00:00:01+00:00",
                role="us",
                text="hey",
                source="llm",
            )
            mem.append(t1)
            mem.append(t2)
            loaded = mem.load("m1")
            self.assertEqual(loaded, [t1, t2])

    def test_next_turn_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem = ChatMemory(root=Path(tmp))
            self.assertEqual(mem.next_turn_id("nope"), 0)
            mem.append(
                ChatTurn(
                    turn_id=0,
                    match_id="m2",
                    ts="t",
                    role="them",
                    text="x",
                    source="mock_user",
                )
            )
            self.assertEqual(mem.next_turn_id("m2"), 1)


def _reply_payload(text: str, ambiguity: bool = False) -> dict:
    return {
        "id": f"fake_{uuid.uuid4().hex[:6]}",
        "content": [
            {
                "type": "text",
                "text": json.dumps({"text": text, "ambiguity": ambiguity, "notes": ""}),
            }
        ],
    }


class GenerateReplyTests(unittest.TestCase):
    def test_successful_reply_creates_us_turn(self) -> None:
        client = FakeChatClient(
            rules=[lambda s, msg: _reply_payload("hey, tell me more about the dogs!")]
        )
        result = generate_reply(
            client=client,
            config=_config(),
            match_id="m1",
            profile=ProfileFeatures(name="Sam", interests=["dogs"]),
            memory=[],
            last_their_message="",
        )
        self.assertFalse(result.ambiguous)
        self.assertEqual(result.turn.role, "us")
        self.assertIn("dogs", result.turn.text)
        self.assertEqual(result.turn.source, "llm")

    def test_ambiguous_reply_flags_ambiguity(self) -> None:
        client = FakeChatClient(
            rules=[lambda s, msg: _reply_payload("", ambiguity=True)]
        )
        result = generate_reply(
            client=client,
            config=_config(),
            match_id="m1",
            profile=None,
            memory=[],
            last_their_message="offensive stuff",
        )
        self.assertTrue(result.ambiguous)
        self.assertEqual(result.turn.text, "")

    def test_empty_non_ambiguous_reply_errors(self) -> None:
        client = FakeChatClient(
            rules=[lambda s, msg: _reply_payload("", ambiguity=False)]
        )
        with self.assertRaises(ChatEngineError):
            generate_reply(
                client=client,
                config=_config(),
                match_id="m1",
                profile=None,
                memory=[],
                last_their_message="",
            )

    def test_invalid_json_errors(self) -> None:
        def rule(s, msg):
            return {
                "id": "x",
                "content": [{"type": "text", "text": "not json at all"}],
            }

        client = FakeChatClient(rules=[rule])
        with self.assertRaises(ChatEngineError):
            generate_reply(
                client=client,
                config=_config(),
                match_id="m1",
                profile=None,
                memory=[],
                last_their_message="",
            )

    def test_memory_threaded_into_system_prompt(self) -> None:
        seen_system: list[str] = []

        def rule(system, msg):
            seen_system.append(system)
            return _reply_payload("short reply")

        client = FakeChatClient(rules=[rule])
        memory = [
            ChatTurn(
                turn_id=0,
                match_id="m1",
                ts="t",
                role="them",
                text="hey stranger",
                source="mock_user",
            )
        ]
        generate_reply(
            client=client,
            config=_config(),
            match_id="m1",
            profile=ProfileFeatures(name="Sam"),
            memory=memory,
            last_their_message="hey stranger",
        )
        self.assertIn("hey stranger", seen_system[0])
        self.assertIn("Alex", seen_system[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
