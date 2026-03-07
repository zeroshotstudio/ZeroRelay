#!/usr/bin/env python3
"""
Base bridge class for ZeroRelay.

All bridges inherit from this. Handles: WebSocket connection,
reconnection with exponential backoff, message routing,
@-mention detection, typing indicators, transcript tracking,
and relay token authentication.

To create a new bridge, subclass AIBridge and implement _sync_generate().
"""

import asyncio
import json
import logging
import os
import re
import uuid
from abc import ABC, abstractmethod

import websockets

log = logging.getLogger("bridge")


class BaseBridge(ABC):
    def __init__(self, relay_url: str, role: str, tags: list[str] | None = None,
                 display_name: str | None = None, max_transcript: int = 30):
        self.relay_url = relay_url
        self.role = role
        self.tags = tags
        self.display_name = display_name or role
        self.max_transcript = max_transcript
        self.transcript: list[dict] = []
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.relay_token = os.environ.get("RELAY_TOKEN", "")
        self.operator_role = os.environ.get("ZERORELAY_OPERATOR", "operator")
        self._mcp_pending: dict[str, asyncio.Future] = {}
        self._available_remote_tools: list[dict] = []

        if tags:
            escaped = [re.escape(t.lstrip("@")) for t in tags]
            self._tag_re = re.compile(rf"@(?:{'|'.join(escaped)})\b", re.IGNORECASE)
        else:
            self._tag_re = None

    def _build_uri(self) -> str:
        """Build relay URI with role and optional token."""
        uri = f"{self.relay_url}?role={self.role}"
        if self.relay_token:
            uri += f"&token={self.relay_token}"
        return uri

    def is_addressed(self, content: str) -> bool:
        if self._tag_re is None: return True
        return bool(self._tag_re.search(content))

    def strip_tags(self, content: str) -> str:
        if self._tag_re is None: return content
        return self._tag_re.sub("", content).strip()

    def format_transcript(self) -> str:
        if not self.transcript: return "(no prior messages)"
        lines = []
        for msg in self.transcript[-self.max_transcript:]:
            c = msg.get("content", "")
            if len(c) > 500: c = c[:500] + "..."
            lines.append(f"[{msg.get('from', 'system')}]: {c}")
        return "\n".join(lines)

    async def send(self, content: str, meta: str | None = None):
        if not self.ws: return
        msg = {"content": content}
        if meta: msg["meta"] = meta
        try: await self.ws.send(json.dumps(msg))
        except Exception as e: log.error(f"Send failed: {e}")

    async def send_typing(self):
        await self.send("", meta="typing_indicator")

    # --- MCP Tool Broker methods ---

    async def register_tools(self, tools: list[dict]):
        """Register tools this bridge exposes with the relay."""
        if not self.ws: return
        msg = {"type": "mcp_register", "tools": tools}
        try: await self.ws.send(json.dumps(msg))
        except Exception as e: log.error(f"MCP register failed: {e}")

    async def call_remote_tool(self, tool_name: str, arguments: dict,
                               timeout: float = 30.0) -> dict:
        """Call a remote tool through the relay. Returns result or error dict."""
        if not self.ws:
            return {"error": "Not connected"}
        call_id = str(uuid.uuid4())
        msg = {"type": "mcp_tool_call", "call_id": call_id,
               "tool_name": tool_name, "arguments": arguments}
        fut = asyncio.get_running_loop().create_future()
        self._mcp_pending[call_id] = fut
        await self.ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._mcp_pending.pop(call_id, None)
            return {"error": "Tool call timed out"}

    async def on_tool_call(self, call_id: str, caller: str,
                           tool_name: str, arguments: dict):
        """Override to handle incoming tool calls. Must send result back."""
        await self._send_tool_result(call_id, error=f"Tool '{tool_name}' not implemented")

    async def _send_tool_result(self, call_id: str, result=None, error=None):
        """Send a tool result back to the relay."""
        if not self.ws: return
        msg: dict = {"type": "mcp_tool_result", "call_id": call_id}
        if result is not None: msg["result"] = result
        if error is not None: msg["error"] = error
        try: await self.ws.send(json.dumps(msg))
        except Exception as e: log.error(f"MCP result send failed: {e}")

    async def on_tools_updated(self, tools: list[dict]):
        """Called when the available remote tools list changes."""
        self._available_remote_tools = tools

    @abstractmethod
    async def on_message(self, sender: str, content: str, data: dict): pass

    async def on_connect(self, peers: list[str]):
        log.info(f"Connected as {self.role}. Peers: {peers}")

    async def on_system(self, message: str):
        log.info(f"System: {message}")

    async def run(self):
        uri = self._build_uri()
        backoff = 3
        while True:
            try:
                log.info(f"Connecting to relay")
                async with websockets.connect(uri) as ws:
                    self.ws = ws
                    backoff = 3  # Reset on success
                    async for raw in ws:
                        try: data = json.loads(raw)
                        except json.JSONDecodeError: continue
                        msg_type = data.get("type")
                        # MCP message dispatch
                        if msg_type == "mcp_tool_call":
                            await self.on_tool_call(data.get("call_id"),
                                data.get("caller"), data.get("tool_name"),
                                data.get("arguments", {}))
                            continue
                        if msg_type == "mcp_tool_result":
                            call_id = data.get("call_id")
                            fut = self._mcp_pending.pop(call_id, None)
                            if fut and not fut.done(): fut.set_result(data)
                            continue
                        if msg_type == "mcp_tools_updated":
                            await self.on_tools_updated(data.get("available_tools", []))
                            continue
                        if msg_type == "connected":
                            for h in data.get("history", []):
                                if h.get("type") == "message": self.transcript.append(h)
                            self._available_remote_tools = data.get("available_tools", [])
                            await self.on_connect(data.get("peers_online", []))
                            continue
                        if msg_type == "system":
                            await self.on_system(data.get("message", "")); continue
                        if msg_type == "message":
                            sender = data.get("from", "")
                            content = data.get("content", "")
                            meta = data.get("meta")
                            if sender == self.role: continue
                            if meta in ("typing_indicator", "stream_start", "stream_chunk"): continue
                            self.transcript.append({"from": sender, "content": content})
                            # Trim transcript
                            if len(self.transcript) > self.max_transcript * 2:
                                self.transcript[:] = self.transcript[-self.max_transcript:]
                            await self.on_message(sender, content, data)
            except websockets.exceptions.ConnectionClosed:
                log.warning(f"Disconnected. Reconnecting in {backoff}s...")
            except ConnectionRefusedError:
                log.warning(f"Relay unavailable. Retrying in {backoff}s...")
            except Exception as e:
                log.error(f"Bridge error: {e}. Reconnecting in {backoff}s...")
            self.ws = None
            # Cancel pending MCP futures so callers don't hang
            for cid, fut in self._mcp_pending.items():
                if not fut.done():
                    fut.set_result({"error": "Disconnected from relay"})
            self._mcp_pending.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


