# ZeroRelay Dashboard Control Plane

## Purpose

This document defines the minimum machine-readable control-plane contract the local OpenWebUI dashboard can rely on today.

## Rule

- The dashboard is a consumer of ZeroRelay state.
- The dashboard does not own relay lifecycle.
- Service management stays with `launchd` on the Mac edge and `systemd` on the VPS.

## Current Stable Status Surface

Use:

```bash
cd /Users/zeroshot/Dev/ZeroRelay
./scripts/status-vps-json.sh
```

Optional targets:

```bash
./scripts/status-vps-json.sh my-vps-admin
./scripts/status-vps-json.sh local
```

The default use case is local dashboard code polling the VPS through the existing `my-vps-admin` SSH target.

## JSON Contract

The script emits one JSON document with these stable top-level keys:

- `generated_at`
- `deployment_mode`
- `runtime_python`
- `runtime_git`
- `broker`
- `services`
- `gateways`

### `deployment_mode`

Current value:

- `staged_runtime_dir`

This means `/opt/zerorelay` is treated as a runtime directory and deploys come from the source repo via staged copy.

### `runtime_git`

Fields:

- `head`
- `dirty`
- `informational_only`
- `status`

Important:

- this is operator context only
- `dirty: true` does not mean deploy drift is unsafe by itself
- the runtime directory is not the authoritative source of truth anymore

### `runtime_python`

Fields:

- `path`
- `version`
- `packages`

Current expectation:

- `path` is `/opt/zerorelay/venv/bin/python`
- `packages.websockets` and `packages.httpx` reflect the pinned production runtime

### `broker`

Fields:

- `host`
- `port`
- `reachable`
- `established_connections`

### `services`

Each service entry includes:

- `status`
- `ok`
- `role`

Current service set:

- `zerorelay`
- `zerobridge`
- `claude-bridge`
- `codex-bridge`
- `content-codex-bridge`
- `telegram-bridge`

### `gateways`

Current gateway checks:

- `codex` → `http://127.0.0.1:18811/health`
- `terminal` → `http://127.0.0.1:8000/health`

Each entry includes:

- `ok`
- `status_code` when healthy
- `body` when healthy
- `error` when unhealthy

## Dashboard Use Today

The dashboard should use this status surface to render:

1. Broker up or down.
2. Bridge service state per agent role.
3. Gateway health for Codex and terminal adapters.
4. Connection-count trend or warning state.
5. Operator note that runtime git state is informational only.

## Control Actions Today

Keep control actions separate from status polling:

- local adapter install or restart:
  - `/Users/zeroshot/Dev/ZeroUI/scripts/install-local-bridge-services.sh`
  - `/Users/zeroshot/Dev/ZeroUI/scripts/check-local-bridge-services.sh`
  - `/Users/zeroshot/Dev/ZeroUI/scripts/refresh-open-webui-models.sh`
- VPS deploy:
  - `/Users/zeroshot/Dev/ZeroRelay/scripts/deploy-vps.sh`
- VPS health:
  - `/Users/zeroshot/Dev/ZeroVPS-test/scripts/check-zerorelay-vps.sh`

## Future HTTP API

If the dashboard moves fully onto the VPS, replace SSH polling with a small authenticated HTTP service that exposes the same shape:

- `GET /health`
- `GET /status`
- `GET /services`
- `POST /actions/restart/<service>`
- `POST /actions/deploy`

Until that exists, `status-vps-json.sh` is the stable contract.
