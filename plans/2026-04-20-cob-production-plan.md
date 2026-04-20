# ZeroRelay COB Production Plan

**Date**: April 20, 2026
**Target**: Production-ready ZeroRelay by close of business on April 20, 2026
**Primary Repo**: `/Users/zeroshot/Dev/ZeroRelay`
**Supporting Repos**: `/Users/zeroshot/Dev/ZeroUI`, `/Users/zeroshot/Dev/ZeroVPS-test`
**Production Target**: `/opt/zerorelay` on the VPS, with Tailscale-first access

## Mission

Ship ZeroRelay as a stable relay product that can be reached from Mac, VPS, ZeroMini, and other personal platforms without relying on fragile foreground shells, `@latest` package pulls, or manual tunnel babysitting.

## Current State Audit

- Completed on April 20, 2026 during the initial production pass.
- Confirmed live local listener on `127.0.0.1:10531` is an unmanaged `node ... openai-oauth` process launched from `npx`.
- Confirmed live local listener on `127.0.0.1:18811` is an SSH tunnel process forwarding to the VPS Codex gateway.
- Confirmed there is no existing LaunchAgent coverage for the local OAuth relay or the remote bridge tunnels.
- Confirmed the VPS Codex gateway already exists as `zerovps-codex-gateway.service` and is healthy under systemd on the VPS, listening on `127.0.0.1:18811`.
- Confirmed the current local bootstrap script still uses `openai-oauth@latest`, which is the main upstream change risk on restart.

## Topology Decision For Today

- Keep the authoritative ZeroRelay broker on the VPS as the stable systemd-managed core.
- Keep the VPS Codex gateway loopback-only and systemd-managed today instead of redesigning production exposure mid-flight.
- Stabilize the Mac edge by pinning the local OAuth relay version and moving local long-lived processes under `launchd`.
- Replace manual tunnel babysitting with `launchd`-managed SSH processes plus keepalive options.
- Defer any Tailscale-direct gateway exposure change until after the stable COB cut unless the current tunnel approach blocks launch.

## Progress Log

### 2026-04-20 Midday Update

- Completed the live topology audit for the local OpenWebUI plus remote bridge path.
- Verified the VPS Codex gateway is already healthy under `zerovps-codex-gateway.service` on the VPS.
- Implemented the Mac-side stability layer in `ZeroUI`:
  - pinned `openai-oauth` to `1.0.2`
  - replaced runtime `@latest` fetch behavior with a local pinned install path
  - added `launchd` templates and install/uninstall scripts
  - added a foreground SSH tunnel runner with keepalive options
  - added a one-command local bridge health check
- Installed the local LaunchAgents and verified all four are loaded:
  - `com.zeroui.openai-oauth`
  - `com.zeroui.tunnel.zeromini-openclaw`
  - `com.zeroui.tunnel.zerovps-open-terminal`
  - `com.zeroui.tunnel.zerovps-codex-gateway`
- Verified post-cutover health:
  - local OAuth relay `/v1/models` is healthy on `127.0.0.1:10531`
  - Zee tunnel is healthy on `127.0.0.1:18789`
  - ZeroVPS terminal tunnel is healthy on `127.0.0.1:18810`
  - ZeroVPS Codex gateway tunnel is healthy on `127.0.0.1:18811`
- Verified restart recovery:
  - kicked `com.zeroui.openai-oauth` and `com.zeroui.tunnel.zerovps-codex-gateway`
  - re-ran the consolidated local health check successfully
  - refreshed Open WebUI cleanly through the new `refresh-open-webui-models.sh` command
- Added the repeatable VPS broker health command in the ops workspace:
  - `/Users/zeroshot/Dev/ZeroVPS-test/scripts/check-zerorelay-vps.sh`
- Wrote the validated cutover and recovery runbook:
  - `/Users/zeroshot/Dev/ZeroRelay/plans/2026-04-20-cutover-runbook.md`
- Performed one controlled production restart of `zerorelay` and verified:
  - all bridge services stayed active
  - broker listener came back cleanly
  - established relay sessions recovered after restart
- Recorded the production validation in `/Users/zeroshot/Dev/ZeroVPS-test/state/blackboard.md`

### 2026-04-20 Afternoon Update

