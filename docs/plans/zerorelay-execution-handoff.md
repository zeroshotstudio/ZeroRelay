# ZeroRelay — Execution Handoff

**Date**: 2026-06-30  
**Audience**: Next implementation agent or owner session  
**Status**: Ready to execute  

---

## Read Order (mandatory)

1. `blackboard.md` — current status and locked decisions  
2. `docs/prd/zerorelay-product-prd.md` — product spec (skim handoff comment first)  
3. **This file** — pick a track and follow its plan  
4. Track-specific plan (see below)  
5. `SECURITY_REVIEW.md` — if touching auth, bridges, or cloud  

---

## Three Execution Tracks

Run **Track A + Track B security slice** in parallel if capacity allows. Do not start paid Cloud billing until Track B security gate passes.

| Track | Plan file | Duration | Outcome |
|-------|-----------|----------|---------|
| **A — GTM validation** | `zerorelay-phase-0-security-gtm-plan.md` §GTM | 2–3 weeks | 500 stars OR 100 waitlist signups |
| **B — Security gate** | `zerorelay-phase-0-security-gtm-plan.md` §Security | 1–2 weeks | P0 fixes merged + tests |
| **C — Cloud MVP** | `zerorelay-cloud-implementation-plan.md` | 8–10 weeks | Paying Solo beta users |
| **D — Managed Stack** | `zerorelay-managed-stack-plan.md` | 4–6 weeks after B | $49/mo SKU live |

**Recommended first sprint (2 weeks):**

```
Week 1: Track B Steps B1–B3 (P0 security) + Track A Step A1 (demo GIF script)
Week 2: Track B Step B4 (security tests) + Track A Steps A2–A3 (HN draft + waitlist page)
Gate:   Merge security PR → publish GIF → post Show HN
```

---

## Success Gates (do not skip)

| Gate | Criteria | Blocks |
|------|----------|--------|
| **G0 — OSS security** | All P0 items in SECURITY_REVIEW closed; new auth tests pass | Paid Cloud launch |
| **G1 — Demand signal** | 500 GitHub stars OR 100 waitlist emails OR 10 stranger installs (survey) | Cloud beta marketing spend |
| **G2 — Cloud alpha** | 5 beta workspaces with ≥2 agents connected ≥7 days | Stripe live |
| **G3 — Cloud beta** | 25 Solo subscribers OR 10 WARS/week | Team tier build |
| **G4 — Managed SKU** | 3 Managed Stack customers | Enterprise outreach |

---

## Repository Layout After Cloud Work Starts

```
ZeroRelay/
├── core/                    # OSS relay (unchanged license)
├── bridges/
├── cloud/
│   ├── api/                 # FastAPI control plane
│   ├── dashboard/           # Next.js admin UI
│   ├── relay-runner/        # Container entrypoint wrapping core/zerorelay.py
│   ├── migrations/          # Postgres (Alembic)
│   └── docker-compose.yml   # Local cloud dev stack
├── docs/
│   ├── prd/
│   └── plans/
├── tests/                   # OSS tests (extend with security tests)
└── blackboard.md
```

Keep OSS root install path working: `python3 setup.py` must not require `cloud/` deps.

---

## Branch Naming

| Work | Branch |
|------|--------|
| Security P0 | `bugfix/security-p0-auth-token` |
| GTM / docs only | `docs/gtm-phase-0` |
| Cloud MVP | `feature/cloud-mvp` |
| Managed stack | `feature/managed-stack-sku` |

Cloud agent convention: `cursor/<descriptive-name>-a48f`

---

## Verification Commands (OSS baseline)

```bash
cd ZeroRelay
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v

# After VPS access available:
./scripts/status-vps-json.sh
./scripts/deploy-vps.sh   # dry-run on staging first
```

---

## Non-Goals (repeat — do not scope creep)

- Replacing LangGraph / CrewAI / AutoGen  
- Building a native mobile chat app  
- IdeaVault-style social network features  
- Multi-region active-active relay in v1  
- Blockchain / proof-of-existence features  

---

## Open Questions for Owner (resolve before Cloud Step 3)

| # | Question | Default if no answer |
|---|----------|---------------------|
| 1 | Cloud domain | `relay.zeroshot.studio` subdomain initially |
| 2 | Vertical wedge landing page | Code Review Room |
| 3 | Auth provider for dashboard | GitHub OAuth only for beta |
| 4 | Managed Stack: ZeroShot-hosted VPS only? | Yes for v1 |

---

## Related Documents

| Doc | Path |
|-----|------|
| PRD | `docs/prd/zerorelay-product-prd.md` |
| Phase 0 | `docs/plans/zerorelay-phase-0-security-gtm-plan.md` |
| Cloud MVP | `docs/plans/zerorelay-cloud-implementation-plan.md` |
| Managed Stack | `docs/plans/zerorelay-managed-stack-plan.md` |
| Analytics | `docs/plans/zerorelay-analytics-schema.md` |
| VPS deploy | `docs/production-vps.md` |
| Dashboard contract | `docs/dashboard-control-plane.md` |

---

*Next action: `git checkout cursor/zerorelay-product-prd-a48f` (or main after merge) → execute Track B Step B1.*
