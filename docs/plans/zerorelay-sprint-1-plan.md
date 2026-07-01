# ZeroRelay Sprint 1 — Phase 0 Execution Plan

**PM owner:** Agent-led PM session  
**Branch:** `pm/phase-0-sprint-1` (planning) → `bugfix/security-p0-auth-token` (security impl)  
**Duration:** 2 weeks (2026-07-01 → 2026-07-14)  
**Goal:** Pass **G0** (security P0) and ship **G1** demand assets (demo GIF + waitlist + HN-ready README)

---

## North star & monetization path

| Gate | Sprint 1 target | Unlocks revenue |
|------|-----------------|-----------------|
| **G0** | P0 security merged + tests green | Paid Cloud / Stripe |
| **G1** | Demo GIF in README + waitlist live + HN draft approved | Cloud beta marketing spend |

**WARS** (Weekly Active Relay Sessions) is the long-term north star — not a Sprint 1 metric.

---

## Parallel tracks (do not serialize)

### Track B — Security (blocks money)

| ID | Task | Owner | Est. | Branch | Done when |
|----|------|-------|------|--------|-----------|
| B1 | Constant-time token compare (`secrets.compare_digest`) | Impl agent | 2h | `bugfix/security-p0-auth-token` | `core/zerorelay.py` updated |
| B2 | Token via `Authorization` / `X-Relay-Token` header; deprecate query string | Impl agent | 1d | same | All bridges connect with header auth |
| B3 | Fix CLI bridge token auth | Impl agent | 2h | same | CLI connects when `RELAY_TOKEN` set |
| B4 | `tests/test_auth_security.py` + rate-limit tests | Impl agent | 1d | same | `unittest discover` green |
| B5 | P1 quick wins (telegram escape, cooldown, chunking, claude retry cap) | Impl agent | 1d | same or follow-up PR | `SECURITY_REVIEW.md` resolved section |

**Exit:** PR merged to `main` → **G0 passed**.

### Track A — GTM (validates demand)

| ID | Task | Owner | Est. | Branch | Done when |
|----|------|-------|------|--------|-----------|
| A1 | Demo GIF storyboard + record 45–60s capture | Owner + PM | 4h | `docs/gtm-phase-0` | `assets/demo.gif` < 5MB |
| A2 | README lead with GIF + LangGraph comparison table | PM / docs | 3h | same | Mobile GitHub render OK |
| A3 | Waitlist form (email, agent count, self-host vs managed) | PM | 2h | same | Submissions reach owner inbox |
| A4 | Show HN post owner review (`docs/plans/show-hn-draft.md`) | Owner | 1h | — | Approved; schedule Tue–Thu 9am ET |
| A5 | Post-HN community seeding | Owner | 2h | — | r/LocalLLaMA + MCP Discord (post-G1) |

**Exit:** GIF live + 100 waitlist OR 500 stars OR 10 stranger installs → **G1 passed**.

---

## Week-by-week schedule

### Week 1 (Jul 1–7)

| Day | Security | GTM |
|-----|----------|-----|
| Mon | B1 + B2 start | A1 storyboard script final |
| Tue | B2 finish + B3 | A1 record GIF (VPS or local 2-agent setup) |
| Wed | B4 test suite | A2 README polish |
| Thu | B4 CI green | A3 waitlist page |
| Fri | B5 P1 items | Owner review A2–A4 |

### Week 2 (Jul 8–14)

| Day | Security | GTM |
|-----|----------|-----|
| Mon | Security PR merge → **G0** | Embed GIF in README |
| Tue | Monitor VPS deploy | HN dry-run with 2 reviewers |
| Wed | — | **Show HN** (if G0 + GIF ready) |
| Thu | Cloud prep: `cloud/` scaffold (no Stripe) | A5 community posts |
| Fri | Sprint retro + Sprint 2 plan (Cloud C1–C3) | Log G1 metrics in blackboard |

---

## Locked decisions (no re-litigation)

1. MIT open core — monetize convenience + compliance  
2. Transport, not orchestration — no LangGraph replacement scope  
3. Golden path: Anthropic/OpenAI + Telegram + VPS or Cloud Solo  
4. Cloud v1 = relay management + audit, not native chat  
5. MCP Tool Broker = core differentiator  
6. **G0 before Stripe**

---

## Open decisions — PM recommendations (owner sign-off)

| # | Question | Recommendation | Rationale |
|---|----------|----------------|-----------|
| 1 | Vertical wedge? | **Code Review Room** | Matches owner VPS usage (Claude + Codex review loop); clearest demo narrative |
| 2 | Cloud domain? | **`relay.zeroshot.studio`** | Consistent with `vault.zeroshot.studio`; short, memorable |
| 3 | Dashboard auth beta? | **GitHub OAuth only** | Lowest friction for B2D audience; defer Clerk until Team tier |
| 4 | Managed Stack hosting? | **ZeroShot-hosted VPS only (v1)** | Operational simplicity; $49 SKU maps to ZeroVPS template |
| 5 | Rebrand ZeroRelay? | **Keep name** | Clear positioning; no confusion cost |
| 6 | Track priority? | **Parallel B + A** | Security is 1–2 weeks; GTM has no code dependency |
| 7 | Cloud before G1? | **Cloud prep only (scaffold)** after G0; **no Stripe** until G1 | Avoid building paid infra without demand signal |

**Action:** Owner replies ✅ or overrides in `docs/plans/open-decisions.md`.

---

## Sprint 1 definition of done

- [x] `bugfix/security-p0-auth-token` + B5 on `sprint-1/complete` → G0 ready for merge
- [x] `assets/demo.gif` in README
- [x] Waitlist page (`docs/waitlist/index.html`) — owner wires Formspree ID
- [x] Show HN draft approved
- [x] `blackboard.md` updated with gate status
- [x] Sprint 2 plan drafted (Cloud C1–C5)

---

## Verification commands

```bash
cd ZeroRelay
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v

# After security PR:
RELAY_TOKEN=test .venv/bin/python bridges/chat/cli.py --relay ws://localhost:8765
```

---

## Non-goals (Sprint 1)

- Stripe / billing integration  
- Full Cloud MVP (starts Sprint 2+)  
- Managed Stack SKU build  
- IdeaVault work  
- Native mobile chat  

---

*Next artifact after sign-off: implementation brief for `bugfix/security-p0-auth-token` (B1–B4 task cards for coding agent).*
