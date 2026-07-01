# Community seeding drafts — Sprint 1 (A5)

**Post after:** Show HN goes live (G1 track)  
**Wedge:** Code Review Room  

---

## r/LocalLLaMA

**Title:** Multi-agent without LangGraph — group chat + cross-model MCP tool calling

**Body:**

I got tired of file-based blackboards between Claude and GPT, so I built a tiny WebSocket relay (~3.5k LOC MIT) that puts agents in one room. You @-mention them from Telegram like Slack; they respond in real time.

The part I use daily: **MCP Tool Broker** — GPT can call `claude/run_tests` as structured JSON while you're still in the chat.

Demo GIF: https://github.com/zeroshotstudio/ZeroRelay  
Self-host: `sudo python3 setup.py`  
Cloud waitlist if you want managed: [link]

Happy to answer setup questions. Not trying to replace LangGraph for complex graphs — this is for 2–5 agent setups where you want humans in the loop.

---

## MCP Discord / LangChain Discord

Short post:

> Shipped **ZeroRelay** — WebSocket relay for multi-agent group chat with cross-model MCP tool calling (`owner/tool_name` routing). OSS MIT, Telegram/Slack bridges. Demo: [GIF]. Feedback welcome: [GitHub link]

---

## X / Twitter thread (5 posts)

1. Problem: multi-agent setups that pass notes through files are slow and brittle.
2. ZeroRelay = group chat for AI agents. @claude @gpt in one Telegram thread.
3. MCP Tool Broker: agents call each other's tools as JSON, not copy-paste.
4. [GIF] — Code Review Room wedge (Claude writes, Codex reviews).
5. MIT OSS + Cloud waitlist. github.com/zeroshotstudio/ZeroRelay

---

## ZeroVPS README cross-link

Add to companion products section:

> **ZeroRelay** — multi-agent group chat relay. [github.com/zeroshotstudio/ZeroRelay](https://github.com/zeroshotstudio/ZeroRelay)
