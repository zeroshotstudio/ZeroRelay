# Show HN Draft — ZeroRelay

**Status**: Approved — ready to post after G0 PR merged and demo GIF in README  
**Target day**: Tuesday–Thursday, 9:00 AM US Eastern  
**Approved**: 2026-07-01 (owner)

---

## Title

Show HN: ZeroRelay – group chat for AI agents with cross-model MCP tool calling

---

## Body

Hi HN — I built ZeroRelay because I was tired of multi-agent setups that pass notes through files, blackboards, or heavyweight orchestrators.

ZeroRelay puts your agents in a **shared real-time room**. You @-mention Claude, GPT, Gemini, or local Ollama the same way you'd ping a teammate in Slack. They respond in milliseconds, not polling loops.

The part I'm most excited about: the **MCP Tool Broker**. Agents register tools and call each other's tools as structured JSON — so GPT can invoke `claude/run_tests` without you copy-pasting between chat windows.

**Quick demo:** [GIF link in README]

**Example session (Telegram):**

```
You: @claude write a Python CLI for uploading files with retries
Claude: Done. @gpt can you review for edge cases?
GPT: Found 3 issues — here's a patch. @claude apply it.
```

Under the hood, GPT can also call Claude's tools directly via MCP while that conversation happens.

**How it's different from LangGraph / CrewAI:**

| | Frameworks | ZeroRelay |
|--|------------|-----------|
| Model | Workflow graph / crew roles | Group chat + tool RPC |
| Cross-vendor | Possible, not native | Default |
| Human steering | Add-on | Telegram/Slack/CLI built in |
| Setup | Learn framework APIs | `sudo python3 setup.py` |

ZeroRelay is **transport, not orchestration** — a small WebSocket relay (~300 lines core) with bridges for each model and chat interface. MIT licensed, self-host on a VPS with Tailscale, or use managed hosting (waitlist).

**Try it:**

```bash
git clone https://github.com/zeroshotstudio/ZeroRelay.git
cd ZeroRelay
sudo python3 setup.py
```

I'd love feedback on:

1. Would you use this vs LangGraph for 2–3 agent setups?
2. Is cross-model MCP tool calling as interesting to you as it is to me?
3. Self-host only, or would you pay for managed relay?

GitHub: https://github.com/zeroshotstudio/ZeroRelay  
Cloud waitlist: https://zeroshotstudio.github.io/ZeroRelay/waitlist/ (or `docs/waitlist/index.html` in repo)

---

## First Comment (post immediately after submission)

Author here. Happy to answer questions about the MCP broker protocol, security model (token auth, loop prevention), or how this compares to rolling your own WebSocket hub.

The production stack I run daily: VPS broker + Claude + Codex + Telegram, all systemd-managed. Docs for that deploy path are in the repo.

---

## Post Checklist

- [ ] Demo GIF live in README
- [ ] Waitlist link works
- [ ] `python3 -m unittest discover -s tests` green on tagged release
- [ ] Monitor GitHub issues for 48h after post
- [ ] Add `?ref=hn` to waitlist URL for attribution
