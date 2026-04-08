"""Unit tests for the harness layer (FakeAdb + ActionExecutor + ScreenshotService)."""

import unittest

from mock_dating.agent.harness.actions import ActionExecutor
from mock_dating.agent.harness.adb import FakeAdb
from mock_dating.agent.harness.screenshot import ScreenshotService, frame_hash


class FrameHashTests(unittest.TestCase):
    def test_same_bytes_same_hash(self) -> None:
        self.assertEqual(frame_hash(b"abc"), frame_hash(b"abc"))

    def test_different_bytes_different_hash(self) -> None:
        self.assertNotEqual(frame_hash(b"abc"), frame_hash(b"abd"))


class ScreenshotServiceTests(unittest.TestCase):
    def test_capture_returns_frame_and_hash(self) -> None:
        adb = FakeAdb(frames=[b"frame1", b"frame2"])
        svc = ScreenshotService(adb)
        d1, h1 = svc.capture()
        d2, h2 = svc.capture()
        self.assertEqual(d1, b"frame1")
        self.assertEqual(d2, b"frame2")
        self.assertNotEqual(h1, h2)

    def test_capture_quiesced_returns_stable_frame(self) -> None:
        # Three distinct frames, then repeats. Quiesce should settle on
        # the final one once two successive captures return the same bytes.
        adb = FakeAdb(frames=[b"a", b"b", b"c", b"c", b"c"])
        svc = ScreenshotService(adb, quiesce_max_wait_s=1.0, quiesce_poll_s=0.0)
        sleeps: list[float] = []
        _, h = svc.capture_quiesced(sleeper=lambda s: sleeps.append(s))
        self.assertEqual(h, frame_hash(b"c"))

    def test_capture_quiesced_returns_last_on_timeout(self) -> None:
        # Every capture differs by running index. We pass a sleeper that
        # advances time past the deadline, so quiesce gives up and returns.
        # Simulate by using a very small wait and real time.
        counter = {"n": 0}

        class ChangingAdb(FakeAdb):
            def screencap(self) -> bytes:
                counter["n"] += 1
                return f"frame{counter['n']}".encode()

        adb = ChangingAdb()
        svc = ScreenshotService(adb, quiesce_max_wait_s=0.0, quiesce_poll_s=0.0)
        _, _ = svc.capture_quiesced(sleeper=lambda s: None)


class ActionExecutorTests(unittest.TestCase):
    def test_swipe_right_uses_screen_relative_coords(self) -> None:
        adb = FakeAdb(screen=(1000, 2000))
        ex = ActionExecutor(adb)
        ex.swipe_right()
        self.assertEqual(len(adb.actions), 1)
        rec = adb.actions[0]
        self.assertEqual(rec.kind, "swipe")
        self.assertEqual(rec.args["x1"], 200)
        self.assertEqual(rec.args["x2"], 800)
        self.assertEqual(rec.args["y1"], 1000)
        self.assertEqual(rec.args["y2"], 1000)

    def test_swipe_left_is_reverse_of_right(self) -> None:
        adb = FakeAdb(screen=(1000, 2000))
        ex = ActionExecutor(adb)
        ex.swipe_left()
        rec = adb.actions[0]
        self.assertEqual(rec.args["x1"], 800)
        self.assertEqual(rec.args["x2"], 200)

    def test_type_message_calls_adb_type_text(self) -> None:
        adb = FakeAdb()
        ex = ActionExecutor(adb)
        ex.type_message("hello world")
        self.assertEqual(adb.actions[0].kind, "type_text")
        self.assertEqual(adb.actions[0].args["text"], "hello world")

    def test_tap_back_sends_keycode(self) -> None:
        adb = FakeAdb()
        ex = ActionExecutor(adb)
        ex.tap_back()
        self.assertEqual(adb.actions[0].kind, "key_event")
        self.assertEqual(adb.actions[0].args["keycode"], 4)

    def test_execute_dispatch(self) -> None:
        adb = FakeAdb()
        ex = ActionExecutor(adb)
        ex.execute("swipe_right", {})
        ex.execute("noop", {})
        ex.execute("type_message", {"text": "hi"})
        kinds = [a.kind for a in adb.actions]
        self.assertEqual(kinds, ["swipe", "type_text"])

    def test_execute_unknown_raises(self) -> None:
        ex = ActionExecutor(FakeAdb())
        with self.assertRaises(ValueError):
            ex.execute("self_destruct", {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
