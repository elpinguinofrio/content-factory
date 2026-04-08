"""Unit tests for audit.logger and audit.replay."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from mock_dating.agent.audit.logger import AuditLogger
from mock_dating.agent.audit.replay import replay_tick
from mock_dating.agent.vision.client import FakeVisionClient, VisionResponse
from mock_dating.agent.vision.prompt import PromptBundle
from mock_dating.agent.vision.schema import Decision, ProfileFeatures


def _decision(action: str = "swipe_right", score: float | None = 0.8) -> Decision:
    return Decision(
        screen="card",
        confidence=0.9,
        action=action,
        reasoning="ok",
        profile=ProfileFeatures(name="Sam", age=29, interests=["dogs"]),
        score=score,
        score_reason="likes: dogs",
    )


class AuditLoggerTests(unittest.TestCase):
    def test_write_tick_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(root=Path(tmp))
            prompt = PromptBundle(system="sys", user="usr", image_bytes=b"\x89PNG")
            event = logger.write_tick(
                tick_id=0,
                prompt=prompt,
                image=b"\x89PNG",
                raw_response={"content": [{"type": "text", "text": "{}"}]},
                decision=_decision(),
                action_executed=True,
                action_args={},
                latency_ms=42,
                llm_call_id="call_1",
                retries=0,
                safe_stop=False,
                safe_stop_reason=None,
                screen_hash="abc",
            )
            tdir = logger.run_dir / "tick_000000"
            for name in ("screen.png", "prompt.txt", "response.json", "decision.json", "action.json", "meta.json"):
                self.assertTrue((tdir / name).exists(), f"missing: {name}")
            # events.jsonl should contain one line
            lines = logger.events_path.read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed["tick_id"], 0)
            self.assertEqual(parsed["decision"]["screen"], "card")
            self.assertEqual(event.tick_id, 0)

    def test_config_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(root=Path(tmp))
            logger.snapshot_config({"k": "v"})
            loaded = json.loads((logger.run_dir / "config_snapshot.json").read_text())
            self.assertEqual(loaded, {"k": "v"})

    def test_stop_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(root=Path(tmp))
            logger.write_stop_marker("test reason")
            stop = json.loads((logger.run_dir / "STOPPED").read_text())
            self.assertEqual(stop["reason"], "test reason")


class ReplayTests(unittest.TestCase):
    def test_replay_produces_compatible_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(root=Path(tmp))
            original = _decision(action="swipe_right", score=0.8)
            prompt = PromptBundle(system="sys", user="usr", image_bytes=b"\x89PNG")
            logger.write_tick(
                tick_id=0,
                prompt=prompt,
                image=b"\x89PNG",
                raw_response={"content": [{"type": "text", "text": "{}"}]},
                decision=original,
                action_executed=True,
                action_args={},
                latency_ms=1,
                llm_call_id="x",
                retries=0,
                safe_stop=False,
                safe_stop_reason=None,
                screen_hash="abc",
            )
            tdir = logger.run_dir / "tick_000000"
            client = FakeVisionClient(
                rules=[lambda p: _decision(action="swipe_right", score=0.85)],
            )
            result = replay_tick(tdir, client)
            self.assertTrue(result.structurally_compatible)
            self.assertEqual(result.original.action, result.replayed.action)

    def test_replay_detects_incompatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(root=Path(tmp))
            prompt = PromptBundle(system="sys", user="usr", image_bytes=b"\x89PNG")
            logger.write_tick(
                tick_id=0,
                prompt=prompt,
                image=b"\x89PNG",
                raw_response={},
                decision=_decision(action="swipe_right", score=0.8),
                action_executed=True,
                action_args={},
                latency_ms=1,
                llm_call_id="x",
                retries=0,
                safe_stop=False,
                safe_stop_reason=None,
                screen_hash="abc",
            )
            tdir = logger.run_dir / "tick_000000"
            client = FakeVisionClient(
                rules=[lambda p: _decision(action="swipe_left", score=0.2)],
            )
            result = replay_tick(tdir, client)
            self.assertFalse(result.structurally_compatible)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
