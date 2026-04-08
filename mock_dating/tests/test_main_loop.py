"""End-to-end loop tests using fake adb + fake LLMs.

Exercises the whole Agent.run() path: observe → decide → safety gate →
scorer override → act → log → watchdogs. These tests are what give us
confidence the glue in main.py actually works.
"""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from mock_dating.agent.audit.logger import AuditLogger
from mock_dating.agent.chat.engine import FakeChatClient
from mock_dating.agent.chat.memory import ChatMemory
from mock_dating.agent.config_loader import Config, Persona, Preferences, Runtime
from mock_dating.agent.harness.adb import FakeAdb
from mock_dating.agent.main import Agent
from mock_dating.agent.vision.client import FakeVisionClient
from mock_dating.agent.vision.schema import Decision, ProfileFeatures


def _config(**runtime_overrides) -> Config:
    runtime_defaults = dict(
        mode="auto",
        tick_interval_s=0.0,
        tick_timeout_s=5,
        max_ticks=10,
        min_confidence=0.5,
        ambiguity_safe_stop=True,
        no_progress_window=3,
        loop_window=6,
        loop_threshold=4,
        quiesce_max_wait_s=0.0,  # tests: don't consume frames in quiesce
        quiesce_poll_s=0.0,
    )
    runtime_defaults.update(runtime_overrides)
    return Config(
        persona=Persona(
            display_name="Alex",
            voice={"tone": "warm"},
            goals=["be curious"],
            hard_rules=["never share contact info"],
        ),
        preferences=Preferences(
            likes=["dogs", "hiking"],
            dislikes=["smoking"],
            red_flags=["negative bio energy"],
            deal_breakers=["explicit drug references"],
            weights={"likes": 0.2, "dislikes": -0.1, "red_flags": -0.2, "deal_breakers": -10.0},
            threshold={"swipe_right_min_score": 0.55},
        ),
        runtime=Runtime(**runtime_defaults),
    )


def _build_agent(vision_client, chat_client, frames, tmpdir: Path, **cfg_kw) -> Agent:
    config = _config(**cfg_kw)
    adb = FakeAdb(frames=frames)
    audit = AuditLogger(root=tmpdir)
    chat_memory = ChatMemory(root=audit.run_dir / "matches")
    return Agent(
        config=config,
        adb=adb,
        vision_client=vision_client,
        chat_client=chat_client,
        audit=audit,
        chat_memory=chat_memory,
        sleeper=lambda s: None,
    )


# ---------------------------------------------------------------------------


class HappyPathTests(unittest.TestCase):
    def test_swipe_sequence_on_card_screens(self) -> None:
        """Five distinct card frames, agent should swipe and log every tick."""
        frames = [f"frame{i}".encode() for i in range(5)]

        def rule(prompt):
            # Good profile → expect deterministic swipe_right after override.
            return Decision(
                screen="card",
                confidence=0.9,
                action="swipe_left",  # LLM is wrong; scorer should fix this
                reasoning="card visible",
                profile=ProfileFeatures(
                    name="Sam",
                    age=29,
                    bio="I love dogs and hiking",
                    interests=["dogs", "hiking"],
                ),
                score=0.3,
            )

        vision = FakeVisionClient(rules=[rule])
        chat = FakeChatClient()

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(vision, chat, frames, Path(tmp), max_ticks=5)
            result = agent.run()

        self.assertEqual(result.ticks, 5)
        self.assertEqual(result.stop_reason, "max_ticks_reached")
        # Every tick should have resulted in a real swipe action on the adb
        # fake.
        swipes = [a for a in agent.adb.actions if a.kind == "swipe"]
        self.assertEqual(len(swipes), 5)
        # Scorer override should have made every one a swipe_right (x1 < x2).
        for s in swipes:
            self.assertLess(s.args["x1"], s.args["x2"])

    def test_mixed_accept_reject_via_scorer(self) -> None:
        frames = [b"good", b"bad"]
        calls = {"n": 0}

        def rule(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                return Decision(
                    screen="card",
                    confidence=0.9,
                    action="swipe_right",
                    reasoning="",
                    profile=ProfileFeatures(bio="dogs and hiking", interests=["dogs", "hiking"]),
                    score=0.7,
                )
            return Decision(
                screen="card",
                confidence=0.9,
                action="swipe_right",  # LLM is wrong about dealbreaker
                reasoning="",
                profile=ProfileFeatures(bio="explicit drug references and dogs"),
                score=0.9,
            )

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                frames,
                Path(tmp),
                max_ticks=2,
            )
            result = agent.run()

        self.assertEqual(result.ticks, 2)
        swipes = [a for a in agent.adb.actions if a.kind == "swipe"]
        self.assertEqual(len(swipes), 2)
        # First swipe_right (x1 < x2), second swipe_left (x1 > x2).
        self.assertLess(swipes[0].args["x1"], swipes[0].args["x2"])
        self.assertGreater(swipes[1].args["x1"], swipes[1].args["x2"])

    def test_chat_flow_writes_memory_and_types_message(self) -> None:
        frames = [b"chat_frame"]

        def rule(prompt):
            return Decision(
                screen="chat",
                confidence=0.9,
                action="type_message",
                reasoning="reply to opener",
                action_args={"text": "placeholder"},
            )

        def reply_rule(system, msg):
            return {
                "id": f"fake_{uuid.uuid4().hex[:6]}",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"text": "hey! tell me about the dogs", "ambiguity": False}),
                    }
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(rules=[reply_rule]),
                frames,
                Path(tmp),
                max_ticks=1,
            )
            result = agent.run()  # noqa: F841

            # Assert the agent typed the CHAT ENGINE's text, not the placeholder.
            typed = [a for a in agent.adb.actions if a.kind == "type_text"]
            self.assertEqual(len(typed), 1)
            self.assertEqual(typed[0].args["text"], "hey! tell me about the dogs")
            # Chat memory should have been appended.
            matches_root = agent.audit.run_dir / "matches"
            memory_files = list(matches_root.rglob("memory.jsonl"))
            self.assertEqual(len(memory_files), 1)
            lines = memory_files[0].read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)
            turn = json.loads(lines[0])
            self.assertEqual(turn["role"], "us")
            self.assertEqual(turn["text"], "hey! tell me about the dogs")


