#!/usr/bin/env python3
"""
ZeroRelay — WebSocket relay server (3-party).
Run on your VPS: python3 zerorelay.py --host YOUR_TAILSCALE_IP

Three clients can connect:
  ws://IP:8765?role=claude_ai    (Claude.ai artifact)
  ws://IP:8765?role=vps_claude   (Claude Code bridge)
  ws://IP:8765?role=jimmy        (you, via the artifact or another client)

Messages from any client are broadcast to all others.
"""

import asyncio
import json
import logging
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
VALID_ROLES = ("vps_claude", "zee", "jimmy")


def make_msg(msg_type: str, **kwargs) -> str:
    return json.dumps({"type": msg_type, "timestamp": datetime.now().isoformat(), **kwargs})


async def broadcast(sender_role: str, msg: dict):
    """Send a message to all connected clients except the sender."""
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

    if role not in VALID_ROLES:
        await websocket.close(1008, f"Invalid role. Use ?role={' | '.join(VALID_ROLES)}")
        return

    if role in clients:
        await websocket.close(1008, f"Role '{role}' already connected. Disconnect first.")
        return

    clients[role] = websocket
    others_online = [r for r in clients if r != role]
    log.info(f"[+] {role} connected  ({len(clients)}/{len(VALID_ROLES)})")

    # Notify everyone else
    await broadcast(role, {
        "type": "system",
        "message": f"{role} joined",
        "timestamp": datetime.now().isoformat()
    })

    # Send welcome + history + who's online
    await websocket.send(make_msg(
        "connected",
        role=role,
        peers_online=others_online,
        history=history[-50:]
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

            # Only store non-streaming messages in history
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
    parser.add_argument("--host", default="100.127.106.41", help="Bind address (use your Tailscale IP)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    args = parser.parse_args()

    log.info(f"ZeroRelay on ws://{args.host}:{args.port}")
    log.info(f"Roles: {', '.join(VALID_ROLES)}")
    log.info("Bound to Tailscale interface only")
    async with websockets.serve(handler, args.host, args.port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
