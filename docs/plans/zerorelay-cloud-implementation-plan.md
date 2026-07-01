# Plan: ZeroRelay Cloud MVP — Implementation

**Date**: 2026-06-30  
**Complexity**: L  
**Duration**: 8–10 weeks  
**PRD reference**: §8.2, §9.6–9.7, §12.2, §13 Phase 1, §14  
**Prerequisite**: Phase 0 gate **G0** (security P0 merged)  
**Branch**: `feature/cloud-mvp`  

---

## Plan Summary

**Complexity**: L  
**Estimated steps**: 18  
**Stack decision (locked)**:

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Control plane API | **FastAPI** + **SQLAlchemy 2** + **Alembic** | Same language as relay; async-friendly; fast CRUD |
| Database | **PostgreSQL 16** | Workspaces, audit, billing metadata |
| Dashboard | **Next.js 15** App Router in `cloud/dashboard/` | Owner knows Next.js; SSR for marketing pages |
| Auth | **Auth.js v5** (GitHub OAuth) for dashboard; API keys for automation | Match IdeaVault patterns; defer SSO to Enterprise |
| Payments | **Stripe** Checkout + Customer Portal | Solo tier $29/mo |
| Relay runtime | **Docker** one container per workspace | Blast-radius isolation (PRD §12.3) |
| Reverse proxy | **Caddy** or existing nginx on VPS | TLS termination, WSS upgrade |
| Secrets | Workspace relay tokens hashed at rest (SHA-256); plaintext shown once on create/rotate |

---

## Architecture

```
cloud/dashboard (Next.js)  ──HTTPS──►  cloud/api (FastAPI :8080)
                                              │
                                              ├── Postgres
                                              ├── Stripe webhooks
                                              └── Relay provisioner
                                                      │
                                                      ▼
                                            docker run zerorelay-workspace-{id}
                                            WSS wss://relay.zeroshot.studio/ws/{workspace_slug}
```

**Event flow for transcript storage:**

Relay container emits JSON lines to stdout → sidecar collector OR relay patch posts to control plane ingest endpoint (`POST /internal/workspaces/{id}/events`). **v1 recommendation**: patch relay with optional `ZERORELAY_AUDIT_URL` webhook (minimal invasive) — implement in Step C6.

---

## Database Schema (v1)

```sql
-- users
id UUID PK, email UNIQUE, github_id UNIQUE NULL, created_at

-- workspaces
id UUID PK, user_id FK, name, slug UNIQUE, tier ENUM('solo','team'), 
relay_token_hash, relay_port INT NULL, status ENUM('provisioning','active','suspended'),
created_at

-- workspace_members (Phase 2 — stub table now)
workspace_id, user_id, role ENUM('admin','operator','viewer')

-- usage_counters (monthly rollup)
workspace_id, period_start, messages_count, mcp_calls_count, agent_slots_peak

-- audit_messages
id, workspace_id, ts, sender_role, content_length, content_redacted TEXT NULL, raw JSONB

-- audit_tool_calls
id, workspace_id, ts, caller, owner, tool_name, success BOOL, latency_ms, error_class NULL

-- subscriptions
workspace_id, stripe_customer_id, stripe_subscription_id, status, current_period_end
```

**Limits enforcement (Solo tier):**

| Limit | Value | Enforcement point |
|-------|-------|-------------------|
| Agent slots | 5 | Relay `ZERORELAY_ROLES` max connections |
| Messages/mo | 50,000 | Ingest counter; soft warn 90%; hard stop 100% |
| MCP calls/mo | 10,000 | Broker hook counts `mcp_tool_call` |
| Retention | 7 days | Cron purge `audit_*` |

---

## Implementation Steps

### Step C1 — Cloud monorepo scaffold

| Field | Value |
|-------|-------|
| **Files** | `cloud/api/`, `cloud/dashboard/`, `cloud/docker-compose.yml`, `cloud/.env.example`, `cloud/README.md` |
| **Create** | FastAPI skeleton with `/health`; Next.js app with `/` marketing stub; compose with Postgres |
| **Depends on** | G0 |
| **Verify** | `cd cloud && docker compose up -d && curl localhost:8080/health` |

### Step C2 — Database models + migrations

| Field | Value |
|-------|-------|
| **Files** | `cloud/api/models/`, `cloud/api/alembic/`, `cloud/api/database.py` |
| **Create** | SQLAlchemy models per schema above; initial Alembic migration |
| **Depends on** | C1 |
| **Verify** | `alembic upgrade head`; tables exist in Postgres |

