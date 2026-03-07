# ZeroRelay Security Code Review

**Date:** 2026-03-07
**Scope:** Full codebase (17 source files, ~3,500 lines)
**Overall Rating:** 7.5/10

---

## HIGH — Fix Soon

### 1. Token comparison is not constant-time (timing attack)
**`core/zerorelay.py:122`**

Python's `!=` for strings short-circuits on the first differing byte. An attacker measuring response times can brute-force the token character by character.

```python
# Current
if token != RELAY_TOKEN:

# Fix
import secrets
if not secrets.compare_digest(token or "", RELAY_TOKEN):
```

### 2. Relay token exposed in WebSocket query string
**`core/zerorelay.py:116`, `core/base_bridge.py:49-51`, all chat bridges**

Tokens passed as `?token=...` appear in reverse proxy access logs, load balancer logs, and browser history. Use a WebSocket subprotocol header or custom header during the upgrade handshake instead.

### 3. CLI bridge does not send relay token
**`bridges/chat/cli.py:69`**

```python
# Missing token — will fail if RELAY_TOKEN is set on relay
async with websockets.connect(f"{RELAY_URL}?role={ROLE}") as ws:
```

The CLI bridge ignores `RELAY_TOKEN` entirely, making it unable to connect when auth is enabled and providing a pattern that bypasses auth when disabled.

---

## MEDIUM — Fix This Release

### 4. Telegram HTML escaping is incomplete
**`bridges/chat/telegram.py:64`**

Custom `html_escape()` misses quote characters. Use `html.escape(t, quote=True)` from the standard library.

### 5. No rate limiting on Telegram service commands
**`bridges/chat/telegram.py:158-172`**

`/killswitch` and `/start` execute `systemctl` with no cooldown. A rapid fire of commands causes service start/stop oscillation (DoS).

### 6. Race condition in rate limit check
**`core/zerorelay.py:86-97`**

Timestamp is appended after the length check. An async yield between check and append could allow two coroutines to pass simultaneously.

### 7. Recursive retry with no depth limit
**`bridges/ai/claude_code.py:77`**

`_sync_generate` calls itself recursively on "already in use" errors with no max retry count. A persistent error causes `RecursionError`.

### 8. OpenClaw token visible in process list
**`bridges/ai/openclaw.py:47`**

`--token` is passed as a command-line argument, visible via `ps aux` to any user on the host. Pass via environment variable instead.

---

## LOW — Fix in Future Releases

### 9. Discord/Slack bridges have no user whitelist
Unlike Telegram (`TELEGRAM_USER_ID`), Discord and Slack accept messages from any user in the channel.

### 10. Telegram messages not chunked for 4096-char limit
AI agent responses can exceed Telegram's max message length. The API will reject these.

### 11. `mcp_tools_updated` broadcast doesn't exclude per-role
**`core/zerorelay.py:174-179`** — `get_tools()` called without `exclude_role`, so agents see their own tools in update broadcasts (but not on initial connect).

### 12. No audit logging of MCP tool call arguments
**`core/zerorelay.py:238`** — Only tool name is logged, not argument keys.

### 13. Discord drops streaming messages
`stream_start` and `stream_chunk` are skipped but `stream_end` falls through to default. Users see nothing during streaming.

---

## Consistency Gaps Between Chat Bridges

| Feature             | Telegram  | Discord | Slack  | CLI       |
|---------------------|-----------|---------|--------|-----------|
| Sender verification | USER_ID   | None    | None   | None      |
| Relay token         | Yes       | Yes     | Yes    | **Missing** |
| Service commands    | Yes       | No      | No     | /reset    |
| Streaming support   | Full      | Partial | Dropped| Dropped   |
| Message size limit  | None(bug) | 2000    | None   | None      |

---

## Missing Test Coverage

- Token authentication (valid/invalid/missing)
- Rate limiting edge cases
- WebSocket frame size rejection
- Malformed JSON fuzzing
- Chat bridge message handling

---

## What's Done Well

- Minimal dependency surface (only `websockets` core)
- MCP Tool Broker: self-call prevention, sender verification, namespacing, timeouts, cleanup on disconnect
- Content not logged (only lengths) — good PII hygiene
- Per-role rate limiting with separate chat/MCP limits
- Exponential backoff on all bridges
- Transcript bounding prevents memory growth
- 64KB WebSocket frame limit
- systemd hardening templates (ProtectSystem, PrivateTmp, NoNewPrivileges)
