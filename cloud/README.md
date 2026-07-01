# ZeroRelay Cloud (scaffold)

Sprint 2+ implementation. See `docs/plans/zerorelay-cloud-implementation-plan.md`.

## Local dev

```bash
cd cloud
cp .env.example .env
docker compose up -d
curl http://localhost:8080/health
```

## Layout

| Path | Purpose |
|------|---------|
| `api/` | FastAPI control plane |
| `dashboard/` | Next.js admin UI (stub) |
| `relay-runner/` | Per-workspace Docker image |
| `migrations/` | Alembic (Sprint 2 C2) |

**Prerequisite:** G0 security merged. **Stripe:** after G1 demand signal.
