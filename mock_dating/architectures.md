# Architectures

Three candidate architectures for the mock-dating automation agent, evaluated against the v1 priorities (simplicity, robustness, debuggability; token cost secondary).

- [Architecture 1 — Accessibility / UI-tree first](#architecture-1--accessibility--ui-tree-first)
- [Architecture 2 — Vision-first agent](#architecture-2--vision-first-agent)
- [Architecture 3 — Hybrid deterministic state machine + LLM planner](#architecture-3--hybrid-deterministic-state-machine--llm-planner)
- [Comparison](#comparison)
- [Recommendation](#recommendation)

---

## Architecture 1 — Accessibility / UI-tree first

### High-level overview

Drive the mock app through Android's accessibility tree (UIAutomator2 / Appium). Every screen state is a parsed XML/JSON node tree. The agent identifies elements by `resource-id`, `content-desc`, `text`, and `class`. LLMs are used **only** for interpretation tasks (vision traits, conversation reply) — never for navigation.

### Components

```
+--------------------+      +------------------+      +-------------------+
|  adb bridge (Mac)  |----->|  UIAutomator2    |----->|  Tree parser      |
+--------------------+      |  dump            |      +---------+---------+
                            +------------------+                |
+--------------------+      +------------------+                v
|  Screenshot grab   |----->|  Image cropper   |      +-------------------+
+--------------------+      +--------+---------+      |  Screen classifier|
                                     |                |  (rule-based)     |
                                     v                +---------+---------+
                            +------------------+                |
                            |  Vision LLM      |                v
                            |  (photos only)   |      +-------------------+
                            +--------+---------+      |  Element resolver |
                                     |                +---------+---------+
                                     v                          |
                            +------------------+                v
                            | Profile features |      +-------------------+
                            +--------+---------+      |  Action executor  |
                                     |                +---------+---------+
                                     v                          |
                            +------------------+                |
                            | Compatibility    |<---------------+
                            | scorer (deterministic)
                            +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Conversation LLM |
                            +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Audit logger     |
                            +------------------+
```

### Data flow

```
emulator
  |  adb dump
  v
[ a11y tree XML ] --+-> [ screen classifier ] --> screen_id
                    |
                    +-> [ element resolver ] --> bounds, text
                                                    |
                    +-> [ screenshot ]              |
                            |                       |
                            v                       |
                    [ photo crops ] -> vision LLM   |
                            |                       |
                            v                       |
                       traits ----------------------+
                                                    v
                                           [ scorer (config) ]
                                                    |
                                                    v
                                          decision: swipe L/R | open chat
                                                    |
                                                    v
                                            [ action executor ]
                                                    |
                                                    v
                                            [ audit logger ]
```

### Pros

- **Lowest token cost** — LLM only for photos and chat replies
- Highly deterministic when locators are stable
- Low latency per tick (a11y dump is fast)
- Element-level debugging is concrete: "this `resource-id` was missing"

### Cons

- Requires the mock app to expose **good accessibility metadata**. If the mock uses Compose / Canvas / custom views, the tree may be sparse or empty.
- Brittle to UI changes — locator drift breaks the agent silently
- You must hand-build a per-screen locator catalog
- Most engineering work *before* the agent does anything useful

### Failure modes

- Resource-ids missing or auto-generated → can't locate
- Cards rendered on a Canvas → no nodes to read at all
- Stale tree during animation → race condition / wrong tap
- Multiple matching nodes → ambiguous tap → wrong action
- Off-screen element → bounds invalid → no-op

### Debugging approach

- Save raw a11y XML per tick alongside the screenshot
- Tree-diff between consecutive ticks to see what changed
- Visual overlay tool: render bounding boxes from the tree onto the screenshot
- Replay any decision from the saved tree (no emulator needed)

### Observability / logging

- One JSONL line per tick: `{tick_id, ts, screen_id, tree_hash, action, latency_ms}`
- Element resolution log: `{locator, candidates, chosen, bounds}`
- LLM trace only when invoked (rare → small audit footprint)

### Token cost profile

- **Lowest of the three.** Vision call only on profile photos (or skipped entirely in v1). Chat call only on message turns.
- Order of magnitude: ~$0.01–0.05 per profile reviewed, ~$0.005 per message turn

### Easiest MVP path

1. Wire `adb` + UIAutomator2 from a Python harness
2. Manually catalog ~6 screens and their key locators
3. Hard-code swipe gestures
4. Stub vision (return empty traits) — wire it later
5. Wire the scorer from a YAML config
6. Add the chat loop with a memory file
7. Add a JSONL audit log

---

## Architecture 2 — Vision-first agent

### High-level overview

Treat the emulator as a **black box**. Each tick: take a screenshot, send it to a multimodal LLM along with the operator persona/config, receive a structured decision (`{screen, action, traits, score, reasoning}`). Action execution uses a **fixed gesture vocabulary** (`swipe_left`, `swipe_right`, `tap_chat`, `type_text`, `back`, `noop`) so the model never has to invent screen coordinates.

### Components

```
+--------------------+      +------------------+
|  adb bridge        |----->|  Screenshot      |
|  (Mac → emulator)  |      |  service         |
+--------------------+      +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Quiesce / dedup  |   skip if frame == prev
                            +--------+---------+
                                     |
                                     v
                            +------------------+      +------------------+
                            | Prompt assembly  |<-----| Persona + scoring|
                            +--------+---------+      | config (YAML)    |
                                     |                +------------------+
                                     v
                            +------------------+
                            | Vision LLM call  |  (multimodal, structured output)
                            +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Schema validator |  pydantic
                            +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Safety gate      |  ambiguity => safe-stop
                            +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Action executor  |  fixed gesture vocab
                            +--------+---------+
                                     |
                                     v
                            +------------------+
                            | Audit logger     |  png + prompt + json
                            +------------------+
```

### Data flow

```
emulator
   |  adb screencap
   v
[ PNG frame ]
   |
   v
[ dedup / quiesce wait ]
   |
   v
[ vision LLM call ] <--- [ persona + config + last-action context ]
   |
   v
[ structured response ]
   { screen, action, traits, score, reasoning, confidence }
   |
   v
[ schema validation + safety gate ]
   |
   v
[ action executor ]  -->  emulator
   |
   v
[ audit logger ]
```

### Pros

- **Maximum robustness to UI changes** — the LLM "just sees" the screen
- **Smallest code surface** of the three; trivial onboarding for a new mock screen
- **Best debugging story**: every decision is a self-contained `(screen.png, prompt.txt, response.json)` triple
- No accessibility-tree dependency, no XML parsing, no locator catalog
- Matches v1 priorities exactly: simplicity + reliability over cost
- LLM-heavy by design, which the user explicitly accepted

### Cons

- **Highest token cost** — every tick is a multimodal call
- Latency 1–3s per tick (acceptable for a test harness)
- LLM may hallucinate screen content → mitigated by structured output + confidence threshold + safe-stop
- Not great if the mock app evolves into something where you eventually want sub-100 ms reaction time

### Failure modes

- Ambiguous screen → safe-stop (handled in safety gate)
- LLM returns invalid JSON → schema validation fails → retry once → safe-stop
- LLM returns an action that would be destructive (e.g. tap on settings) → restricted action vocab catches it
- Throttling / network timeout → exponential backoff → safe-stop after N
- Frame not yet quiesced → dedup waits one extra tick

### Debugging approach

- Each tick is a self-contained folder:
  ```
  runs/<run_id>/tick_000123/
      screen.png
      prompt.txt
      response.json
      action.json
      meta.json
  ```
- Replay = re-run the same prompt against the same image (no emulator needed)
- "Time-travel" UI: scroll through tick folders like a flipbook
- Bisect bad runs by jumping to the first non-empty `safe_stop_reason`

### Observability / logging

- One JSONL line per tick in `runs/<run_id>/events.jsonl`
- Per-tick directory with png + prompt + response (above)
- Aggregate counters: tick rate, action distribution, safe-stop count, retry count, validator failures
- Tracing: `run_id → tick_id → llm_call_id` is the canonical chain

### Token cost profile

- **Highest** of the three. Every tick = multimodal call.
- Rough order: $0.01–0.03 per tick (depending on image resolution + model)
- A 50-swipe session ≈ $0.50–$1.50
- A 20-message chat ≈ $0.20–$0.60
- This is fine for v1 — the user explicitly deprioritized cost

### Easiest MVP path

This is the **shortest path to a working agent** of the three:

1. `adb exec-out screencap -p` → PNG bytes
2. Send to Claude with a structured-output schema (see [`design.md`](design.md))
3. Map `response.action` to one of `{swipe_left, swipe_right, tap_chat, type_message, back, noop}`
4. Loop with screenshot dedup + 1–2s sleep
5. Write the tick folder
6. Done. No locator work, no XML parsing, no a11y rabbit hole.

A first end-to-end pass is achievable in a single sitting.

---

## Architecture 3 — Hybrid deterministic state machine + LLM planner

### High-level overview

A formal state machine encodes the known screens of the mock app (`BOOT`, `DISCOVER`, `CARD`, `MATCH_POPUP`, `CHAT_LIST`, `CHAT`, `SETTINGS`, `UNKNOWN`). State **transitions** are deterministic. **Within** each state, an LLM planner makes the *judgment* calls (rate this profile, write this reply) but never the *navigation* calls. Screen detection is hybrid: try a fast classifier first (template match / OCR / a11y heuristic), fall back to vision LLM only on `UNKNOWN`.

### Components

```
+----------------+    +------------------+
| adb bridge     |--->| Frame capture    |   screenshot + (optional) a11y dump
+----------------+    +--------+---------+
                               |
                               v
                      +------------------+
                      | Fast classifier  |   pixel checks, OCR keywords, anchors
                      +--------+---------+
                               |
              confident <------+------> uncertain
                  |                          |
                  v                          v
            screen_id              +------------------+
                  |                | Vision fallback  |  LLM
                  |                | classifier       |
                  |                +--------+---------+
                  |                         |
                  +------------+------------+
                               |
                               v
                      +------------------+
                      | State machine    |
                      | (Python)         |
                      +--------+---------+
                               |
        +------+------+--------+--------+--------+
        |      |      |        |        |        |
        v      v      v        v        v        v
    BOOT  DISCOVER  CARD  MATCH_POPUP  CHAT  UNKNOWN
       handler  handler  handler  handler  handler  handler
                          |        |        |
                          v        v        v
                     [ extract ][ open ][ reply LLM ]
                          |
                          v
                     [ scorer ]
                          |
                          v
                     [ action executor ]
                          |
                          v
                     [ audit logger ]
```

### State machine

```
            +--------+
       +--->|  BOOT  |
       |    +---+----+
       |        |
       |        v
       |   +-----------+
       |   | DISCOVER  |<------+
       |   +-----+-----+       |
       |         |             |
       |         v             |
       |     +-------+         |
       |     | CARD  |--swipe--+
       |     +---+---+
       |         |
       |       match!
       |         v
       |   +-------------+
       |   | MATCH_POPUP |
       |   +------+------+
       |          |
       |       open chat
       |          v
       |     +-------+
       |     | CHAT  |
       |     +---+---+
       |         |
       |      done/back
       |         v
       |   +-----------+
       |   | CHAT_LIST |---back--->  DISCOVER
       |   +-----------+
       |
       |   any unrecognised frame
       |          |
       |          v
       |   +-----------+
       +---|  UNKNOWN  |--recover or safe-stop
           +-----------+
```

### Data flow

```
emulator
   |
   v
[ frame capture ]
   |
   v
[ fast classifier ] --confident--> screen_id
   |
   uncertain
   |
   v
[ vision classifier ] --> screen_id
   |
   v
[ state transition ]
   |
   v
[ state handler ]
   |       |        |
   v       v        v
extract  score   act
   |
   v
[ audit logger ]
```

### Pros

- **Best long-term shape** — pays for itself as deterministic paths replace LLM calls
- Predictable, auditable, and easy to add per-state metrics
- Combines vision robustness with state-machine clarity
- Bugs are contained to the responsible state handler
- Has the highest **eventual** ceiling: this is what v3 should look like

### Cons

- **Most upfront engineering** of the three
- You must know your screens before you start, which is awkward when the mock app is evolving
- More moving parts → more debugging surfaces in v1
- The "fast vs vision" meta-decision is itself a thing you have to test

### Failure modes

- Misclassified screen → wrong handler runs → recoverable via the `UNKNOWN` guard at the next tick
- Fast classifier false-positive → wrong action; mitigate with a confidence threshold and only trust the fast path above e.g. 0.9
- Handler bug → contained to that state, doesn't blow up the whole loop
- State machine deadlock (loops between two states) → watchdog timer → safe-stop
- New screen the catalog doesn't know about → falls into `UNKNOWN` → vision fallback → escalate

### Debugging approach

- State trace log (transitions only) gives a one-line-per-tick story of the whole run
- Per-state debug bundles
- Replay engine consumes the event log and reproduces every decision offline
- "Why am I in `UNKNOWN`?" tooling: dumps the last frame + classifier confidences

### Observability / logging

- Event log entries: `{tick, state_in, state_out, classifier_path, confidence, action, latency_ms}`
- Per-state metrics: time spent, retries, errors
- LLM traces (vision + chat) only where the call was actually made
- Dashboard panels per state

### Token cost profile

- **Middle of the three.** Trends toward Architecture 1 cost as you add deterministic paths.
- v1 cost ≈ 50–70% of vision-first
- After a couple of optimization passes, approaches accessibility-first cost

### Easiest MVP path

This is the **longest** MVP path of the three:

1. Define states + draw the diagram
2. Start with **every** screen classifier returning `UNKNOWN` → escalate to vision (which means v1 looks a lot like Architecture 2 anyway)
3. Implement `CARD` handler first
4. Add `MATCH_POPUP` handler
5. Add `CHAT` handler
6. Add deterministic classifiers for the 3 most common states
7. Add the replay engine

---

## Comparison

| Dimension | A1 a11y/tree | A2 vision-first | A3 hybrid |
|---|---|---|---|
| Time to first useful run | Medium | **Shortest** | Longest |
| Robustness to UI change | Low | **Highest** | High |
| Token cost v1 | **Lowest** | Highest | Medium |
| Determinism | **High** | Medium | High |
| Debug ergonomics | Good | **Best** | Good |
| Engineering surface in v1 | Medium | **Smallest** | Largest |
| Long-term ceiling | Medium | Medium | **Highest** |
| Dependence on the mock app's internals | High | **None** | Medium |
| Matches v1 priorities | OK | **Best** | OK |

---

## Recommendation

**Architecture 2 (vision-first) for v1.** Then incrementally evolve toward Architecture 3 (hybrid) by replacing the most expensive vision calls with deterministic classifiers and handlers as the mock app stabilizes.

Reasoning, mapped against the user's stated priorities:

| Priority | Why A2 wins |
|---|---|
| Maximum simplicity | Smallest code surface; no XML, no locators, no per-screen catalog |
| Maximum robustness | Zero coupling to the mock app's accessibility tree, which may not even exist |
| Easy debugging | Every tick is a `(screen.png, prompt, response)` triple — no archaeology needed |
| Token cost is secondary | A2's only real downside; user explicitly accepted this |
| "Initial implementation can rely heavily on LLMs" | This is literally A2 |
| "Later we can optimize repeated steps with deterministic code" | The v1 → v3 path *is* the migration from A2 to A3 |

The detailed design of the v1 system, the module boundaries, the (logical) state machine, the storage / event schemas, and the prompt templates are in [`design.md`](design.md). The staged implementation roadmap and the optimization roadmap from v1 → v2 → v3 are in [`roadmap.md`](roadmap.md).
