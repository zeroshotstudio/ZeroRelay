# Plan: ZeroRelay Phase 0 — Security Gate + GTM Validation

**Date**: 2026-06-30  
**Complexity**: M  
**Duration**: 2–3 weeks (parallel tracks)  
**PRD reference**: §13 Phase 0, §15 Security  
**Blocks**: Paid Cloud launch (security); Cloud beta marketing (GTM gate G1)  

---

## Overview

Phase 0 runs two parallel workstreams:

1. **Security** — Close P0 (and selected P1) items from `SECURITY_REVIEW.md` in the OSS repo.
2. **GTM** — Ship demo assets and launch surfaces to validate demand before heavy Cloud investment.

Either workstream can start immediately. **Do not enable Stripe until Security gate G0 passes.**

---

## Track B — Security (P0 gate)

**Branch**: `bugfix/security-p0-auth-token`  
**Exit gate G0**: All steps B1–B5 complete; CI green.

### Step B1 — Constant-time token comparison

| Field | Value |
|-------|-------|
| **Files** | `core/zerorelay.py` |
| **Change** | Replace `token != RELAY_TOKEN` with `not secrets.compare_digest(token or "", RELAY_TOKEN)` when `RELAY_TOKEN` is set |
| **Depends on** | None |
| **Verify** | `python3 -m unittest tests.test_auth_security -v` (create in B4) |

### Step B2 — Move relay token off query string

| Field | Value |
|-------|-------|
| **Files** | `core/zerorelay.py`, `core/base_bridge.py`, all `bridges/**/*.py`, `claude-bridge.py`, `telegram-bridge.py`, `zerobridge.py`, `codex-bridge.py`, `content-codex-bridge.py` |
| **Change** | Accept token via WebSocket header `Authorization: Bearer <token>` OR `X-Relay-Token: <token>`. Keep query-string token as **deprecated fallback** for one release with warning log. Update `_build_uri()` in `BaseBridge` to use `additional_headers` in `websockets.connect()`. |
| **Depends on** | B1 |
| **Verify** | All existing MCP integration tests pass; manual connect with header auth |

**Implementation notes:**

```python
# base_bridge.py — preferred pattern
headers = {}
if self.relay_token:
    headers["Authorization"] = f"Bearer {self.relay_token}"
async with websockets.connect(uri, additional_headers=headers) as ws:
```

Server-side in `zerorelay.py` `process_request` or handshake handler: read headers from `request.headers` before query params.

### Step B3 — Fix CLI bridge token auth

| Field | Value |
|-------|-------|
| **Files** | `bridges/chat/cli.py` |
| **Change** | Use `BaseBridge._build_uri()` pattern or pass `RELAY_TOKEN` via same header mechanism as B2 |
| **Depends on** | B2 |
| **Verify** | `RELAY_TOKEN=test .venv/bin/python bridges/chat/cli.py --relay ws://localhost:8765` connects when broker requires auth |

### Step B4 — Security test suite

| Field | Value |
|-------|-------|
| **Files** | `tests/test_auth_security.py` (create), `tests/test_rate_limit.py` (create) |
| **Tests** | Valid token accepts; invalid rejects; missing token rejects when required; constant-time path exercised; rate limit boundary (20+1 messages) |
| **Depends on** | B1–B3 |
| **Verify** | `python3 -m unittest discover -s tests -v` — all green |

### Step B5 — P1 quick wins (same PR or follow-up)

| ID | File | Fix |
|----|------|-----|
| 4 | `bridges/chat/telegram.py` | `html.escape(t, quote=True)` |
| 5 | `bridges/chat/telegram.py` | 5s cooldown on `/killswitch`, `/start` |
| 6 | `core/zerorelay.py` | Append timestamp before length check OR use lock |
| 7 | `bridges/ai/claude_code.py` | Max 5 retries with sleep, not unbounded recursion |
| 8 | `bridges/ai/openclaw.py` | Read token from env only, not CLI arg |
| 10 | `bridges/chat/telegram.py` | Chunk messages at 4000 chars |

