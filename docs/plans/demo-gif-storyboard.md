# Demo GIF Storyboard — ZeroRelay Phase 0

**Duration:** 45–60 seconds  
**Format:** Screen recording → GIF (< 5MB)  
**File:** `assets/demo.gif`  
**Wedge:** Code Review Room (recommended)

---

## Setup (before recording)

- [ ] Relay running locally or on VPS with `RELAY_TOKEN` set
- [ ] Telegram bot connected (`telegram-bridge.py`)
- [ ] Two agents live: e.g. `claude-bridge` + `codex-bridge` (or Claude + GPT API bridges)
- [ ] Optional: MCP tool configured for cross-agent call (log tail visible)
- [ ] Clean Telegram chat — no unrelated messages above fold
- [ ] Terminal with relay logs visible (split screen or PiP)

---

## Shot list

| Sec | Visual | Action / VO text |
|-----|--------|------------------|
| 0–5 | Title card or Telegram chat | *"Your AI agents in one group chat — like Slack for agents."* |
| 5–15 | Telegram | Send: `@claude write a 10-line Python function that validates email format` |
| 15–25 | Telegram | Claude responds with code block |
| 25–35 | Telegram | Send: `@codex review for edge cases and suggest fixes` |
| 35–45 | Telegram | Codex responds with review |
| 45–55 | Optional: terminal log | Show MCP broker routing `owner/tool_name` (if configured) |
| 55–60 | End card | **ZeroRelay** — group chat for AI agents · github.com/zeroshotstudio/ZeroRelay |

---

## Recording tips

- Use **Gifox** or `ffmpeg` palette filter for small GIF size
- Crop to Telegram window + minimal chrome
- Font size readable at GitHub README width (~800px)
- Dark mode OK if README matches

---

## Fallback (no Telegram)

Asciinema: two CLI bridges in split panes, `@claude` / `@gpt` tags in `bridges/chat/cli.py` session.

---

## Acceptance

- [ ] GIF < 5MB
- [ ] Renders in GitHub README without scroll
- [ ] Shows ≥2 distinct agents responding
- [ ] Owner approves before HN post
