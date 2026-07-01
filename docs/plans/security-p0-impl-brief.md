# Security P0 — Implementation Brief (B1–B4)

**For:** Coding / implementation agent  
**Branch:** `bugfix/security-p0-auth-token` (branch from `main` after planning PR merges)  
**Gate:** G0 — blocks paid Cloud launch  
**Reference:** `docs/plans/zerorelay-phase-0-security-gtm-plan.md` §Track B, `SECURITY_REVIEW.md`

---

## B1 — Constant-time token comparison

**File:** `core/zerorelay.py` (~line 122)

```python
import secrets
# Replace: if token != RELAY_TOKEN:
if not secrets.compare_digest(token or "", RELAY_TOKEN):
```

**Verify:** Invalid token rejected; valid accepted.

---

## B2 — Token off query string

**Files:** `core/zerorelay.py`, `core/base_bridge.py`, all bridges using `?token=`

1. Server: read `Authorization: Bearer <token>` or `X-Relay-Token` from WS handshake headers first.
2. Client (`BaseBridge`): pass token via `additional_headers` in `websockets.connect()`.
3. Keep `?token=` as deprecated fallback — log warning once per connection.

**Verify:** `python3 -m unittest discover -s tests -v` green; manual header connect works.

---

## B3 — CLI bridge token

**File:** `bridges/chat/cli.py`

Use same header pattern as `BaseBridge`; read `RELAY_TOKEN` from env.

**Verify:**
```bash
RELAY_TOKEN=test .venv/bin/python bridges/chat/cli.py --relay ws://localhost:8765
```

---

## B4 — Security test suite

**Create:** `tests/test_auth_security.py`, `tests/test_rate_limit.py`

| Test | Expect |
|------|--------|
| Valid token | Connection accepted |
| Invalid token | Rejected when auth required |
| Missing token | Rejected when `RELAY_TOKEN` set |
| Rate limit | 21st message in window rejected or dropped |

**Verify:** Full test suite green in CI.

---

## PR checklist

- [ ] No secrets in diff
- [ ] `SECURITY_REVIEW.md` — add "Resolved" section with date
- [ ] README mentions header auth (query string deprecated)
- [ ] Owner VPS deploy tested with `./scripts/deploy-vps.sh` (staging first)

**Do not merge B5 P1 items in same PR if it delays G0 > 2 days — split follow-up PR.**
