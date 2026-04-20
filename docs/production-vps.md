# ZeroRelay VPS Production Deploy

## Scope

This document defines the production deployment path for the live ZeroRelay stack on the VPS.

## Production Rule

- Treat `/opt/zerorelay` as a runtime directory, not as a git working tree you update in place.
- Do not run `git pull` inside `/opt/zerorelay`.
- Deploy from a source-controlled repo checkout through a staged release copy.

This rule exists because the live runtime directory contains mutable state and host-specific files:

- `relay.env`, `gateway.env`, `telegram.env`
- session files such as `claude-session-id` and `codex-session-id`
- inbox and outbox files
- historical backups and runtime scratch files

## Current Service Set

The live production stack consists of these systemd services:

- `zerorelay`
- `zerobridge`
- `claude-bridge`
- `codex-bridge`
- `content-codex-bridge`
- `telegram-bridge`

## Deployment Command

From the source repo checkout:

```bash
cd /Users/zeroshot/Dev/ZeroRelay
./scripts/deploy-vps.sh
```

Optional alternate SSH target:

```bash
./scripts/deploy-vps.sh my-vps-admin
```

## What The Deploy Script Does

1. Packages the source-controlled runtime files and unit files from the repo.
2. Uploads them to a temporary staging directory on the VPS.
3. Backs up the currently installed runtime files and service units into `/opt/zerorelay/backups/deploy-<timestamp>`.
4. Installs the new runtime files into `/opt/zerorelay`.
5. Creates or updates the pinned runtime virtualenv at `/opt/zerorelay/venv`.
6. Installs the service units into `/etc/systemd/system`.
7. Reloads systemd.
8. Restarts the broker first, then the bridge services.
9. Verifies:
   - all six services are active
   - every service uses `/opt/zerorelay/venv/bin/python`
   - ZeroRelay is listening on `100.127.106.41:8765`
   - the Codex gateway health endpoint on `127.0.0.1:18811` is healthy
   - the terminal gateway health endpoint on `127.0.0.1:8000` is healthy

## Files Managed By The Deploy Script

Runtime files:

- `README.md`
- `requirements.txt`
- `zerorelay.py`
- `zerobridge.py`
- `claude-bridge.py`
- `codex-bridge.py`
- `content-codex-bridge.py`
- `telegram-bridge.py`
- `venv/` created from `requirements.txt`

Service files:

- `zerorelay.service`
- `zerobridge.service`
- `claude-bridge.service`
- `codex-bridge.service`
- `content-codex-bridge.service`
- `telegram-bridge.service`

## Files Preserved In Place

The deploy does not overwrite or remove:

- `relay.env`
- `gateway.env`
- `telegram.env`
- session files
- inbox and outbox files
- `.ssh/`
- backup folders

## Verification

Run the ops health check after deploy:

```bash
cd /Users/zeroshot/Dev/ZeroVPS-test
./scripts/check-zerorelay-vps.sh
```

## Rollback

Each deploy prints a `backup_dir=...` path. To roll back quickly:

1. Copy the desired backed-up runtime files from that directory back into `/opt/zerorelay`.
2. Copy the backed-up service files from that directory back into `/etc/systemd/system`.
3. Recreate the venv from the backed-up `requirements.txt` if dependency rollback is required.
4. Run `systemctl daemon-reload`.
5. Restart the same six services in the normal order.
