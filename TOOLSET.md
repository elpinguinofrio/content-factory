# Toolset Decision — Best-in-Class Video Post-Production with Claude Code

Decision doc, not research. Claims from training knowledge are marked **[verify]**.

## Verdict

Hybrid setup. Keep the terminal (ffmpeg/whisper) pipeline as the deterministic batch core. Add a DaVinci Resolve MCP for interactive finishing (timeline, color, titles, renders). Do not replace the terminal pipeline with Resolve — they serve different halves of the work.

## What to do, in order

1. **Commit the untracked skills** — `/translate`, `/burn-subs` and their scripts exist only on disk. Lose the machine, lose the work.
2. **Productize denoise** — `denoise-work/COMPARISON.md` already picked a winner (DeepFilterNet variant). Turn it into `scripts/denoise.sh` + `/denoise`, and insert it into `/postprod` before transcription (cleaner audio → better transcript).
3. **Install a DaVinci Resolve MCP** — e.g. `samuelgursky/davinci-resolve-mcp` **[verify current best option]**. It drives Resolve via its Python scripting API.
   - Caveat: external scripting has historically required a **Resolve Studio** license; the free tier restricts it **[verify against your installed version]**.
   - Use it for: assembling keep-ranges onto a real timeline (instead of blind ffmpeg re-encodes), color, titles, multi-format renders.
4. **Keep the terminal pipeline for batch work** — transcription, translation, sub burning, audio normalize, denoise. These are deterministic, scriptable, verifiable with ffprobe, and need no GUI license.
5. **Wire the two together** — `/postprod` gains a fork at the assemble step: `--engine ffmpeg` (current, headless, frame-accurate) or `--engine resolve` (MCP, editable timeline you can touch up by hand afterwards).

## Rule of thumb: which engine when

| Task | Engine |
|---|---|
| Transcribe / translate / burn subs / denoise / normalize | Terminal (ffmpeg + whisper) |
| Rough cut you will never touch again | Terminal (`assemble.py`) |
| Cut you want to refine by hand, color, titles, multi-platform export | Resolve via MCP |
| Anything unattended / scheduled / cloud | Terminal only — Resolve needs the app running |

## Explicitly not doing

- No cloud editing SaaS (Descript-style) — the local pipeline already covers text-based editing, and the repo research favored owning the pipeline.
- No ffmpeg MCP server — Bash + ffmpeg is already the better interface for Claude Code.
