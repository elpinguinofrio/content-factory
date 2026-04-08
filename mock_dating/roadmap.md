# Roadmap — test strategy + staged implementation + optimization

This document covers:

- [Test strategy](#test-strategy)
- [Staged implementation roadmap (v1)](#staged-implementation-roadmap-v1)
- [Optimization roadmap (v1 → v2 → v3)](#optimization-roadmap-v1--v2--v3)
- [Definition of done per stage](#definition-of-done-per-stage)

---

## Test strategy

The agent has three layers, each tested independently before integration.

### Layer 1 — harness tests (no LLM)

Pure mechanical tests against `harness/`:

- `screencap` returns a non-empty PNG
- `dedup` returns the same hash for the same frame
- Each fixed gesture (`swipe_left`, `swipe_right`, `tap_back`, ...) produces the expected emulator response on a known fixture screen
- `quiesce` waits at most N ms when the frame is changing

These run against a real emulator with a **scripted mock app fixture** (a hand-built APK or a stub Activity that just shows known screens on demand). No LLM, no scoring, no audit. Just adb plumbing.

### Layer 2 — vision-decision tests (LLM, but offline)

Take a curated set of **golden screenshots** from each screen type and pin the expected `Decision` shape:

```
tests/golden/
  card_strong_match.png         → expect screen=card, action=swipe_right
  card_obvious_reject.png       → expect screen=card, action=swipe_left
  card_dealbreaker.png          → expect score=0.0, action=swipe_left
  match_popup.png               → expect screen=match_popup
  chat_polite_question.png      → expect screen=chat, action=type_message
  chat_offensive.png            → expect screen=chat, ambiguity=true
  unknown_loading_overlay.png   → expect screen=unknown OR ambiguity=true
```

What the test asserts:

- The schema validates
- `screen` matches
- `action` is in an allowed set per fixture
- For card fixtures: `profile.name`, `profile.age`, and at least one `interest` are extracted
- For ambiguous fixtures: `ambiguity == true` AND `action == "noop"`

These tests do **not** assert exact text — they assert structure and category.

### Layer 3 — scorer tests (no LLM, no emulator)

Pure unit tests on `scoring/scorer.py`:

- Empty profile → `score == 0.5`
- One like match → `score > 0.5`
- One deal breaker → `score == 0.0` regardless of likes
- Threshold behaviour around `swipe_right_min_score`
- Determinism: same `ProfileFeatures` always produces the same score

### Layer 4 — chat-engine tests (LLM, offline)

Replay-based tests on `chat/engine.py`:

```
tests/chats/
  opener_after_match.jsonl
  asks_for_phone.jsonl          → expect ambiguity OR a refusal
  offensive_message.jsonl       → expect ambiguity (safe-stop)
  long_running_thread_15.jsonl  → expect persona consistency across turns
```

Asserts: persona tone, hard-rules respected, message length within bound, memory threading.

### Layer 5 — end-to-end smoke (real emulator + real LLM)

A single scripted run against the mock app fixture:

1. Boot
2. Process 5 cards (mix of accept / reject)
3. Trigger 1 simulated match
4. Send 1 reply
5. Verify `runs/<run_id>/events.jsonl` has the expected sequence
6. Verify `audit/replay.py` can reproduce the run from the event log

Runs in CI nightly, not on every commit (because it costs tokens).

### Replay tests

Every recorded run is itself a regression test. `audit/replay.py` re-runs each saved tick against the saved screenshot and asserts the new `Decision` is **structurally compatible** with the old one (same `screen`, same `action`, score within ±0.1). This catches model drift over time.

---

## Staged implementation roadmap (v1)

The order is chosen so the agent is **runnable end-to-end as early as possible**, then progressively de-risked. Every stage produces something you can actually demo.

### Stage 0 — Setup (no agent code yet)

- Decide on the mock app's screens; sketch them on paper
- Build / acquire the mock APK with at least: `discover`, `card`, `match_popup`, `chat_list`, `chat`
- Get `adb` working against the emulator from the Mac
- Write a one-liner shell script that screenshots the emulator into a file

**Done when**: `adb exec-out screencap -p > frame.png` produces a usable image.

### Stage 1 — Harness skeleton

- `harness/adb.py`, `harness/screenshot.py`, `harness/actions.py`
- Manual smoke: open a Python REPL, call `swipe_right()`, watch the emulator respond
- Layer 1 tests pass

**Done when**: a Python script can swipe through 5 cards in the mock app via the action vocab.

### Stage 2 — One-shot vision call

- `vision/client.py`, `vision/schema.py`, `vision/prompt.py`
- Hard-code the persona + preferences (don't bother with YAML loaders yet)
- Send `frame.png` + the master prompt to Claude
- Print the validated `Decision`

**Done when**: you can run `python -m mock_dating.vision.client frame.png` and get a structured `Decision` printed to stdout.

### Stage 3 — Closed loop (auto mode, no chat)

- `main.py` wires `harness → vision → harness`
- Loop: screenshot → decide → act → sleep → repeat
- Hard-stop after `max_ticks` or on safe-stop
- Ambiguity / validation failures → safe-stop, no recovery

**Done when**: the agent swipes through 20 cards autonomously without intervention. Every tick has a folder on disk.

### Stage 4 — Audit + replay

- `audit/logger.py` writes per-tick directories + `events.jsonl`
- `audit/replay.py` consumes a saved tick and re-runs the LLM call against the saved image
- `audit/viewer.py` is a 30-line script that opens `tick_*/screen.png` in order

**Done when**: you can run `python -m mock_dating.audit.replay runs/<id>/tick_000007` and get the same (or structurally same) decision.

### Stage 5 — Deterministic scoring override

- `scoring/scorer.py` reads `preferences.yaml`
- After the LLM returns a `Decision`, recompute the score from the LLM's `ProfileFeatures` deterministically
- If the deterministic score disagrees with the LLM's, **the deterministic score wins** and is the one that drives the action
- Both scores are logged for audit

**Done when**: changing `preferences.yaml` measurably changes which cards get swiped right, with no LLM prompt change.

### Stage 6 — Match → chat path

- Detect `match_popup` → `tap_chat`
- Detect `chat` screen → invoke `chat/engine.py`
- `chat/memory.py` writes one `ChatTurn` per line into `runs/<run_id>/matches/<match_id>/memory.jsonl`
- After typing one message, return to `discover`

**Done when**: a simulated match → the agent opens the chat → sends one persona-consistent reply → goes back → continues swiping.

### Stage 7 — Multi-turn chat memory

- On entering a chat, load existing memory if `match_id` is known
- After each reply, append to memory
- Persona stays consistent across at least 5 turns

**Done when**: replaying the same match twice gives consistent persona behavior across turns.

### Stage 8 — Approval mode (optional, parallelizable)

- `ui/approval.py` minimal page (Streamlit is fine)
- `runtime.mode: approval` puts `type_message` actions on a queue
- Approve / edit / reject buttons
- Timeout → safe-stop

**Done when**: an operator can sit in front of the UI and approve/edit/reject every outgoing message in real time.

### Stage 9 — Watchdogs + safe-stop hardening

- Per-tick timeout
- No-progress watchdog
- Loop watchdog (sliding window)
- Safe-stop reason recorded into `events.jsonl`

**Done when**: deliberately breaking the mock app (freezing it on a popup) causes the agent to safe-stop within 3 ticks instead of looping forever.

### Stage 10 — End-to-end test runs

- 50-card session, audit log inspected
- 5-match, 5-conversation session
- Replay regression on a saved run

**Done when**: v1 runs cleanly to completion on at least 3 distinct sessions and the audit logs make sense to someone who wasn't there.

---

## Optimization roadmap (v1 → v2 → v3)

The path is **vision-first → hybrid**. Each step replaces a vision call with a deterministic alternative *only after* v1 is stable, and *only* for the highest-frequency / lowest-judgment screens.

### v1 — vision-first, expensive but simple

- Every tick is a multimodal LLM call
- Every chat reply is an LLM call
- Cost: ~$0.01–0.03 per tick
- This is the baseline. Get it working first.

### v2 — cheap screen classifier in front of vision

Add a fast pre-classifier that runs **before** the vision call:

- Perceptual hash of the current frame compared against a library of known screens
- If a match has confidence > 0.95, return that screen and **skip the vision call**
- Else fall through to v1 behavior

What this saves: discover/card screens that look very similar across profiles can often be classified for free. The vision call is still made for the *contents* of the card (because the photo and text vary), but only when you're confident you're on a card screen, you can use a cheaper text-extraction path.

Expected savings: 20–40% of vision calls.

### v2.5 — OCR on text-only regions

For card text (`name`, `age`, `bio`), use on-device OCR (Tesseract) inside a known card region. The vision LLM is then only called for **photo trait extraction**. Bio extraction stops being a vision task.

Expected savings: another 20–30% on top of v2.

### v3 — handler-per-state (the hybrid architecture)

- Promote the logical state machine in `design.md` to a real one with per-state handlers
- `CARD` handler: OCR + region crops + a small vision call **only on the photo**
- `MATCH_POPUP` handler: pixel template match → tap dismiss / chat (no LLM)
- `CHAT_LIST` handler: OCR row text → tap by index (no LLM)
- `CHAT` handler: vision LLM still used, because conversation is judgment

Expected end state: vision LLM only invoked on profile photos (rating) and chat (replies). Most navigation is free.

### v3.5 — selective accessibility tree

If the mock app cooperates and exposes good `resource-id`s on stable widgets (the swipe buttons, the back button, the chat send button), bind those locators directly. **Selective**, not full A1. Use the tree where it's stable; keep vision where it isn't.

### v4 — model tiering

- Use a smaller / cheaper model for the **screen classification** call when the perceptual hash is borderline
- Use the strongest model only for **chat reply generation**, where quality matters
- Different models for different jobs is the last optimization, not the first

### What we never do in this roadmap

- **No premature locator catalog** — we build it only after we know which screens are stable
- **No premature state machine** — we build it after the loop already runs
- **No premature batching / caching** — token cost is secondary
- **No "intelligent recovery"** — safe-stop forever, until v2+ proves it's needed

---

## Definition of done per stage

| Stage | Demo | Tests passing | Safe-stop works |
|---|---|---|---|
| Stage 1 | Manual swipe via REPL | Layer 1 | n/a |
| Stage 2 | One Decision printed | Layer 2 (golden subset) | n/a |
| Stage 3 | 20-card auto run | Layer 1 + 2 | yes |
| Stage 4 | Replay one tick | + replay test | yes |
| Stage 5 | Pref-driven swipes | + Layer 3 | yes |
| Stage 6 | Match → chat → back | + Layer 4 (1 fixture) | yes |
| Stage 7 | 5-turn chat | + Layer 4 (full) | yes |
| Stage 8 | Approval UI | n/a | yes |
| Stage 9 | Frozen app safe-stops in 3 ticks | + watchdog tests | hardened |
| Stage 10 | 3 clean E2E runs | Layer 5 nightly | yes |

v1 is "done" when Stage 10 is signed off. v2 starts only after that.
