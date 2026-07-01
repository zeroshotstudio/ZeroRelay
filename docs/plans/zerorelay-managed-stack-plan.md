# Plan: ZeroRelay Managed Relay Stack (ZeroVPS SKU)

**Date**: 2026-06-30  
**Complexity**: M  
**Duration**: 4–6 weeks  
**PRD reference**: §8.3, §13 Phase 2  
**Prerequisite**: Phase 0 gate **G0** + either **G1** (demand) OR **G2** (cloud alpha working)  
**Branch**: `feature/managed-stack-sku`  

---

## Product Definition

**SKU name**: ZeroRelay Managed Stack  
**Tagline**: Private multi-agent command center on your VPS — deployed, secured, and monitored.

**What the customer gets:**

| Included | Detail |
|----------|--------|
| VPS provisioning | New VPS or onboard existing (Tailscale mesh) |
| ZeroRelay broker | systemd-managed, pinned venv, staged deploy |
| Golden-path bridges | Anthropic OR OpenAI + Telegram (customer API keys) |
| TLS / access | Tailscale-first; optional public WSS via nginx |
| Monitoring | Health checks, restart on failure, monthly patch apply |
| Setup call | 30-min onboarding (optional higher tier) |

**What the customer brings:**

- Anthropic and/or OpenAI API keys
- Telegram bot token (if using Telegram interface)
- Domain optional (Tailscale sufficient for v1)

---

## Pricing (draft — validate with 3 design partners)

| Tier | Price | Includes |
|------|-------|----------|
| **Setup + Self-manage** | $199 one-time | Deploy + 1hr handoff doc |
| **Managed** | $49/mo | Monitoring, patches, backup config, email support 48h |
| **Managed Pro** | $99/mo | + second VPS staging slot, priority support 24h |

Billing: Stripe (reuse Cloud Stripe account) or manual invoice for first 3 customers.

---

## Architecture

```
Customer devices (phone/laptop)
        │
        ▼ Tailscale
┌───────────────────────────────────────┐
│  Customer VPS (or ZeroShot-provisioned)│
│  /opt/zerorelay                        │
│  ├── zerorelay.service                 │
│  ├── claude-bridge / openai-bridge     │
│  └── telegram-bridge                   │
└───────────────────────────────────────┘
        │
        ▼ optional
ZeroShot monitoring cron (SSH or Tailscale)
  └── scripts/status-vps-json.sh → alert if unhealthy
```

**Not included in v1:** Multi-tenant Cloud control plane. Each Managed Stack is an isolated VPS — same as current owner production topology documented in `plans/2026-04-20-cob-production-plan.md`.

---

## Implementation Steps

### Step M1 — Productized setup profile in `setup.py`

| Field | Value |
|-------|-------|
| **Files** | `setup.py`, `profiles/managed-stack.json` (create) |
| **Change** | Add `--profile managed-stack` preset: Anthropic + Telegram + Tailscale bind + systemd install + health check |
| **Depends on** | G0 |
| **Verify** | `./setup.py --profile managed-stack --from-env` on clean Ubuntu VM succeeds |

### Step M2 — Managed deploy runbook

| Field | Value |
|-------|-------|
| **Files** | `docs/managed-stack-runbook.md` (create) |
| **Content** | Prerequisites, API key collection checklist, deploy steps, verification, rollback, customer handoff PDF outline |
| **Depends on** | M1 |
| **Verify** | Follow runbook on staging VPS end-to-end |

### Step M3 — ZeroVPS integration

| Field | Value |
|-------|-------|
| **Files** | `ZeroVPS-template` repo (separate PR): skill or command `/deploy-zerorelay-stack` |
| **Change** | Document in ZeroVPS: clone ZeroRelay → `deploy-vps.sh` → `setup.py --profile managed-stack` |
| **Depends on** | M2 |
| **Verify** | ZeroVPS `/quick-deploy` style flow from fresh VPS in <30 min |

### Step M4 — Monitoring + alerting

| Field | Value |
|-------|-------|
| **Files** | `scripts/monitor-stack.sh` (create), `docs/monitoring.md` |
| **Behavior** | Cron every 5 min: run `status-vps-json.sh`; if broker down or bridge inactive → webhook/email |
| **Depends on** | M2 |
| **Verify** | Kill zerorelay service → alert fires within 10 min |

### Step M5 — Customer-facing docs + landing section

| Field | Value |
|-------|-------|
| **Files** | `docs/managed-stack.md`, README section "Managed Stack" |
| **Content** | Pricing table, what's included, FAQ, link to waitlist/contact |
| **Depends on** | M1–M4 |
| **Verify** | Non-technical reader can understand offer |

### Step M6 — Billing + fulfillment workflow

| Field | Value |
|-------|-------|
| **Files** | `docs/managed-stack-fulfillment.md` |
| **Process** | Stripe payment → intake form (API keys via secure channel, NOT email plaintext) → schedule deploy → handoff call → monthly check |
| **Security** | Use one-time secret link (1Password share, Tailscale serve form) for API keys |
| **Depends on** | M5 |
| **Verify** | Dry-run with friend/fake customer |

### Step M7 — First 3 design partners

| Field | Value |
|-------|-------|
| **Goal** | 3 paying Managed customers at $49/mo or discounted $29 beta |
| **Success** | All 3 stacks healthy 30 days; collect testimonial quote |
| **Depends on** | M6, G1 |
| **Verify** | Gate G4 |

---

## Support Boundaries (document clearly)

**In scope:**

- ZeroRelay broker + included bridges uptime
- systemd service recovery
- Security patch apply for ZeroRelay repo
- Tailscale connectivity troubleshooting

**Out of scope:**

- Customer LLM API billing or rate limits
- Custom bridge development (bill separately)
- Non-ZeroRelay apps on same VPS (best-effort only)

---

## Risks

| Risk | Mitigation |
|------|------------|
| Support load scales linearly | Cap Managed customers until runbook proven |
| Customer API keys mishandled | Never store keys; customer enters on VPS via SSH |
| VPS variance | Support Ubuntu 22.04/24.04 only for v1 |

---

## Relationship to Cloud

| | Managed Stack | Cloud Solo |
|--|---------------|------------|
| Infra | Customer/ZeroShot VPS | ZeroShot multi-tenant |
| Data residency | Customer-controlled | ZeroShot-controlled |
| Buyer | Ops-averse power user | Fastest time to value |
| Margin | Lower scale, higher touch | Higher scale, lower touch |

Both can coexist. Managed is **not** a fallback for Cloud — different buyer psychographics.

---

*Execute after Cloud alpha OR if GTM shows strong self-host demand with "deploy for me" requests in waitlist survey.*