| **Depends on** | B4 |
| **Verify** | CI green; update `SECURITY_REVIEW.md` with "Resolved" section dated 2026-XX-XX |

---

## Track A — GTM Validation

**Branch**: `docs/gtm-phase-0` (docs/assets only — no runtime changes required)  
**Exit gate G1**: 500 GitHub stars OR 100 waitlist signups OR 10 verified external installs  

### Step A1 — Demo GIF / video

| Field | Value |
|-------|-------|
| **Files** | `assets/demo.gif` (create), `README.md` (embed) |
| **Content** | 45–60s screen recording: Telegram thread → `@claude` builds snippet → `@gpt` reviews → MCP tool call visible in logs (optional split screen) |
| **Tools** | Gifox, ffmpeg, or asciinema for CLI-only fallback |
| **Depends on** | Working VPS or local relay with 2 agents |
| **Verify** | GIF < 5MB; renders on GitHub README |

**Script outline:**

1. Open Telegram chat with ZeroRelay bot.
2. Send: `@claude write a 10-line Python function that validates email format`
3. Claude responds; send: `@gpt review for edge cases and suggest fixes`
4. GPT responds; optionally show MCP: `@gpt call claude/run_tests` if configured.
5. End card: "ZeroRelay — group chat for AI agents" + GitHub URL.

### Step A2 — README polish pass

| Field | Value |
|-------|-------|
| **Files** | `README.md` |
| **Change** | Lead with GIF; add "Why not LangGraph?" 4-row comparison; add waitlist link; fix any stale port/host references |
| **Depends on** | A1 |
| **Verify** | Read through on mobile GitHub render |

### Step A3 — Waitlist page

| Field | Value |
|-------|-------|
| **Files** | `docs/waitlist/` or external Notion/Tally form |
| **Minimum fields** | Email, "How many agents do you run?", "Self-host or managed?" |
| **Hosting** | `relay.zeroshot.studio/waitlist` or GitHub Pages from `docs/` |
| **Depends on** | None |
| **Verify** | Form submission reaches owner inbox/Sheet |

### Step A4 — Show HN post draft

| Field | Value |
|-------|-------|
| **Files** | `docs/plans/show-hn-draft.md` (create) |
| **Title** | `Show HN: ZeroRelay – group chat for AI agents with cross-model MCP tool calling` |
| **Body structure** | Problem → 30s demo link → differentiator table → quick start → ask for feedback |
| **Depends on** | A1, A2 |
| **Verify** | Owner review; post Tuesday–Thursday 9am ET |

### Step A5 — Community seeding (post-launch)

| Channel | Action |
|---------|--------|
| r/LocalLLaMA | "Multi-agent without LangGraph" post with GIF |
| MCP Discord / LangChain Discord | Share MCP broker doc section |
| X/Twitter | Thread: problem → demo → link |
| ZeroVPS README | Cross-link ZeroRelay as companion product |

| **Depends on** | A4 published |
| **Verify** | Track UTM links in waitlist form |

---

## Vertical Wedge Landing (optional Phase 0.5)

**Only after owner confirms wedge** (default: Code Review Room).

| Field | Value |
|-------|-------|
| **Files** | `docs/wedges/code-review-room.md` or single-page site |
| **Content** | Hero, 3-step setup, example Telegram transcript, link to OSS quick start |
| **Depends on** | G1 not required; owner decision required |
| **Verify** | Lighthouse mobile score > 90 |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Header auth breaks existing VPS bridges | Deprecated query-string fallback for one release |
| HN post flops | Waitlist + Reddit backup; iterate headline |
| Demo GIF shows owner secrets | Use redacted API keys; test account |

---

## Commit Checklist

- [ ] `python3 -m unittest discover -s tests -v`
- [ ] Update `SECURITY_REVIEW.md` resolved items
- [ ] Update `blackboard.md` Completed section
- [ ] Conventional commit: `fix:` security, `docs:` GTM

---

*Gate G0 + at least one G1 signal → proceed to `zerorelay-cloud-implementation-plan.md` Step C1.*
