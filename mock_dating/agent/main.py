"""Run loop for the vision-first mock-dating agent.

This is the only place where everything comes together. The loop is:

    while not done:
        observe()
        decide()
        safety_gate()
        maybe_override_score()   # scorer corrects the LLM on cards
        act()
        log()
        check_watchdogs()

Every branch either advances the tick or safe-stops. No recovery.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audit.logger import AuditLogger
from .chat.engine import ChatClient, FakeChatClient, generate_reply
from .chat.memory import ChatMemory
from .config_loader import Config, load_config
from .harness.actions import ActionExecutor
from .harness.adb import Adb, FakeAdb, RealAdb
from .harness.screenshot import ScreenshotService
from .scoring.scorer import override_decision
from .vision.client import (
    AnthropicVisionClient,
    FakeVisionClient,
    VisionClient,
    VisionClientError,
    VisionResponse,
)
from .vision.prompt import build_decision_prompt
from .vision.safety import apply_safety_gate
from .vision.schema import Decision, TickEvent

log = logging.getLogger("mock_dating.main")


@dataclass
class LoopResult:
    run_id: str
    ticks: int
    stop_reason: str
    events: list[TickEvent] = field(default_factory=list)


@dataclass
class Agent:
    config: Config
    adb: Adb
    vision_client: VisionClient
    chat_client: ChatClient
    audit: AuditLogger
    chat_memory: ChatMemory
    sleeper: Any = time.sleep  # injectable for tests

    def __post_init__(self) -> None:
        self.screenshot = ScreenshotService(
            self.adb,
            quiesce_max_wait_s=self.config.runtime.quiesce_max_wait_s,
            quiesce_poll_s=self.config.runtime.quiesce_poll_s,
        )
        self.actions = ActionExecutor(self.adb)

    # ------------------------------------------------------------------
    # Watchdogs
    # ------------------------------------------------------------------

    def _check_loop(self, history: deque[tuple[str, str]]) -> str | None:
        """Loop watchdog: same exact (screen_hash, action) repeats in a window.

        This catches "the app keeps landing on the same literal screen and
        we keep taking the same action but nothing is moving forward".
        """
        window = self.config.runtime.loop_window
        threshold = self.config.runtime.loop_threshold
        if len(history) < threshold:
            return None
        window_slice = list(history)[-window:]
        last = window_slice[-1]
        count = sum(1 for item in window_slice if item == last)
        if count >= threshold:
            return (
                f"loop watchdog: ({last[0]}, {last[1]}) "
                f"repeated {count}x in last {len(window_slice)} ticks"
            )
        return None

    def _check_no_progress(self, history: deque[tuple[str, str]]) -> str | None:
        """No-progress watchdog: the frame hash has not changed for N ticks.

        Real progress means the mock app rendered a different frame. If the
        hash has been identical for N ticks in a row, the emulator is frozen
        or we're stuck on a popup we can't dismiss.
        """
        n = self.config.runtime.no_progress_window
        if len(history) < n:
            return None
        tail = list(history)[-n:]
        hashes = {item[0] for item in tail}
        if len(hashes) == 1:
            return (
                f"no-progress watchdog: frame hash {tail[-1][0]} unchanged "
                f"for {n} consecutive ticks"
            )
        return None

    # ------------------------------------------------------------------
    # One tick
    # ------------------------------------------------------------------

    def _decide_with_retry(self, prompt) -> tuple[VisionResponse | None, int, str | None]:
        retries = 0
        last_err: str | None = None
        max_retries = self.config.runtime.retries
        while retries <= max_retries:
            try:
                resp = self.vision_client.decide(prompt)
                return resp, retries, None
            except VisionClientError as e:
                last_err = str(e)
                log.warning("vision client error (retry %d): %s", retries, e)
                retries += 1
        return None, retries, last_err

    def run(self) -> LoopResult:
        self.audit.snapshot_config(self.config.snapshot())
        history: deque[tuple[str, str]] = deque(maxlen=max(16, self.config.runtime.loop_window))
        recent_actions: deque[str] = deque(maxlen=3)
        prev_hash: str | None = None
        events: list[TickEvent] = []
        stop_reason = "max_ticks_reached"

        for tick_id in range(self.config.runtime.max_ticks):
            t0 = time.monotonic()
            try:
                image, curr_hash = self.screenshot.capture_quiesced(sleeper=self.sleeper)
            except Exception as e:  # noqa: BLE001 - boundary
                stop_reason = f"screencap failed: {e}"
                self.audit.write_stop_marker(stop_reason)
                break

            if not image:
                stop_reason = "empty screencap"
                self.audit.write_stop_marker(stop_reason)
                break

            prompt = build_decision_prompt(
                config=self.config,
                tick_id=tick_id,
                image=image,
                curr_hash=curr_hash,
                prev_hash=prev_hash,
                recent_actions=list(recent_actions),
            )

            resp, retries, err = self._decide_with_retry(prompt)
            if resp is None:
                decision = Decision(
                    screen="unknown",
                    confidence=0.0,
                    action="noop",
                    reasoning=f"vision client failure: {err}",
                    ambiguity=True,
                    safe_stop_reason=err or "vision failure",
                )
                raw_response: dict = {"error": err}
                call_id = None
            else:
                decision = resp.decision
                raw_response = resp.raw
                call_id = resp.call_id

            # Scorer override happens BEFORE safety gate so the deterministic
            # score contributes to the safety decision (threshold checks etc).
            decision, _ = override_decision(decision, self.config.preferences)

            gate = apply_safety_gate(decision, self.config.runtime)
            will_execute = gate.allow
            decision = gate.decision
            safe_stop = not will_execute
            safe_stop_reason = gate.reason

            # Chat side-effect: if we're in a chat and the action is
            # type_message, replace the LLM's action_args.text with one
            # generated by the chat engine using persistent memory.
            if will_execute and decision.action == "type_message":
                # In v1 we treat each match as a separate memory keyed by a
                # stable pseudo id derived from the current screen hash.
                match_id = f"match_{curr_hash}"
                memory = self.chat_memory.load(match_id)
                try:
                    reply = generate_reply(
                        client=self.chat_client,
                        config=self.config,
                        match_id=match_id,
                        profile=decision.profile,
                        memory=memory,
                        last_their_message=memory[-1].text if memory else "",
                    )
                except Exception as e:  # noqa: BLE001 - boundary
                    will_execute = False
                    safe_stop = True
                    safe_stop_reason = f"chat engine error: {e}"
                else:
                    if reply.ambiguous:
                        will_execute = False
                        safe_stop = True
                        safe_stop_reason = "chat engine ambiguity"
                    else:
                        decision.action_args["text"] = reply.turn.text
                        self.chat_memory.append(reply.turn)

            # Execute the action.
            try:
                if will_execute:
                    self.actions.execute(decision.action, decision.action_args)
            except Exception as e:  # noqa: BLE001 - boundary
                will_execute = False
                safe_stop = True
                safe_stop_reason = f"action executor error: {e}"

            latency_ms = int((time.monotonic() - t0) * 1000)

            event = self.audit.write_tick(
                tick_id=tick_id,
                prompt=prompt,
                image=image,
                raw_response=raw_response,
                decision=decision,
                action_executed=will_execute,
                action_args=decision.action_args,
                latency_ms=latency_ms,
                llm_call_id=call_id,
                retries=retries,
                safe_stop=safe_stop,
                safe_stop_reason=safe_stop_reason,
                screen_hash=curr_hash,
            )
            events.append(event)

            if safe_stop:
                stop_reason = f"safe_stop: {safe_stop_reason}"
                self.audit.write_stop_marker(stop_reason)
                break

            history.append((curr_hash, decision.action))
            recent_actions.append(decision.action)

            loop_reason = self._check_loop(history)
            if loop_reason:
                stop_reason = f"safe_stop: {loop_reason}"
                self.audit.write_stop_marker(stop_reason)
                break
            progress_reason = self._check_no_progress(history)
            if progress_reason:
                stop_reason = f"safe_stop: {progress_reason}"
                self.audit.write_stop_marker(stop_reason)
                break

            prev_hash = curr_hash
            self.sleeper(self.config.runtime.tick_interval_s)

        return LoopResult(
            run_id=self.audit.run_id,
            ticks=len(events),
            stop_reason=stop_reason,
            events=events,
        )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_vision_client(model: str) -> VisionClient:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.warning("ANTHROPIC_API_KEY not set; using FakeVisionClient")
        return FakeVisionClient()
    return AnthropicVisionClient(api_key=key, model=model)


def _build_chat_client(model: str) -> ChatClient:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.warning("ANTHROPIC_API_KEY not set; using FakeChatClient")
        return FakeChatClient()
    # Reuse the vision client's HTTP path via a thin adapter.
    client = AnthropicVisionClient(api_key=key, model=model)

    class _Adapter:
        def reply(self, system: str, last_their_message: str) -> dict:  # noqa: ARG002
            body = {
                "model": model,
                "max_tokens": 512,
                "system": system,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": last_their_message or "(start the conversation)",
                            }
                        ],
                    }
                ],
            }
            return client._post(body)  # noqa: SLF001

    return _Adapter()  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mock-dating vision-first agent")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--fake", action="store_true", help="Use fakes for adb + LLMs (smoke test)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    config = load_config(Path(args.config_dir) if args.config_dir else None)

    adb: Adb
    vision_client: VisionClient
    chat_client: ChatClient
    if args.fake:
        adb = FakeAdb(frames=[b"\x89PNG\r\n\x1a\n" + b"\x00" * 64])
        vision_client = FakeVisionClient()
        chat_client = FakeChatClient()
    else:
        adb = RealAdb()
        vision_client = _build_vision_client(config.runtime.model)
        chat_client = _build_chat_client(config.runtime.model)

    runs_dir = Path(args.runs_dir)
    audit = AuditLogger(root=runs_dir)
    chat_memory = ChatMemory(root=audit.run_dir / "matches")

    agent = Agent(
        config=config,
        adb=adb,
        vision_client=vision_client,
        chat_client=chat_client,
        audit=audit,
        chat_memory=chat_memory,
    )
    result = agent.run()
    log.info(
        "run %s finished: ticks=%d stop_reason=%s",
        result.run_id,
        result.ticks,
        result.stop_reason,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