class AIBridge(BaseBridge):
    """Base for AI bridges. Subclass and implement _sync_generate()."""

    def __init__(self, system_prompt: str = "", **kwargs):
        super().__init__(**kwargs)
        self.system_prompt = system_prompt

    async def on_message(self, sender: str, content: str, data: dict):
        # Only accept RESET from operator
        if content.strip() == "[RESET]":
            if sender == self.operator_role:
                self.transcript.clear()
                log.info("Session reset")
            return
        if not self.is_addressed(content): return
        prompt = self.strip_tags(content)
        if not prompt: return
        await self.send_typing()
        context = self.format_transcript()

        async def generate_with_typing():
            loop = asyncio.get_event_loop()
            task = loop.run_in_executor(None, self._sync_generate, prompt, context)
            while not task.done():
                await asyncio.sleep(4)
                if not task.done(): await self.send_typing()
            return await task

        try:
            response = await generate_with_typing()
        except Exception as e:
            log.error(f"Generation failed: {e}")
            response = f"[{self.display_name} error — check server logs]"
        self.transcript.append({"from": self.role, "content": response})
        await self.send(response)
        log.info(f"Responded ({len(response)} chars)")

    def _sync_generate(self, prompt: str, context: str) -> str:
        raise NotImplementedError("Implement _sync_generate in your bridge subclass")
