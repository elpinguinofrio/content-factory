# Content Factory for a Micro-Creator (350 subs, Russian)

*Research date: 2026-03-03*
*Sources: Web research + Gemini + Codex*

## The Honest Truth About Your Stage

At 350 subscribers you are NOT building a media empire. You are building **trust with a small group**. Everything below is calibrated to that reality.

**What works at your scale:** consistency, direct engagement, repurposing one piece into many.
**What's a waste of time:** viral strategies, complex analytics dashboards, heavy branding, multi-tool tech stacks.

---

## The Master Loop (Your Weekly System)

**One core piece per week. Everything else is derived from it.**

This is the 1-3-5 method (Justin Welsh) adapted to RU platforms:

| Step | What | Time |
|------|------|------|
| 1. Record | 1 video (8-15 min) on a specific problem your audience has | 2h |
| 2. Edit | Cut video + rough-cut 3 short clips (hooks) | 1h |
| 3. Automate | Run script: transcript -> TG post + VK post + clips list | 0.5h |
| 4. Polish & publish | Review drafts, publish to TG/VK/Dzen | 1h |
| 5. Engage | Reply to comments, DMs, collect next topic ideas | 0.5h |
| **Total** | | **~5h/week** |

---

## Platform Strategy for RU Ecosystem

| Platform | Frequency | Role |
|----------|-----------|------|
| **Telegram** | 3-5x/week | Your "living room" — raw thoughts, links, polls, engagement |
| **VK Video** | 1x/week | Discovery engine (algorithmic reach, mirrors YouTube) |
| **YouTube** | 1x/week | Archive for VPN users, long-term SEO |
| **Dzen** | 1-2x/week | Yandex SEO — text articles get indexed fast |
| **VK Clips / Shorts** | 3x/week | Brand awareness from short clips |

Key RU-specific insight: **Telegram doesn't give you random traffic** — it's for nurturing existing followers. VK and Dzen are your discovery channels. Always provide a VK mirror link for people who can't access YouTube.

---

## The Repurposing Pipeline (1 video -> 8+ pieces)

```
1 Video (10 min)
  |
  +-> Transcript (auto-generated)
  |     +-> 1 Telegram long post (key insights, <4096 chars)
  |     +-> 1 VK post (adapted format)
  |     +-> 1 Dzen article (expanded with headers/images)
  |
  +-> 3 Short clips (best hooks/moments)
  |     +-> YouTube Shorts
  |     +-> VK Clips
  |
  +-> 1 Telegram poll (based on video's conclusion)
  +-> 1 Quote card (key takeaway as image)
```

This is Dan Koe's approach: write once, deconstruct everywhere.

---

## What to Focus On vs Ignore

### FOCUS (high ROI at 350 subs)
- **Hook quality** in first 10-20 seconds of every video
- **Consistency** — 1 core piece/week, never skip
- **Comment-to-content loop** — every question becomes next week's topic
- **Direct engagement** — you should know 50+ subscribers by name
- **Ask your audience**: "What's the #1 thing stopping you from [your topic]?"
- **The 4A Framework** (Dickie Bush): every topic written 4 ways — Actionable (how-to), Analytical (why it works), Aspirational (you can do it), Anthropological (why we fail)

