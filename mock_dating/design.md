# Design — Vision-first agent (v1)

Detailed design for the recommended architecture from [`architectures.md`](architectures.md).

- [Module boundaries](#module-boundaries)
- [Logical state machine](#logical-state-machine)
- [Storage & event schemas](#storage--event-schemas)
- [Action vocabulary](#action-vocabulary)
- [Prompt templates](#prompt-templates)
- [Run modes](#run-modes)
- [Safe-stop policy](#safe-stop-policy)

---

## Module boundaries

```
mock_dating/agent/
├── main.py                 # entrypoint, run loop
├── config/
│   ├── persona.yaml        # operator persona, tone, goals
│   ├── preferences.yaml    # likes / dislikes / red flags / deal breakers
│   └── runtime.yaml        # mode (auto|approval), tick interval, model, retries
├── harness/
│   ├── adb.py              # exec wrappers around `adb shell`, `screencap`, `input`
│   ├── screenshot.py       # PNG capture + dedup hash + quiesce wait
│   └── actions.py          # fixed gesture vocab: swipe_left, swipe_right, tap_xy, ...
├── vision/
│   ├── client.py           # multimodal LLM client
│   ├── prompt.py           # prompt assembly from templates
│   ├── schema.py           # pydantic models for structured output
│   └── safety.py           # validator + safety gate (ambiguity, retries)
├── scoring/
│   ├── scorer.py           # deterministic compatibility score from preferences.yaml
│   └── features.py         # ProfileFeatures dataclass
├── chat/
│   ├── engine.py           # reply LLM, persona injection, memory load/save
│   └── memory.py           # per-conversation memory store (one file per match_id)
├── audit/
│   ├── logger.py           # writes per-tick directories + events.jsonl
│   ├── replay.py           # offline re-runs from a saved tick
│   └── viewer.py           # simple flipbook over runs/<run_id>/tick_*/
└── ui/
    └── approval.py         # optional minimal operator approval UI (Streamlit / FastAPI+HTMX)
```

### Boundaries (one-line contracts)

| Module | Owns | Knows nothing about |
|---|---|---|
| `harness` | The emulator. PNG bytes in, gestures out. | LLMs, prompts, scoring |
| `vision` | One multimodal call. Image in, validated decision out. | adb, scoring config |
| `scoring` | Deterministic math on a `ProfileFeatures` and a `Preferences`. | LLMs, the emulator |
| `chat` | Reply generation + per-conversation memory. | adb, scoring, vision |
| `audit` | Persistence of every tick + replayability. | Decision-making |
| `ui` | Operator approval, only used in approval mode. | Anything else |
| `main` | The loop. Wires modules together. | Implementation details |

The dependency graph is a DAG: `main` → `{harness, vision, scoring, chat, audit, ui}`. None of those depend on each other.

---

## Logical state machine

Even though A2 lets the LLM classify the screen, the **agent** still runs a small explicit state machine. This is what gives us safe-stops and watchdog timers.

```
                    +--------+
                    |  BOOT  |
                    +---+----+
                        | screen detected
                        v
                  +-----------+
            +---->| OBSERVE   |  capture frame, dedup, send to vision LLM
            |     +-----+-----+
            |           |
            |           v
            |     +-----------+
            |     |  DECIDE   |  validate response, run safety gate
            |     +-----+-----+
            |           |
            |    +------+------+----------+
            |    |             |          |
            |    v             v          v
            |  ACT          AMBIGUOUS  TERMINAL
            |    |             |          |
            |    v             v          v
            |  +----+      +-------+   +------+
            |  |TICK|      | SAFE  |   | DONE |
            |  +-+--+      | STOP  |   +------+
            |    |         +-------+
            +----+
```

States:

- **BOOT** — wait until adb sees a frame
- **OBSERVE** — `screenshot → dedup → quiesce`
- **DECIDE** — `prompt assembly → vision LLM → validate → safety gate`
- **ACT** — execute one action from the fixed vocab
- **AMBIGUOUS** — response failed validation OR safety gate triggered → **safe-stop**
- **TERMINAL** — done condition met (e.g. operator stop, max ticks, end-of-stack)

Transitions are explicit Python — no implicit state hiding in module-level variables.

### Watchdogs

- **Per-tick timeout** — if `OBSERVE → ACT` takes longer than `runtime.tick_timeout_s`, kill the tick and safe-stop
- **No-progress watchdog** — if 3 consecutive ticks produced the same screen hash AND the same action, safe-stop
- **Loop watchdog** — if the same `(screen, action)` pair appears N times in a sliding window, safe-stop

---

## Storage & event schemas

### On-disk layout

```
runs/
  <run_id>/
    config_snapshot.yaml         # persona + preferences + runtime, frozen at run start
    events.jsonl                 # one TickEvent per line
    tick_000000/
      screen.png
      prompt.txt
      response.json              # raw LLM response
      decision.json              # validated Decision
      action.json                # executed Action
      meta.json                  # timings, hashes, retries
    tick_000001/
      ...
    matches/
      <match_id>/
        profile.json             # ProfileSnapshot at match time
        memory.jsonl             # one ChatTurn per line
        chat_000.png
        chat_001.png
        ...
```

### Schemas (pydantic-style)

```python
# vision/schema.py

class ProfileFeatures(BaseModel):
    name: str | None
    age: int | None
    bio: str | None
    location: str | None
    interests: list[str] = []
    occupation: str | None = None
    photo_traits: list[str] = []      # e.g. "outdoors", "with pet", "gym selfie"
    red_flags: list[str] = []         # observed, not configured

class Decision(BaseModel):
    screen: Literal[
        "boot", "discover", "card", "match_popup",
        "chat_list", "chat", "settings", "popup", "unknown"
    ]
    confidence: float                 # 0..1, the LLM's self-rated confidence
    profile: ProfileFeatures | None   # only when screen == "card"
    score: float | None               # 0..1, only when screen == "card"
    score_reason: str | None
    action: Literal[
        "swipe_left", "swipe_right", "tap_chat",
        "type_message", "tap_back", "tap_dismiss", "wait", "noop"
    ]
    action_args: dict = {}            # e.g. {"text": "..."} for type_message
    reasoning: str                    # one-paragraph free-text rationale
    ambiguity: bool = False           # LLM tells us it's unsure
    safe_stop_reason: str | None = None

class TickEvent(BaseModel):
    tick_id: int
    run_id: str
    ts: datetime
    screen_hash: str
    decision: Decision
    action_executed: bool
    latency_ms: int
    llm_call_id: str | None
    retries: int
    safe_stop: bool

class ChatTurn(BaseModel):
    turn_id: int
    match_id: str
    ts: datetime
    role: Literal["them", "us"]
    text: str
    source: Literal["mock_user", "llm", "operator", "approval"]
    llm_call_id: str | None
    approval_state: Literal["n/a", "pending", "approved", "rejected"] = "n/a"

class AuditRecord(BaseModel):
    run_id: str
    config_snapshot_path: str
    events_path: str
    started_ts: datetime
    ended_ts: datetime | None
    stop_reason: str | None
```

### Config schemas

```yaml
# config/preferences.yaml
likes:
  - "dogs"
  - "hiking"
  - "live music"
  - "cooking"
dislikes:
  - "smoking"
  - "club photos only"
red_flags:
  - "negative bio energy"
  - "MLM language"
deal_breakers:
  - "explicit drug references"
weights:
  likes: 1.0
  dislikes: -0.5
  red_flags: -1.0
  deal_breakers: -10.0      # any non-zero overlap → auto-reject
threshold:
  swipe_right_min_score: 0.55
```

```yaml
# config/persona.yaml
display_name: "Alex"
voice:
  tone: "warm, dry, low-effort-but-thoughtful"
  emoji: "rare"
  message_length: "1-2 sentences"
goals:
  - "find shared interests"
  - "propose a low-stakes IRL meet after 5+ exchanges"
hard_rules:
  - "never claim to be a real person if asked directly"
  - "never share contact info"
  - "stay in character but mark this is a mock test if asked"
```

```yaml
# config/runtime.yaml
mode: "auto"               # "auto" | "approval"
tick_interval_s: 2.0
tick_timeout_s: 15
max_ticks: 500
model: "claude-sonnet-4-6"
retries: 1
ambiguity_safe_stop: true
log_level: "INFO"
```

---

## Action vocabulary

The action executor only knows these. The LLM can return nothing else; the validator rejects anything off-list.

| Action | Args | Maps to |
|---|---|---|
| `swipe_left` | none | fixed gesture: drag from `(0.8w, 0.5h) → (0.2w, 0.5h)` |
| `swipe_right` | none | fixed gesture: drag from `(0.2w, 0.5h) → (0.8w, 0.5h)` |
| `tap_chat` | `{match_id?}` | tap on the match in `chat_list`; in v1 the LLM picks the row by index |
| `type_message` | `{text: str}` | `adb shell input text` (escaped) |
| `tap_back` | none | `adb shell input keyevent 4` |
| `tap_dismiss` | none | tap on a center-screen "X" or hardware back |
| `wait` | `{ms: int}` | sleep |
| `noop` | none | do nothing this tick |

In v1 every gesture is **screen-relative** so it survives different emulator resolutions.

---

## Prompt templates

### Master decision prompt (vision)

System prompt:

```
You are an automation agent driving a MOCK Android dating app inside an emulator.
This is a TEST environment. There are NO real users. Your job is to look at one
screenshot and return a single structured decision.

You must:
- Identify the current screen.
- If the screen is a profile card, extract structured features and rate the
  profile against the operator's preferences.
- Choose exactly one action from the allowed vocabulary.
- Be honest about uncertainty. If you are not confident, set `ambiguity: true`
  and choose `action: "noop"`. The harness will safe-stop. Do not guess.

Allowed actions:
  swipe_left, swipe_right, tap_chat, type_message,
  tap_back, tap_dismiss, wait, noop

You must respond with JSON matching this schema (no prose outside JSON):
<<DECISION_SCHEMA>>

Operator persona:
<<PERSONA_YAML>>

Operator preferences:
<<PREFERENCES_YAML>>

Recent context (last 3 actions, oldest first):
<<RECENT_ACTIONS>>
```

User content (per tick):

```
[image: screen.png]

This is tick <<TICK_ID>>. The previous screen hash was <<PREV_HASH>>; the
current screen hash is <<CURR_HASH>>. The two are <<SAME_OR_DIFFERENT>>.

Return one Decision JSON object.
```

### Profile rating sub-prompt (when `screen == "card"`)

The decision schema already covers this — the master prompt asks the model to
fill `profile`, `score`, and `score_reason` whenever `screen == "card"`. We do
not make a second LLM call for rating in v1.

Scoring rule the LLM is told to apply:

```
score_reason MUST cite specific configured likes / dislikes / red flags /
deal breakers that influenced the score. Any deal_breaker overlap forces
score = 0.0 and action = "swipe_left". Otherwise:

  score = clip(
    0.5
    + 0.1 * (#likes_matched)
    - 0.1 * (#dislikes_matched)
    - 0.2 * (#red_flags_matched),
    0.0, 1.0
  )

Then: action = "swipe_right" if score >= preferences.threshold.swipe_right_min_score
      else "swipe_left".
```

In v1 we let the LLM compute and return the score, then `scoring/scorer.py`
**recomputes it deterministically** from the LLM's `profile` features and
*overrides* the LLM's score if they disagree. That gives us:

- LLM does perception (extract features)
- Python does math (score)
- The two are independently auditable

### Chat reply prompt

System prompt:

```
You are <<DISPLAY_NAME>>, the operator persona below, replying in a MOCK
dating app's chat. This is a test environment. The other party is a simulated
user. Stay in character per the persona, follow the hard rules, and respect
the message length limit.

Persona:
<<PERSONA_YAML>>

Goals (optimize toward, do not state explicitly):
<<GOALS>>

Hard rules (never violate):
<<HARD_RULES>>

Conversation memory so far (oldest first):
<<MEMORY>>

Match profile snapshot (from when you matched):
<<PROFILE_JSON>>

Reply with JSON: { "text": "...", "ambiguity": false, "notes": "..." }

If you are uncertain how to reply (e.g. message is offensive, off-topic in a
confusing way, asks for personal info you must not share), set
ambiguity: true and text: "". The harness will safe-stop or escalate to the
operator approval UI.
```

### Match popup handling

The master prompt already covers this: when `screen == "match_popup"` the
allowed actions are `tap_dismiss` (continue swiping) or `tap_chat` (open the
new chat). Per `runtime.yaml` we can default to `tap_chat` so the chat module
gets exercised.

---

## Run modes

### Full-auto mode (`runtime.mode: auto`)

The default in the mock environment. The loop runs unattended:

```
loop:
  observe
  decide
  if ambiguous or safety_gate_failed:
    safe-stop
  act
  log
```

### Approval mode (`runtime.mode: approval`)

Same loop, but **before any `type_message` action is executed**, the action
goes to a pending queue and the loop blocks on operator approval. All other
actions (`swipe_*`, `tap_*`) still run automatically. Why only messages: the
operator cares about message quality, not about every swipe.

```
on type_message:
  push to ApprovalQueue
  emit websocket event to UI
  block (with timeout) until UI emits approve|reject|edit
  if approve: execute as-is
  if edit: execute with edited text
  if reject: skip turn, log, continue
  if timeout: safe-stop
```

The approval UI is intentionally minimal: a single page that shows the latest
screenshot, the conversation memory, the pending message text, and three
buttons. Implementation can be Streamlit or FastAPI + HTMX. It is **not on
the critical path for v1** — auto mode is.

---

## Safe-stop policy

The agent must **never** guess into an irreversible action. Safe-stop is
triggered when **any** of the following hold:

1. LLM response failed schema validation twice in a row
2. LLM returned `ambiguity: true`
3. LLM returned `confidence < runtime.min_confidence` (default 0.5)
4. The chosen action is not in the allowed vocabulary
5. The screen classifier returned `unknown`
6. The same `(screen_hash, action)` pair has appeared N times in a sliding window
7. A tick exceeded `tick_timeout_s`
8. adb returned a non-zero exit code

Safe-stop writes a `STOPPED` marker into `events.jsonl`, dumps the offending
tick, and exits with a non-zero code. It does **not** try to recover. Recovery
is a v2 concern.
