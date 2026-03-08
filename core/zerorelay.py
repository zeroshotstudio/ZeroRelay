#!/usr/bin/env python3
"""
ZeroRelay — WebSocket relay server.

A lightweight message broker for multi-party AI conversations.
Supports any number of named roles. Messages from any client
are broadcast to all others.

Features:
  - Token authentication (RELAY_TOKEN env var)
  - Rate limiting (20 msgs / 60s per role)
  - Bounded history (deque, maxlen=200)
  - Max WebSocket message size (64KB)
  - Content not logged at INFO level
  - MCP Tool Broker: agents register tools, call each other's tools via JSON
  - Tool namespacing: tools are stored as {owner}/{tool_name}

Usage:
  python3 zerorelay.py --host 0.0.0.0 --port 8765
  python3 zerorelay.py --host $(tailscale ip -4) --port 8765
"""

import asyncio
import json
import logging
import os
import secrets
import sys
import time
from collections import deque
from datetime import datetime
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import websockets

from core.mcp_registry import MCPRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("zerorelay")

clients: dict[str, object] = {}
client_info: dict[str, dict] = {}  # role -> {tags: [...], display_name: str}
history: deque = deque(maxlen=200)

# MCP Tool Broker state
mcp_registry = MCPRegistry()
mcp_pending: dict[str, dict] = {}  # call_id -> {caller, tool_name, owner, time}
MCP_CALL_TIMEOUT = int(os.environ.get("ZERORELAY_MCP_TIMEOUT", "30"))

# MCP rate limiting (separate from chat rate limits)
MCP_RATE_LIMIT_MAX = int(os.environ.get("ZERORELAY_MCP_RATE_MAX", "60"))
MCP_RATE_LIMIT_WINDOW = int(os.environ.get("ZERORELAY_MCP_RATE_WINDOW", "60"))
mcp_rate_limits: dict[str, deque] = {}

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
        rate_limits[role] = deque(maxlen=RATE_LIMIT_MAX + 1)
    timestamps = rate_limits[role]
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW:
        timestamps.popleft()
    timestamps.append(now)
    if len(timestamps) > RATE_LIMIT_MAX:
        timestamps.pop()
        return True
    return False


def check_mcp_rate_limit(role: str) -> bool:
    """Return True if MCP message should be dropped."""
    now = time.monotonic()
    if role not in mcp_rate_limits:
        mcp_rate_limits[role] = deque(maxlen=MCP_RATE_LIMIT_MAX + 1)
    timestamps = mcp_rate_limits[role]
    while timestamps and now - timestamps[0] > MCP_RATE_LIMIT_WINDOW:
        timestamps.popleft()
    timestamps.append(now)
    if len(timestamps) > MCP_RATE_LIMIT_MAX:
        timestamps.pop()
        return True
    return False


