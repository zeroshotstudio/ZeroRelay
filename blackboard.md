# Blackboard — ZeroRelay Session Continuity

> Updated by agents at session start/end. Append-only for history sections.
> Schema: v1

## Current Status

| Field              | Value |
|--------------------|-------|
| **Last updated**   | 2026-06-30 |
| **Current focus**  | Planning complete — ready to execute Phase 0 (security + GTM) in parallel with Cloud MVP prep |
| **Blocking issues**| GitHub push from cloud agent failed (403) — owner must push branch locally |
| **Build status**   | OSS: `python3 -m unittest discover -s tests` expected green; no Cloud code yet |

## Planning Artifacts (2026-06-30)

| Document | Purpose |
|----------|---------|
| `docs/prd/zerorelay-product-prd.md` | Full product PRD v1.0 |
| `docs/plans/zerorelay-execution-handoff.md` | **Start here** — read order, tracks, gates |
| `docs/plans/zerorelay-phase-0-security-gtm-plan.md` | Security P0/P1 + launch validation (2–3 weeks) |
| `docs/plans/zerorelay-cloud-implementation-plan.md` | Cloud MVP build plan (8–10 weeks) |
| `docs/plans/zerorelay-managed-stack-plan.md` | ZeroVPS Managed Relay Stack SKU (Phase 2) |
| `docs/plans/zerorelay-analytics-schema.md` | Event schema for product metrics |

## In Progress

None — planning session only.

## Active Decisions

### Product strategy — 2026-06-30
- ZeroRelay is the primary productization bet over IdeaVault (portfolio review).
- Open core stays MIT; monetize convenience + compliance.
- Golden path: Anthropic or OpenAI + Telegram + VPS self-host OR Cloud Solo.
- Cloud v1 is relay management + audit — not a native chat replacement.

### Cloud stack — 2026-06-30 (recommended in implementation plan)
- **Control plane API**: Python FastAPI + PostgreSQL + Stripe (same language family as relay).
- **Dashboard**: Next.js 15 App Router in `cloud/dashboard/` (reuse owner Next.js experience from IdeaVault).
- **Relay runtime**: One Docker container per workspace on VPS/K8s; OSS `core/zerorelay.py` unchanged.
- **Auth**: Auth.js v5 or Clerk — decision deferred to Cloud Step 1 spike (see cloud plan).

### Execution order — 2026-06-30
1. Phase 0 security P0 (blocks paid launch) — can start immediately on OSS repo.
2. Phase 0 GTM (demo GIF, HN, waitlist) — parallel, no code dependency.
3. Cloud MVP — start after P0 security merged OR in parallel if separate `cloud/` tree.
4. Managed Stack — after Cloud Solo billing proven OR self-host demand validated.

## Blockers

### Cloud agent cannot push to GitHub — 2026-06-30
Branch `cursor/zerorelay-product-prd-a48f` exists locally with planning commits. Owner must:
```bash
git push -u origin cursor/zerorelay-product-prd-a48f
```

### Wedge choice for vertical landing pages — open
Owner must pick one before building wedge-specific marketing (see PRD §5.2):
- Code Review Room (recommended default in handoff)
- Content Pipeline
- DevOps Triage

## Completed

### Product planning pack — 2026-06-30
- Wrote comprehensive PRD, cloud implementation plan, Phase 0 plan, managed stack plan, analytics schema, execution handoff, and this blackboard.

## Lessons Learned

### IdeaVault portfolio review context — 2026-06-30
- IdeaVault is technically mature (65 tests, prod live) but has zero public feed traction.
- ZeroRelay has clearer B2D buyer, day-one utility, and active production usage on owner VPS.
- Do not carry IdeaVault scope patterns (social layer before users) into ZeroRelay GTM.
