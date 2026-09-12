# ZeroRelay Personal Adapter — Design Spec

**Date:** 2026-09-12  
**Status:** Approved for v1 implementation  
**SKU:** Sidecar (does not replace the WebSocket relay or Code Review Room GTM)

## Problem

Users already pay for CLI/OAuth subscriptions (AGY, Claude Code, later Codex/Cursor). Many tools only accept an OpenAI-compatible `base_url` + API key. They cannot spend that subscription usage from Operator OS, Cline, Continue, or similar clients.

## Goal

Mint a local `zr-` API key and serve `POST /v1/chat/completions` on `127.0.0.1` that forwards chat messages to the user’s **already logged-in official CLI**.

## Non-goals (v1)

- Hosted Cloud keys, Stripe, multi-tenant sharing
- Tailscale / non-loopback bind
- Codex, Cursor, ChatGPT providers (documented only)
- Embeddings, images, Anthropic Messages API
- Real token streaming (full completion only)
- Routing `model=` across providers
- Changing `python3 setup.py` or the OSS relay install path

## Constraints

- Bind `127.0.0.1` by default.
- One human, their own CLI sessions. No “rent my Claude Pro.”
- Official CLIs only (`agy`, `claude`). No cookie/credential scraping.
- Copy: “use the CLI you already pay for, from tools that speak OpenAI HTTP.” Do not market as billing bypass.
- Provider ToS still apply. Legal review before any public Cloud SKU.
- Never log the minted key.

## Architecture

```
OpenAI-compatible client
  Authorization: Bearer zr-...
  POST /v1/chat/completions
        |
        v
services/openai_gateway.py   (stdlib HTTP, mint + serve)
        |
        v
services/providers.py
  CompletionProvider.generate(messages, model) -> str
        |
        +-- AgyProvider      (default)
        +-- ClaudeCodeProvider
```

HTTP stays stdlib so a later FastAPI/LiteLLM layer can replace the server without rewriting providers.

## HTTP surface

| Method | Path | Auth | Behavior |
|--------|------|------|----------|
| GET | `/health`, `/v1/health` | none | `{status, service}` |
| GET | `/v1/models` | Bearer | One model id = active provider name |
| POST | `/chat/completions`, `/v1/chat/completions` | Bearer | Non-streaming chat completion |

Auth: `Authorization: Bearer <ZERORELAY_OPENAI_KEY>`. Missing/wrong key → 401. Invalid JSON → 400. Empty `messages` → 400. CLI timeout → 504. CLI missing/fail → 502.

Response shape matches the existing gateway (`id: chatcmpl-zerorelay`, `choices[0].message.content`).

## Key minting

`python3 services/openai_gateway.py --mint`

- Key: existing `ZERORELAY_OPENAI_KEY` or `zr-` + `secrets.token_urlsafe(32)`
- Write `~/.zerorelay/openai-gateway.env` (or `$ZERORELAY_HOME`) mode `0600`
- Fields: `ZERORELAY_OPENAI_HOST`, `ZERORELAY_OPENAI_PORT`, `ZERORELAY_OPENAI_KEY`, `ZERORELAY_ADAPTER_PROVIDER`
- Print once: `{base_url, key, env_file}`
- Default host/port: `127.0.0.1:8767`

One local key. No hashed multi-key table in v1.

## Provider interface

```python
class CompletionProvider(Protocol):
    name: str
    def generate(self, messages: list[dict], model: str) -> str: ...
```

Registry: `ZERORELAY_ADAPTER_PROVIDER=agy|claude` (default `agy`). Unknown name raises `ValueError`. The serving process holds one provider instance so Claude session mode can persist across requests.

`model` in the JSON body is echoed in the response. It does not switch providers.

### AgyProvider (`name = "agy"`)

Move existing `call_agy` behavior:

- Binary: `ZERORELAY_AGY_BIN` (default `agy`)
- CWD: `ZERORELAY_AGY_CWD` or `$ZERORELAY_HOME/agy-brain-sandbox`
- Timeout: `ZERORELAY_AGY_TIMEOUT` (default 120s)
- Preamble: `ZERORELAY_SYSTEM_PREAMBLE` if set (including empty = none); otherwise keep the current Operator OS preamble so AGY tests stay identical

### ClaudeCodeProvider (`name = "claude"`)

Patterned on `bridges/ai/claude_code.py`:

- Binary: `ZERORELAY_CLAUDE_BIN` (default `claude`)
- `claude -p --model <ZERORELAY_CLAUDE_MODEL> --session-id <uuid>` with prompt on stdin
- Default **stateless**: new session id per HTTP request
- `ZERORELAY_CLAUDE_SESSION=1`: `--resume` after first success; idle reset 30 min; rotate on “already in use” (max 5)
- Timeout: `ZERORELAY_CLAUDE_TIMEOUT` (default 120)
- No Operator OS preamble unless `ZERORELAY_SYSTEM_PREAMBLE` is set

### Later providers (spec only, no code)

| Provider | Backend | Notes |
|----------|---------|--------|
| Codex | `codex exec` | Same shape as `codex-bridge.py` |
| Cursor | Cursor CLI | After AGY + Claude pass gateway tests |
| ChatGPT | ChatGPT/Codex CLI | Not a separate unofficial API |

## Process / install

```bash
python3 services/openai_gateway.py --mint
python3 services/openai_gateway.py --serve
```

macOS LaunchAgent: `deploy/macos/studio.zeroshot.zerorelay-openai-gateway.plist` (loopback, `ZERORELAY_HOME=~/.zerorelay`, PATH includes Homebrew and `~/.local/bin`).

`setup.py` is unchanged.

## Error handling

| Condition | HTTP | Message |
|-----------|------|---------|
| No/invalid Bearer | 401 | unauthorized |
| Bad JSON / missing messages | 400 | invalid json / messages required |
| CLI timeout | 504 | `{provider} timed out` |
| Binary missing | 502 | `{provider} not installed` |
| Empty or failed CLI | 502 | error text, truncated, no key |

Logs must not include the minted key.

## Testing

- Keep `tests/test_openai_gateway.py` AGY cases passing (health, 401, completions, `/v1` path, mint).
- Unit tests for `get_provider`, AgyProvider, ClaudeCodeProvider (fake binaries).
- Gateway integration: `ZERORELAY_ADAPTER_PROVIDER=claude` + fake `claude`.
- `/v1/models` returns the active provider id.

## Success

- Fake-agy and fake-claude gateway tests green.
- `--mint` prints `zr-` key + `http://127.0.0.1:8767`.
- Live check (manual): minted key + curl or Operator OS against a logged-in CLI.

## Follow-ups

Codex/Cursor providers, Tailscale bind, fake SSE streaming if a client requires `stream: true`, Cloud SKU after legal review.
