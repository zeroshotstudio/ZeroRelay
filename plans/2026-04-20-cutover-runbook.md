# ZeroRelay April 20 Cutover Runbook

## Purpose

This runbook captures the commands that were validated during the April 20, 2026 stabilization push.

## Local Mac Edge

The local Open WebUI edge now runs in supervised mode through `launchd`.

### Install Or Reinstall The Local Services

```bash
cd /Users/zeroshot/Dev/ZeroUI
./scripts/install-local-bridge-services.sh
```

This installs and starts:

- `com.zeroui.openai-oauth`
- `com.zeroui.tunnel.zeromini-openclaw`
- `com.zeroui.tunnel.zerovps-open-terminal`
- `com.zeroui.tunnel.zerovps-codex-gateway`

### Health Check The Local Services

```bash
cd /Users/zeroshot/Dev/ZeroUI
./scripts/check-local-bridge-services.sh
```

Expected result:

- all four LaunchAgents show as loaded
- `OpenAI OAuth relay ... ok`
- `Zee OpenClaw tunnel ... ok`
- `ZeroVPS Codex gateway tunnel ... ok`
- `ZeroVPS terminal tunnel ... ok`

### Refresh Open WebUI After Bridge Restarts

If Open WebUI keeps a stale model list after a bridge restart:

```bash
cd /Users/zeroshot/Dev/ZeroUI
./scripts/refresh-open-webui-models.sh
```

Expected result:

- `zero-ui-open-webui` returns to `healthy`

### Roll Back The Local Services

To remove the supervised local layer:

```bash
cd /Users/zeroshot/Dev/ZeroUI
./scripts/uninstall-local-bridge-services.sh
```

If you need the old manual path again:

```bash
cd /Users/zeroshot/Dev/ZeroUI
./scripts/install-openai-oauth.sh
./scripts/start-openai-oauth.sh
./scripts/start-remote-bridges.sh
```

## VPS Broker Health

The repeatable production health command for the live VPS stack is:

```bash
cd /Users/zeroshot/Dev/ZeroVPS-test
./scripts/check-zerorelay-vps.sh
```

Validated checks:

- `zerorelay`
- `zerobridge`
- `claude-bridge`
- `codex-bridge`
- `content-codex-bridge`
- `telegram-bridge`
- ZeroRelay broker TCP listener on the VPS Tailscale address
- ZeroVPS Codex gateway `/health`
- ZeroVPS terminal `/health`

## VPS Deploy Path

The validated production deploy command is:

```bash
cd /Users/zeroshot/Dev/ZeroRelay
./scripts/deploy-vps.sh
```

This path was validated on April 20, 2026. It now defines the safe deployment contract for the VPS runtime.

What it does:

- stages the release on the VPS instead of deploying from the live runtime checkout
- backs up the currently installed runtime files and unit files into `/opt/zerorelay/backups/deploy-<timestamp>`
- creates or updates the pinned runtime venv at `/opt/zerorelay/venv`
- installs the source-controlled runtime files into `/opt/zerorelay`
- installs the source-controlled unit files into `/etc/systemd/system`
- reloads systemd and restarts the broker first, then the bridge services
- verifies the services are running from `/opt/zerorelay/venv/bin/python`
- verifies broker reachability plus the local gateway health endpoints

Important rule:

- treat `/opt/zerorelay` as a runtime directory, not as the authoritative git deploy checkout
- do not run `git pull` inside `/opt/zerorelay`
- use runtime git status there only as informational context

Detailed notes now live in:

- `/Users/zeroshot/Dev/ZeroRelay/docs/production-vps.md`
- `/Users/zeroshot/Dev/ZeroRelay/docs/dashboard-control-plane.md`

### Current Runtime Validation

Validated on April 20, 2026:

- `/opt/zerorelay/venv/bin/python` exists on the VPS
- `websockets==16.0`
- `httpx==0.28.1`
- all six services are active on the venv interpreter
