<div align="center">

# ZeroRelay

**Multi-agent AI relay chat over private mesh networking**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![WebSocket](https://img.shields.io/badge/protocol-WebSocket-010101?style=flat-square&logo=socketdotio&logoColor=white)](https://websockets.readthedocs.io/)
[![Tailscale](https://img.shields.io/badge/network-Tailscale-242424?style=flat-square&logo=tailscale&logoColor=white)](https://tailscale.com)
[![Telegram Bot](https://img.shields.io/badge/interface-Telegram_Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![systemd](https://img.shields.io/badge/managed_by-systemd-4B8BBE?style=flat-square&logo=linux&logoColor=white)](#systemd-services)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

A real-time WebSocket broker that enables structured multi-party conversations between humans and AI agents — each running different models, on different infrastructure, communicating through a unified relay with @-mention routing, session persistence, and loop prevention.

[Architecture](#architecture) · [Features](#features) · [Setup](#setup) · [How It Works](#how-it-works)

</div>

---

## Why ZeroRelay?

Running multiple AI agents is easy. Getting them to **talk to each other** — without infinite loops, lost context, or copy-paste middlemen — is the hard part.

ZeroRelay solves this with a lightweight WebSocket broker that:

- **Routes messages via @-mentions** — agents only respond when addressed, eliminating loops
- **Bridges different AI backends** — Claude (Anthropic) and Zee (OpenClaw/GPT) in the same conversation
- **Keeps humans in the loop** — full visibility and control via Telegram
- **Runs on private infrastructure** — Tailscale mesh, no public endpoints, your models on your hardware

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         TAILSCALE MESH                          │
│                                                                  │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐ │
│  │   Telegram   │────►│                  │◄────│    Claude     │ │
│  │   Bridge     │     │    ZeroRelay     │     │    Bridge     │ │
│  │              │◄────│    (broker)      │────►│              │ │
│  │  jimmy       │     │    :8765         │     │  vps_claude  │ │
│  └──────┬───────┘     │                  │     └──────┬───────┘ │
│         │             └────────┬─────────┘            │         │
│         │                      │                      │         │
│         ▼                      │                      ▼         │
│  ┌──────────────┐              │              ┌──────────────┐  │
│  │  Telegram    │              └──────────────►│  Claude CLI  │  │
│  │  Bot API     │     ┌──────────────┐        │  (claude -p) │  │
│  └──────────────┘     │  Zee Bridge  │        └──────────────┘  │
│                       │              │                           │
│                       │  zee         │                           │
│                       └──────┬───────┘                           │
│                              │                                   │
│                              ▼                                   │
│                       ┌──────────────┐                           │
│                       │  OpenClaw    │                           │
│                       │  Gateway     │                           │
│                       │  (Docker)    │                           │
│                       └──────────────┘                           │
└──────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Role ID | Runtime | Description |
|-----------|---------|---------|-------------|
| **zerorelay.py** | — | WebSocket server | Message broker with role validation, broadcast routing, and history |
| **claude-bridge.py** | `vps_claude` | `claude -p` | Anthropic Claude via CLI with persistent sessions and context compression |
| **zerobridge.py** | `zee` | `docker exec` → OpenClaw | GPT-class model via OpenClaw gateway with transcript context injection |
| **telegram-bridge.py** | `jimmy` | Telegram Bot API | Human interface with commands, sticky routing, and typing indicators |

## Features

### @-Mention Routing

Agents only activate when explicitly addressed — the core mechanism that prevents infinite AI-to-AI loops.

```
Jimmy:   @c what do you think about microservices vs monolith?
Claude:  For your scale, monolith. But @z could check what's actually deployed.
Zee:     Running on 3 containers right now. Monolith would simplify the stack.
```

| Tag | Routes to |
|-----|-----------|
| `@claude` · `@c` | Claude (Anthropic) |
| `@z` · `@zee` | Zee (OpenClaw/GPT) |

### Sticky Addressing

Tag once, then just type. Messages auto-route to the last agent you addressed until you switch.

```
Jimmy:   @c explain kubernetes       ← sets sticky to Claude
Jimmy:   what about docker swarm?    ← auto-routed to Claude
Jimmy:   @z check our docker setup   ← switches sticky to Zee
Jimmy:   show me the compose file    ← auto-routed to Zee
```

### Telegram Commands

Registered in the bot menu — tap `/` to see them.

| Command | Action |
|---------|--------|
| `/status` | Service health check (✓/✗ per bridge) |
| `/start` | Start Claude + Zee bridges |
| `/reset` | Rotate sessions, clear context |
| `/killswitch` | Emergency stop — kills all AI bridges |

### Session Management

| Agent | Strategy | Context Window | Reset |
|-------|----------|---------------|-------|
| Claude | Persistent CLI sessions (`--session-id`) | Full history with automatic compression | `/reset` rotates session UUID |
| Zee | OpenClaw session key | Transcript buffer (last 30 messages) | `/reset` or auto-reset after 30 min idle |

### Loop Prevention

Three layers ensure agents never trigger infinite response chains:

1. **Tag-gating** — agents ignore untagged messages entirely
2. **Self-skip** — agents discard their own messages
3. **Meta filtering** — typing indicators and stream chunks are invisible to agents

### Typing Indicators

Native Telegram "typing..." animation while agents generate responses. Kept alive with 4-second heartbeats — no silent waiting.

### Agent System Prompts

Each agent receives structured instructions covering:
- **Identity** — who they are, where they run, their role name
- **Relay mechanics** — how @-routing works, what they can see
- **Capabilities** — what to handle vs. what to defer to the other agent
- **Response style** — conversational, concise, no document formatting

## Setup

### Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **Python 3.12+** | Runtime for all bridges |
| **Tailscale** | Private mesh networking |
| **Claude Code CLI** | `claude -p` for AI responses ([docs](https://docs.anthropic.com/en/docs/claude-code)) |
| **OpenClaw** | Gateway for Zee agent (Docker) |
| **Telegram Bot** | Human interface ([@BotFather](https://t.me/BotFather)) |

### Install

```bash
# 1. Dependencies
pip install websockets httpx

# 2. Deploy
mkdir -p /opt/zerorelay
cp zerorelay.py zerobridge.py claude-bridge.py telegram-bridge.py /opt/zerorelay/

# 3. Configure Telegram
cat > /opt/zerorelay/telegram.env << 'EOF'
TELEGRAM_BOT_TOKEN=<your-token>
TELEGRAM_CHAT_ID=<your-chat-id>
EOF
chmod 600 /opt/zerorelay/telegram.env

# 4. Install services
cp *.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now zerorelay claude-bridge zerobridge telegram-bridge

# 5. Verify
systemctl status zerorelay claude-bridge zerobridge telegram-bridge
```

### Configuration

Each bridge reads constants from the top of its file:

| File | Key Settings |
|------|-------------|
| `zerorelay.py` | `--host` (Tailscale IP), `--port` (default `8765`) |
| `claude-bridge.py` | `RELAY_URL`, `CLAUDE_CONTEXT` (system prompt), `CLI_TIMEOUT_SEC` |
| `zerobridge.py` | `RELAY_URL`, `GATEWAY_URL`, `GATEWAY_TOKEN`, `RELAY_CONTEXT`, `SESSION_IDLE_RESET_SEC` |
| `telegram-bridge.py` | `RELAY_URL`, credentials via `telegram.env` |

## How It Works

```
  Jimmy (Telegram)              ZeroRelay                Claude Bridge
       │                          │                          │
       │  "@c review this plan"   │                          │
       ├─────────────────────────►│                          │
       │                          │  broadcast               │
       │                          ├─────────────────────────►│
       │                          │                          │  detect @c tag
       │                          │                          │  claude -p --session-id
       │                          │                          │  ┌──────────────┐
       │                          │                          │──│ Claude API   │
       │                          │                          │  └──────┬───────┘
       │                          │       response           │◄────────┘
       │                          │◄─────────────────────────┤
       │   "🧠 Claude: ..."      │                          │
       │◄─────────────────────────┤                          │
       │                          │                          │
```

1. **Jimmy** types in Telegram → Telegram bridge forwards to relay
2. **Relay** broadcasts to all connected role clients
3. **Bridge** with matching @-tag activates, calls its AI backend
4. **Response** flows back through relay → appears in Telegram
5. If the response contains another @-tag, the other agent picks it up

### Systemd Services

All four components run as systemd services with `Restart=on-failure`. The relay starts first, bridges connect after.

```
zerorelay.service          ← broker (must start first)
├── claude-bridge.service  ← After=zerorelay.service
├── zerobridge.service     ← After=zerorelay.service
└── telegram-bridge.service ← After=zerorelay.service
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Transport** | WebSockets via [`websockets`](https://websockets.readthedocs.io/) |
| **Network** | [Tailscale](https://tailscale.com) — private WireGuard mesh |
| **AI (Claude)** | [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) — `claude -p` with session persistence |
| **AI (Zee)** | [OpenClaw](https://github.com/openclaw) gateway — `docker exec` CLI shell-out |
| **Human I/O** | [Telegram Bot API](https://core.telegram.org/bots/api) via `httpx` long-polling |
| **Process mgmt** | systemd with auto-restart on failure |

## Project Structure

```
zerorelay/
├── zerorelay.py              # WebSocket broker
├── claude-bridge.py          # Claude ↔ relay bridge
├── zerobridge.py             # Zee/OpenClaw ↔ relay bridge
├── telegram-bridge.py        # Telegram ↔ relay bridge
├── zerorelay.service         # systemd unit — broker
├── claude-bridge.service     # systemd unit — Claude
├── zerobridge.service        # systemd unit — Zee
├── telegram-bridge.service   # systemd unit — Telegram
├── telegram.env.example      # Telegram credentials template
├── zerorelay-chat.jsx        # Browser chat UI (React, legacy)
└── .gitignore
```

## License

[MIT](LICENSE) — use it, fork it, ship it.

---

<div align="center">

Built by [ZeroShot Studio](https://github.com/zeroshotstudio)

</div>
