"""Fixed gesture vocabulary.

All coordinates are screen-relative so gestures survive different
emulator resolutions. The LLM never picks coordinates directly; it
picks an action name from the canonical ACTIONS list in
``vision.schema``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adb import Adb


KEYCODE_BACK = 4
_DEFAULT_SIZE = (1080, 1920)


@dataclass
class ActionExecutor:
    adb: Adb
    swipe_duration_ms: int = 300
    _size_cache: tuple[int, int] | None = field(default=None, init=False, repr=False)

    def _size(self) -> tuple[int, int]:
        if self._size_cache is None:
            w, h = self.adb.screen_size()
            self._size_cache = (w, h) if w > 0 and h > 0 else _DEFAULT_SIZE
        return self._size_cache

    def swipe_left(self) -> None:
        w, h = self._size()
        self.adb.swipe(
            int(0.8 * w), int(0.5 * h), int(0.2 * w), int(0.5 * h), self.swipe_duration_ms
        )

    def swipe_right(self) -> None:
        w, h = self._size()
        self.adb.swipe(
            int(0.2 * w), int(0.5 * h), int(0.8 * w), int(0.5 * h), self.swipe_duration_ms
        )

    def tap_chat(self, row_index: int = 0) -> None:
        w, h = self._size()
        y = int(0.18 * h) + row_index * int(0.12 * h)
        self.adb.tap(int(0.5 * w), y)

    def type_message(self, text: str) -> None:
        self.adb.type_text(text)

    def tap_back(self) -> None:
        self.adb.key_event(KEYCODE_BACK)

    def tap_dismiss(self) -> None:
        w, h = self._size()
        self.adb.tap(int(0.9 * w), int(0.1 * h))

    def execute(self, action: str, args: dict[str, Any] | None = None) -> None:
        args = args or {}
        if action == "swipe_left":
            self.swipe_left()
        elif action == "swipe_right":
            self.swipe_right()
        elif action == "tap_chat":
            self.tap_chat(int(args.get("row_index", 0)))
        elif action == "type_message":
            self.type_message(str(args.get("text", "")))
        elif action == "tap_back":
            self.tap_back()
        elif action == "tap_dismiss":
            self.tap_dismiss()
        elif action in ("wait", "noop"):
            pass
        else:
            raise ValueError(f"unknown action: {action!r}")
