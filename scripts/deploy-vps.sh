#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_HOST="${1:-my-vps-admin}"
STAGE_DIR="/tmp/zerorelay-release-$(date -u +%Y%m%dT%H%M%SZ)"
RUNTIME_DIR="/opt/zerorelay"
VENV_DIR="/opt/zerorelay/venv"
SERVICE_DIR="/etc/systemd/system"

RUNTIME_FILES=(
  README.md
  requirements.txt
  zerorelay.py
  zerobridge.py
  claude-bridge.py
  codex-bridge.py
  content-codex-bridge.py
  telegram-bridge.py
)

SERVICE_FILES=(
  zerorelay.service
  zerobridge.service
  claude-bridge.service
  codex-bridge.service
  content-codex-bridge.service
  telegram-bridge.service
)

SERVICES=(
  zerorelay
  zerobridge
  claude-bridge
  codex-bridge
  content-codex-bridge
  telegram-bridge
)

log() {
  printf '[deploy-vps] %s\n' "$1"
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || {
    printf 'Missing required file: %s\n' "$path" >&2
    exit 1
  }
}

for file in "${RUNTIME_FILES[@]}"; do
  require_file "$REPO_ROOT/$file"
done

for file in "${SERVICE_FILES[@]}"; do
  require_file "$REPO_ROOT/$file"
done

log "Staging release on ${TARGET_HOST}:${STAGE_DIR}"
ssh "$TARGET_HOST" "rm -rf '$STAGE_DIR' && mkdir -p '$STAGE_DIR'"

tar -C "$REPO_ROOT" -cf - "${RUNTIME_FILES[@]}" "${SERVICE_FILES[@]}" \
  | ssh "$TARGET_HOST" "tar -xf - -C '$STAGE_DIR'"

log "Installing release into ${RUNTIME_DIR}"
ssh "$TARGET_HOST" "STAGE_DIR='$STAGE_DIR' RUNTIME_DIR='$RUNTIME_DIR' VENV_DIR='$VENV_DIR' SERVICE_DIR='$SERVICE_DIR' bash -s" <<'EOF'
set -euo pipefail

runtime_files=(
  README.md
  requirements.txt
  zerorelay.py
  zerobridge.py
  claude-bridge.py
  codex-bridge.py
  content-codex-bridge.py
  telegram-bridge.py
)

service_files=(
  zerorelay.service
  zerobridge.service
  claude-bridge.service
  codex-bridge.service
  content-codex-bridge.service
  telegram-bridge.service
)

services=(
  zerorelay
  zerobridge
  claude-bridge
  codex-bridge
  content-codex-bridge
  telegram-bridge
)

backup_dir="$RUNTIME_DIR/backups/deploy-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUNTIME_DIR" "$backup_dir"

python3 -m venv --help >/dev/null 2>&1 || {
  echo "python3 venv module is not available on the target host" >&2
  exit 1
}

for file in "${runtime_files[@]}"; do
  if [[ -f "$RUNTIME_DIR/$file" ]]; then
    install -m 0644 "$RUNTIME_DIR/$file" "$backup_dir/$file"
  fi
done

for file in "${service_files[@]}"; do
  if [[ -f "$SERVICE_DIR/$file" ]]; then
    install -m 0644 "$SERVICE_DIR/$file" "$backup_dir/$file"
  fi
done

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
PIP_DISABLE_PIP_VERSION_CHECK=1 "$VENV_DIR/bin/pip" install --quiet --upgrade -r "$STAGE_DIR/requirements.txt"

for file in "${runtime_files[@]}"; do
  install -m 0644 "$STAGE_DIR/$file" "$RUNTIME_DIR/$file"
done

for file in "${service_files[@]}"; do
  install -m 0644 "$STAGE_DIR/$file" "$SERVICE_DIR/$file"
done

systemctl daemon-reload
systemctl restart zerorelay
sleep 2

for service in "${services[@]:1}"; do
  systemctl restart "$service"
done

for service in "${services[@]}"; do
  systemctl is-active --quiet "$service"
done

for service in "${services[@]}"; do
  systemctl show "$service" --property=ExecStart | grep -q "$VENV_DIR/bin/python"
done

ss -ltn sport = :8765 | grep -q '100.127.106.41:8765'
curl -fsS http://127.0.0.1:18811/health >/dev/null
curl -fsS http://127.0.0.1:8000/health >/dev/null

"$VENV_DIR/bin/python" -m pip show websockets httpx >/dev/null

printf 'backup_dir=%s\n' "$backup_dir"
EOF

log "Cleaning remote stage"
ssh "$TARGET_HOST" "rm -rf '$STAGE_DIR'"

log "Deploy complete"
