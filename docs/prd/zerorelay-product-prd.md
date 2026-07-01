<!--
═══════════════════════════════════════════════════════════════════════════════
 AGENT HANDOFF NOTES — READ FIRST
═══════════════════════════════════════════════════════════════════════════════

Context
-------
This PRD was drafted on 2026-06-30 during an IdeaVault portfolio review session.
The owner decided IdeaVault has strong engineering but weak GTM traction, and
ZeroRelay is the preferred productization bet. This document captures the full
commercial product vision for ZeroRelay (OSS core → hosted cloud → managed VPS →
enterprise). It was written from a cloned copy of the repo in a cloud workspace;
switch to the ZeroRelay repo before executing against it.

Repo
----
  GitHub : https://github.com/zeroshotstudio/ZeroRelay
  License: MIT (open core)
  Local  : clone and work from ZeroRelay root (not IdeaVault)

What already exists (do NOT re-spec from scratch)
-------------------------------------------------
  ✓ WebSocket relay broker           core/zerorelay.py
  ✓ MCP Tool Broker                  core/mcp_registry.py
  ✓ AI bridges (Claude/GPT/Gemini/Ollama/OpenClaw/Claude Code)
  ✓ Chat bridges (Telegram/Discord/Slack/CLI)
  ✓ Interactive setup wizard         setup.py
  ✓ VPS production deploy            scripts/deploy-vps.sh, docs/production-vps.md
  ✓ Status JSON contract             scripts/status-vps-json.sh, docs/dashboard-control-plane.md
  ✓ CI + unit/integration tests      tests/
  ✓ Security review baseline         SECURITY_REVIEW.md (2026-03-07, 7.5/10)
  ✓ Production cutover runbook       plans/2026-04-20-cutover-runbook.md

What this PRD adds (net-new product work)
-----------------------------------------
  □ ZeroRelay Cloud (multi-tenant hosted relay + dashboard)
  □ Billing (Stripe) and tier enforcement
  □ Web dashboard (workspace management, agent registry, audit log)
  □ Auth model for cloud (API keys, orgs, SSO in enterprise tier)
  □ Security hardening items from SECURITY_REVIEW.md (P0 before paid launch)
  □ Bridge marketplace / certified bridge packs
  □ ZeroVPS "Managed Relay Stack" SKU bundling
  □ Vertical wedge landing pages (code review room, content pipeline, etc.)
  □ Marketing site separate from README
  □ Analytics/telemetry for product metrics in §8

Recommended next session workflow
---------------------------------
  1. Read this PRD end-to-end.
  2. Read SECURITY_REVIEW.md — Phase 0 security gate blocks paid launch.
  3. Run: python3 -m unittest discover -s tests && ./scripts/status-vps-json.sh (if VPS access)
  4. Pick ONE execution track:
       Track A — GTM validation (demo GIF, HN post, waitlist) — §16 Phase 0
       Track B — Cloud MVP (auth + dashboard + hosted relay) — §13 Phase 1
       Track C — Managed VPS bundle with ZeroVPS-template — §13 Phase 2
  5. Read blackboard.md and docs/plans/zerorelay-execution-handoff.md (planning pack complete 2026-06-30).
  6. Do NOT scope-creep into LangGraph replacement — ZeroRelay is transport, not orchestration.

Planning pack (2026-06-30)
----------------------------
  ✓ blackboard.md
  ✓ docs/plans/zerorelay-execution-handoff.md       ← start here
  ✓ docs/plans/zerorelay-phase-0-security-gtm-plan.md
  ✓ docs/plans/zerorelay-cloud-implementation-plan.md
  ✓ docs/plans/zerorelay-managed-stack-plan.md
  ✓ docs/plans/zerorelay-analytics-schema.md
  ✓ docs/plans/show-hn-draft.md

Sections marked INCOMPLETE in this PRD
--------------------------------------
  §10.2 — Exact Stripe price IDs and regional tax handling
  §11.4 — Enterprise SLA numbers (TBD with first design partner)
  §14   — Full OpenAPI spec (generated during Cloud Step C4 — see cloud plan)
  §17   — Competitive pricing research table (needs fresh April–June 2026 refresh)

Decision log (locked for v1 unless owner overrides)
---------------------------------------------------
  • Open core stays MIT; paid tiers sell convenience + compliance, not relay code.
  • Golden path for v1 GTM: Anthropic or OpenAI + Telegram + VPS self-host OR Cloud Solo.
  • Do not block OSS on cloud launch; ship security fixes to OSS first.
  • ZeroRelay Cloud v1 is NOT a chat UI — it is relay management + audit. Chat stays in Telegram/Slack/CLI.
  • Cross-model MCP tool broker remains the primary differentiator in all positioning.

Owner contact for open questions
--------------------------------
  zeroshot / ZeroShot Studio — validate wedge choice (§5.2) before building vertical landing pages.

═══════════════════════════════════════════════════════════════════════════════
-->

# PRD: ZeroRelay — Multi-Agent Coordination Platform

