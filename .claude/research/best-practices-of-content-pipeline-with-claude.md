# Research: Best Practices of Content Pipeline with Claude

Generated: 2026-05-12
Agents: Opus (codebase + WebSearch)
Scope: Video content production pipeline (transcribe → edit → translate → assemble → normalize → burn-subs), Claude Code as orchestrator, micro-creator context (350 subs, Russian-language YouTube).

---

## Executive Summary

The content-factory repo already implements most of the consensus 2026 best practices for an LLM-driven video pipeline: **CLI-native stages, no shared state, slash commands per task, fallback chains, and timestamp invariants enforced by tests**. The gaps versus industry leaders are (a) no evaluation/regression harness for content quality (only mechanical tests exist), (b) no observability across stages, (c) no explicit context-engineering between stages (each stage re-reads the full transcript), and (d) the "Master Loop" research describes 1 video → 8 pieces of derivative content but the pipeline currently stops at 1 normalized video. The recommended next steps focus on closing those four gaps without breaking the elegant no-state design.

---

## Codebase Patterns (How We Do It)

### Pipeline Stages (current)

| # | Stage | Command | Script | Output |
|---|-------|---------|--------|--------|
| 1 | Transcribe | `/transcribe` | `scripts/transcribe.sh` | `<name>.transcript.json`, `<name>.srt` |
| 2 | Edit decisions | `/edit-transcript` | (Claude inline) | `<name>.keep-ranges.json` |
| 3 | Translate | `/translate` | `scripts/translate.sh` | `<name>.<lang>.transcript.json`, `<name>.<lang>.srt` |
| 4 | Assemble | (part of `/postprod`) | `scripts/assemble.py` | `<name>_assembled.mp4` |
| 5 | Normalize | (part of `/postprod`) | `scripts/normalize-audio.sh` | `<name>_normalized.mp4` |
| 6 | Burn subs | `/burn-subs` | `scripts/burn-subs.sh` | `<name>_subbed.mp4` |
| ★ | Orchestrator | `/postprod` | (chains 1-5) | final video |

### Architectural Conventions (with citations)

- **No state retention** — each stage reads input file → writes output file. No DB, no temp folder, no shared config. Files in the same directory as input.
- **Timestamp invariant** — `scripts/translate.sh:185-192` only mutates `text`; `start`/`end` copied byte-for-byte. Enforced by `tests/test_translate.sh:23-27` (`test_translate_preserves_timestamps_exactly`).
- **Fallback chain for transcription** — `scripts/transcribe.sh:35-227` tries Gemini 2.5-flash → whisper-cpp → whisper-ctranslate2. Each tier prints `>> Using <method>` so the user knows what ran.
- **API-key loading** — `scripts/transcribe.sh:20-33` and `scripts/translate.sh:54-68` walk a candidate chain: env var → `../../.env` → `$HOME/dev_local/.env` → `../.env` → `.env`. Mock mode via `TRANSLATE_MOCK_RESPONSE_FILE` lets tests run offline.
- **Frame-accurate assembly** — `scripts/assemble.py:55-81` uses `trim` + `setpts=PTS-STARTPTS` filters; `-pix_fmt yuv420p` for QuickTime compatibility (commit f1ce8c9).
- **SRT path-escaping side-step** — `scripts/burn-subs.sh:50-84` `cd`s into the SRT directory and references it by bare basename, avoiding the ffmpeg `subtitles=` filter's nested-escaping hell.
- **Loudness pipeline** — `scripts/normalize-audio.sh:38-42` chains highpass(80Hz) → presence-EQ(3kHz,+3dB) → compressor(3:1) → `loudnorm=I=-16:TP=-1.5:LRA=11` (EBU R128, YouTube spec).
- **Pure-bash test runner** — `tests/test_translate.sh`, `tests/test_burn_subs.sh` use `mktemp` working dirs and runtime-generated fixtures (1-sec blue MP4, 2-cue SRT). No pytest/jest.

### Existing Research Notes (under `research/` and `.claude/research/`)