async def handler(websocket):
    path = websocket.request.path if hasattr(websocket, "request") else websocket.path
    query = parse_qs(urlparse(f"ws://x{path}").query)
    role = query.get("role", [None])[0]

    # Token authentication
    if RELAY_TOKEN:
        token = query.get("token", [None])[0]
        if not token or not secrets.compare_digest(token, RELAY_TOKEN):
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

    # Parse optional tags and display_name from query string
    raw_tags = query.get("tags", [None])[0]
    tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []
    display_name = query.get("display_name", [None])[0] or role

    clients[role] = websocket
    client_info[role] = {"tags": tags, "display_name": display_name}
    others_online = [r for r in clients if r != role]
    log.info(f"[+] {role} connected ({len(clients)} clients) tags={tags}")

    # Build peer_info for the connecting client (all others' info)
    peer_info = {r: info for r, info in client_info.items() if r != role}

    # Notify existing clients about the new peer
    join_msg = json.dumps({"type": "peer_joined", "role": role,
                           "info": client_info[role],
                           "timestamp": datetime.now().isoformat()})
    for r, ws_client in list(clients.items()):
        if r != role:
            try:
                await ws_client.send(join_msg)
            except Exception:
                pass

    await broadcast(role, {
        "type": "system", "message": f"{role} joined",
        "timestamp": datetime.now().isoformat()
    })

    await websocket.send(make_msg(
        "connected", role=role, peers_online=others_online,
        peer_info=peer_info,
        history=list(history)[-MAX_HISTORY:],
        available_tools=mcp_registry.get_tools(exclude_role=role)
    ))

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            # --- MCP Tool Broker messages ---
            if msg_type == "mcp_register":
                tools = data.get("tools", [])
                if not isinstance(tools, list):
                    log.warning(f"[MCP] {role}: mcp_register 'tools' is not a list, ignoring")
                    continue
                if check_mcp_rate_limit(role):
                    log.warning(f"[MCP] Rate limit: {role} (register)")
                    continue
                registered = mcp_registry.register(role, tools)
                log.info(f"[MCP] {role} registered {len(registered)} tools: {registered}")
                now_ts = datetime.now().isoformat()
                for r, ws_client in list(clients.items()):
                    try:
                        update = json.dumps({"type": "mcp_tools_updated",
                            "available_tools": mcp_registry.get_tools(exclude_role=r),
                            "timestamp": now_ts})
                        await ws_client.send(update)
                    except Exception: pass
                continue

            if msg_type == "mcp_tool_call":
                call_id = data.get("call_id")
                tool_name = data.get("tool_name")
                arguments = data.get("arguments", {})
                now_iso = datetime.now().isoformat()

                # Input validation
                if not isinstance(call_id, str) or not call_id:
                    await websocket.send(json.dumps({"type": "mcp_tool_result",
                        "call_id": call_id, "error": "Invalid or missing 'call_id'",
                        "timestamp": now_iso}))
                    continue
                if not isinstance(tool_name, str) or not tool_name:
                    await websocket.send(json.dumps({"type": "mcp_tool_result",
                        "call_id": call_id, "error": "Invalid or missing 'tool_name'",
                        "timestamp": now_iso}))
                    continue
                if not isinstance(arguments, dict):
                    arguments = {}

                if check_mcp_rate_limit(role):
                    log.warning(f"[MCP] Rate limit: {role} (tool_call)")
                    await websocket.send(json.dumps({"type": "mcp_tool_result",
                        "call_id": call_id, "tool_name": tool_name,
                        "error": "MCP rate limit exceeded",
                        "timestamp": now_iso}))
                    continue

                owner = mcp_registry.resolve(tool_name)

                # Self-call prevention
                if owner == role:
                    await websocket.send(json.dumps({"type": "mcp_tool_result",
                        "call_id": call_id, "tool_name": tool_name,
                        "error": "Cannot call your own tool",
                        "timestamp": now_iso}))
                    continue

                if not owner or owner not in clients:
                    await websocket.send(json.dumps({"type": "mcp_tool_result",
                        "call_id": call_id, "tool_name": tool_name,
                        "error": f"Tool '{tool_name}' not available",
                        "timestamp": now_iso}))
                    continue

                # Parse namespaced name to get plain tool name for the owner
                parsed = MCPRegistry.parse_name(tool_name)
                plain_name = parsed[1] if parsed else tool_name

                mcp_pending[call_id] = {"caller": role, "tool_name": tool_name,
                                        "owner": owner, "time": time.monotonic()}
                forward = {"type": "mcp_tool_call", "call_id": call_id,
                           "caller": role, "tool_name": plain_name,
                           "arguments": arguments, "timestamp": now_iso}
                try:
                    await clients[owner].send(json.dumps(forward))
                    log.info(f"[MCP] {role} -> {owner}: {tool_name} args_keys={list(arguments.keys())}")
                except Exception:
                    mcp_pending.pop(call_id, None)
                    await websocket.send(json.dumps({"type": "mcp_tool_result",
                        "call_id": call_id, "tool_name": tool_name,
                        "error": "Failed to reach tool owner",
                        "timestamp": now_iso}))
                continue

            if msg_type == "mcp_tool_result":
                call_id = data.get("call_id")
                if not isinstance(call_id, str) or not call_id:
                    log.warning(f"[MCP] {role}: mcp_tool_result with invalid call_id")
                    continue
                if check_mcp_rate_limit(role):
                    log.warning(f"[MCP] Rate limit: {role} (tool_result)")
                    continue
                pending = mcp_pending.pop(call_id, None)
                if not pending:
                    log.warning(f"[MCP] Unknown call_id from {role}: {call_id}")
                    continue
                # Sender verification: only the tool owner can send results
                if role != pending["owner"]:
                    log.warning(f"[MCP] {role} sent result for call owned by {pending['owner']}, dropping")
                    mcp_pending[call_id] = pending  # restore
                    continue
                caller_role = pending["caller"]
                if caller_role not in clients:
                    log.warning(f"[MCP] Caller {caller_role} disconnected")
                    continue
                result_msg = {"type": "mcp_tool_result", "call_id": call_id,
                              "tool_name": pending["tool_name"], "owner": role,
                              "timestamp": datetime.now().isoformat()}
                if "result" in data: result_msg["result"] = data["result"]
                if "error" in data: result_msg["error"] = data["error"]
                await clients[caller_role].send(json.dumps(result_msg))
                log.info(f"[MCP] {role} -> {caller_role}: result for {pending['tool_name']}")
                continue

            # --- Regular message handling ---
            content = data.get("content", str(data))
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
        client_info.pop(role, None)
        # Notify peers about departure
        leave_msg = json.dumps({"type": "peer_left", "role": role,
                                "timestamp": datetime.now().isoformat()})
        for r, ws_client in list(clients.items()):
            try:
                await ws_client.send(leave_msg)
            except Exception:
                pass
        # Clean up rate limits
        rate_limits.pop(role, None)
        mcp_rate_limits.pop(role, None)
        # MCP cleanup: unregister tools and notify pending callers
        if mcp_registry.unregister_role(role):
            now_ts = datetime.now().isoformat()
            for r, ws_client in list(clients.items()):
                try:
                    update = json.dumps({"type": "mcp_tools_updated",
                        "available_tools": mcp_registry.get_tools(exclude_role=r),
                        "timestamp": now_ts})
                    await ws_client.send(update)
                except Exception: pass
        orphaned = [cid for cid, p in mcp_pending.items() if p["owner"] == role]
        for cid in orphaned:
            p = mcp_pending.pop(cid)
            if p["caller"] in clients:
                try:
                    await clients[p["caller"]].send(json.dumps({
                        "type": "mcp_tool_result", "call_id": cid,
                        "tool_name": p["tool_name"],
                        "error": f"Tool owner '{role}' disconnected",
                        "timestamp": datetime.now().isoformat()}))
                except Exception: pass
        await broadcast(role, {
            "type": "system", "message": f"{role} left",
            "timestamp": datetime.now().isoformat()
        })