**Product**: ZeroRelay  
**Author**: ZeroShot Studio  
**Date**: 2026-06-30  
**Status**: Draft v1.0  
**Priority**: P0  
**License (OSS core)**: MIT  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Product Thesis & Vision](#3-product-thesis--vision)
4. [Target Users & Personas](#4-target-users--personas)
5. [Market Context & Positioning](#5-market-context--positioning)
6. [Goals & Success Metrics](#6-goals--success-metrics)
7. [Current State (OSS Baseline)](#7-current-state-oss-baseline)
8. [Product Lines & Packaging](#8-product-lines--packaging)
9. [Feature Specifications](#9-feature-specifications)
10. [Business Model & Pricing](#10-business-model--pricing)
11. [Go-To-Market Strategy](#11-go-to-market-strategy)
12. [Technical Architecture](#12-technical-architecture)
13. [Implementation Phases](#13-implementation-phases)
14. [API & Control Plane Contract](#14-api--control-plane-contract)
15. [Security & Compliance](#15-security--compliance)
16. [Non-Functional Requirements](#16-non-functional-requirements)
17. [Competitive Analysis](#17-competitive-analysis)
18. [Risks & Mitigations](#18-risks--mitigations)
19. [Out of Scope (v1)](#19-out-of-scope-v1)
20. [Open Questions](#20-open-questions)
21. [Appendix A — Glossary](#appendix-a--glossary)
22. [Appendix B — Related Documents](#appendix-b--related-documents)

---

## 1. Executive Summary

ZeroRelay is a **real-time coordination layer for multi-agent AI systems**. It puts agents from different model vendors into a shared conversation room, routes @-mentions between them, and — critically — exposes an **MCP Tool Broker** so agents can invoke each other's tools as structured JSON across model boundaries.

Most multi-agent setups today use shared files, blackboards, or heavyweight orchestration frameworks (LangGraph, CrewAI, AutoGen). Those approaches work but are often slow, brittle, single-vendor, and over-engineered for individuals and small teams who want agents to collaborate the way humans do in Slack.

ZeroRelay's commercial strategy is **open core**:

| Layer | What it is | Monetization |
|-------|------------|--------------|
| **ZeroRelay OSS** | Self-hosted relay + bridges + MCP broker | Free (MIT) — adoption & community |
| **ZeroRelay Cloud** | Managed relay, dashboard, audit log, RBAC | Subscription (Solo / Team) |
| **Managed Relay Stack** | ZeroVPS-deployed private instance, monitored | Subscription or one-time setup fee |
| **ZeroRelay Enterprise** | On-prem, SSO, compliance pack, SLA | Custom annual contract |

The near-term wedge is **developers and AI-native operators** who already run multiple agents and need them to talk — from a phone via Telegram, from a VPS via systemd, or from a managed cloud workspace without operating WebSocket infrastructure.

**Why now**: Multi-agent orchestration is a recognized market category (2026). Teams are adopting agent frameworks at scale, but cross-vendor, human-in-the-loop coordination remains awkward. ZeroRelay occupies the **transport + tool-routing primitive** layer — complementary to, not competitive with, LangGraph-style workflow engines.

---

## 2. Problem Statement

### 2.1 The coordination gap

Building multi-agent systems in 2026 typically looks like this:

```
Agent A writes output to a file or DB
        ↓
Orchestrator polls or triggers Agent B
        ↓
Agent B parses natural language to guess what to do
        ↓
Repeat (slow, lossy, vendor-locked)
```

Pain points:

| Pain | Impact |
|------|--------|
| **Indirect communication** | Agents "leave notes" instead of collaborating in real time |
| **Orchestrator bottlenecks** | Rigid turn-taking; hard to inject human steering mid-flow |
| **Single-vendor tool silos** | Claude tools stay in Claude; GPT tools stay in GPT |
| **High setup cost** | LangGraph/CrewAI learning curve for simple "two agents, one room" use cases |
| **No mobile-native control plane** | Hard to steer agents from a phone without custom work |
| **Fragile self-host ops** | WebSocket relays, tunnel babysitting, `@latest` npm pulls, manual restarts |

### 2.2 What users actually want

From production usage (owner's VPS stack, April 2026 COB cutover):

> "I want Claude and GPT in one thread. I want to @-mention whoever I need. I want GPT to call Claude's tools when it needs a test run — without me copy-pasting. I want it stable on my VPS and reachable from Telegram."

That is a **coordination** problem, not a **workflow DSL** problem.

### 2.3 Why existing tools don't fully solve it

| Category | Examples | Gap ZeroRelay fills |
|----------|----------|---------------------|
| Agent frameworks | LangGraph, CrewAI, AutoGen | Workflow/state-machine first; cross-vendor chat + MCP broker not native |
| Chat platforms | Slack, Discord | No agent tool broker; not model-aware |
| MCP servers | Individual tool servers | No cross-agent routing or multi-model room semantics |
| Agent gateways | TrueFoundry, LangSmith | Enterprise governance above frameworks — different layer |

ZeroRelay is **the group chat + tool RPC bus** — a primitive that frameworks can sit on top of or that individuals can use directly.

---

## 3. Product Thesis & Vision

### 3.1 One-line thesis

**ZeroRelay is Slack for your AI agents — with cross-model tool calling built in.**

### 3.2 Core behaviors (v1 success path)

1. Operator connects two or more AI backends to one relay room.
2. Operator sends `@claude build X` from Telegram (or CLI/Slack/Discord).
3. Claude responds; optionally delegates `@gpt review this`.
4. GPT invokes `claude/run_tests` via MCP broker — structured, not parsed from chat.
5. Operator sees the full transcript and can intervene at any point.
6. System runs reliably under systemd on a VPS (or managed cloud) without manual tunnel babysitting.

### 3.3 Strategic principles

1. **Transport, not orchestration** — do not rebuild LangGraph; integrate with it where useful.
2. **Cross-vendor by default** — model mix is a feature, not an edge case.
3. **Human-in-the-loop native** — chat bridges are first-class, not afterthoughts.
4. **Private by default** — Tailscale/self-host friendly; cloud is opt-in convenience.
5. **Minimal core** — relay stays small, auditable, dependency-light.
6. **Monetize convenience & compliance** — never paywall the MIT relay core.

### 3.4 Long-term vision (24 months)

ZeroRelay becomes the **default coordination substrate** for small teams running heterogeneous agent stacks: open source for hackers, cloud for teams who want zero-ops, enterprise for regulated environments, and a bridge ecosystem for vertical workflows (code review, content, DevOps triage).

---

## 4. Target Users & Personas

### Persona 1: Indie AI Builder (Primary — B2D)

| Field | Detail |
|-------|--------|
| **Who** | Solo developer, indie hacker, AI consultant |
| **Stack** | Claude Code + GPT API + Ollama + Telegram |
| **Job to be done** | Run a private "agent command center" without writing orchestration code |
| **Willingness to pay** | $29–49/mo for managed hosting OR free self-host on existing VPS |
| **Acquisition** | GitHub, HN, AI Twitter, r/LocalLLaMA |

### Persona 2: Small Product Team (Secondary — Team tier)

| Field | Detail |
|-------|--------|
| **Who** | 3–10 person startup building AI-assisted workflows |
| **Stack** | Multiple API keys, shared Slack/Telegram ops channel |
| **Job to be done** | Shared agent room with audit trail and access control |
| **Willingness to pay** | $99–299/mo Team tier |
| **Acquisition** | Word of mouth, integration partners, vertical wedge landing pages |

### Persona 3: Platform / DevTools Engineer (Tertiary — OSS contributor)

| Field | Detail |
|-------|--------|
| **Who** | Engineer extending MCP bridges or embedding relay in larger systems |
| **Job to be done** | Stable WebSocket + MCP routing primitive with clear extension API |
| **Willingness to pay** | OSS free; may convert to Enterprise for support/SLA |
| **Acquisition** | MCP ecosystem, GitHub contributors, framework integrators |

### Persona 4: Regulated Ops Lead (Enterprise — later)

| Field | Detail |
|-------|--------|
| **Who** | IT lead at finance/legal/health org exploring internal agents |
| **Job to be done** | On-prem relay, SSO, audit, air-gap, approved bridge allowlist |
| **Willingness to pay** | $10k–100k+/yr |
| **Acquisition** | Direct outreach, design partners, ZeroVPS enterprise bundle |

### Anti-personas (v1)

- **Non-technical consumers** who want a ChatGPT wrapper — not the buyer.
- **Fortune 500 batch orchestration teams** who need LangGraph-grade checkpointing as primary — they may use ZeroRelay as a bus, not as primary purchase driver in v1.

---

## 5. Market Context & Positioning

### 5.1 Market timing

- Multi-agent orchestration is a named category in analyst coverage (2026).
- MCP is standardizing tool exposure across the industry.
- Developers are running **multiple model subscriptions** simultaneously (Claude Pro + ChatGPT + local Ollama).
- Agent framework adoption is high for prototyping; production pain shifts to **reliability, cross-vendor coordination, and human steering**.

### 5.2 Positioning statement

**For** developers and small teams **who** run multiple AI agents across vendors,  
**ZeroRelay** is a real-time coordination platform **that** combines group-chat semantics with cross-model MCP tool routing,  
**Unlike** LangGraph/CrewAI **which** optimize workflow graphs and role-based crews,  
**ZeroRelay** delivers immediate human-in-the-loop multi-agent collaboration with minimal setup.

### 5.3 Vertical wedges (marketing skins on same core)

Pick **one** for initial GTM; same relay underneath:

| Wedge | Headline | Agent roles |
|-------|----------|-------------|
| **Code Review Room** | "Two-model code review in one Telegram thread" | Implementer + Reviewer |
| **Content Pipeline** | "Research → draft → edit agents" | Researcher + Writer + Editor |
| **DevOps Triage** | "Logs agent + fix agent + deploy agent" | Observer + Fixer + Deployer |

**INCOMPLETE**: Owner should confirm wedge before building dedicated landing pages (see handoff notes).

### 5.4 Relationship to ZeroVPS

ZeroVPS-template is the **deployment rail** for self-hosters. ZeroRelay Managed Stack is a **productized SKU**:

```
ZeroVPS /quick-deploy + ZeroRelay setup.py + monitoring = Managed Relay Stack
```

Cross-promote: every ZeroVPS user is a ZeroRelay prospect; every ZeroRelay self-hoster is a ZeroVPS prospect.

---

## 6. Goals & Success Metrics

### 6.1 North star metric

**Weekly Active Relay Sessions (WARS)** — distinct relay rooms with ≥1 human-initiated message and ≥2 connected agent bridges in a 7-day window.

### 6.2 Phase metrics

| Phase | Timeframe | Metric | Target |
|-------|-----------|--------|--------|
| **Phase 0 — Validation** | 0–8 weeks | GitHub stars | 500 |
| | | External self-host installs (survey/waitlist) | 50 |
| | | Demo video views | 5,000 |
| **Phase 1 — Cloud beta** | 2–4 months | Paying Cloud Solo customers | 25 |
| | | Cloud relay uptime | 99.5% |
| | | Free → paid conversion | 5% of active free cloud trials |
| **Phase 2 — Team & Managed** | 4–8 months | Team workspaces | 10 |
| | | Managed VPS stacks sold | 20 |
| | | MRR | $5,000 |
| **Phase 3 — Enterprise pipeline** | 8–12 months | Enterprise design partners | 2 |
| | | Bridge marketplace downloads/week | 200 |

### 6.3 Product health metrics

| Metric | Target | Notes |
|--------|--------|-------|
| MCP tool call success rate | > 98% | Excludes owner-disconnected errors |
| Bridge reconnect time (p95) | < 10s | After broker restart |
| Broker message latency (p95) | < 100ms | Same-region self-host |
| Support tickets per 100 users | < 5/mo | Post-cloud launch |

### 6.4 Analytics event schema — INCOMPLETE

Minimum events to instrument (Cloud + optional OSS telemetry opt-in):

```
relay.session.started
relay.agent.connected        { role, bridge_type }
relay.message.sent           { source_role, tagged_roles[], channel }
relay.mcp.tool_call          { caller, owner, tool, success, latency_ms }
relay.mcp.tool_error         { error_class }
cloud.workspace.created
cloud.subscription.started   { tier }
```

Full schema, PII policy, and retention windows — **TBD in implementation plan**.

---

## 7. Current State (OSS Baseline)

As of 2026-06-30, the open-source repository delivers:

### 7.1 Core platform

| Component | Status | Location |
|-----------|--------|----------|
| WebSocket relay broker | ✅ Production | `core/zerorelay.py` |
| MCP Tool Broker | ✅ Production | `core/mcp_registry.py` |
| Bridge base class (reconnect, loop prevention, MCP) | ✅ Production | `core/base_bridge.py` |
| AI bridges (6 backends) | ✅ Production | `bridges/ai/` |
| Chat bridges (4 interfaces) | ✅ Production | `bridges/chat/` |
| Loop prevention (3 layers) | ✅ Production | Tag-gating, self-skip, meta filter |
| Interactive setup | ✅ Production | `setup.py` |
| VPS deploy pipeline | ✅ Production | `scripts/deploy-vps.sh` |
| Status JSON for dashboards | ✅ Production | `scripts/status-vps-json.sh` |
| CI test suite | ✅ Production | `tests/` |
| Security review | ⚠️ 7.5/10 | `SECURITY_REVIEW.md` — P0 fixes required before paid launch |

### 7.2 Production topology (owner reference)

Documented in `plans/2026-04-20-cob-production-plan.md`:

- Authoritative broker on VPS (`zerorelay.service`) via Tailscale
- Bridges: `zerobridge`, `claude-bridge`, `codex-bridge`, `content-codex-bridge`, `telegram-bridge`
- Mac edge: launchd-managed tunnels + pinned OAuth relay (ZeroUI repo)
- Runtime directory: `/opt/zerorelay` (staged deploy, not git pull in place)

### 7.3 Known gaps vs this PRD

| Gap | Priority |
|-----|----------|
| Security P0 items (token handling, constant-time compare) | P0 |
| Cloud multi-tenant relay | P1 |
| Web dashboard | P1 |
| Billing | P1 |
| Bridge marketplace | P2 |
| Enterprise SSO / compliance pack | P3 |

---

## 8. Product Lines & Packaging

### 8.1 ZeroRelay OSS (MIT)

**Includes:**

- Relay broker + MCP Tool Broker
- All current AI and chat bridges
- `setup.py` wizard (interactive, auto, from-env)
- systemd unit templates
- VPS deploy script
- Documentation and examples

**Excludes (paid or separate repos):**

- Hosted infrastructure
- Web dashboard (beyond status JSON script)
- Audit log retention > 7 days
- RBAC / org management
- Certified bridge packs (may have free community + paid certified)

### 8.2 ZeroRelay Cloud

**Value proposition:** "Your agent room, without running WebSocket infra."

| Capability | Solo | Team | Enterprise |
|------------|------|------|------------|
| Managed relay endpoint (WSS) | ✅ | ✅ | ✅ |
| Workspaces | 1 | 5 | Unlimited |
| Connected agent slots | 5 | 25 | Custom |
| Messages / month | 50,000 | 500,000 | Custom |
| MCP tool calls / month | 10,000 | 100,000 | Custom |
| Message history retention | 7 days | 30 days | Custom |
| Audit log export | ❌ | ✅ CSV | ✅ + SIEM |
| RBAC | ❌ | ✅ | ✅ |
| SSO | ❌ | ❌ | ✅ SAML/OIDC |
| Uptime SLA | Best effort | 99.5% | 99.9% **TBD** |
| Support | Community | Email 48h | Dedicated **TBD** |

**Cloud is NOT a chat replacement.** Users still interact via Telegram/Slack/CLI bridges pointed at their cloud relay URL.

### 8.3 ZeroRelay Managed Relay Stack (ZeroVPS bundle)

**Value proposition:** "Private agent command center on your VPS — we deploy and monitor it."

Includes:

- ZeroVPS provisioning (or customer VPS onboarding)
- ZeroRelay + golden-path bridges pre-configured
- Tailscale mesh setup
- systemd + health checks
- Monthly monitoring + security patch apply (optional tier)

Target price: **$49/mo managed** or **$199 one-time setup + $29/mo monitoring** — **INCOMPLETE: validate with first 3 customers**.

### 8.4 ZeroRelay Enterprise

**Value proposition:** "On-prem multi-agent coordination with compliance."

Includes everything in Team plus:

- Air-gap / on-prem install package
- SSO (SAML/OIDC)
- Bridge allowlist policy engine
- Immutable audit log
- Custom SLA and support channel
- Professional services for custom bridges

Pricing: **custom annual contract** — target $15k+ ACV.

---

## 9. Feature Specifications

### 9.1 Relay broker (OSS — maintain & harden)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| R-001 | Broadcast chat messages to all connected roles except sender | P0 |
| R-002 | Route @-tagged messages to tagged AI bridges only | P0 |
| R-003 | Support configurable `RELAY_TOKEN` auth on WebSocket upgrade | P0 |
| R-004 | Reject connections with invalid/missing token when auth enabled | P0 |
| R-005 | Expose broker health: connected roles, connection count, uptime | P0 |
| R-006 | Survive broker restart with bridges reconnecting automatically | P0 |
| R-007 | Rate limit MCP register/call/message floods per role | P1 |
| R-008 | Support TLS termination at reverse proxy (nginx/caddy) | P1 |

**Acceptance criteria:**

- `tests/test_broker_smoke.py` passes after every deploy.
- Controlled broker restart recovers all bridge services within 60s (validated in COB runbook).

### 9.2 MCP Tool Broker (OSS — core differentiator)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| M-001 | Agents register tools on connect via `mcp_register` | P0 |
| M-002 | Tools namespaced as `{owner}/{tool_name}` | P0 |
| M-003 | Callers use namespaced name; owners receive plain name | P0 |
| M-004 | Route `mcp_tool_call` point-to-point with `call_id` correlation | P0 |
| M-005 | Return structured errors for: unknown tool, owner offline, timeout, self-call | P0 |
| M-006 | Broadcast `mcp_tools_updated` on register/unregister/disconnect | P0 |
| M-007 | Configurable timeout via `ZERORELAY_MCP_TIMEOUT` (default 30s) | P0 |
| M-008 | Auto-unregister tools when owner disconnects | P0 |
| M-009 | MCP rate limiting per role | P1 |
| M-010 | Tool call audit hook for Cloud tier (callback/event emission) | P1 |

**Acceptance criteria:**

- `tests/test_mcp_registry.py` and `tests/test_mcp_integration.py` pass.
- Cross-bridge call: GPT bridge calls `claude/run_tests` and receives JSON result in integration test.

### 9.3 AI bridges (OSS — extend)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| A-001 | Each bridge implements `_sync_generate()` for model calls | P0 |
| A-002 | Each bridge declares `tags[]` for @-mention routing | P0 |
| A-003 | Each bridge supports MCP tool registration and `on_tool_call()` | P0 |
| A-004 | Exponential backoff reconnect to relay | P0 |
| A-005 | Loop prevention: ignore untagged, self, and meta messages | P0 |
| A-006 | OpenAI-compatible base URL override (`OPENAI_BASE_URL`) | P1 |
| A-007 | Documented template for custom bridges (`Build Your Own Bridge`) | P1 |
| A-008 | Bridge health metric export for dashboard | P2 |

**New bridges (post-v1 roadmap):**

- `bridges/ai/mistral_api.py`
- `bridges/tools/github.py`, `postgres.py`, `sentry.py` (marketplace candidates)

### 9.4 Chat bridges (OSS — maintain)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| C-001 | Telegram: sticky addressing, `/status`, `/reset`, `/killswitch` | P0 |
| C-002 | Telegram: user ID whitelist (`TELEGRAM_USER_ID`) | P0 |
| C-003 | Discord + Slack: user/channel allowlist (security gap — see §15) | P1 |
| C-004 | Telegram: chunk messages >4096 chars | P1 |
| C-005 | CLI: send `RELAY_TOKEN` correctly when auth enabled | P0 (security fix) |
| C-006 | All chat bridges: typing/stream indicators where supported | P2 |

### 9.5 Setup & deployment (OSS)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| D-001 | `setup.py` interactive wizard with health check | P0 |
| D-002 | `setup.py --auto` and `--from-env` for CI/unattended | P0 |
| D-003 | Creates dedicated `zerorelay` system user | P0 |
| D-004 | `deploy-vps.sh` staged release to `/opt/zerorelay` | P0 |
| D-005 | `setup.py --check`, `--upgrade`, `--uninstall` | P0 |
| D-006 | Pin runtime deps in `/opt/zerorelay/venv` — no `@latest` in prod | P0 |
| D-007 | One-command demo GIF script for README | P1 (GTM) |

### 9.6 ZeroRelay Cloud — Control plane (net-new)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| CL-001 | User signup/login (email + OAuth GitHub) | P1 |
| CL-002 | Create workspace → provision isolated relay namespace | P1 |
| CL-003 | Issue workspace-scoped relay token + WSS URL | P1 |
| CL-004 | Dashboard: connected agents, live connection count | P1 |
| CL-005 | Dashboard: registered MCP tools by agent | P1 |
| CL-006 | Message history viewer (retention per tier) | P1 |
| CL-007 | MCP tool call log with success/error/latency | P1 |
| CL-008 | Usage metering against tier limits | P1 |
| CL-009 | Stripe subscription management | P1 |
| CL-010 | Team invites + role-based access (admin/operator/viewer) | P2 |
| CL-011 | Webhook notifications (agent disconnect, killswitch triggered) | P2 |
| CL-012 | API keys for programmatic workspace management | P2 |

**User flow (Cloud Solo):**

```
1. Sign up at cloud.zerorelay.io (domain TBD)
2. Create workspace "my-lab"
3. Copy WSS URL + token
4. Run: RELAY_URL=wss://... RELAY_TOKEN=... python3 bridges/ai/anthropic_api.py
5. Run: python3 bridges/chat/telegram.py (configured with same relay)
6. Dashboard shows connected agents within 30s
7. Send Telegram message → see transcript in dashboard
```

### 9.7 Web dashboard (net-new)

**MVP pages:**

| Page | Purpose |
|------|---------|
| Overview | Broker status, connected agents, alerts |
| Agents | List roles, bridge type, connected since, last message |
| Tools | MCP registry across agents |
| Transcript | Searchable message history |
| Tool calls | MCP audit table |
| Settings | Token rotation, tier usage, billing link |
| Team | Invites, roles (Team tier+) |

**Design note:** Reuse JSON contract from `status-vps-json.sh` as internal API shape where possible — dashboard already partially specified in `docs/dashboard-control-plane.md`.

### 9.8 Bridge marketplace (post-cloud)

**Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| BM-001 | Bridge package spec: `zerorelay-bridge.yaml` manifest | P2 |
| BM-002 | Community directory in GitHub org | P2 |
| BM-003 | "Certified" badge for tested bridges | P3 |
| BM-004 | Paid bridge packs (Postgres, GitHub, Jira) | P3 |

---

## 10. Business Model & Pricing

### 10.1 Pricing philosophy

- **Free OSS** drives adoption and trust.
- **Paid tiers** charge for ops burden removed (hosting, audit, RBAC) — not for relay source code.
- **Never tax tokens** — Anthropic/OpenAI keep inference revenue.

### 10.2 Proposed pricing (v1 — INCOMPLETE)

| Tier | Monthly | Annual (2 mo free) | Primary limit |
|------|---------|-------------------|---------------|
| **OSS Self-Host** | $0 | $0 | Your infra |
| **Cloud Solo** | $29 | $290 | 1 workspace, 5 agents, 50k msgs |
| **Cloud Team** | $99 | $990 | 5 workspaces, 25 agents, 500k msgs |
| **Managed Stack** | $49 | $490 | 1 VPS, monitoring included |
| **Enterprise** | Custom | Custom | On-prem, SSO, SLA |

**Overage (Cloud):**

- +$5 per 10k messages
- +$5 per 5k MCP tool calls

**Stripe product/price IDs:** TBD — **INCOMPLETE**

### 10.3 Revenue projections (illustrative, not forecast)

| Milestone | Customers | ARPU | MRR |
|-----------|-----------|------|-----|
| Beta | 25 Solo | $29 | $725 |
| PMF signal | 50 Solo + 10 Team | blended ~$40 | $2,450 |
| Scale target | 100 Solo + 25 Team + 5 Managed | blended ~$45 | ~$6,000+ |

---

## 11. Go-To-Market Strategy

### 11.1 Phase 0 — Awareness (weeks 1–8)

**Objective:** Prove developers want this.

| Action | Detail |
|--------|--------|
| README demo GIF | Record Telegram multi-agent session (30–60s) |
| Launch post | Hacker News: "Show HN: ZeroRelay — group chat for AI agents with cross-model MCP tools" |
| Community | r/LocalLLaMA, AI Twitter/X, Discord servers (MCP, LangChain) |
| Waitlist | Simple page: email + "how many agents do you run?" survey |
| Docs | "ZeroRelay vs LangGraph" honest comparison page |

**Success gate:** 500 GitHub stars OR 100 waitlist signups → proceed to Cloud beta.

### 11.2 Phase 1 — Cloud beta (months 2–4)

| Action | Detail |
|--------|--------|
| Private beta | 25 users from waitlist, free for 90 days |
| Case studies | 3 written stories (code review room, content pipeline, VPS ops) |
| Pricing live | Stripe Solo tier |
| Security | All P0 items from SECURITY_REVIEW.md closed |

### 11.3 Phase 2 — Team + Managed (months 4–8)

| Action | Detail |
|--------|--------|
| Team tier launch | RBAC + audit export |
| ZeroVPS bundle | `/quick-deploy zerorelay-stack` documentation + SKU page |
| Bridge marketplace v0 | Community repo template |
| Conference talks | Local meetups, MCP workshops |

### 11.4 Phase 3 — Enterprise (months 8–12)

| Action | Detail |
|--------|--------|
| Design partners | 2 regulated or high-trust orgs |
| SSO + compliance pack | SOC2 prep if revenue justifies |
| Partner channel | ZeroVPS consultants, AI agencies |

### 11.5 Messaging pillars

1. **"Agents that actually talk to each other."**
2. **"Cross-model tool calling, not copy-paste."**
3. **"From Telegram to VPS in 15 minutes."**
4. **"Transport, not orchestration."**

---

## 12. Technical Architecture

### 12.1 OSS architecture (current)

```
┌─────────────────────────────────────────────────────────┐
│                    Chat Bridges                          │
│   Telegram │ Discord │ Slack │ CLI                      │
└────────────────────────┬────────────────────────────────┘
                         │ WebSocket
┌────────────────────────▼────────────────────────────────┐
│              ZeroRelay Broker (:8765)                    │
│  • Message broadcast                                     │
│  • @-mention routing                                     │
│  • MCP Tool Broker (register / call / result)            │
└────────────────────────┬────────────────────────────────┘
                         │ WebSocket
┌────────────────────────▼────────────────────────────────┐
│                    AI Bridges                            │
│  Claude Code │ Anthropic │ OpenAI │ Gemini │ Ollama │ …  │
└─────────────────────────────────────────────────────────┘
```

### 12.2 Cloud architecture (target)

```
                    ┌──────────────────┐
                    │  cloud.zerorelay │
                    │  (Next.js or     │
                    │   static + API)  │
                    └────────┬─────────┘
                             │ HTTPS
                    ┌────────▼─────────┐
                    │  Control Plane   │
                    │  API + Postgres  │
                    │  Stripe webhooks │
                    └────────┬─────────┘
                             │ provisions
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   Workspace A          Workspace B          Workspace C
   relay pod            relay pod            relay pod
   (isolated token)     (isolated token)     (isolated token)
         ▲                   ▲                   ▲
         │ WSS               │ WSS               │ WSS
    Customer bridges    Customer bridges    Customer bridges
```

**Isolation requirements:**

- Unique relay token per workspace
- Network isolation between workspace relay processes (separate containers or namespaces)
- No cross-workspace message leakage under any failure mode
- Encryption in transit (TLS 1.2+); encryption at rest for audit logs

### 12.3 Multi-tenancy strategy

**v1 recommendation:** One relay process (or container) per workspace — simple blast-radius isolation. Optimize density later.

### 12.4 Integration with agent frameworks

ZeroRelay should publish **integration guides**, not framework forks:

| Framework | Integration pattern |
|-----------|---------------------|
| LangGraph | LangGraph node posts to relay; relay responses trigger graph transitions |
| CrewAI | Each crew agent runs as a bridge role |
| Custom Python | Subclass `AIBridge` |

---

## 13. Implementation Phases

### Phase 0 — Security & GTM prep (2–3 weeks)

| Task | Owner | Exit criteria |
|------|-------|---------------|
| Fix P0 security items | Engineering | SECURITY_REVIEW HIGH items closed |
| CLI token auth fix | Engineering | CLI connects with RELAY_TOKEN set |
| Demo GIF + README polish | Marketing/Dev | GIF in README |
| HN launch draft | Marketing | Post ready |
| `blackboard.md` init | Agent ops | Session continuity in ZeroRelay repo |

### Phase 1 — Cloud MVP (8–10 weeks)

| Task | Exit criteria |
|------|---------------|
| Control plane API (auth, workspaces, tokens) | User can create workspace via API |
| Relay provisioning automation | Workspace gets WSS URL in <60s |
| Dashboard MVP (overview, agents, transcript) | Beta user can view live session |
| Stripe Solo tier | Paid signup works |
| Usage metering | Limits enforced with graceful errors |
| Beta with 25 users | ≥10 WARS/week across beta cohort |

### Phase 2 — Team + Managed (6–8 weeks)

| Task | Exit criteria |
|------|---------------|
| RBAC + team invites | 2 roles minimum: admin, viewer |
| Audit log export | CSV download |
| Managed Stack runbook | ZeroVPS deploy doc + pricing page |
| Discord/Slack allowlists | Security review ≥8.5/10 |

### Phase 3 — Enterprise & marketplace (ongoing)

| Task | Exit criteria |
|------|---------------|
| SSO | SAML test with IdP |
| Bridge marketplace template | 3 community bridges published |
| Enterprise design partner | 1 paid pilot |

---

## 14. API & Control Plane Contract

### 14.1 Existing stable contract (OSS)

`scripts/status-vps-json.sh` output — documented in `docs/dashboard-control-plane.md`.

**Stable keys:** `generated_at`, `deployment_mode`, `runtime_python`, `runtime_git`, `broker`, `services`, `gateways`

### 14.2 Future HTTP API (Cloud) — outline INCOMPLETE

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/v1/workspaces` | List workspaces |
| POST | `/v1/workspaces` | Create workspace |
| GET | `/v1/workspaces/{id}` | Workspace detail + WSS URL |
| POST | `/v1/workspaces/{id}/tokens/rotate` | Rotate relay token |
| GET | `/v1/workspaces/{id}/agents` | Connected agents |
| GET | `/v1/workspaces/{id}/tools` | MCP registry |
| GET | `/v1/workspaces/{id}/messages` | Paginated transcript |
| GET | `/v1/workspaces/{id}/tool-calls` | MCP audit log |
| GET | `/v1/usage` | Current period usage vs limits |

Full OpenAPI 3.1 spec — **to be generated in implementation plan**.

---

## 15. Security & Compliance

### 15.1 P0 — Must fix before Cloud paid launch

From `SECURITY_REVIEW.md`:

| # | Issue | Fix |
|---|-------|-----|
| 1 | Token compare not constant-time | `secrets.compare_digest` |
| 2 | Token in WebSocket query string | Move to header/subprotocol |
| 3 | CLI bridge ignores RELAY_TOKEN | Pass token on connect |

### 15.2 P1 — Fix in first Cloud release

| # | Issue |
|---|-------|
| 4 | Telegram HTML escaping incomplete |
| 5 | No rate limit on Telegram `/killswitch` |
| 6 | Rate limit race in relay |
| 7 | Claude Code recursive retry unbounded |
| 8 | OpenClaw token in process list |

### 15.3 P2 — Hardening

| # | Issue |
|---|-------|
| 9 | Discord/Slack no user whitelist |
| 10 | Telegram message chunking |
| 11 | MCP tools_updated broadcast scope |

### 15.4 Cloud-specific security

| Requirement | Detail |
|-------------|--------|
| Tenant isolation | No shared tokens; separate relay processes |
| Token rotation | User-initiated + automatic on leak suspicion |
| Audit immutability | Append-only tool call log (Team+) |
| Secrets management | Vault or cloud KMS for workspace tokens |
| DDoS | Rate limits at edge + per-workspace |
| Data retention | Configurable; default per tier in §8.2 |

### 15.5 Compliance roadmap

| Standard | When |
|----------|------|
| SOC 2 Type I | After $20k MRR or first enterprise deal |
| GDPR | Privacy policy + data export/delete at Cloud launch |
| HIPAA | Out of scope unless enterprise healthcare partner |

---

## 16. Non-Functional Requirements

| Category | Requirement |
|----------|---------------|
| **Availability** | Cloud Solo: 99.5% monthly uptime |
| **Latency** | Broker broadcast p95 <100ms same-region |
| **Scalability** | 1,000 concurrent connections per relay pod (initial target) |
| **Recoverability** | Broker restart ≤60s to full bridge recovery |
| **Observability** | Structured logs, connection metrics, MCP call metrics |
| **Portability** | OSS runs on Linux/macOS; Python 3.12+ |
| **Dependencies** | Core relay: `websockets` only; bridges optional deps |
| **Backward compatibility** | MCP message types must remain backward compatible for bridges |

---

## 17. Competitive Analysis

| Product | Layer | Strength vs ZeroRelay | ZeroRelay advantage |
|---------|-------|----------------------|---------------------|
| **LangGraph** | Workflow engine | Production graphs, checkpointing | Simpler; cross-vendor chat native; faster time-to-demo |
| **CrewAI** | Role-based crews | Rapid prototyping | Real-time; MCP cross-calls; human chat bridges |
| **AutoGen / MS Agent Framework** | Conversational agents | Azure ecosystem | Vendor-neutral; lighter weight |
| **OpenAI Swarm** | Handoff pattern | OpenAI-native | Multi-vendor; self-host; MCP broker |
| **Discord/Slack bots** | Chat | Ubiquitous | Agent-aware routing; tool broker |
| **Custom WebSocket hub** | DIY | Full control | Batteries included; bridges; setup wizard |

**INCOMPLETE:** Refresh with pricing and feature matrices from LangGraph Cloud, CrewAI enterprise offerings (Q2 2026).

---

## 18. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| "Just use LangGraph" objection | High | Medium | Position as transport; publish integration guides |
| Security incident before hardening | Medium | High | Phase 0 security gate blocks paid launch |
| Cloud ops burden underestimated | Medium | High | Start with Solo beta; one relay pod per workspace |
| Bridge matrix support explosion | High | Medium | Golden path only in v1; community for long tail |
| Low conversion OSS → paid | Medium | Medium | Managed Stack for ops-averse users |
| MCP spec changes | Low | Medium | Version broker protocol; abstraction layer |
| Competitor ships similar broker | Medium | Medium | Move fast on brand + cloud convenience |

---

## 19. Out of Scope (v1)

- Built-in LLM inference (users bring API keys)
- Visual workflow editor / node canvas
- Replacing Telegram/Slack with native chat app
- Mobile native apps
- Blockchain anchoring or proof-of-existence features (that's IdeaVault)
- Multi-region active-active relay (single region v1)
- Real-time voice/video agent rooms
- Automatic agent task planning without human @-mentions (unless user configures)

---

## 20. Open Questions

| # | Question | Owner | Blocking |
|---|----------|-------|----------|
| 1 | Which vertical wedge for launch marketing? | zeroshot | Phase 0 GTM |
| 2 | Cloud domain: `cloud.zerorelay.io` vs subdomain of zeroshot.studio? | zeroshot | Phase 1 |
| 3 | Build cloud control plane in Python (match stack) or TypeScript (dashboard speed)? | Engineering | Phase 1 |
| 4 | Managed Stack: ZeroShot-operated VPS only or customer BYO VPS? | zeroshot | Phase 2 |
| 5 | Keep ZeroRelay name or rebrand (ZeroBridge, ZeroRoom)? | zeroshot | Marketing |
| 6 | Telemetry opt-in for OSS installs? | Engineering + Legal | Phase 1 |
| 7 | First enterprise design partner target vertical? | zeroshot | Phase 3 |

---

## Appendix A — Glossary

| Term | Definition |
|------|------------|
| **Relay** | WebSocket message broker connecting bridges |
| **Bridge** | Adapter connecting an AI backend or chat interface to the relay |
| **Role** | Unique identifier for a connected bridge (e.g. `claude`, `gpt`) |
| **MCP Tool Broker** | ZeroRelay component routing cross-agent tool calls |
| **Namespaced tool** | Tool reference `{owner}/{tool_name}` in MCP calls |
| **WARS** | Weekly Active Relay Sessions (north star metric) |
| **Golden path** | Recommended v1 setup: 1 API provider + Telegram + VPS or Cloud |

---

## Appendix B — Related Documents

| Document | Path | Purpose |
|----------|------|---------|
| README | `/README.md` | User-facing product overview |
| Security Review | `/SECURITY_REVIEW.md` | Pre-launch security gate |
| VPS Production Deploy | `/docs/production-vps.md` | Self-host deploy runbook |
| Dashboard Control Plane | `/docs/dashboard-control-plane.md` | Status JSON contract |
| COB Production Plan | `/plans/2026-04-20-cob-production-plan.md` | April 2026 production topology |
| Cutover Runbook | `/plans/2026-04-20-cutover-runbook.md` | Recovery procedures |
| ZeroVPS Template | `github.com/zeroshotstudio/ZeroVPS-template` | Deployment rail |
| IdeaVault PRD (reference) | Separate repo — portfolio comparison context only |
| Execution handoff | `docs/plans/zerorelay-execution-handoff.md` |
| Phase 0 plan | `docs/plans/zerorelay-phase-0-security-gtm-plan.md` |
| Cloud MVP plan | `docs/plans/zerorelay-cloud-implementation-plan.md` |
| Managed Stack plan | `docs/plans/zerorelay-managed-stack-plan.md` |
| Analytics schema | `docs/plans/zerorelay-analytics-schema.md` |
| Show HN draft | `docs/plans/show-hn-draft.md` |
| Session state | `blackboard.md` |

---

*End of PRD v1.0 — Draft. Implementation plans: see `docs/plans/zerorelay-execution-handoff.md`.*
