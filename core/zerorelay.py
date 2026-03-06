#!/usr/bin/env python3
"""
ZeroRelay — WebSocket relay server.

A lightweight message broker for multi-party AI conversations.
Supports any number of named roles. Messages from any client
are broadcast to all others.

Usage:
  python3 zerorelay.py --host 0.0.0.0 --port 8765
  python3 zerorelay.py --host 100.x.y.z --port 8765  # Tailscale only
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("zerorelay")

clients: dict[str, websockets.WebSocketServerProtocol] = {}
history: list[dict] = []

# Roles are dynamic — any string is valid. Set ZERORELAY_ROLES to restrict.
VALID_ROLES: set[str] | None = None
_roles_env = os.environ.get("ZERORELAY_ROLES", "")
if _roles_env:
    VALID_ROLES = set(r.strip() for r in _roles_env.split(",") if r.strip())

MAX_HISTORY = int(os.environ.get("ZERORELAY_MAX_HISTORY", "50"))


def make_msg(msg_type: str, **kwargs) -> str:
    return json.dumps({"type": msg_type, "timestamp": datetime.now().isoformat(), **kwargs})


async def broadcast(sender_role: str, msg: dict):
    payload = json.dumps(msg)
    for role, ws in list(clients.items()):
        if role != sender_role:
            try:
                await ws.send(payload)
            except Exception as e:
                log.error(f"Relay to {role} failed: {e}")


async def handler(websocket):
    path = websocket.request.path if hasattr(websocket, "request") else websocket.path
    query = parse_qs(urlparse(f"ws://x{path}").query)
    role = query.get("role", [None])[0]

    if not role:
        await websocket.close(1008, "Must specify ?role=<name>")
        return

    if VALID_ROLES and role not in VALID_ROLES:
        await websocket.close(1008, f"Invalid role '{role}'. Allowed: {', '.join(sorted(VALID_ROLES))}")
        return

    if role in clients:
        await websocket.close(1008, f"Role '{role}' already connected. Disconnect first.")
        return

    clients[role] = websocket
    others_online = [r for r in clients if r != role]
    log.info(f"[+] {role} connected  ({len(clients)} clients)")

    await broadcast(role, {
        "type": "system",
        "message": f"{role} joined",
        "timestamp": datetime.now().isoformat()
    })

    await websocket.send(make_msg(
        "connected",
        role=role,
        peers_online=others_online,
        history=history[-MAX_HISTORY:]
    ))

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                content = data.get("content", str(data))
            except json.JSONDecodeError:
                content = raw

            meta = data.get("meta") if isinstance(data, dict) else None
            msg = {
                "type": "message",
                "from": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
            if meta:
                msg["meta"] = meta

            if meta not in ("stream_chunk", "stream_start", "typing_indicator"):
                history.append(msg)

            if meta != "typing_indicator":
                log.info(f"[{role}] {content[:100]}")

            await broadcast(role, msg)

    except websockets.exceptions.ConnectionClosed:
        log.info(f"[-] {role} disconnected")
    finally:
        clients.pop(role, None)
        await broadcast(role, {
            "type": "system",
            "message": f"{role} left",
            "timestamp": datetime.now().isoformat()
        })


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="ZeroRelay WebSocket server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    args = parser.parse_args()

    roles_info = f"Restricted to: {', '.join(sorted(VALID_ROLES))}" if VALID_ROLES else "Any role accepted"
    log.info(f"ZeroRelay on ws://{args.host}:{args.port}")
    log.info(roles_info)
    async with websockets.serve(handler, args.host, args.port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