### Step C3 — Auth (dashboard)

| Field | Value |
|-------|-------|
| **Files** | `cloud/dashboard/auth.ts`, `cloud/api/deps/auth.py`, `cloud/api/routes/auth.py` |
| **Create** | GitHub OAuth via Auth.js; session JWT validated by FastAPI via shared secret or session lookup |
| **Depends on** | C2 |
| **Verify** | Login flow creates `users` row; protected route returns 401 without session |

### Step C4 — Workspace CRUD API

| Field | Value |
|-------|-------|
| **Files** | `cloud/api/routes/workspaces.py` |
| **Endpoints** | `POST /v1/workspaces`, `GET /v1/workspaces`, `GET /v1/workspaces/{id}`, `DELETE /v1/workspaces/{id}` |
| **Behavior** | On create: generate `relay_token` (32 bytes hex), store hash, set status `provisioning`, enqueue provision job |
| **Depends on** | C3 |
| **Verify** | `curl -X POST` with auth creates row; response includes `relay_token` once + `wss_url` |

OpenAPI: generate `cloud/api/openapi.yaml` from FastAPI on this step.

### Step C5 — Relay provisioner

| Field | Value |
|-------|-------|
| **Files** | `cloud/relay-runner/Dockerfile`, `cloud/api/services/provisioner.py`, `cloud/api/scripts/provision_workspace.py` |
| **Behavior** | Start container: `ZERORELAY_ROLES=`, `RELAY_TOKEN=`, `ZERORELAY_AUDIT_URL=`, port mapped dynamically or path-based routing via reverse proxy |
| **Routing** | `wss://relay.zeroshot.studio/ws/{slug}` → upstream workspace container |
| **Depends on** | C4 |
| **Verify** | Create workspace → container running → `docker ps` shows `zerorelay-ws-{slug}`; bridge connects |

### Step C6 — Audit ingest (relay → control plane)

| Field | Value |
|-------|-------|
| **Files** | `core/zerorelay.py` (optional webhook), `cloud/api/routes/internal/ingest.py` |
| **Change** | When `ZERORELAY_AUDIT_URL` set, POST message/tool_call events (content optional/redacted) |
| **Privacy** | Default: store `content_length` + roles only; opt-in full transcript for Solo |
| **Depends on** | C5 |
| **Verify** | Send Telegram message → row appears in `audit_messages` within 5s |

### Step C7 — Dashboard MVP pages

| Field | Value |
|-------|-------|
| **Files** | `cloud/dashboard/app/(app)/overview/`, `agents/`, `tools/`, `transcript/`, `settings/` |
| **Pages** | Overview (status, usage bar), Agents (connected roles), Tools (MCP registry snapshot), Transcript (paginated), Settings (token rotate, WSS URL copy) |
| **Depends on** | C4, C6 |
| **Verify** | Manual: connect 2 bridges → dashboard updates within 30s |

Reuse JSON shape from `scripts/status-vps-json.sh` where applicable for Overview cards.

### Step C8 — Usage metering + limits

| Field | Value |
|-------|-------|
| **Files** | `cloud/api/services/usage.py`, `cloud/api/middleware/limits.py` |
| **Behavior** | Increment counters on ingest; relay checks `GET /internal/workspaces/{id}/limits` on interval OR push suspend flag |
| **Depends on** | C6 |
| **Verify** | Exceed test limit in dev → relay returns policy error message to bridges |

### Step C9 — Stripe integration

| Field | Value |
|-------|-------|
| **Files** | `cloud/api/routes/billing.py`, `cloud/dashboard/app/settings/billing/`, Stripe webhook handler |
| **Products** | Solo $29/mo — create in Stripe dashboard; store price ID in env |
| **Flow** | Checkout → webhook `checkout.session.completed` → activate workspace tier |
| **Depends on** | C4 |
| **Verify** | Stripe test mode checkout → subscription row → limits applied |

### Step C10 — Token rotation

| Field | Value |
|-------|-------|
| **Files** | `cloud/api/routes/workspaces.py`, provisioner reload |
| **Endpoint** | `POST /v1/workspaces/{id}/tokens/rotate` |
| **Behavior** | New token, restart relay container, invalidate old connections |
| **Depends on** | C5, C7 |
| **Verify** | Old token rejected; new token works |

### Step C11 — Cloud deploy pipeline

