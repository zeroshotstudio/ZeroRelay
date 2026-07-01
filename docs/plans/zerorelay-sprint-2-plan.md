# ZeroRelay Sprint 2 — Cloud MVP kickoff

**Dates:** 2026-07-15 → 2026-09-15 (8 weeks)  
**Prerequisite:** G0 merged, G1 demand signal in progress  
**Branch:** `feature/cloud-mvp`  
**Full plan:** `zerorelay-cloud-implementation-plan.md`

---

## Sprint 2 goals

| Goal | Steps | Exit |
|------|-------|------|
| Cloud scaffold live | C1–C2 | `docker compose up` + `/health` + DB migrated |
| Auth + workspaces | C3–C4 | GitHub OAuth; create workspace API |
| Relay provisioning | C5 | Container per workspace connects |
| Dashboard MVP | C7 | Workspace list, token rotate UI |
| Billing (after G1) | C9 | Stripe Solo $29/mo |

**Do not enable Stripe until G1** (500 stars OR 100 waitlist OR 10 stranger installs).

---

## Week-by-week (high level)

| Week | Focus | Steps |
|------|-------|-------|
| 1 | Scaffold + DB | C1, C2 |
| 2 | Auth | C3 |
| 3 | Workspace API + OpenAPI | C4 |
| 4 | Provisioner + relay runner | C5 |
| 5 | Audit ingest webhook | C6 |
| 6 | Dashboard pages | C7 |
| 7 | Usage limits | C8 |
| 8 | Stripe + beta onboarding | C9, C10, C12 |

---

## C1–C5 task cards

### C1 — Monorepo scaffold ✅ (started Sprint 1)
- `cloud/api/`, `cloud/docker-compose.yml`, `cloud/.env.example`
- FastAPI `/health` endpoint
- Verify: `cd cloud && docker compose up -d && curl localhost:8080/health`

### C2 — Database models
- SQLAlchemy models: users, workspaces, audit_*, subscriptions
- Alembic initial migration
- Verify: `alembic upgrade head`

### C3 — GitHub OAuth
- Auth.js in `cloud/dashboard/` (stub)
- FastAPI session validation
- Verify: login creates user row

### C4 — Workspace CRUD
- `POST/GET/DELETE /v1/workspaces`
- Generate relay token (show once), hash at rest
- Export `cloud/api/openapi.yaml`

### C5 — Relay provisioner
- `cloud/relay-runner/Dockerfile` (exists)
- `provision_workspace.py` starts container per slug
- Route `wss://relay.zeroshot.studio/ws/{slug}`

---

## Non-goals Sprint 2

- Team tier / SSO
- Multi-region
- Native mobile app
- IdeaVault integration

---

## Handoff to implementation agent

```
Read zerorelay-cloud-implementation-plan.md Steps C1–C5.
Branch: feature/cloud-mvp from main (after sprint-1/complete merges).
G0 must be merged. G1 recommended before C9 Stripe.
Start: C2 database models — C1 scaffold is in cloud/.
```
