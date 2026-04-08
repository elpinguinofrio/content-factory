"""Screenshot capture + dedup + quiesce wait.

We hash the raw PNG bytes. That's good enough to detect "nothing
changed" without pulling in PIL. If the mock app is animating, two
frames will differ even if conceptually the same screen; the quiesce
loop waits a bounded number of ticks for the hash to stabilize.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from .adb import Adb


def frame_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


@dataclass
class ScreenshotService:
    adb: Adb
    quiesce_max_wait_s: float = 1.5
    quiesce_poll_s: float = 0.1

    def capture(self) -> tuple[bytes, str]:
        data = self.adb.screencap()
        return data, frame_hash(data)

    def capture_quiesced(self, sleeper=time.sleep) -> tuple[bytes, str]:
        """Capture until the frame hash stops changing.

        ``sleeper`` is injectable so tests can pass a no-op sleep.
        """
        data, h = self.capture()
        deadline = time.monotonic() + self.quiesce_max_wait_s
        while time.monotonic() < deadline:
            sleeper(self.quiesce_poll_s)
            data2, h2 = self.capture()
            if h2 == h:
                return data2, h2
            data, h = data2, h2
        return data, h
