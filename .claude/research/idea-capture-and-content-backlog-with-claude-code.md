# Research: Idea Capture & Content Backlog with Claude Code (Blogger Workflow)

Generated: 2026-05-13
Agents: Opus + Codex (Gemini quota-exhausted)
Scope: How solo bloggers / YouTube micro-creators use Claude Code to capture random ideas, surface them as a PM-style topic backlog, and let an agent enrich a chosen topic (bullets, sources, video transcripts, outline). User context: solo Russian-language YouTube creator (350 subs) with the content-factory repo.

---

## Executive Summary

The 2026 consensus for solo creators is **a file-first markdown vault inside a git repo + Claude Code slash commands + a few targeted MCP servers** (Obsidian, YouTube transcripts, optionally Notion/Linear). The flow is: `diary.md` → `/triage` extracts topics into `backlog.md` (Kanban-style with `status:` frontmatter) → user picks one → `/research-topic <slug>` enriches it with bullets, web sources, YouTube transcripts, and an outline. **Backlog.md** (markdown-native Kanban CLI) is the most-cited tool for the PM-list piece; **MCPVault** or **newtype-01/obsidian-mcp** for vault ops; **TubeMCP** / **hancengiz/youtube-transcript-mcp** for video research. The pitfalls everyone warns about: taxonomy-fetish over shipping, idea graveyards from no triage cadence, AI slop that loses creator voice (needs explicit voice samples in the prompt), and prompt-injection ("lethal trifecta") risk when MCP servers can both read your vault and reach the internet.

---

## Codebase Patterns (What This Repo Already Has)

Quick scan: `content-factory` is currently a **video post-production pipeline only**. There is no idea-management surface yet.

- `.claude/commands/` contains 5 video-pipeline commands (`transcribe.md`, `edit-transcript.md`, `translate.md`, `burn-subs.md`, `postprod.md`). No idea/backlog commands.
- `research/` directory exists with 4 prior research notes (deep research, best practices, CLI tools, ElevenLabs alternatives).
- `.claude/research/` contains 2 research outputs (the one I just wrote on best practices, and an iOS TDD one).
- No `diary.md`, `inbox/`, `ideas/`, or `backlog.md` files.
- No MCP server configured for Obsidian, Notion, Linear, or YouTube transcripts (none in `.claude/settings.json`).

**Implication**: This is greenfield for an idea-management layer. The existing video pipeline gives you the *output* side (turn a topic into a finished video); you need to bolt on the *input* side (capture, triage, enrich).

The repo's conventions to preserve when adding this layer:
- **File-in/file-out, no DB, no daemons** — every existing stage reads a file and writes a file (see prior research doc, sections "Architectural Conventions").
- **Slash command per stage** — keep that grain.
- **Idempotent re-runs** — important here, since `/triage` will run repeatedly over the same `diary.md`.
- **Mock/fixture testing in pure bash** — pattern from `tests/test_translate.sh`.

---

## Expert Approaches (How Giants Do It)

### 1. File-first inbox + agentic processing (the dominant pattern)