- Imported the live VPS-only bridge artifacts into the repo so the production runtime layout is source-controlled:
  - `claude-bridge.py`
  - `zerobridge.py`
  - `zerorelay.service`
  - `zerobridge.service`
  - `claude-bridge.service`
  - `telegram-bridge.service`
- Added the production deployment path to the repo:
  - `/Users/zeroshot/Dev/ZeroRelay/scripts/deploy-vps.sh`
  - `/Users/zeroshot/Dev/ZeroRelay/docs/production-vps.md`
- Added a repeatable broker startup and broadcast smoke test in the repo:
  - `/Users/zeroshot/Dev/ZeroRelay/tests/test_broker_smoke.py`
- Validated the broker smoke test in a throwaway venv using `requirements.txt`
- Added the minimum machine-readable dashboard contract for today:
  - `/Users/zeroshot/Dev/ZeroRelay/scripts/status-vps-json.sh`
  - `/Users/zeroshot/Dev/ZeroRelay/docs/dashboard-control-plane.md`
- Verified the JSON status surface against the live VPS relay stack
- Added pinned VPS runtime dependency hardening:
  - `requirements.txt` now pins the production runtime packages
  - systemd units now target `/opt/zerorelay/venv/bin/python`
  - the staged deploy now creates or updates `/opt/zerorelay/venv`
- Locked the deployment rule for today:
  - `/opt/zerorelay` is a runtime directory
  - do not `git pull` inside `/opt/zerorelay`
  - staged release copies from the source repo are now the deployment path
- Ran the new staged deployment to production and verified:
  - a deploy backup was written to `/opt/zerorelay/backups/deploy-20260420T103409Z`
  - all managed runtime files and service units on the VPS match the repo after deploy
  - the broker and all six services are healthy after the controlled deploy restart
- Updated the VPS health check to include the full six-service production footprint, including `content-codex-bridge`
- Reframed the live `/opt/zerorelay` git state as informational only, because it is no longer the authoritative deployment source
- Completed the VPS runtime dependency hardening cutover:
  - created `/opt/zerorelay/venv`
  - pinned runtime packages to `websockets==16.0` and `httpx==0.28.1`
  - switched all six production services to `/opt/zerorelay/venv/bin/python`
  - validated backup `/opt/zerorelay/backups/deploy-20260420T105247Z`
- Strengthened the operator and dashboard status surfaces:
  - the VPS health check now asserts the venv interpreter path and pinned packages
  - the JSON dashboard contract now includes `runtime_python.path`, `runtime_python.version`, and pinned package versions
- Re-ran the broker smoke test against the pinned `requirements.txt` in a throwaway venv and it passed
- Revalidated one secondary platform path after the VPS venv cutover:
  - `check-local-bridge-services.sh` passed on the Mac
  - local `127.0.0.1:18811/health` returned `{"status":"ok"}`
  - local `127.0.0.1:10531/v1/models` still returned the expected Codex OAuth model list
  - `zero-ui-open-webui` remained `healthy`

## Scope Lock

Today is about shipping the relay product, not building every long-term platform feature.

### Must Be True By COB

- [x] The authoritative ZeroRelay broker is running stably on the VPS under systemd.
- [x] The local OpenWebUI or Codex-facing adapter path no longer depends on `npx -y openai-oauth@latest`.
- [x] Every long-lived relay-related process is supervised by `launchd`, `systemd`, or `systemd --user`.
- [x] Health checks exist for the broker and for every critical adapter path.
- [x] Recovery steps are documented and fast enough to run without guessing.
- [x] Smoke tests have been run locally and against the live VPS deployment.
- [x] Cross-platform access is Tailscale-first and does not require manual SSH tunnel babysitting in steady state.

### Explicitly Out Of Scope Today

- Public anonymous internet access to the raw relay.
- Multi-tenant auth, billing, or RBAC.
- Full database-backed event history and analytics if that delays the production cut.
- Dashboard polish beyond the minimum stable control-plane contract needed for management.

## Definition Of Done

ZeroRelay counts as "done for today" only if all of the following are true:

1. The VPS broker survives service restarts and reconnects cleanly.
2. The local management path survives shell closure or laptop session changes because it is service-managed.
3. Model or agent discovery is stable enough that OpenWebUI or the future dashboard can recover after relay restarts without mystery failures.
4. A fresh machine or new session can be bootstrapped from repo docs and scripts without tribal knowledge.
5. There is a clear rollback path for both the VPS deploy and the local adapter layer.