### IGNORE (waste of time at this stage)
- Complex multi-tool auto-publishing pipelines
- Analytics dashboards and BI tools
- Heavy branding redesigns
- Trying to go "viral"
- Optimizing thumbnails with A/B testing (you don't have the volume)
- Full Dzen automation (no stable API — use manual or Telegram crosspost bot)

---

## Content Mix Formula

- **70%** bread-and-butter content your audience craves
- **20%** iterations/repurposing into new styles
- **10%** experiments with completely new formats

---

## The "Thinker" Frameworks Applied to Micro-Creators

- **Justin Welsh (The Hybrid):** Solve a specific problem for a specific sub-niche (e.g., "AI for Russian accountants," not just "AI")
- **Dan Koe (You Are the Niche):** Document your journey. At 350 subs, your "process" is more interesting than your "results"
- **Dickie Bush (4A Framework):** Every topic written 4 ways: Actionable, Analytical, Aspirational, Anthropological
- **The "2-Year Test":** Best content comes from solving problems your "past self" had 24 months ago

---

## The Highest-ROI Activity Right Now

**Direct outreach + consultation.** Content at 350 subs is a trust-builder for direct transactions. Turn answers from your audience into a paid micro-product ($10-50) or 1-on-1 consultation. Stop trying to scale. Be **useful to 350 people**.

---

## Russian Ecosystem Specifics

- **VK Video is the new YouTube RU** — due to systemic throttling, VK has near-parity with YouTube in traffic. Mirror content there.
- **Telegram Mini Apps (TMA)** — the future of RU monetization. Consider building a simple TMA hub for resources.
- **Dzen is for Yandex** — writing on Dzen gets you into Yandex search results faster than any other platform.
- **VPN Gate** — always provide a VK/Rutube mirror link in your Telegram channel for people who can't access YouTube.
- **Growth methods for Telegram in 2025**: seeding (via aggregators), native advertising with influencers, and Telegram Ads.
- **Direct deals** with niche channel owners generate the highest engagement.

---

## Automation Tools That Work at Small Scale

| Tool | Purpose | Cost |
|------|---------|------|
| **yt-dlp** | Download audio / extract RU subtitles | Free |
| **Whisper / Yandex SpeechKit** | Transcribe Russian audio | Free / pay-per-use |
| **Claude / GPT API** | Format transcript into platform drafts | ~$0.01-0.10/video |
| **OpusClip / CapCut** | Auto-reframe long video into vertical clips | Free tier available |
| **Descript** | Edit video by editing text transcript | Free tier |
| **Make.com / Zapier** | Connect YouTube RSS -> TG bot auto-draft | Free tier |
| **@zen_sync_bot** | Telegram -> Dzen crosspost | Free |

---

## First Automation Step: `transcript -> draft pack` Script

**What it does:** Takes a YouTube URL, extracts transcript, generates ready-to-publish drafts for Telegram + VK + a clips suggestion list.

### Tech stack
- `yt-dlp` — download audio / extract RU subtitles
- `whisper` or Yandex SpeechKit — transcribe if no subs available
- Claude/GPT API — format transcript into platform-specific drafts
- Output: `telegram_post.md` + `vk_post.md` + `clips.csv` (start, end, hook text)

### Expected output
```
python factory.py https://youtube.com/watch?v=YOUR_VIDEO

Output:
  output/
    transcript_ru.txt
    telegram_post.md    (<=4096 chars, formatted for TG)
    vk_post.md          (VK-optimized)
    clips.csv           (timestamp, hook, reason)
```

### Why this first
- Removes blank-page friction (hardest part of publishing)
- Saves 60-90 minutes per video
- Increases publishing consistency immediately
- Keeps quality control manual where it matters (you still edit the final text)
- No auto-posting risk — just drafts you review

### Build time
4-8 hours for MVP.

### MVP logic
1. Try YouTube RU subtitles first (`--write-auto-subs --sub-langs "ru.*,ru"`)
2. If no usable subs, transcribe downloaded audio
3. Feed transcript to LLM with strict schema
4. Enforce Telegram 4096-char limit automatically
5. Output files to `output/` directory

---

## Sources

- [20 Rules for Content in 2026](https://rpn.beehiiv.com/p/20-rules-for-content-in-2026)
- [Justin Welsh: 1-3-5 Method](https://www.justinwelsh.me/newsletter/how-1-piece-of-content-becomes-16-the-1-3-5-method)
- [Dan Koe's Repurposing System](https://mikeromaine.com/dan-koes-newsletter-repurposing-content-system/)
- [Russian Social Media Platforms 2025](https://russia-promo.com/blog/popular-and-alternative-social-media-for-promotion-in-russia)
- [Telegram Advertising 2025](https://russia-promo.com/blog/telegram-ad-formats)
- [Content Repurposing Automation](https://www.automateed.com/ai-content-repurposing-workflows)
- [Repurpose.io](https://repurpose.io/)
- [Content Workflow Management](https://www.activepieces.com/blog/content-workflow-management)
- [Bloomberg: Russian Influencers Move to Telegram](https://www.bloomberg.com/news/articles/2025-08-29/youtube-and-instagram-blocks-pushed-russian-influencers-to-telegram)
- [Content OS by Justin Welsh](https://learn.justinwelsh.me/content)
