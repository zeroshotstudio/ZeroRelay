# ZeroRelay — Cross-Model Chat Relay

Three-party real-time chat between Jimmy, Claude.ai, and Z (ChatGPT/OpenClaw).

## Architecture

```
┌──────────────┐
│  Jimmy       │──┐
│  (artifact)  │  │
└──────────────┘  │    WebSocket
                  ├──► ZeroRelay ◄──► ZeroBridge ──► openclaw gateway call ──► Z
┌──────────────┐  │    (port 8765)                    (agent + agent.wait)
│  Claude.ai   │──┘
│  (artifact)  │
└──────────────┘

All traffic over Tailscale. Nothing on public IP.
```

## Components

| File | What | Where it runs |
|------|------|---------------|
| `zerorelay.py` | WebSocket message broker (3 roles) | VPS |
| `zerobridge.py` | Relay ↔ OpenClaw CLI bridge | VPS |
| `zerorelay-chat.jsx` | Browser chat UI (React artifact) | Claude.ai |

## Setup

```bash
# On your VPS

# 1. Get your Tailscale IP
tailscale ip -4
# → 100.x.y.z

# 2. Install dependency
pip install websockets

# 3. Start the relay (tmux or screen recommended)
python3 zerorelay.py --host 100.x.y.z

# 4. Start the bridge (separate terminal)
python3 zerobridge.py --relay ws://100.x.y.z:8765
```

## Usage

1. Open the **ZeroRelay Chat** artifact in Claude.ai
2. Choose your role (Jimmy or Claude.ai)
3. Enter VPS Tailscale IP → Connect
4. Chat — messages route through the relay to Z via OpenClaw CLI

### Connecting as Jimmy
You're in the conversation as yourself. Talk to Z directly, or watch Claude.ai and Z interact.

### Connecting as Claude.ai
This slot is for relaying messages from Claude.ai into the chat.

### Opening both
Open two browser tabs — one as Jimmy, one as Claude.ai. Three-way conversation.

## Bridge Options

```bash
# Custom agent
python3 zerobridge.py --agent-id my-agent --session-key agent:my-agent:main

# Custom relay URL
python3 zerobridge.py --relay ws://100.x.y.z:9000
```

## How the Bridge Talks to Z

v1 (current) uses CLI shell-out — two calls per message:

```bash
# 1. Submit
openclaw gateway call agent \
  --params '{"agentId":"main","sessionKey":"agent:main:main","message":"...","idempotencyKey":"uuid"}'

# 2. Wait for response
openclaw gateway call agent.wait \
  --params '{"runId":"...","timeoutMs":120000}' \
  --timeout 130000
```

v2 (future): Direct WebSocket to Gateway at `ws://127.0.0.1:18789` with challenge-signing auth.

## Notes

- **Session persistence**: OpenClaw manages Z's session via `sessionKey` — conversation context is maintained
- **Tailscale only**: Relay binds to Tailscale interface, no public exposure
- **Auto-reconnect**: Bridge and artifact both reconnect automatically on disconnect
- **Response parsing**: Bridge tries several payload keys (`response`, `message`, `text`, `content`, `result`) — check logs if Z's responses look wrong, the payload shape may need adjusting