- `research/content-factory-deep-research.md` — Russian YouTube monetization reality (YPP suspended → Boosty.to alt), platform mix (TG/VK/Dzen).
- `research/content-factory-best-practices.md` — Master Loop: 1 video/week → 3 short clips → auto-script for TG/VK/Dzen, 5h/week total.
- `research/cli-transcription-text-based-editing.md` — Whisper, Gemini 2.5 flash, Auto-Editor comparison.
- `research/elevenlabs-alternatives.md` — Yandex SpeechKit, Google TTS, Vocos (no ElevenLabs in RU).
- `research/existing-open-source-video-pipelines.md` — (untracked, just-created comparison).

### Constraints

No `CLAUDE.md` in this project root; global rules at `~/.claude/CLAUDE.md` apply (TDD red-phase enforced, no regressions, exact values sacred, verification before "done"). The pipeline already complies with these via the timestamp-invariant test and the bash test harness.

---

## Expert Approaches (How Giants Do It)

### 1. Slash-commands-as-skills, not as imperative scripts

> "If you do something more than once a day, turn it into a skill or command." ([Builder.io](https://www.builder.io/blog/claude-code))

The Claude Code 2026 consensus: a slash command is a **prompt template plus tool grant**, not a shell wrapper. The wrapper-script approach (this repo's current style, e.g. `/translate` → `scripts/translate.sh`) is fine, but the higher-leverage pattern is to write the command's *.md* with the actual prompt body and let Claude itself decide which tool to invoke. That gives Claude room to recover from edge cases (e.g. corrupted input, missing fixture) instead of failing the bash script.

### 2. Three-layer abstraction for video editing

From [MindStudio's Claude Code video pipeline](https://www.mindstudio.ai/blog/automate-video-editing-claude-code) and Mejba Ahmed's [end-to-end automation](https://www.mejba.me/blog/claude-code-video-editing-workflow):

| Layer | Purpose | Tools |
|-------|---------|-------|
| **Semantic** | Transcript-as-timeline; edit by deleting words | Whisper output, Claude's text reasoning |
| **Precision** | Word-level timestamps for frame-accurate cuts | Whisper word_timestamps, ffmpeg trim filter |
| **Mechanical** | Encoding, concat, audio normalization | ffmpeg, ffmpeg-normalize |

This repo already lives in all three layers (transcript JSON / keep-ranges JSON / ffmpeg). The takeaway is to **keep the layers explicit** — don't let semantic decisions (what to cut) leak into mechanical scripts (assemble.py), and don't let mechanical realities (keyframe alignment) corrupt the semantic transcript.

### 3. Defense-in-depth for LLM-generated output

> "Unit tests for prompt templates, offline regression suites for model updates, online guardrails as runtime confidence filters." ([orq.ai](https://orq.ai/blog/llm-orchestration))

Current state: only **mechanical invariants** are tested (timestamps preserved, file exists, duration ≈ input). There are no quality regressions for the LLM stages — if Gemini's `/edit-transcript` model changes behavior, we won't catch a drop in editorial quality.

### 4. Context engineering between stages

The 2026 framing: **context is a managed resource**, not a free input. Each stage should receive *only* what it needs. Today this is fine because every stage is a small CLI; but as you add stages (e.g., "generate Telegram post from transcript"), feed the **edited** transcript + keep-ranges, not the raw transcript — the keep decisions are signal.

### 5. Master-loop content repurposing

From [TrueLancer 2026](https://blog.truelancer.com/ai-creator-economy-brand-content-2026/) and the repo's own `content-factory-best-practices.md`:

- **1 long-form video** → transcript →
  - **3 short clips** (cuts identified via keep-ranges or auto-detected high-energy segments)
  - **Telegram post** (summary in target voice)
  - **VK / Dzen article** (long-form rewrite, SEO keywords)
  - **Translated versions** (already supported via `/translate`)
  - **Quote cards** (single-sentence highlights for IG/X)

The repo has the *engine* but not the *fan-out stages*.

### 6. Reference implementations worth borrowing from

- **[jftuga/transcript-critic](https://github.com/jftuga/transcript-critic)** — Claude Code skill that transcribes with whisper.cpp and produces structured critical analysis (timestamped summaries, fallacies, underdeveloped sections). Similar shape to a future `/critique-transcript` here.
- **[davila7/claude-code-templates whisper skill](https://agentskills.so/skills/davila7-claude-code-templates-whisper)** — Reference for skill-style packaging.
- **MindStudio 8-skills system** — A complete post-prod pipeline using "no application code or interface, only ffmpeg, a local whisper model, and structured instructions Claude Code reads and executes." That's essentially this repo, validated by an external team.

---

## Pitfalls to Avoid

### Common Mistakes (industry)

1. **Hidden state between stages** — putting intermediate results in a DB or daemon. The CLI-native, file-passing design wins because it's debuggable, resumable, and testable. **The repo already avoids this.**
2. **Eager full-context prompting** — sending the entire transcript to every stage. Costs scale linearly; quality often *drops* due to attention dilution. Pass only the relevant slice.
3. **Mocking the LLM in tests** — you'll pass tests while the actual model regresses. Mock the *transport* (TRANSLATE_MOCK_RESPONSE_FILE pattern, already in use) for mechanical tests; run a separate eval suite against the real model on a frozen fixture set for quality regressions.
4. **Letting ffmpeg silently re-encode audio** — concat-demuxer with mismatched audio codecs produces pops. The repo's `assemble.py --fix-audio` flag addresses this; **always set it** when concat-cutting voice tracks.
5. **Hard-coding language assumptions** — Whisper's auto-detect drifts on short clips. The repo passes `--language ru` explicitly in `transcribe.sh`; preserve this discipline as you add languages.
6. **No idempotency on re-runs** — important when a long pipeline fails mid-stage. The repo's `-y` flag and "no pre-existing-output check" pattern gives idempotency for free.
7. **Burn-in subtitles too early** — once burned, you can't translate or restyle. **Keep the SRT as a sibling artifact**, burn only at the end of a per-platform branch (TG-RU, YT-EN, etc.).

### Repo-Specific Risks

- **Mock-mode drift**: `TRANSLATE_MOCK_RESPONSE_FILE` lets `test_translate.sh` run without API. Add a CI guard that *also* runs the test with a real key on a frozen fixture, weekly. Otherwise the mock will diverge from real Gemini output and tests give false confidence.
- **Transcribe fallback silent quality drop**: `transcribe.sh` falls back from Gemini → whisper-cpp without telling the editorial stage. If `/edit-transcript` was tuned on Gemini's output style (which includes filler words like "э, ну, значит"), whisper-cpp output may not. Add a `"source": "gemini" | "whisper-cpp"` field in the transcript JSON so downstream stages can adapt.
- **No quality regression**: a Gemini model update could degrade transcripts overnight. The mechanical tests won't catch it.
- **No fan-out stages**: research/content-factory-best-practices.md describes 1 video → 3 clips → TG/VK/Dzen posts. Pipeline currently stops at 1 video. The leverage is in the fan-out.

---

## Recommended Approach

In priority order, smallest change first:

### 1. Add a `source` provenance field to transcript JSON (1 hour)

`scripts/transcribe.sh` already chooses among Gemini / whisper-cpp / whisper-ctranslate2. Have it write a top-level field:

```json
{ "source": "gemini-2.5-flash", "language": "ru", "segments": [...] }
```

Downstream stages can branch on this. Trivial addition to the existing JSON shape; no test break (the test only checks `segments`).

### 2. Frozen-fixture quality regression test (3 hours)

Create `tests/fixtures/golden/`:
- `60s_clip.mp4` (one canonical input)
- `60s_clip.transcript.golden.json` (last known-good Gemini output)
- `60s_clip.keep-ranges.golden.json` (last known-good editorial output)

Add `tests/test_quality_regression.sh` that runs the *real* pipeline (requires `GEMINI_API_KEY`) and asserts:
- Segment count within ±10% of golden
- ≥90% of keep-range boundaries within 0.5s of golden boundaries
- Total transcript edit-distance from golden ≤ 5%

Run weekly or pre-release, not on every commit. This is your defense against silent model drift.

### 3. Add fan-out stages (1-2 days each, prioritized)

Per `research/content-factory-best-practices.md`:

- **`/extract-clips`** — read transcript + keep-ranges, identify 3 standalone 30-60s segments using Claude reasoning, write `<name>.clips.json` (array of `{start, end, hook, title}`). Then `scripts/assemble.py` can render each.
- **`/draft-tg-post`** — read translated transcript, produce a 500-char Telegram post in the creator's voice. Output: `<name>.tg.md`.
- **`/draft-dzen-article`** — read translated transcript, produce 1500-word SEO-keyword-aware article. Output: `<name>.dzen.md`.

All follow the existing pattern: file-in, file-out, idempotent, no state.

### 4. Provenance log per run (1 hour)

Write `<name>.pipeline.log` at the end of each `/postprod` run:

```
2026-05-12T14:32:11 transcribe gemini-2.5-flash 42 segments 47.3s
2026-05-12T14:32:48 edit-transcript claude-opus-4-7 keep=31/42 cut=11/42
2026-05-12T14:33:12 assemble frame-accurate 38.1s
2026-05-12T14:33:55 normalize loudnorm=-16LUFS
```

Single append-only file per video. Makes debugging multi-stage failures trivial without breaking the no-state design.

### 5. Skill-ify the highest-friction command (later)

Today the `/transcribe` command runs a bash script. The 2026 idiomatic form is a skill: a `.md` file in `.claude/skills/` with YAML frontmatter declaring triggers ("transcribe", "subtitle", "captions"), tool grants, and inline prompt body. The script becomes one of the tools the skill calls, not the only thing it does. Defer until you actually feel friction.

---

## Sources

### Codebase Files
- `/Users/elpinguino/dev_local/content-factory/scripts/transcribe.sh:20-227` — fallback chain, API-key loading, Gemini prompt
- `/Users/elpinguino/dev_local/content-factory/scripts/translate.sh:54-68,185-192` — env loading, timestamp invariant
- `/Users/elpinguino/dev_local/content-factory/scripts/assemble.py:55-81` — frame-accurate trim+setpts filter chain
- `/Users/elpinguino/dev_local/content-factory/scripts/normalize-audio.sh:38-42` — loudness chain (highpass→EQ→compressor→loudnorm)
- `/Users/elpinguino/dev_local/content-factory/scripts/burn-subs.sh:50-84` — SRT path-escape side-step
- `/Users/elpinguino/dev_local/content-factory/tests/test_translate.sh:23-27,58-76` — timestamp-invariant test
- `/Users/elpinguino/dev_local/content-factory/tests/test_burn_subs.sh:47-62` — idempotency, fixture generation
- `/Users/elpinguino/dev_local/content-factory/research/content-factory-best-practices.md` — Master Loop (1→8 repurposing)
- `/Users/elpinguino/dev_local/content-factory/research/content-factory-deep-research.md` — Russian-platform monetization reality

### Web Sources
- [How I Automated Video Editing With Claude Code — Mejba Ahmed](https://www.mejba.me/blog/claude-code-video-editing-workflow) — end-to-end Claude pipeline pattern
- [Automate Video Editing End-to-End With Claude Code — MindStudio](https://www.mindstudio.ai/blog/automate-video-editing-claude-code) — 8-skills no-app-code system
- [transcript-critic — jftuga/GitHub](https://github.com/jftuga/transcript-critic) — whisper.cpp + Claude analysis skill
- [Claude Code skills docs](https://code.claude.com/docs/en/skills) — skills vs slash commands distinction
- [LLM Orchestration 2026 — orq.ai](https://orq.ai/blog/llm-orchestration) — defense-in-depth, eval infrastructure
- [LLM Orchestration in 2026 — Label Your Data](https://labelyourdata.com/articles/llm-fine-tuning/llm-orchestration) — task decomposition, context engineering
- [LLMOps in Production case studies — ZenML](https://www.zenml.io/blog/llmops-in-production-287-more-case-studies-of-what-actually-works) — production LLM patterns
- [AI Creator Economy 2026 — TrueLancer](https://blog.truelancer.com/ai-creator-economy-brand-content-2026/) — 1 idea → N platforms
- [Faceless AI video automation 2026 — flowshorts.app](https://flowshorts.app/blog/how-to-make-faceless-tiktok-videos-ai) — pipeline patterns
- [Claude Code best practices — builder.io](https://www.builder.io/blog/claude-code) — "do it twice → make it a command"
- [Best Claude Code Skills 2026 — Toolradar](https://toolradar.com/blog/best-claude-code-skills-2026) — skills inventory
- [Local Audio Transcription with MLX Whisper — Hylke Rozema](https://www.hylkerozema.nl/2026/02/24/local-audio-transcription-with-mlx-whisper-and-claude-on-apple-silicon/) — Apple Silicon local-whisper pattern

### Agent Contributions
- Opus: codebase exploration (via Explore subagent), WebSearch synthesis, consolidation
