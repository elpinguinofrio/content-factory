"""adb bridge.

Abstract ``Adb`` protocol with two implementations:

- ``RealAdb``: runs ``adb`` as a subprocess. Used at runtime against an
  actual emulator.
- ``FakeAdb``: plays back PNG bytes from an in-memory queue and records
  every action invocation. Used by tests.

The loop code in ``main.py`` takes an ``Adb`` and never looks at
anything else.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol


class Adb(Protocol):
    def screencap(self) -> bytes: ...
    def tap(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None: ...
    def key_event(self, keycode: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def screen_size(self) -> tuple[int, int]: ...


class AdbError(RuntimeError):
    pass


@dataclass
class RealAdb:
    """Subprocess-backed adb. Uses the ``adb`` binary on PATH by default."""

    serial: str | None = None
    binary: str = "adb"
    default_size: tuple[int, int] = (1080, 1920)

    def _cmd(self, *args: str) -> list[str]:
        base = [self.binary]
        if self.serial:
            base += ["-s", self.serial]
        return base + list(args)

    def _run(self, args: list[str], capture: bool = False) -> bytes:
        if shutil.which(self.binary) is None:
            raise AdbError(f"{self.binary!r} not found on PATH")
        try:
            proc = subprocess.run(
                args,
                check=True,
                capture_output=capture,
            )
        except subprocess.CalledProcessError as e:
            raise AdbError(f"adb failed: {args}: {e}") from e
        return proc.stdout if capture else b""

    def screencap(self) -> bytes:
        return self._run(self._cmd("exec-out", "screencap", "-p"), capture=True)

    def tap(self, x: int, y: int) -> None:
        self._run(self._cmd("shell", "input", "tap", str(x), str(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        self._run(
            self._cmd(
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            )
        )

    def key_event(self, keycode: int) -> None:
        self._run(self._cmd("shell", "input", "keyevent", str(keycode)))

    def type_text(self, text: str) -> None:
        # adb's `input text` uses spaces as delimiters; escape them.
        escaped = text.replace(" ", "%s")
        # Single-quote the argument so the shell doesn't re-interpret it.
        self._run(self._cmd("shell", "input", "text", f"'{escaped}'"))

    def screen_size(self) -> tuple[int, int]:
        # Querying wm size is cheap; cache could be added later.
        try:
            out = self._run(self._cmd("shell", "wm", "size"), capture=True)
        except AdbError:
            return self.default_size
        for line in out.decode("utf-8", "replace").splitlines():
            if "Physical size:" in line or "Override size:" in line:
                try:
                    dims = line.split(":", 1)[1].strip()
                    w, h = dims.split("x", 1)
                    return int(w), int(h)
                except Exception:
                    continue
        return self.default_size


@dataclass
class ActionRecord:
    kind: str
    args: dict

    def as_tuple(self) -> tuple:
        return (self.kind, tuple(sorted(self.args.items())))


@dataclass
class FakeAdb:
    """In-memory Adb for tests.

    Serves frames from ``frames`` in order. If ``frames`` is exhausted
    the last frame is returned repeatedly.
    """

    frames: list[bytes] = field(default_factory=list)
    screen: tuple[int, int] = (1080, 1920)
    actions: list[ActionRecord] = field(default_factory=list)
    _idx: int = 0

    def screencap(self) -> bytes:
        if not self.frames:
            return b""
        if self._idx >= len(self.frames):
            return self.frames[-1]
        frame = self.frames[self._idx]
        self._idx += 1
        return frame

    def tap(self, x: int, y: int) -> None:
        self.actions.append(ActionRecord("tap", {"x": x, "y": y}))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        self.actions.append(
            ActionRecord(
                "swipe",
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms},
            )
        )

    def key_event(self, keycode: int) -> None:
        self.actions.append(ActionRecord("key_event", {"keycode": keycode}))

    def type_text(self, text: str) -> None:
        self.actions.append(ActionRecord("type_text", {"text": text}))

    def screen_size(self) -> tuple[int, int]:
        return self.screen
