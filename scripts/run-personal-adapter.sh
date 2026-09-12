#!/usr/bin/env bash
# Run the Personal Adapter from this Mac.
#   local — mint/serve here (AGY default)
#   vps   — copy to the VPS, serve on VPS loopback, SSH-tunnel 127.0.0.1:8767
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY="$REPO_ROOT/services/openai_gateway.py"
PROVIDERS="$REPO_ROOT/services/providers.py"
REMOTE_DIR="/opt/zerorelay/adapter"
DEFAULT_PORT="8767"
DEFAULT_SSH_HOST="my-vps-admin"

LOCATION=""
DO_MINT=0
DO_SERVE=0
PROVIDER=""
SSH_HOST="$DEFAULT_SSH_HOST"
PORT="$DEFAULT_PORT"
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [local|vps] [options]

Run the Personal Adapter from this Mac. It must run on the machine where
the CLI is logged in. Clients always talk to http://127.0.0.1:${DEFAULT_PORT}.

  local   Mint/serve on this Mac. Default provider: agy
  vps     Copy adapter files to the VPS, serve on VPS 127.0.0.1, then
          SSH-tunnel so local tools still use 127.0.0.1:${DEFAULT_PORT}.
          Default provider: claude
          SSH host: ${DEFAULT_SSH_HOST} (same as ./scripts/deploy-vps.sh)

If neither --mint nor --serve is given, both run. vps then keeps a tunnel
open until you Ctrl-C.

Options:
  --mint              Mint a zr- key and print {base_url, key, env_file} once
  --serve             Run the HTTP gateway
  --provider NAME     agy | claude
  --host NAME         SSH target for vps mode (default: ${DEFAULT_SSH_HOST})
  --port N            Port on 127.0.0.1 (default: ${DEFAULT_PORT})
  --dry-run           Print commands, do not execute
  -h, --help          Show this help
EOF
}

log_cmd() {
  printf '+ %s\n' "$*"
}

run_cmd() {
  log_cmd "$*"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    local | vps)
      LOCATION="$1"
      shift
      ;;
    --mint)
      DO_MINT=1
      shift
      ;;
    --serve)
      DO_SERVE=1
      shift
      ;;
    --provider)
      PROVIDER="${2:?--provider requires agy or claude}"
      shift 2
      ;;
    --host)
      SSH_HOST="${2:?--host requires an SSH target}"
      shift 2
      ;;
    --port)
      PORT="${2:?--port requires a number}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

LOCATION="${LOCATION:-local}"
if [[ "$DO_MINT" -eq 0 && "$DO_SERVE" -eq 0 ]]; then
  DO_MINT=1
  DO_SERVE=1
fi

if [[ -z "$PROVIDER" ]]; then
  if [[ "$LOCATION" == "vps" ]]; then
    PROVIDER="claude"
  else
    PROVIDER="agy"
  fi
fi

if [[ "$PROVIDER" != "agy" && "$PROVIDER" != "claude" ]]; then
  printf 'Provider must be agy or claude, got: %s\n' "$PROVIDER" >&2
  exit 2
fi

export ZERORELAY_ADAPTER_PROVIDER="$PROVIDER"
export ZERORELAY_OPENAI_HOST="127.0.0.1"
export ZERORELAY_OPENAI_PORT="$PORT"

local_health_ok() {
  curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null
}

run_local() {
  [[ -f "$GATEWAY" ]] || {
    printf 'Missing gateway: %s\n' "$GATEWAY" >&2
    exit 1
  }
  if [[ "$DO_MINT" -eq 1 ]]; then
    run_cmd python3 "$GATEWAY" --mint
  fi
  if [[ "$DO_SERVE" -eq 1 ]]; then
    if [[ "$DRY_RUN" -eq 0 ]] && local_health_ok; then
      printf 'Gateway already running at http://127.0.0.1:%s (LaunchAgent or prior serve). Skipping --serve.\n' "$PORT"
      if [[ "$DO_MINT" -eq 1 ]] && launchctl print "gui/$(id -u)/studio.zeroshot.zerorelay-openai-gateway" >/dev/null 2>&1; then
        printf 'Restarting LaunchAgent so it loads the minted key.\n'
        launchctl kickstart -k "gui/$(id -u)/studio.zeroshot.zerorelay-openai-gateway"
      fi
      return 0
    fi
    run_cmd python3 "$GATEWAY" --serve --host 127.0.0.1 --port "$PORT"
  fi
}

remote_env() {
  printf 'ZERORELAY_HOME=%s ZERORELAY_ADAPTER_PROVIDER=%s ZERORELAY_OPENAI_HOST=127.0.0.1 ZERORELAY_OPENAI_PORT=%s' \
    "$REMOTE_DIR" "$PROVIDER" "$PORT"
}

run_vps() {
  [[ -f "$GATEWAY" && -f "$PROVIDERS" ]] || {
    printf 'Missing adapter files under services/\n' >&2
    exit 1
  }

  run_cmd ssh "$SSH_HOST" "mkdir -p '$REMOTE_DIR'"
  run_cmd scp "$GATEWAY" "$PROVIDERS" "$SSH_HOST:$REMOTE_DIR/"

  local env_prefix
  env_prefix="$(remote_env)"
  local remote_py="$REMOTE_DIR/openai_gateway.py"

  if [[ "$DO_MINT" -eq 1 ]]; then
    run_cmd ssh "$SSH_HOST" "$env_prefix python3 '$remote_py' --mint"
  fi

  if [[ "$DO_SERVE" -eq 1 ]]; then
    run_cmd ssh "$SSH_HOST" "$env_prefix nohup python3 '$remote_py' --serve --host 127.0.0.1 --port '$PORT' >'$REMOTE_DIR/gateway.log' 2>&1 &"
    run_cmd ssh -N -L "127.0.0.1:${PORT}:127.0.0.1:${PORT}" "$SSH_HOST"
  fi
}

case "$LOCATION" in
  local)
    run_local
    ;;
  vps)
    run_vps
    ;;
  *)
    printf 'Location must be local or vps, got: %s\n' "$LOCATION" >&2
    exit 2
    ;;
esac