This is the pattern Codex flagged as most common in May 2026, and every "second brain with Claude Code" blog post echoes it ([Code With Seb](https://www.codewithseb.com/blog/claude-code-obsidian-second-brain-guide), [MindStudio](https://www.mindstudio.ai/blog/build-ai-second-brain-claude-code-obsidian), [Ali Pilevar / Medium](https://alipilevar.medium.com/how-i-built-an-ai-second-brain-using-claude-code-and-obsidian-b9347ac34a69), [Stefan Imhoff](https://www.stefanimhoff.de/agentic-note-taking-obsidian-claude-code/)):

```
ideas/
  inbox/diary.md          ← low-friction dump, append-only, no schema
  backlog.md              ← AI-extracted topics with status frontmatter
  drafts/                 ← outlines produced by /research-topic
  research/<slug>/        ← per-topic source pack (web links, video transcripts)
  archive/                ← shipped or killed topics
```

The diary is **append-only and schema-free** — anything goes (voice memo transcripts, half-sentences, links). The friction-killer is critical: if capture takes >5 seconds, you stop capturing, and the system dies. Steph Ango's ["file over app"](https://stephango.com/file-over-app) philosophy applies directly: keep the substrate as plain `.md` files you own.

### 2. The PM-list (Backlog.md)

For the "show me a list of topics, let me pick one" piece, the consensus tool is **[Backlog.md](https://github.com/MrLesk/Backlog.md)**: a markdown-native Kanban with a live terminal board (`backlog board`) and a web UI (`backlog browser`). It's git-versioned, AI-agent-aware, and auto-configures Claude Code with workflow instructions ([HN discussion](https://news.ycombinator.com/item?id=44483530), [Stephan Miller's actual use](https://www.stephanmiller.com/vibe-coding-with-backlogmd/)).

Alternative pure-markdown approaches (no extra tool):
- Single `backlog.md` with `## Inbox / ## Researching / ## Drafting / ## Shipped` sections.
- One file per topic in `topics/<slug>.md` with YAML frontmatter `status: inbox | researching | drafting | shipped`. List view = `grep -l "status: inbox" topics/*.md`.

### 3. Research enrichment for a picked topic

The pattern Codex described, with concrete tool plug-ins:

```md
# /research-topic <slug>
1. Read topics/<slug>.md (user's seed)
2. Expand into 10-15 bullet claims/questions (Claude reasoning)
3. Fetch via MCP:
   - Web: 3-5 recent sources (WebSearch or Brave MCP)
   - YouTube: 3 transcripts of relevant videos (TubeMCP / hancengiz/youtube-transcript-mcp)
4. Write:
   - research/<slug>/notes.md      (digested findings)
   - research/<slug>/sources.json  (raw links + metadata)
   - drafts/<slug>-outline.md      (proposed structure)
5. Update topics/<slug>.md: status → drafting
```

**Sub-agent pattern for YouTube research** ([hancengiz/youtube-transcript-mcp CLAUDE_CODE_AGENT_GUIDE](https://github.com/hancengiz/youtube-transcript-mcp/blob/main/CLAUDE_CODE_AGENT_GUIDE.md)): launch a sub-agent per video so each transcript stays in its own context window, and only the summary returns to the main context. Saves tokens and prevents your main session from drowning in 8 × 30-minute transcripts.

### 4. PARA + Zettelkasten as packaging, not religion

Tiago Forte (PARA originator) [argues](https://fortelabs.com/blog/why-para-is-the-key-to-the-ai-era/) that PARA's value in the AI era is **bundling context** — give the agent a Project bundle, not scattered notes. Andy Matuschak warns the [opposite mistake](https://notes.andymatuschak.org/About_these_notes): performative note collection without evolution.

Practical synthesis used by [parazettel.com creator](https://parazettel.com/articles/claude-code-has-second-brain/) and others:
- **Zettelkasten** for *atoms* — small reusable idea notes (`zk/202605131347-russian-monetization.md`)
- **PARA** for *bundles* — `Projects/`, `Areas/`, `Resources/`, `Archive/` folders
- Claude Code operates on bundles (PARA project folder), pulls atoms (zettel links) as needed

### 5. The "voice gate" — don't let AI slop your style

Universally flagged failure: enriched topics come back generic. Fix used by efficient bloggers:
- Maintain `voice-samples.md` (3-5 of your own pieces, raw).
- Every `/research-topic` and `/draft` command prefixes prompts with: *"Match the voice of these samples: @voice-samples.md. Match cadence, vocabulary, length of sentences, what they choose not to say."*
- Human approval gate before publish (Joe Karlsson's [blog skill workflow](https://www.joekarlsson.com/blog/building-a-claude-code-blog-skill-what-i-learned-systematizing-content-creation/) makes this explicit).

### 6. Capture sources beyond manual typing

Efficient bloggers in 2026 plug multiple input streams into the same `inbox/`:
- **Voice memo → transcript** (your existing `/transcribe` works perfectly for this — `transcribe voice-2026-05-13.m4a` → segments append to diary).
- **Email forwarding** → email-to-file (HEY, Forte's Readwise, or plain IMAP → Markdown via cron).
- **Browser → highlight** (Readwise Reader exports to markdown).
- **iOS Shortcut** that appends to `diary.md` over SSH or syncs via iCloud Drive.

For your repo: a `/capture "<text>"` slash command that appends a timestamped block to `ideas/inbox/diary.md` is the 10-minute MVP.

### 7. Reference implementations worth cloning

- **[MrLesk/Backlog.md](https://github.com/MrLesk/Backlog.md)** — the PM-list piece.
- **[eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)** — 32-command cross-CLI skill set for Obsidian, "vault-first research, scheduled agents, write-time AI-first validator." The closest match to the user's full ask.
- **[logicalicy/ai-zettelkasten-lite](https://github.com/logicalicy/ai-zettelkasten-lite)** — minimal Claude Code + Pinecone setup, good starter.
- **[hancengiz/youtube-transcript-mcp](https://github.com/hancengiz/youtube-transcript-mcp)** — best documented YouTube MCP with explicit sub-agent guide.
- **[BlockBenny/tubemcp](https://github.com/BlockBenny/tubemcp)** — TubeMCP with local SQLite cache (avoid re-fetching the same video).
- **[bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault)** — safer Obsidian vault ops (frontmatter-aware).
- **[newtype-01/obsidian-mcp](https://github.com/newtype-01/obsidian-mcp)** — broader vault management.

---

## Pitfalls to Avoid

### Industry-wide

1. **Taxonomy fetish over shipping.** Spending 3 weeks building the perfect note system instead of writing. Forte: PKM is for shipping, not for performing organization.
2. **No triage cadence.** Inbox grows, never gets processed, becomes a graveyard. Fix: a recurring `/triage` (daily or twice-weekly), not "when I feel like it."
3. **AI slop in your voice.** Enrichment produces fluent generic prose. Fix: voice-samples in every prompt + human approval gate.
4. **Context sprawl.** Claude's `MEMORY.md` auto-loads but truncates after ~200 lines. Don't dump your entire vault into memory; keep memory as pointers, load on demand.
5. **Lethal trifecta** (Simon Willison's [warning](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)): private vault access + untrusted input (web pages, transcripts) + outbound tool use = prompt-injection vector. The risk: a malicious YouTube transcript instructs the agent to exfiltrate `diary.md`. Mitigations: separate "trusted" and "untrusted" content into different folders; the agent reads untrusted content but writes only to a sandboxed location; never let untrusted content reach an outbound tool in the same session.
6. **Locking knowledge into Notion/app-only systems.** Hard to version, hard to grep, hard to feed to local agents. File-over-app wins for solo creators.
7. **Over-automating triage.** If the agent auto-promotes topics from inbox → backlog → drafting without you, you lose editorial taste. Keep the *picking* manual; automate the *enriching*.

### Repo-specific risks

- **No voice samples yet.** The content-factory repo has zero `voice-samples.md` or equivalent. Without that, any drafting command will produce generic output.
- **Russian-language quirks.** Whisper/Gemini transcription quality is strong for RU, but YouTube transcripts via MCP often default to auto-translated English. Confirm the transcript MCP supports `language=ru` (TubeMCP does; hancengiz's supports language fallback).
- **No MCP config.** `.claude/settings.json` is empty re: MCP. Adding 3 servers (vault, YouTube, web) is fine; adding 10 is the path to the lethal trifecta.

---

## Recommended Approach (1-day MVP, then iterate)

In priority order. Designed to fit the repo's existing CLI-native, file-in/file-out conventions.

### Stage 0 — Folder skeleton (5 min)

```
content-factory/
  ideas/
    inbox/diary.md          # append-only, schema-free
    topics/                 # one .md per topic, frontmatter status
    voice-samples.md        # 3-5 of your raw videos' transcripts
  research/                 # already exists; per-topic subfolders go here
  drafts/                   # new — outlines & first drafts
```

### Stage 1 — `/capture` command (10 min, today)

Append timestamped block to `ideas/inbox/diary.md`. Zero schema.

```md
<!-- .claude/commands/capture.md -->
---
description: Append a raw idea to the diary inbox
---
Append the following to ideas/inbox/diary.md with timestamp:

## 2026-05-13 14:32
$ARGUMENTS

(use Write tool with append mode, or read+write)
```

Bonus: bind a global iOS Shortcut or hotkey that runs `claude -p "/capture <text>"` so capture happens from anywhere.

### Stage 2 — `/triage` command (30 min)

Reads `ideas/inbox/diary.md`, extracts distinct topic ideas, writes/updates `ideas/topics/<slug>.md` files with frontmatter:

```yaml
---
status: inbox
created: 2026-05-13
source: diary
sketch: "Russian YouTube monetization without YPP"
votes: 0
---
# Original snippets
- 2026-05-13 14:32 — "what if I make a video about Boosty vs Patreon for RU creators"
- 2026-05-13 18:01 — "Igor monetization 350 subs question"
```

After triage, the diary lines that were absorbed get tagged `<!-- triaged 2026-05-13 -->` rather than deleted (preserves audit trail). Run weekly or on-demand.

### Stage 3 — `/backlog` command (10 min) — your PM-list

Either install Backlog.md (`brew install backlog-md` or via npm), or implement as a one-liner that prints all `topics/*.md` grouped by `status:`. The Backlog.md tool is recommended because it gives you the terminal Kanban + web UI for free.

```bash
backlog board   # live terminal kanban
backlog browser # web UI on localhost
```

Tasks/topics already live in markdown; Backlog.md just visualizes.

### Stage 4 — `/research-topic <slug>` (1-2 hours)

The enrichment command. Pseudocode:

```md
<!-- .claude/commands/research-topic.md -->
---
description: Enrich a backlog topic with bullets, sources, video transcripts, outline
---
Given the topic file: ideas/topics/$ARGUMENTS.md

1. Read it. Note the sketch and any snippets.
2. Expand into 10-15 specific claims / questions / angles.
3. Use WebSearch for 3-5 recent sources. Save URLs and 1-line summaries to research/$ARGUMENTS/sources.md.
4. Use YouTube transcript MCP (TubeMCP) to fetch transcripts of 3 relevant videos. Save raw transcripts to research/$ARGUMENTS/videos/. Summarize each in research/$ARGUMENTS/notes.md.
5. Match the voice of @ideas/voice-samples.md. Draft an outline in drafts/$ARGUMENTS-outline.md.
6. Update ideas/topics/$ARGUMENTS.md: set status: drafting, append a "## Research summary" section linking to the new artifacts.
```

This single command is the highest-leverage piece. It takes ~3 minutes of Claude time and replaces 1-2 hours of manual research.

### Stage 5 — MCP servers (30 min)

Install only what you need:

```bash
# YouTube transcripts (try one, not both)
claude mcp add tubemcp -- npx tubemcp
# or
claude mcp add youtube-transcript -- npx -y @hancengiz/youtube-transcript-mcp

# Obsidian-style vault ops (only if you actually use Obsidian; otherwise skip — your repo IS the vault)
# claude mcp add mcpvault -- npx mcpvault

# Notion / Linear ONLY if you have collaborators or want mobile access
# claude mcp add --transport http notion https://mcp.notion.com/mcp
```

**Skip Obsidian MCP if you're not using Obsidian.** The content-factory repo is already a folder of markdown files — Claude Code can read/write it natively without an MCP layer.

### Stage 6 — Voice samples (15 min)

Drop 3-5 of your existing video transcripts into `ideas/voice-samples.md`. Mark the best paragraphs with `<!-- VOICE: prefer this rhythm -->`. Every research/draft command prefixes prompts with this file.

### Stage 7 — Weekly triage cadence (the discipline part)

Calendar: Sunday 10:00, 30 min. Run `/triage`, run `backlog board`, pick 1 topic for the week, run `/research-topic <slug>`. The Master Loop in `research/content-factory-best-practices.md` already specifies 1 video/week — this slots in front of it.

---

## Decision Matrix (when to use what)

| Need | Tool / Pattern |
|------|----------------|
| Low-friction capture | `/capture` slash command → `ideas/inbox/diary.md` |
| PM-style topic list | Backlog.md (terminal Kanban) or `grep -l "status: inbox"` |
| Extract topics from diary | `/triage` slash command |
| Enrich a topic | `/research-topic <slug>` slash command + WebSearch + YouTube MCP |
| Find relevant videos | TubeMCP or hancengiz/youtube-transcript-mcp, called in sub-agent |
| Match your voice | `ideas/voice-samples.md` referenced in every prompt |
| Mobile capture | iOS Shortcut → `claude -p "/capture <text>"` over SSH, or sync diary.md via iCloud |
| Cross-device PM view | Backlog.md `browser` UI, accessed via tailscale/ngrok |
| Use Notion (only if you must) | Notion MCP — but expect drift between repo and Notion |
| Use Obsidian (only if you must) | newtype-01/obsidian-mcp OR just point Obsidian at the repo folder (Obsidian = folder viewer) |

---

## Sources

### Codebase Files
- `/Users/elpinguino/dev_local/content-factory/.claude/commands/` — existing video-pipeline commands (no idea-mgmt yet)
- `/Users/elpinguino/dev_local/content-factory/research/content-factory-best-practices.md` — "Master Loop": 1 video/week → 8 derivatives
- `/Users/elpinguino/dev_local/content-factory/.claude/research/best-practices-of-content-pipeline-with-claude.md` — prior research on this repo's conventions (file-in/out, slash command per stage)

### Web Sources — Patterns & Workflows
- [Obsidian + Claude Code second brain — Code With Seb](https://www.codewithseb.com/blog/claude-code-obsidian-second-brain-guide) — canonical guide
- [AI Second Brain with Claude Code + Obsidian — MindStudio](https://www.mindstudio.ai/blog/build-ai-second-brain-claude-code-obsidian) — workflow stages
- [How I Built My Second Brain with Obsidian + Claude Code — Evgeni Rusev / Medium](https://medium.com/@evgeni.n.rusev/how-i-built-my-second-brain-with-obsidian-claude-code-9fb54b7665ca)
- [Agentic Note-Taking with Claude Code — Stefan Imhoff](https://www.stefanimhoff.de/agentic-note-taking-obsidian-claude-code/) — inbox-processing routine
- [AI-Powered Zettelkasten — Code With Seb](https://www.codewithseb.com/blog/ai-zettelkasten-obsidian-claude-knowledge-graph) — atoms + bundles
- [My Claude Code Now Has Its Own Second Brain — PARAZETTEL](https://parazettel.com/articles/claude-code-has-second-brain/) — PARA × Zettelkasten synthesis
- [Joe Karlsson — Building a Claude Code Blog Skill](https://www.joekarlsson.com/blog/building-a-claude-code-blog-skill-what-i-learned-systematizing-content-creation/) — explicit gates pattern
- [Stephan Miller — Vibe Coding with Backlog.md](https://www.stephanmiller.com/vibe-coding-with-backlogmd/) — actual blogger workflow

### Web Sources — Tools
- [MrLesk/Backlog.md](https://github.com/MrLesk/Backlog.md) — markdown-native Kanban for AI agents
- [Backlog.md on HN](https://news.ycombinator.com/item?id=44483530) — discussion
- [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) — 32 commands, vault-first research, scheduled agents
- [logicalicy/ai-zettelkasten-lite](https://github.com/logicalicy/ai-zettelkasten-lite) — minimal starter
- [hancengiz/youtube-transcript-mcp](https://github.com/hancengiz/youtube-transcript-mcp) — best-documented YouTube MCP
- [hancengiz CLAUDE_CODE_AGENT_GUIDE](https://github.com/hancengiz/youtube-transcript-mcp/blob/main/CLAUDE_CODE_AGENT_GUIDE.md) — sub-agent token-saving pattern
- [BlockBenny/tubemcp](https://github.com/BlockBenny/tubemcp) — TubeMCP with SQLite cache
- [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) — safe Obsidian vault ops
- [newtype-01/obsidian-mcp](https://github.com/newtype-01/obsidian-mcp) — broader vault management

### Web Sources — Philosophy & Pitfalls
- [Steph Ango — File Over App](https://stephango.com/file-over-app) — durable substrate philosophy
- [Andy Matuschak — About these notes](https://notes.andymatuschak.org/About_these_notes) — evolution > collection
- [Tiago Forte — PARA in the AI Era](https://fortelabs.com/blog/why-para-is-the-key-to-the-ai-era/) — bundles as context units
- [Simon Willison — Lethal Trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) — prompt-injection vector
- [Simon Willison — LLM coding workflow](https://simonwillison.net/2025/Mar/11/using-llms-for-code/) — verification discipline
- [Andrej Karpathy — Sequoia Ascent 2026 summary](https://karpathy.bearblog.dev/sequoia-ascent-2026/) — agentic engineering framing
- [Claude Code slash commands docs](https://docs.claude.com/en/docs/claude-code/slash-commands)
- [Claude Code hooks guide](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- [Notion MCP overview](https://developers.notion.com/guides/mcp/overview)
- [Linear MCP docs](https://linear.app/docs/mcp)

### Agent Contributions
- Opus: codebase scan, WebSearch (4 queries), consolidation, MVP design
- Codex (gpt-5.3-codex, high reasoning): expert-attributed recommendations, tool inventory, primary-source URLs
- Gemini: attempted, quota-exhausted (no output)
