# Personal Adapter (local API keys)

Mint a localhost OpenAI-compatible key that forwards chat completions to a CLI you are already logged into (AGY or Claude Code).

This is a **sidecar**. It is not the WebSocket relay, not Cloud, and not a way to resell a subscription. Provider terms still apply.

## Where to run it

The gateway must run **on the same machine as the logged-in CLI**. Clients always call `http://127.0.0.1:8767`.

| You want to spend | Run on | From this Mac |
|-------------------|--------|----------------|
| **AGY** (Antigravity on this Mac) | This Mac | `./scripts/run-personal-adapter.sh local` |
| **Claude Code** (already on the VPS) | VPS loopback + SSH tunnel | `./scripts/run-personal-adapter.sh vps` |

`vps` uses SSH host `my-vps-admin` (same as `./scripts/deploy-vps.sh`). It copies the adapter to `/opt/zerorelay/adapter`, serves on the VPS `127.0.0.1:8767`, then forwards that port to your Mac. Ctrl-C closes the tunnel.

```bash
./scripts/run-personal-adapter.sh --help
./scripts/run-personal-adapter.sh local --mint          # this Mac, AGY
./scripts/run-personal-adapter.sh vps                   # VPS Claude + tunnel
./scripts/run-personal-adapter.sh vps --dry-run         # print SSH commands only
```

Do not bind the VPS adapter on a public IP. The tunnel keeps the key on localhost.

## Limits

- Binds **127.0.0.1** only. Do not expose it on a public interface.
- One person, their own logged-in CLIs. Do not share the minted key.
- Official CLIs only (`agy`, `claude`). Codex and Cursor are not wired yet.
- Copy for humans: *use the CLI you already pay for, from tools that speak OpenAI HTTP.*

## Mint a key

```bash
python3 services/openai_gateway.py --mint
```

Prints once:

```json
{"base_url": "http://127.0.0.1:8767", "key": "zr-...", "env_file": "/Users/you/.zerorelay/openai-gateway.env"}
```

The env file is mode `0600`. The key is never written to logs.

## Serve

```bash
python3 services/openai_gateway.py --serve
```

Health (no key): `curl http://127.0.0.1:8767/health`

Completion:

```bash
curl http://127.0.0.1:8767/v1/chat/completions \
  -H "Authorization: Bearer zr-YOUR-KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"agy","messages":[{"role":"user","content":"ping"}]}'
```

Paste `base_url` + `key` into any OpenAI-compatible client (Operator OS, OpenAI Python SDK, Cline/Continue custom provider).

## Choose a backend

| Env | Values | Default |
|-----|--------|---------|
| `ZERORELAY_ADAPTER_PROVIDER` | `agy`, `claude` | `agy` |
| `ZERORELAY_AGY_BIN` | path to `agy` | `agy` |
| `ZERORELAY_CLAUDE_BIN` | path to `claude` | `claude` |
| `ZERORELAY_CLAUDE_SESSION` | `1` to reuse a Claude CLI session | off (stateless per request) |
| `ZERORELAY_SYSTEM_PREAMBLE` | extra system text; empty string disables the AGY Operator OS default | AGY default only |

The CLI must already be authenticated (`agy` / `claude` on PATH).

## macOS LaunchAgent

Plist: [deploy/macos/studio.zeroshot.zerorelay-openai-gateway.plist](../deploy/macos/studio.zeroshot.zerorelay-openai-gateway.plist)

```bash
mkdir -p "$HOME/Library/Logs/zerorelay"
cp deploy/macos/studio.zeroshot.zerorelay-openai-gateway.plist "$HOME/Library/LaunchAgents/"
# Edit the copy if your checkout is not /Users/zero/Projects/active/ZeroRelay
launchctl load "$HOME/Library/LaunchAgents/studio.zeroshot.zerorelay-openai-gateway.plist"
```

Unload: `launchctl unload "$HOME/Library/LaunchAgents/studio.zeroshot.zerorelay-openai-gateway.plist"`

## Design

[docs/superpowers/specs/2026-09-12-personal-adapter-design.md](superpowers/specs/2026-09-12-personal-adapter-design.md)