async def mcp_timeout_sweep():
    """Expire pending MCP tool calls that exceed the timeout."""
    while True:
        await asyncio.sleep(10)
        now = time.monotonic()
        expired = [cid for cid, p in mcp_pending.items()
                   if now - p["time"] > MCP_CALL_TIMEOUT]
        for cid in expired:
            p = mcp_pending.pop(cid, None)
            if p and p["caller"] in clients:
                try:
                    await clients[p["caller"]].send(json.dumps({
                        "type": "mcp_tool_result", "call_id": cid,
                        "tool_name": p["tool_name"],
                        "error": "Tool call timed out",
                        "timestamp": datetime.now().isoformat()}))
                    log.warning(f"[MCP] Timed out: {p['tool_name']} (caller={p['caller']})")
                except Exception: pass


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="ZeroRelay WebSocket server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Port")
    args = parser.parse_args()

    roles_info = f"Restricted: {', '.join(sorted(VALID_ROLES))}" if VALID_ROLES else "Any role"
    log.info(f"ZeroRelay on ws://{args.host}:{args.port}")
    log.info(f"Auth: {'enabled' if RELAY_TOKEN else 'DISABLED'}")
    if RELAY_TOKEN:
        log.warning("Token is passed via query string. Use WSS (TLS) or a reverse proxy to prevent token exposure in logs.")
    log.info(f"MCP: timeout={MCP_CALL_TIMEOUT}s, rate={MCP_RATE_LIMIT_MAX}/{MCP_RATE_LIMIT_WINDOW}s")
    log.info(roles_info)
    asyncio.create_task(mcp_timeout_sweep())
    async with websockets.serve(handler, args.host, args.port, max_size=65536):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
