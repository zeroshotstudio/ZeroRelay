# ZeroRelay

Three-party AI relay chat over Tailscale. Jimmy (human, via Telegram), Claude (Anthropic, via Claude Code CLI), and Zee (OpenClaw/GPT) talk to each other in real-time through a WebSocket broker.

## Architecture

```
┌─────────────────┐
│  Jimmy          │
│  (Telegram Bot) │──┐
└─────────────────┘  │
                     │    ┌─────────────────┐
                     ├───►│   ZeroRelay      │  WebSocket broker
                     │    │   (port 8765)    │  Tailscale only
┌─────────────────┐  │    └────────┬────────┘
│  Claude         │──┘             │
│  (claude -p)    │           broadcasts
└─────────────────┘             to all
                                   │
┌─────────────────┐                │
│  Zee            │◄───────────────┘
│  (OpenClaw CLI) │
└─────────────────┘
```

## Components

| File | Role | What it does |
|------|------|-------------|
| `zerorelay.py` | Broker | WebSocket message relay. Validates roles, broadcasts messages, keeps history |
| `claude-bridge.py` | `vps_claude` | Runs `claude -p` (Claude Code CLI) with persistent sessions. Responds when `@claude` or `@c` is tagged |
| `zerobridge.py` | `zee` | Calls OpenClaw gateway via `docker exec` CLI. Responds when `@z` or `@zee` is tagged |
| `telegram-bridge.py` | `jimmy` | Bridges Telegram Bot API ↔ relay. Handles commands, sticky addressing, typing indicators |

### Systemd Services

| Service | Description |
|---------|-------------|
| `zerorelay.service` | WebSocket broker on Tailscale IP |
| `claude-bridge.service` | Claude AI bridge |
| `zerobridge.service` | Zee/OpenClaw bridge |
| `telegram-bridge.service` | Jimmy's Telegram interface |

## Features

### @-Mention Addressing
Agents only respond when tagged — prevents infinite loops between AIs.
- `@claude` or `@c` → routes to Claude
- `@z` or `@zee` → routes to Zee
- Agents can tag each other to continue conversations

### Sticky Addressing
After tagging an agent, subsequent untagged messages auto-route to the same agent. Switch by tagging a different one.

### Telegram Commands
| Command | Action |
|---------|--------|
| `/status` | Show which bridges are running |
| `/start` | Start Claude + Zee bridges |
| `/reset` | Clear all sessions and context |
| `/killswitch` | Stop all AI bridges immediately |

### Session Management
- **Claude**: Persistent sessions via `--session-id`. Full conversation history with automatic context compression. Rotated on `/reset`.
- **Zee**: OpenClaw session key with auto-reset after 30 min idle. Rotated on `/reset`.

### Typing Indicators
Native Telegram "typing..." indicator stays alive while agents generate responses (re-sent every 4s).

### Agent System Prompts
Each agent gets context-aware instructions: who's in the chat, how to address others, their role/strengths, and what to defer to the other agent.

## Setup

### Prerequisites
- VPS with Tailscale
- Python 3.12+ with `websockets` and `httpx`
- Claude Code CLI (`claude`) authenticated
- OpenClaw running in Docker (for Zee)
- Telegram bot token + chat ID

### Install

```bash
# Install dependencies
pip install websockets httpx

# Copy files to /opt/zerorelay/
mkdir -p /opt/zerorelay
cp zerorelay.py zerobridge.py claude-bridge.py telegram-bridge.py /opt/zerorelay/

# Configure Telegram credentials
cat > /opt/zerorelay/telegram.env << 'EOF'
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
EOF
chmod 600 /opt/zerorelay/telegram.env

# Install systemd services
cp *.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now zerorelay claude-bridge zerobridge telegram-bridge
```

### Configuration

Edit the constants at the top of each bridge file:

| File | Key constants |
|------|---------------|
| `zerorelay.py` | `--host` (Tailscale IP), `--port` (default 8765) |
| `claude-bridge.py` | `RELAY_URL`, `CLAUDE_CONTEXT` (system prompt) |
| `zerobridge.py` | `RELAY_URL`, `GATEWAY_URL`, `GATEWAY_TOKEN`, `RELAY_CONTEXT` (system prompt) |
| `telegram-bridge.py` | `RELAY_URL`, bot token/chat ID via `telegram.env` |

## How It Works

1. **Jimmy** sends a message in Telegram (e.g. `@c what do you think?`)
2. **Telegram bridge** detects the `@c` tag, shows typing indicator, forwards to relay
3. **Relay** broadcasts to all connected clients
4. **Claude bridge** sees the `@c` tag, calls `claude -p` with the message + session history
5. **Claude's response** is sent back through the relay → appears in Telegram
6. If Claude's response contains `@z`, Zee picks it up and responds too

### Loop Prevention
- Agents only respond when explicitly tagged
- Agents skip their own messages and typing indicators
- No agent can trigger itself

## Tech Stack

- **Transport**: WebSockets (`websockets` library)
- **Network**: Tailscale (private mesh, not exposed to public internet)
- **Claude**: Claude Code CLI (`claude -p --session-id`)
- **Zee**: OpenClaw gateway via `docker exec` CLI shell-out
- **Jimmy**: Telegram Bot API via `httpx` (long-polling)
- **Process management**: systemd with auto-restart

## License

MIT