## 1. Baseline And Final Topology

- [x] Audit the current local OpenWebUI plus `openai-oauth` startup path.
- [x] Confirm what stays local today versus what moves to the VPS today.
- [x] Lock the production topology with the VPS ZeroRelay broker as the stable core.
- [x] Lock Tailscale as the default network boundary for the relay layer.
- [x] Prefer outward local adapter connections over brittle manual tunnels wherever possible.
- [x] Record ports, hostnames, and ownership for each moving part.

## 2. Repo Hardening In `ZeroRelay`

- [x] Add a production task-oriented install and health story, not just an interactive setup path.
- [x] Add macOS support for long-running local agents via `launchd`.
- [x] Add a machine-readable health or doctor command for repeatable checks.
- [x] Tighten dependency handling so installs are reproducible.
- [x] Add or expand smoke tests that validate the core relay startup path.
- [x] Update docs so "how to run this in production" is explicit.

## 3. Local Adapter Hardening

- [x] Replace any `@latest` runtime fetches with pinned installs or pinned wrappers.
- [x] Move the local OAuth or model adapter into a managed service.
- [x] Add a watchdog for the adapter health endpoint and a clear restart path.
- [x] Stabilize model discovery behavior for OpenWebUI after adapter restarts.
- [x] Eliminate manual SSH tunnels where possible; if one must remain today, make it self-healing.

## 4. VPS Production Hardening

- [x] Review the current `systemd` unit files and restart behavior.
- [x] Confirm the deploy flow from repo to `/opt/zerorelay`.
- [x] Add any missing health checks, status scripts, or operational runbook items.
- [x] Verify service ownership, permissions, env files, and restart sequencing.
- [x] Validate that all required bridge roles reconnect cleanly after a broker restart.

## 5. Dashboard And Control-Plane Contract

- [x] Define the minimum management surface the dashboard needs today.
- [x] Expose stable agent and health information for the dashboard to consume.
- [x] Keep the dashboard as a consumer of the relay boundary, not the owner of it.
- [ ] If the dashboard is deployed today, keep it behind auth and avoid exposing raw relay internals publicly.

## 6. Production Cutover

- [x] Create backups or rollback notes before changing the live VPS deployment.
- [x] Deploy the updated ZeroRelay repo to the VPS.
- [x] Restart services in a controlled order.
- [x] Run live smoke tests from the local machine.
- [x] Run live smoke tests from the VPS host.
- [x] Run live smoke tests from one secondary platform path if available.
- [x] Capture final validation notes and any follow-up debt.

## Ordered Execution Plan

1. Lock scope and final topology.
2. Fix the local instability sources first: pinned adapter version, service manager, health watchdog.
3. Harden the repo and operational scripts so the install path is repeatable.
4. Apply the VPS deployment changes and validate reconnect behavior.
5. Wire the minimum dashboard or control-plane contract needed for management.
6. Run end-to-end smoke tests and either ship or explicitly cut scope.

## Acceptance Checklist

- [x] No relay-critical process depends on a terminal window staying open.
- [x] No relay-critical process pulls an unpinned upstream version at runtime.
- [x] Broker health can be checked with one repeatable command.
- [x] Local adapter health can be checked with one repeatable command.
- [x] Restarting the broker does not leave clients permanently stranded.
- [x] Restarting the local adapter has a documented recovery path for OpenWebUI.
- [x] The VPS deployment path is documented and verified.
- [x] The rollback path is documented and verified enough to use under pressure.

## Risks To Watch

- OpenWebUI stale model discovery after relay or adapter restarts.
- Hidden assumptions in local-only auth files or user-specific paths.
- Tunnels that appear "up" but silently stop forwarding traffic.
- Shipping too much dashboard work before the relay boundary itself is stable.

## Defer If Time Gets Tight

- Persistent database-backed relay state.
- Rich analytics or historical dashboards.
- Public internet exposure beyond Tailscale plus authenticated proxy.
- Nice-to-have UI improvements that do not increase stability.

## End-Of-Day Deliverables

- [x] Updated ZeroRelay repo with the required production hardening changes.
- [x] Live production deployment on the VPS.
- [x] Local adapter layer stabilized and supervised.
- [x] A short deployment and recovery runbook.
- [x] Clear list of anything intentionally deferred after launch.