| Field | Value |
|-------|-------|
| **Files** | `cloud/scripts/deploy-cloud.sh`, `docs/cloud-production.md` |
| **Target** | VPS or separate cloud host; Caddy TLS; Postgres managed or on-box |
| **Depends on** | C5–C10 |
| **Verify** | Deploy to staging; smoke test end-to-end |

### Step C12 — Beta onboarding

| Field | Value |
|-------|-------|
| **Files** | `docs/cloud-beta-runbook.md` |
| **Process** | Invite 25 waitlist users; free 90 days; feedback form |
| **Depends on** | C11, G1 |
| **Verify** | Gate G2: 5 workspaces active 7+ days |

### Steps C13–C18 — Beta hardening (weeks 8–10)

| Step | Task |
|------|------|
| C13 | Error monitoring (Sentry) for API + dashboard |
| C14 | Backup strategy for Postgres |
| C15 | GDPR: export/delete user endpoint |
| C16 | Load test: 50 concurrent WSS connections across 10 workspaces |
| C17 | Documentation: "Connect your bridges to Cloud" guide |
| C18 | Gate G3 review: 25 paying OR 10 WARS/week |

---

## API Contract (OpenAPI summary)

Full spec generated at `cloud/api/openapi.yaml` in Step C4.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Liveness |
| POST | `/v1/workspaces` | Session | Create workspace |
| GET | `/v1/workspaces` | Session | List |
| GET | `/v1/workspaces/{id}` | Session | Detail + usage |
| DELETE | `/v1/workspaces/{id}` | Session | Tear down container + data |
| POST | `/v1/workspaces/{id}/tokens/rotate` | Session | Rotate relay token |
| GET | `/v1/workspaces/{id}/agents` | Session | Connected agents snapshot |
| GET | `/v1/workspaces/{id}/tools` | Session | MCP registry snapshot |
| GET | `/v1/workspaces/{id}/messages` | Session | Paginated audit messages |
| GET | `/v1/workspaces/{id}/tool-calls` | Session | Paginated MCP audit |
| GET | `/v1/usage` | Session | Current period vs limits |
| POST | `/v1/billing/checkout` | Session | Stripe Checkout session |
| POST | `/webhooks/stripe` | Stripe sig | Subscription events |
| POST | `/internal/workspaces/{id}/events` | HMAC internal | Relay audit ingest |

---

## Testing Requirements

| Area | Tests |
|------|-------|
| API | `cloud/api/tests/` pytest: workspace CRUD, auth, limits |
| Provisioner | Integration test with Docker socket (CI optional) |
| OSS relay | Extend `tests/test_auth_security.py` for audit webhook |
| Dashboard | Playwright smoke: login → create workspace → see overview |
| Billing | Stripe webhook fixture tests |

Run before each release:

```bash
python3 -m unittest discover -s tests -v          # OSS
cd cloud/api && pytest                             # Control plane
cd cloud/dashboard && npm run lint && npm run build
```

---

## Dependencies (verify versions at install time)

| Package | Purpose |
|---------|---------|
| fastapi | Control plane API |
| uvicorn[standard] | ASGI server |
| sqlalchemy[asyncio] | ORM |
| alembic | Migrations |
| asyncpg | Postgres driver |
| pydantic-settings | Config |
| stripe | Billing |
| httpx | Internal calls |
| next, next-auth | Dashboard |
| docker SDK (Python) | Provisioner |

---

## Risks

| Risk | Mitigation |
|------|------------|
| One container per workspace doesn't scale cheaply | Cap beta seats; optimize density in Phase 2 |
| Relay patch for audit forks OSS | Optional env flag; upstream to MIT core |
| WSS routing complexity | Start with path-based Caddy; one domain |
| Stripe + GDPR | Privacy policy before beta; minimal PII |

---

## Off-Limits

- Do not move OSS relay to proprietary license
- Do not require Cloud for self-host `setup.py` path
- Do not store LLM API keys in control plane (bridges stay client-side)

---

## Commit Strategy

| Milestone | Commit prefix | Example |
|-----------|---------------|---------|
| Scaffold | `feat(cloud):` | `feat(cloud): add api and dashboard scaffold` |
| Workspace API | `feat(cloud):` | `feat(cloud): workspace CRUD and provisioning` |
| Billing | `feat(cloud):` | `feat(cloud): stripe solo tier` |
| OSS audit hook | `feat(relay):` | `feat(relay): optional audit webhook` |

Phase: execute

---

*Prerequisite plan: `zerorelay-phase-0-security-gtm-plan.md`. Next phase: `zerorelay-managed-stack-plan.md` after Gate G3.*
