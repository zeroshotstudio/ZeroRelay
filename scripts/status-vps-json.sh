#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-my-vps-admin}"

if [[ "$TARGET" == "local" ]]; then
  python3 - <<'PY'
import json
import socket
import subprocess
import urllib.request
from datetime import datetime, UTC

SERVICES = [
    "zerorelay",
    "zerobridge",
    "claude-bridge",
    "codex-bridge",
    "content-codex-bridge",
    "telegram-bridge",
]

ROLE_MAP = {
    "zerobridge": "zee",
    "claude-bridge": "vps_claude",
    "codex-bridge": "vps_codex",
    "content-codex-bridge": "content_codex",
    "telegram-bridge": "jimmy",
}


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def service_status(name):
    code, out, err = run(["systemctl", "is-active", name])
    status = out or err or f"rc={code}"
    return {
        "status": status,
        "ok": status == "active",
        "role": ROLE_MAP.get(name),
    }


def gateway_health(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"ok": True, "status_code": response.status, "body": body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def package_version(package):
    code, out, _ = run(["/opt/zerorelay/venv/bin/python", "-m", "pip", "show", package])
    if code != 0 or not out:
        return None
    for line in out.splitlines():
        if line.startswith("Version: "):
            return line.split(": ", 1)[1]
    return None


code, out, _ = run(["tailscale", "ip", "-4"])
broker_host = out.splitlines()[0] if code == 0 and out else "127.0.0.1"

broker_reachable = False
try:
    sock = socket.create_connection((broker_host, 8765), timeout=2)
    sock.close()
    broker_reachable = True
except OSError:
    broker_reachable = False

_, out, _ = run(["ss", "-tan"])
established_connections = sum(1 for line in out.splitlines() if ":8765" in line and "ESTAB" in line)

_, head_out, _ = run(["git", "-C", "/opt/zerorelay", "rev-parse", "--short", "HEAD"])
_, status_out, _ = run(["git", "-C", "/opt/zerorelay", "status", "--short"])

payload = {
    "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "deployment_mode": "staged_runtime_dir",
    "runtime_python": {
        "path": "/opt/zerorelay/venv/bin/python",
        "version": run(["/opt/zerorelay/venv/bin/python", "--version"])[1],
        "packages": {
            "websockets": package_version("websockets"),
            "httpx": package_version("httpx"),
        },
    },
    "runtime_git": {
        "head": head_out,
        "dirty": bool(status_out.strip()),
        "informational_only": True,
        "status": status_out.splitlines() if status_out else [],
    },
    "broker": {
        "host": broker_host,
        "port": 8765,
        "reachable": broker_reachable,
        "established_connections": established_connections,
    },
    "services": {service: service_status(service) for service in SERVICES},
    "gateways": {
        "codex": gateway_health("http://127.0.0.1:18811/health"),
        "terminal": gateway_health("http://127.0.0.1:8000/health"),
    },
}

print(json.dumps(payload, indent=2))
PY
else
  ssh -T "$TARGET" 'python3 -' <<'PY' | python3 -c 'import sys; text = sys.stdin.read(); marker = "__ZERORELAY_STATUS_JSON__"; index = text.find(marker); index != -1 or (sys.stderr.write(text), (_ for _ in ()).throw(SystemExit("status marker not found in remote output"))); print(text[index + len(marker):].lstrip())'
import json
import socket
import subprocess
import urllib.request
from datetime import datetime, UTC

SERVICES = [
    "zerorelay",
    "zerobridge",
    "claude-bridge",
    "codex-bridge",
    "content-codex-bridge",
    "telegram-bridge",
]

ROLE_MAP = {
    "zerobridge": "zee",
    "claude-bridge": "vps_claude",
    "codex-bridge": "vps_codex",
    "content-codex-bridge": "content_codex",
    "telegram-bridge": "jimmy",
}


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def service_status(name):
    code, out, err = run(["systemctl", "is-active", name])
    status = out or err or f"rc={code}"
    return {
        "status": status,
        "ok": status == "active",
        "role": ROLE_MAP.get(name),
    }


def gateway_health(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"ok": True, "status_code": response.status, "body": body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def package_version(package):
    code, out, _ = run(["/opt/zerorelay/venv/bin/python", "-m", "pip", "show", package])
    if code != 0 or not out:
        return None
    for line in out.splitlines():
        if line.startswith("Version: "):
            return line.split(": ", 1)[1]
    return None


code, out, _ = run(["tailscale", "ip", "-4"])
broker_host = out.splitlines()[0] if code == 0 and out else "127.0.0.1"

broker_reachable = False
try:
    sock = socket.create_connection((broker_host, 8765), timeout=2)
    sock.close()
    broker_reachable = True
except OSError:
    broker_reachable = False

_, out, _ = run(["ss", "-tan"])
established_connections = sum(1 for line in out.splitlines() if ":8765" in line and "ESTAB" in line)

_, head_out, _ = run(["git", "-C", "/opt/zerorelay", "rev-parse", "--short", "HEAD"])
_, status_out, _ = run(["git", "-C", "/opt/zerorelay", "status", "--short"])

payload = {
    "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "deployment_mode": "staged_runtime_dir",
    "runtime_python": {
        "path": "/opt/zerorelay/venv/bin/python",
        "version": run(["/opt/zerorelay/venv/bin/python", "--version"])[1],
        "packages": {
            "websockets": package_version("websockets"),
            "httpx": package_version("httpx"),
        },
    },
    "runtime_git": {
        "head": head_out,
        "dirty": bool(status_out.strip()),
        "informational_only": True,
        "status": status_out.splitlines() if status_out else [],
    },
    "broker": {
        "host": broker_host,
        "port": 8765,
        "reachable": broker_reachable,
        "established_connections": established_connections,
    },
    "services": {service: service_status(service) for service in SERVICES},
    "gateways": {
        "codex": gateway_health("http://127.0.0.1:18811/health"),
        "terminal": gateway_health("http://127.0.0.1:8000/health"),
    },
}

print("__ZERORELAY_STATUS_JSON__")
print(json.dumps(payload, indent=2))
PY
fi