# ---------------------------------------------------------------------------


class SafeStopTests(unittest.TestCase):
    def test_unknown_screen_safe_stops(self) -> None:
        def rule(prompt):
            return Decision(
                screen="unknown",
                confidence=0.9,
                action="noop",
                reasoning="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                [b"a", b"b", b"c"],
                Path(tmp),
            )
            result = agent.run()

            self.assertEqual(result.ticks, 1)
            self.assertTrue(result.stop_reason.startswith("safe_stop"))
            self.assertTrue((agent.audit.run_dir / "STOPPED").exists())

    def test_low_confidence_safe_stops(self) -> None:
        def rule(prompt):
            return Decision(
                screen="card",
                confidence=0.1,
                action="swipe_right",
                reasoning="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                [b"a"],
                Path(tmp),
            )
            result = agent.run()

        self.assertEqual(result.ticks, 1)
        self.assertIn("confidence", result.stop_reason)

    def test_ambiguous_llm_response_safe_stops(self) -> None:
        def rule(prompt):
            return Decision(
                screen="card",
                confidence=0.9,
                action="noop",
                reasoning="",
                ambiguity=True,
                safe_stop_reason="unsure what screen this is",
            )

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                [b"a"],
                Path(tmp),
            )
            result = agent.run()

        self.assertEqual(result.ticks, 1)
        self.assertIn("unsure what screen this is", result.stop_reason)

    def test_vision_client_error_safe_stops_after_retries(self) -> None:
        from mock_dating.agent.vision.client import VisionClientError

        class BrokenClient:
            def __init__(self) -> None:
                self.calls = 0

            def decide(self, prompt):  # noqa: ARG002
                self.calls += 1
                raise VisionClientError("boom")

        broken = BrokenClient()
        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                broken,
                FakeChatClient(),
                [b"a"],
                Path(tmp),
            )
            result = agent.run()

        self.assertTrue(result.stop_reason.startswith("safe_stop"))
        # retries=1 by default → 2 total calls
        self.assertEqual(broken.calls, 2)


# ---------------------------------------------------------------------------


class WatchdogTests(unittest.TestCase):
    def test_no_progress_watchdog_fires(self) -> None:
        # Same screen hash + same action for 3 consecutive ticks should trip
        # the no-progress watchdog.
        def rule(prompt):
            return Decision(
                screen="discover",
                confidence=0.9,
                action="wait",
                reasoning="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                [b"static"] * 10,
                Path(tmp),
                no_progress_window=3,
                loop_window=10,
                loop_threshold=100,  # disable loop watchdog
            )
            result = agent.run()

        self.assertIn("no-progress", result.stop_reason)
        # Exactly 3 ticks before the watchdog fires.
        self.assertEqual(result.ticks, 3)

    def test_loop_watchdog_fires(self) -> None:
        """Two alternating frames + same action → same (hash, action) pairs."""
        def rule(prompt):
            return Decision(
                screen="card",
                confidence=0.9,
                action="swipe_left",  # no profile → scorer won't override
                reasoning="",
            )

        # Alternate between two hashes so the no-progress watchdog never fires
        # (because the hash changes every tick) but the (hash, action) pair
        # repeats 4x in a 7-tick window, tripping the loop watchdog.
        frames = [b"A", b"B"] * 10

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                frames,
                Path(tmp),
                no_progress_window=100,  # disable no-progress
                loop_window=7,
                loop_threshold=4,
            )
            result = agent.run()

        self.assertIn("loop watchdog", result.stop_reason)
        # The loop watchdog fires on the first tick where any (hash, action)
        # pair has accumulated to threshold entries in the window. With two
        # alternating hashes and threshold=4, this happens on tick 7 (4 A's
        # or 4 B's), so result.ticks == 7.
        self.assertGreaterEqual(result.ticks, 4)
        self.assertLessEqual(result.ticks, 8)


# ---------------------------------------------------------------------------


class AuditArtifactTests(unittest.TestCase):
    def test_events_jsonl_is_reloadable(self) -> None:
        def rule(prompt):
            return Decision(
                screen="card",
                confidence=0.9,
                action="swipe_left",
                reasoning="",
                profile=ProfileFeatures(bio="nothing matches"),
                score=0.3,
            )

        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(rules=[rule]),
                FakeChatClient(),
                [f"f{i}".encode() for i in range(3)],
                Path(tmp),
                max_ticks=3,
                no_progress_window=100,
                loop_threshold=100,
            )
            result = agent.run()  # noqa: F841

            events_path = agent.audit.events_path
            lines = events_path.read_text().strip().splitlines()
            self.assertEqual(len(lines), 3)
            for line in lines:
                data = json.loads(line)
                self.assertIn("decision", data)
                self.assertEqual(data["decision"]["screen"], "card")

    def test_config_snapshot_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = _build_agent(
                FakeVisionClient(),  # default ambiguous → safe-stop tick 0
                FakeChatClient(),
                [b"a"],
                Path(tmp),
            )
            agent.run()
            snap_path = agent.audit.run_dir / "config_snapshot.json"
            self.assertTrue(snap_path.exists())
            snap = json.loads(snap_path.read_text())
            self.assertIn("persona", snap)
            self.assertIn("runtime", snap)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
