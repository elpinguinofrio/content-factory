# mock_dating

Design notes for an automation agent that drives a **mock Android dating app** running in an emulator on Mac.

> This is a dummy app / testbed. It is **not** a live dating platform and is **not** connected to real users. It exists to test UI automation, ranking logic, and conversation quality in a controlled environment.

## Goals (v1)

In priority order:

1. **Maximum simplicity**
2. **Maximum robustness**
3. **Easy debugging**
4. Token cost is *secondary*

The agent must work end-to-end against the mock app before we start optimizing anything.

## What the agent must do

Functional:

- Detect the current screen / app state
- Extract visible profile text and metadata
- Interpret visible images into structured traits relevant to ranking
- Compute a compatibility score from configurable likes / dislikes / red flags / deal breakers
- Auto-swipe in the mock app
- Detect simulated matches
- Open chats
- Generate replies via LLM, conditioned on user-defined tone and goals
- Maintain per-conversation memory
- Support **two run modes**:
  - **full-auto** (the agent acts on its own — primary mode for the mock environment)
  - **approval** (a minimal operator UI gates messages before they are sent)
- Keep a **full audit trail** for every decision: screenshot, parsed UI state, extracted features, ranking decision, chosen action, and prompt/response traces where useful
- Handle popups, delays, loading states, and unexpected screens
- **Safe-stop on ambiguity** — never guess into a wrong action

Non-functional:

- Robust to moderate UI changes
- Modular boundaries
- Replayable from logs
- Low hidden state
- Deterministic fallbacks where possible
- Easy to optimize later (v1 → v2 → v3)

## Document index

| File | Purpose |
|---|---|
| [`architectures.md`](architectures.md) | Three candidate architectures, side-by-side, with the recommendation for v1 |
| [`design.md`](design.md) | Detailed design of the recommended architecture: module boundaries, state machine, storage / event schemas, prompt templates |
| [`roadmap.md`](roadmap.md) | Test strategy, staged implementation roadmap, and optimization roadmap from expensive/simple v1 to cheaper v2/v3 |

## TL;DR recommendation

**Vision-first agent** for v1. It has the smallest code surface, the fewest assumptions about the mock app's internals, and the best debugging story (screenshot + JSON per tick). Token cost is its weak point, which the user has already deprioritized. The path from v1 → v3 progressively replaces vision calls with deterministic classifiers and handlers, ending close to a hybrid state-machine design. See [`architectures.md`](architectures.md) for the full comparison.

## Implementation

The vision-first agent is implemented in [`agent/`](agent/):

```
agent/
  main.py              # run loop
  config/              # persona.yaml, preferences.yaml, runtime.yaml
  config_loader.py
  harness/             # adb bridge, screenshot service, action executor
  vision/              # schema, prompt, LLM client, safety gate
  scoring/             # deterministic compatibility scorer
  chat/                # reply engine + per-conversation memory
  audit/               # per-tick logger + offline replay
```

Tests live in [`tests/`](tests/) and run with stdlib unittest:

```bash
python3 -m unittest discover -s mock_dating/tests -t .
```

Smoke-run the full pipeline with fakes (no emulator, no API key needed):

```bash
python3 -m mock_dating.agent.main --runs-dir /tmp/mock_runs --fake
```

When run with a real emulator + `ANTHROPIC_API_KEY` set, drop the `--fake` flag and the same code drives `adb` and the Anthropic Messages API.
