# Blackboard — ZeroRelay Session Continuity

> Updated by agents at session start/end. Append-only for history sections.
> Schema: v1

## Current Status

| Field              | Value |
|--------------------|-------|
| **Last updated**   | 2026-07-01 |
| **Current focus**  | **Sprint 1 (Phase 0)** — parallel security P0 (G0) + GTM assets (G1) |
| **Active branch**  | `pm/phase-0-sprint-1` (PM/planning); next impl: `bugfix/security-p0-auth-token` |
| **Blocking issues**| Owner sign-off on open decisions (`docs/plans/open-decisions.md`) — PM defaults apply until overridden |
| **Build status**   | OSS: `python3 -m unittest discover -s tests` expected green; no Cloud code yet |
| **Gates**          | G0 ☐ · G1 ☐ · G2 ☐ · G3 ☐ · G4 ☐ |

## Planning Artifacts (2026-06-30)

| Document | Purpose |
|----------|---------|
| `docs/prd/zerorelay-product-prd.md` | Full product PRD v1.0 |
| `docs/plans/zerorelay-execution-handoff.md` | **Start here** — read order, tracks, gates |
| `docs/plans/zerorelay-phase-0-security-gtm-plan.md` | Security P0/P1 + launch validation (2–3 weeks) |
| `docs/plans/zerorelay-cloud-implementation-plan.md` | Cloud MVP build plan (8–10 weeks) |
| `docs/plans/zerorelay-managed-stack-plan.md` | ZeroVPS Managed Relay Stack SKU (Phase 2) |
| `docs/plans/zerorelay-analytics-schema.md` | Event schema for product metrics |
| `docs/plans/zerorelay-sprint-1-plan.md` | **Sprint 1 task plan** (2 weeks, Jul 1–14) |
| `docs/plans/open-decisions.md` | Owner sign-off tracker |
| `docs/plans/demo-gif-storyboard.md` | GTM demo GIF shot list |
| `docs/plans/security-p0-impl-brief.md` | Coding agent handoff for B1–B4 |

## In Progress

| Track | Task | Branch |
|-------|------|--------|
| PM | Sprint 1 planning + day tracker | `pm/phase-0-sprint-1` |
| B — Security | B1–B4 awaiting impl agent | `bugfix/security-p0-auth-token` (not started) |
| A — GTM | A1 demo GIF storyboard ready; record pending owner | `docs/gtm-phase-0` (not started) |

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

### Owner sign-off on open decisions — 2026-07-01
PM defaults documented in `docs/plans/open-decisions.md`. Proceeding with Code Review Room wedge unless overridden.

### Demo GIF requires live relay — 2026-07-01
Owner or impl agent must run 2-agent setup (Telegram + Claude + Codex) for A1 recording. Storyboard ready.

## Completed

### Planning pushed to GitHub — 2026-07-01
- Branch `cursor/zerorelay-product-prd-a48f`: PRD + planning pack + Gemini CLI bridge merged on single branch.

### PM Sprint 1 kickoff — 2026-07-01
- Sprint plan, open decisions log, demo GIF storyboard, security P0 impl brief, PM day tracker (`.cursor/day-plan/`).

### Product planning pack — 2026-06-30
- Wrote comprehensive PRD, cloud implementation plan, Phase 0 plan, managed stack plan, analytics schema, execution handoff, and this blackboard.

## Lessons Learned

### IdeaVault portfolio review context — 2026-06-30
- IdeaVault is technically mature (65 tests, prod live) but has zero public feed traction.
- ZeroRelay has clearer B2D buyer, day-one utility, and active production usage on owner VPS.
- Do not carry IdeaVault scope patterns (social layer before users) into ZeroRelay GTM.
