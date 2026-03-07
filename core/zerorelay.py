#!/usr/bin/env python3
"""
ZeroRelay — WebSocket relay server.

A lightweight message broker for multi-party AI conversations.
Supports any number of named roles. Messages from any client
are broadcast to all others.

Security features:
  - Token authentication (RELAY_TOKEN env var)
  - Rate limiting (20 msgs / 60s per role)
  - Bounded history (deque, maxlen=200)
  - Max WebSocket message size (64KB)
  - Content not logged at INFO level

Usage:
  python3 zerorelay.py --host 0.0.0.0 --port 8765
  python3 zerorelay.py --host $(tailscale ip -4) --port 8765
"""

import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("zerorelay")

clients: dict[str, object] = {}
history: deque = deque(maxlen=200)

# Roles: restrict via env or accept any
VALID_ROLES: set[str] | None = None
_roles_env = os.environ.get("ZERORELAY_ROLES", "")
if _roles_env:
    VALID_ROLES = set(r.strip() for r in _roles_env.split(",") if r.strip())

MAX_HISTORY = int(os.environ.get("ZERORELAY_MAX_HISTORY", "50"))

# Auth token from environment
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

# Rate limiting
rate_limits: dict[str, deque] = {}
RATE_LIMIT_WINDOW = int(os.environ.get("ZERORELAY_RATE_WINDOW", "60"))
RATE_LIMIT_MAX = int(os.environ.get("ZERORELAY_RATE_MAX", "20"))


def make_msg(msg_type: str, **kwargs) -> str:
    return json.dumps({"type": msg_type, "timestamp": datetime.now().isoformat(), **kwargs})


async def broadcast(sender_role: str, msg: dict):
    payload = json.dumps(msg)
    for role, ws in list(clients.items()):
        if role != sender_role:
            try:
                await ws.send(payload)
            except Exception:
                log.error(f"Relay to {role} failed")


def check_rate_limit(role: str) -> bool:
    """Return True if message should be dropped."""
    now = time.monotonic()
    if role not in rate_limits:
        rate_limits[role] = deque(maxlen=RATE_LIMIT_MAX)
    timestamps = rate_limits[role]
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False


async def handler(websocket):
    path = websocket.request.path if hasattr(websocket, "request") else websocket.path
    query = parse_qs(urlparse(f"ws://x{path}").query)
    role = query.get("role", [None])[0]

    # Token authentication
    if RELAY_TOKEN:
        token = query.get("token", [None])[0]
        if token != RELAY_TOKEN:
            log.warning(f"Rejected: invalid token (role={role})")
            await websocket.close(1008, "Invalid or missing token")
            return

    if not role:
        await websocket.close(1008, "Must specify ?role=<name>")
        return

    if VALID_ROLES and role not in VALID_ROLES:
        await websocket.close(1008, f"Invalid role '{role}'. Allowed: {', '.join(sorted(VALID_ROLES))}")
        return

    if role in clients:
        await websocket.close(1008, f"Role '{role}' already connected.")
        return

    clients[role] = websocket
    others_online = [r for r in clients if r != role]
    log.info(f"[+] {role} connected ({len(clients)} clients)")

    await broadcast(role, {
        "type": "system", "message": f"{role} joined",
        "timestamp": datetime.now().isoformat()
    })

    await websocket.send(make_msg(
        "connected", role=role, peers_online=others_online,
        history=list(history)[-MAX_HISTORY:]
    ))

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                content = data.get("content", str(data))
            except json.JSONDecodeError:
                content = raw

            meta = data.get("meta") if isinstance(data, dict) else None
            msg = {"type": "message", "from": role, "content": content,
                   "timestamp": datetime.now().isoformat()}
            if meta:
                msg["meta"] = meta

            # Rate limit (skip meta messages)
            if meta not in ("typing_indicator", "stream_chunk", "stream_start"):
                if check_rate_limit(role):
                    log.warning(f"Rate limit: {role}")
                    continue

            if meta not in ("stream_chunk", "stream_start", "typing_indicator"):
                history.append(msg)

            # Log length, not content (M3)
            if meta != "typing_indicator":
                log.info(f"[{role}] ({len(content)} chars)")

            await broadcast(role, msg)

    except websockets.exceptions.ConnectionClosed:
        log.info(f"[-] {role} disconnected")
    finally:
        clients.pop(role, None)
        await broadcast(role, {
            "type": "system", "message": f"{role} left",
            "timestamp": datetime.now().isoformat()
        })


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="ZeroRelay WebSocket server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Port")
    args = parser.parse_args()

    roles_info = f"Restricted: {', '.join(sorted(VALID_ROLES))}" if VALID_ROLES else "Any role"
    log.info(f"ZeroRelay on ws://{args.host}:{args.port}")
    log.info(f"Auth: {'enabled' if RELAY_TOKEN else 'DISABLED'}")
    log.info(roles_info)
    async with websockets.serve(handler, args.host, args.port, max_size=65536):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
