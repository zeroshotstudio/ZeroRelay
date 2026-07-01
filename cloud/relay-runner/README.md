# Relay workspace container (Sprint 2 C5)

Build from repo root:

```bash
docker build -f cloud/relay-runner/Dockerfile -t zerorelay-workspace .
```

Runs `core/zerorelay.py` with env-injected `RELAY_TOKEN` and `ZERORELAY_ROLES`.
