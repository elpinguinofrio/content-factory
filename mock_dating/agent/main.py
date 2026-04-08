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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ._util import utcnow_iso
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
    anthropic_post,
)
from .vision.prompt import PromptBundle, build_system_prompt, build_user_prompt
from .vision.safety import apply_safety_gate
from .vision.schema import Decision, TickEvent

log = logging.getLogger("mock_dating.main")


@dataclass
class LoopResult:
    run_id: str
    ticks: int
    stop_reason: str


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
        self._system_prompt = build_system_prompt(self.config)

    # ------------------------------------------------------------------
    # Watchdogs
    # ------------------------------------------------------------------

    def _check_loop(self, history: deque[tuple[str, str]]) -> str | None:
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
        tick_count = 0
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

            prompt = PromptBundle(
                system=self._system_prompt,
                user=build_user_prompt(
                    tick_id=tick_id,
                    curr_hash=curr_hash,
                    prev_hash=prev_hash,
                    recent_actions=list(recent_actions),
                ),
                image_bytes=image,
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

            decision, _ = override_decision(decision, self.config.preferences)

            gate = apply_safety_gate(decision, self.config.runtime)
            will_execute = gate.allow
            decision = gate.decision
            safe_stop = not will_execute
            safe_stop_reason = gate.reason

            if will_execute and decision.action == "type_message":
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
                        decision = replace(
                            decision,
                            action_args={**decision.action_args, "text": reply.turn.text},
                        )
                        self.chat_memory.append(reply.turn)

            try:
                if will_execute:
                    self.actions.execute(decision.action, decision.action_args)
            except Exception as e:  # noqa: BLE001 - boundary
                will_execute = False
                safe_stop = True
                safe_stop_reason = f"action executor error: {e}"

            latency_ms = int((time.monotonic() - t0) * 1000)

            event = TickEvent(
                tick_id=tick_id,
                run_id=self.audit.run_id,
                ts=utcnow_iso(),
                screen_hash=curr_hash,
                decision=decision,
                action_executed=will_execute,
                latency_ms=latency_ms,
                llm_call_id=call_id,
                retries=retries,
                safe_stop=safe_stop,
                safe_stop_reason=safe_stop_reason,
            )
            self.audit.write_tick(
                event,
                prompt=prompt,
                image=image,
                raw_response=raw_response,
            )
            tick_count += 1

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
            ticks=tick_count,
            stop_reason=stop_reason,
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


@dataclass
class AnthropicChatClient:
    api_key: str
    model: str
    max_tokens: int = 512
    timeout_s: float = 30.0

    def reply(self, system: str, last_their_message: str) -> dict:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
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
        return anthropic_post(self.api_key, body, self.timeout_s)


def _build_chat_client(model: str) -> ChatClient:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.warning("ANTHROPIC_API_KEY not set; using FakeChatClient")
        return FakeChatClient()
    return AnthropicChatClient(api_key=key, model=model)


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
