<div align="center">

# ZeroRelay Template

**Build your own multi-agent AI relay chat**

Mix and match AI models and chat platforms in real-time conversations with humans in the loop.

[Prerequisites](#prerequisites) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Bridges](#ai-bridges) · [Security](#security) · [Troubleshooting](#troubleshooting)

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
python3 bridges/chat/cli.py --relay ws://localhost:8765 --role operator
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
import asyncio
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
python3 core/zerorelay.py & python3 bridges/ai/ollama.py & python3 bridges/chat/cli.py --role operator
```

**Three Models + Discord**:
```bash
ANTHROPIC_API_KEY=... python3 bridges/ai/anthropic_api.py &
OPENAI_API_KEY=... python3 bridges/ai/openai_api.py &
GOOGLE_API_KEY=... python3 bridges/ai/gemini_api.py &
DISCORD_BOT_TOKEN=... DISCORD_CHANNEL_ID=... python3 bridges/chat/discord.py
```

## Security

ZeroRelay is designed to run on private infrastructure. Multiple layers protect your relay:

| Layer | Mechanism | Configuration |
|-------|-----------|---------------|
| **Network** | Tailscale mesh — relay never exposed to public internet | `--host $(tailscale ip -4)` |
| **Authentication** | Token-based — all bridges must present matching token | `RELAY_TOKEN` env var |
| **Rate limiting** | Per-role message throttling (20 msgs / 60s default) | `ZERORELAY_RATE_MAX`, `ZERORELAY_RATE_WINDOW` |
| **Message size** | WebSocket frame limit (64KB) | Hardcoded in relay |
| **Role locking** | One connection per role — prevents impersonation | Enforced by relay |
| **Sender verification** | Telegram bridge verifies user ID | `TELEGRAM_USER_ID` |
| **Operator commands** | Only the operator role can issue `[RESET]` | `ZERORELAY_OPERATOR` |
| **Service isolation** | systemd hardening (ProtectSystem, PrivateTmp, NoNewPrivileges) | See `services/README.md` |

**Important:** Always set `RELAY_TOKEN` in production. Without it, anyone who can reach the relay port can connect.

## Environment Variables

All configuration is via environment variables. See `config.example.env` for the full reference. Key variables:

| Variable | Used By | Required | Description |
|----------|---------|----------|-------------|
| `RELAY_TOKEN` | All | Recommended | Shared secret for relay authentication |
| `ZERORELAY_ROLES` | Relay | No | Comma-separated allowed roles (empty = any) |
| `ZERORELAY_OPERATOR` | Bridges | No | Role that can issue `[RESET]` (default: `operator`) |
| `ANTHROPIC_API_KEY` | Anthropic bridge | Yes | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI bridge | Yes | OpenAI API key |
| `GOOGLE_API_KEY` | Gemini bridge | Yes | Google AI API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bridge | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Telegram bridge | Yes | Target chat ID |
| `TELEGRAM_USER_ID` | Telegram bridge | Recommended | Sender verification — rejects messages from other users |

## Troubleshooting

### Connection refused

```
ConnectionRefusedError: relay not available
```

The relay isn't running or the URL is wrong. Check:

```bash
# Is the relay running?
systemctl status zerorelay        # if using systemd
ss -tlnp | grep 8765              # check if port is listening

# Is the URL correct?
# Bridges must use the same host:port the relay is bound to
python3 core/zerorelay.py --host 0.0.0.0 --port 8765   # listen on all interfaces
```

### Invalid or missing token

```
websockets.exceptions.ConnectionClosedError: 1008 Invalid or missing token
```

`RELAY_TOKEN` is set on the relay but bridges aren't sending it. Ensure all components share the same token via `.env` or environment:

```bash
# Check what the relay sees
journalctl -u zerorelay -n 20     # look for "Auth: enabled"

# Ensure bridges have it
grep RELAY_TOKEN /opt/zerorelay/.env
```

### Role already connected

```
websockets.exceptions.ConnectionClosedError: 1008 Role 'claude' already connected
```

Another instance of the same bridge is still running. Stop it first:

```bash
systemctl stop zerorelay-claude
# or find and kill the process
ps aux | grep bridges/ai
```

### pip install fails on newer distros

```
error: externally-managed-environment
```

Python 3.12+ on Debian/Ubuntu blocks system-wide pip installs. Options:

```bash
# Option 1: Use a virtual environment (recommended)
python3 -m venv /opt/zerorelay/venv
source /opt/zerorelay/venv/bin/activate
pip install websockets

# Option 2: Force system install (less safe)
pip install --break-system-packages websockets

# Option 3: Use system packages
sudo apt install python3-websockets
```

If using a venv, update your systemd `ExecStart` to use the venv Python:
```ini
ExecStart=/opt/zerorelay/venv/bin/python3 /opt/zerorelay/core/zerorelay.py --host ...
```

### Claude Code bridge: "session already in use"

The Claude CLI session is locked by another process. The bridge handles this automatically by rotating to a new session, but if it persists:

```bash
# Reset the session
rm /opt/zerorelay/claude-session-id
systemctl restart zerorelay-claude

# Or send /reset from your chat interface
```

### Telegram bot not responding

1. Verify your bot token: `curl https://api.telegram.org/bot<TOKEN>/getMe`
2. Verify chat ID: send a message to the bot, then check `curl https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Check `TELEGRAM_USER_ID` — if set incorrectly, all messages are rejected as unauthorized

### Bridges reconnecting in a loop

Normal behavior when the relay isn't reachable. Bridges use exponential backoff (3s, 6s, 12s, ... up to 60s). Once the relay starts, they connect automatically.

### Ollama bridge: "is it running?"

```bash
# Check Ollama is running
systemctl status ollama
ollama list                       # verify model is pulled

# Test directly
curl http://localhost:11434/api/chat -d '{"model":"llama3.2","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

### How do I add a new AI model?

See [Build Your Own Bridge](#build-your-own-bridge). Implement `_sync_generate()` — the base class handles everything else.

## Origin

Started as a hack to stop copy-pasting between Claude.ai and ChatGPT. Grew into a production relay on a VPS with Tailscale, systemd, and Telegram. This template extracts the pattern for anyone.

Built by [ZeroShot Studio](https://github.com/zeroshotstudio). [MIT License](LICENSE).
