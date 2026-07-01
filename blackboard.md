# Blackboard — ZeroRelay Session Continuity

> Updated by agents at session start/end. Append-only for history sections.
> Schema: v1

## Current Status

| Field              | Value |
|--------------------|-------|
| **Last updated**   | 2026-07-01 |
| **Current focus**  | **Sprint 1 complete** — merge `sprint-1/complete` → post Show HN → G1 |
| **Active branch**  | `sprint-1/complete` |
| **Blocking issues**| Owner: set Formspree ID in `docs/waitlist/index.html`; merge PR to pass G0 |
| **Build status**   | 41/41 tests green (`unittest discover -s tests`) |
| **Gates**          | G0 🔄 (PR ready) · G1 🔄 (assets ready, post HN) · G2 ☐ · G3 ☐ · G4 ☐ |

## Planning Artifacts (2026-06-30)

| Document | Purpose |
|----------|---------|
| `docs/prd/zerorelay-product-prd.md` | Full product PRD v1.0 |
| `docs/plans/zerorelay-execution-handoff.md` | **Start here** — read order, tracks, gates |
| `docs/plans/zerorelay-phase-0-security-gtm-plan.md` | Security P0/P1 + launch validation (2–3 weeks) |
| `docs/plans/zerorelay-cloud-implementation-plan.md` | Cloud MVP build plan (8–10 weeks) |
| `docs/plans/zerorelay-managed-stack-plan.md` | ZeroVPS Managed Relay Stack SKU (Phase 2) |
| `docs/plans/zerorelay-analytics-schema.md` | Event schema for product metrics |
| `docs/plans/zerorelay-sprint-1-plan.md` | Sprint 1 task plan (complete) |
| `docs/plans/zerorelay-sprint-2-plan.md` | Sprint 2 Cloud C1–C5 kickoff |
| `docs/plans/open-decisions.md` | Owner sign-off tracker (all approved) |
| `docs/plans/community-seeding-drafts.md` | Post-HN community posts (A5) |

## In Progress

| Track | Task | Branch |
|-------|------|--------|
| Merge | PR `sprint-1/complete` → `main` | `sprint-1/complete` |
| GTM | Show HN post (Tue–Thu 9am ET) | — |
| GTM | Wire Formspree on waitlist page | `docs/waitlist/` |
| Cloud | C2 database models (Sprint 2) | `feature/cloud-mvp` (not started) |

## Active Decisions

### Product strategy — 2026-06-30
- ZeroRelay is the primary productization bet over IdeaVault (portfolio review).
- Open core stays MIT; monetize convenience + compliance.
- Golden path: Anthropic or OpenAI + Telegram + VPS self-host OR Cloud Solo.
- Cloud v1 is relay management + audit — not a native chat replacement.

### Locked decisions — 2026-07-01 (owner approved)
- Wedge: **Code Review Room**
- Cloud domain: **relay.zeroshot.studio**
- Dashboard auth beta: **GitHub OAuth only**
- Sprint 1: **parallel security + GTM**

### Cloud stack — 2026-06-30 (recommended in implementation plan)
- **Control plane API**: Python FastAPI + PostgreSQL + Stripe (same language family as relay).
- **Dashboard**: Next.js 15 App Router in `cloud/dashboard/` (reuse owner Next.js experience from IdeaVault).
- **Relay runtime**: One Docker container per workspace on VPS/K8s; OSS `core/zerorelay.py` unchanged.
- **Auth**: Auth.js v5 or Clerk — decision deferred to Cloud Step 1 spike (see cloud plan).

### Execution order — 2026-06-30
1. Phase 0 security P0 (blocks paid launch) — **complete, awaiting merge**.
2. Phase 0 GTM (demo GIF, HN, waitlist) — **assets shipped**.
3. Cloud MVP — C1 scaffold in `cloud/`; Sprint 2 starts C2.
4. Managed Stack — after Cloud Solo billing proven OR self-host demand validated.

## Blockers

### Formspree endpoint — 2026-07-01
Replace `YOUR_FORM_ID` in `docs/waitlist/index.html` after creating Formspree form.

### Demo GIF — 2026-07-01
`assets/demo.gif` is a generated placeholder (33KB). Replace with real Telegram recording per `demo-gif-storyboard.md` before HN if possible.

## Completed

### Sprint 1 complete — 2026-07-01
- B1–B5 security (P0 + P1 quick wins)
- GTM: demo GIF, README polish, waitlist page, HN approved, community drafts
- Cloud C1 scaffold (`cloud/api`, docker-compose)
- Sprint 2 plan

### Security P0 — 2026-07-01
- Header auth, test suite, all bridges updated

### Planning pushed to GitHub — 2026-07-01
- Branches: `cursor/zerorelay-product-prd-a48f`, `pm/phase-0-sprint-1`, `bugfix/security-p0-auth-token`

### Product planning pack — 2026-06-30
- Wrote comprehensive PRD, cloud implementation plan, Phase 0 plan, managed stack plan, analytics schema, execution handoff, and this blackboard.

## Lessons Learned

### IdeaVault portfolio review context — 2026-06-30
- IdeaVault is technically mature (65 tests, prod live) but has zero public feed traction.
- ZeroRelay has clearer B2D buyer, day-one utility, and active production usage on owner VPS.
- Do not carry IdeaVault scope patterns (social layer before users) into ZeroRelay GTM.
