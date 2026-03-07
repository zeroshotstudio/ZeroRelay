<div align="center">

# ZeroRelay Template

**Build your own multi-agent AI relay chat**

Mix and match AI models and chat platforms in real-time conversations with humans in the loop.

[Prerequisites](#prerequisites) · [Quick Start](#quick-start) · [Architecture](#architecture) · [AI Bridges](#ai-bridges) · [Chat Bridges](#chat-bridges) · [Build Your Own](#build-your-own-bridge)

</div>

---

## What Is This?

ZeroRelay is a template for building **multi-party AI relay chats** — conversations where humans and AI agents (running different models, on different infrastructure) talk together through a unified WebSocket broker.

Pick your AI backends. Pick your chat interface. Deploy. Talk.

```
You (Telegram) ←→ ZeroRelay ←→ Claude (Anthropic)
                     ↕
                   GPT-4o (OpenAI)
                     ↕
                   Gemini (Google)
                     ↕
                   Llama (Ollama, local)
```

### Key Features

- **@-mention routing** — agents only respond when addressed, preventing infinite loops
- **Model-agnostic** — Claude, GPT, Gemini, Ollama, OpenClaw, or any API
- **Platform-agnostic** — Telegram, Discord, Slack, browser, or terminal
- **Human-in-the-loop** — you're the conductor, not a spectator
- **Private by default** — designed for Tailscale mesh, no public endpoints required
- **Minimal** — pure Python, no framework, no database

## Prerequisites

### Everyone Needs

| Requirement | Why | Check |
|---|---|---|
| **Linux server** | VPS, Raspberry Pi, home server — anything with systemd | Any Debian/Ubuntu/Fedora/Arch |
| **Python 3.12+** | Runtime for relay and all bridges | `python3 --version` |
| **pip** | Package installer | `pip --version` |
| **git** | To clone the repo | `git --version` |

### Recommended

| Requirement | Why | Check |
|---|---|---|
| **Tailscale** | Private mesh networking — keeps relay off public internet | `tailscale status` |
| **Root access** | For systemd service install (not needed for testing) | `whoami` |

### Per AI Backend

| Backend | What You Need | Cost | Setup Time |
|---|---|---|---|
| **Ollama** | [Ollama](https://ollama.com) installed + a model pulled | Free | 5 min |
| **Claude (API)** | [Anthropic API key](https://console.anthropic.com/) | Pay-per-use (~$3/1M tokens) | 2 min |
| **GPT (API)** | [OpenAI API key](https://platform.openai.com/api-keys) | Pay-per-use (~$2.50/1M tokens) | 2 min |
| **Gemini (API)** | [Google API key](https://aistudio.google.com/apikey) | Free tier (15 RPM) | 2 min |
| **Claude Code CLI** | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed + Anthropic account | Pro sub ($20/mo) | 10 min |
| **OpenClaw** | Docker + [OpenClaw](https://github.com/openclaw) running + ChatGPT subscription | Sub ($20/mo) | 30 min |

### Per Chat Interface

| Interface | What You Need | Cost | Setup Time |
|---|---|---|---|
| **Terminal CLI** | Nothing extra | Free | 0 min |
| **Telegram** | Bot token from [@BotFather](https://t.me/BotFather) + your chat ID from [@userinfobot](https://t.me/userinfobot) | Free | 5 min |
| **Discord** | Bot from [Discord Developer Portal](https://discord.com/developers/applications) + channel ID | Free | 10 min |
| **Slack** | Slack App with [Socket Mode](https://api.slack.com/apis/socket-mode) + workspace admin | Free | 15 min |

### Cheapest Setup (Zero Cost)

Ollama + Terminal CLI. No API keys, no accounts, runs entirely local:

```bash
# Install Ollama (if not already)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2

# Run ZeroRelay
python3 setup.py   # Select Ollama + CLI
```

### Most Common Setup

One cloud API (Anthropic or OpenAI) + Telegram. Costs a few cents per conversation, works from your phone.

## Quick Start

### Automated Setup (recommended)

```bash
git clone https://github.com/zeroshotstudio/ZeroRelay.git
cd ZeroRelay
sudo python3 setup.py
```

The setup script will walk you through choosing backends, configuring credentials, installing dependencies, and starting systemd services.

### Manual Setup

```bash
git clone https://github.com/zeroshotstudio/ZeroRelay.git && cd ZeroRelay
cp config.example.env .env   # Edit with your API keys
pip install websockets

# Start relay
python3 core/zerorelay.py --host 0.0.0.0 &

# Start an AI backend
ANTHROPIC_API_KEY=sk-... python3 bridges/ai/anthropic_api.py --relay ws://localhost:8765 &

# Start a chat interface
python3 bridges/chat/cli.py --relay ws://localhost:8765 --role jimmy
```

Then type: `@claude what's the best way to handle rate limiting?`

### Verify Install

```bash
python3 setup.py --check
```

## Architecture

```
  Chat Bridges          ZeroRelay         AI Bridges
  ┌──────────┐         ┌────────┐       ┌────────────┐
  │ Telegram │◄──ws──►│        │◄──ws──►│ Claude CLI │
  │ Discord  │◄──ws──►│ Broker │◄──ws──►│ OpenAI API │
  │  Slack   │◄──ws──►│ :8765  │◄──ws──►│ Gemini API │
  │   CLI    │◄──ws──►│        │◄──ws──►│   Ollama   │
  └──────────┘         └────────┘       └────────────┘
```

Every bridge connects as a named **role**. Messages broadcast to all others. AI bridges only respond when @-mentioned.

## AI Bridges

| Bridge | File | Backend | Tags | Dependency |
|--------|------|---------|------|------------|
| Claude Code | `bridges/ai/claude_code.py` | `claude -p` CLI | `@claude` `@c` | Claude Code CLI |
| Anthropic | `bridges/ai/anthropic_api.py` | Messages API | `@claude` `@c` | `anthropic` |
| OpenAI | `bridges/ai/openai_api.py` | Chat Completions | `@gpt` `@g` | `openai` |
| Gemini | `bridges/ai/gemini_api.py` | Gemini API | `@gemini` `@gem` | `google-genai` |
| Ollama | `bridges/ai/ollama.py` | Local REST API | `@ollama` `@local` | Ollama running |
| OpenClaw | `bridges/ai/openclaw.py` | Gateway CLI | `@z` `@zee` | Docker + OpenClaw |

The OpenAI bridge works with any compatible API — set `OPENAI_BASE_URL` for Together, Groq, etc.

## Chat Bridges

| Bridge | File | Platform | Dependency |
|--------|------|----------|------------|
| Telegram | `bridges/chat/telegram.py` | Telegram Bot | `httpx` |
| Discord | `bridges/chat/discord.py` | Discord Bot | `discord.py` |
| Slack | `bridges/chat/slack.py` | Slack Socket Mode | `slack-bolt` |
| CLI | `bridges/chat/cli.py` | Terminal | (none) |

Telegram includes: sticky addressing, `/status`, `/start`, `/reset`, `/killswitch`, typing indicators, streaming.

## Loop Prevention

Three layers prevent infinite AI-to-AI response chains:

1. **Tag-gating** — AI bridges ignore messages without their @-tag
2. **Self-skip** — bridges discard their own messages
3. **Meta filtering** — typing indicators and stream chunks are invisible to AI

## Build Your Own Bridge

Subclass `AIBridge` and implement `_sync_generate()`:

```python
from core.base_bridge import AIBridge

class MyBridge(AIBridge):
    def __init__(self, relay_url):
        super().__init__(
            relay_url=relay_url, role="my_model",
            tags=["@mymodel", "@m"], display_name="My Model",
            system_prompt="You are a helpful assistant in a relay chat.",
        )

    def _sync_generate(self, prompt, context):
        response = my_api.chat(prompt)
        return response.text

asyncio.run(MyBridge("ws://localhost:8765").run())
```

The base class handles: WebSocket connection, reconnection, @-mention routing, transcript tracking, typing indicators, and loop prevention.

## Deployment

See `services/README.md` for systemd unit templates. The pattern:

```
zerorelay.service          ← broker (start first)
├── claude-bridge.service  ← After=zerorelay.service
├── gpt-bridge.service     ← After=zerorelay.service
└── telegram-bridge.service ← After=zerorelay.service
```

For private networking, bind to Tailscale: `python3 core/zerorelay.py --host $(tailscale ip -4)`

## Example Setups

**Local Ollama + Terminal** (zero API keys):
```bash
python3 core/zerorelay.py & python3 bridges/ai/ollama.py & python3 bridges/chat/cli.py --role jimmy
```

**Three Models + Discord**:
```bash
ANTHROPIC_API_KEY=... python3 bridges/ai/anthropic_api.py &
OPENAI_API_KEY=... python3 bridges/ai/openai_api.py &
GOOGLE_API_KEY=... python3 bridges/ai/gemini_api.py &
DISCORD_BOT_TOKEN=... DISCORD_CHANNEL_ID=... python3 bridges/chat/discord.py
```

## Origin

Started as a hack to stop copy-pasting between Claude.ai and ChatGPT. Grew into a production relay on a VPS with Tailscale, systemd, and Telegram. This template extracts the pattern for anyone.

Built by [ZeroShot Studio](https://github.com/zeroshotstudio). [MIT License](LICENSE).
