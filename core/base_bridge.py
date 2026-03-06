#!/usr/bin/env python3
"""
Base bridge class for ZeroRelay.

All bridges (AI backends and chat interfaces) inherit from this.
Handles: WebSocket connection, reconnection, message routing,
@-mention detection, typing indicators, and transcript tracking.

To create a new bridge, subclass BaseBridge and implement:
  - on_message(sender, content, data) — called for every message
  - For AI bridges: also implement generate_response(prompt, transcript)
"""

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime

import websockets

log = logging.getLogger("bridge")


class BaseBridge(ABC):
    """Base class for all ZeroRelay bridges."""

    def __init__(
        self,
        relay_url: str,
        role: str,
        tags: list[str] | None = None,
        display_name: str | None = None,
        max_transcript: int = 30,
    ):
        self.relay_url = relay_url
        self.role = role
        self.tags = tags
        self.display_name = display_name or role
        self.max_transcript = max_transcript
        self.transcript: list[dict] = []
        self.ws: websockets.WebSocketClientProtocol | None = None

        if tags:
            escaped = [re.escape(t.lstrip("@")) for t in tags]
            pattern = "|".join(escaped)
            self._tag_re = re.compile(rf"@(?:{pattern})\b", re.IGNORECASE)
        else:
            self._tag_re = None

    def is_addressed(self, content: str) -> bool:
        if self._tag_re is None:
            return True
        return bool(self._tag_re.search(content))

    def strip_tags(self, content: str) -> str:
        if self._tag_re is None:
            return content
        return self._tag_re.sub("", content).strip()

    def format_transcript(self) -> str:
        if not self.transcript:
            return "(no prior messages)"
        lines = []
        for msg in self.transcript[-self.max_transcript:]:
            sender = msg.get("from", "system")
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"[{sender}]: {content}")
        return "\n".join(lines)

    async def send(self, content: str, meta: str | None = None):
        if not self.ws:
            return
        msg = {"content": content}
        if meta:
            msg["meta"] = meta
        try:
            await self.ws.send(json.dumps(msg))
        except Exception as e:
            log.error(f"Send failed: {e}")

    async def send_typing(self):
        await self.send("", meta="typing_indicator")

    @abstractmethod
    async def on_message(self, sender: str, content: str, data: dict):
        pass

    async def on_connect(self, peers: list[str]):
        log.info(f"Connected as {self.role}. Peers: {peers}")

    async def on_system(self, message: str):
        log.info(f"System: {message}")

    async def run(self):
        uri = f"{self.relay_url}?role={self.role}"
        while True:
            try:
                log.info(f"Connecting to relay: {uri}")
                async with websockets.connect(uri) as ws:
                    self.ws = ws
                    log.info(f"Connected as {self.role}")
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        msg_type = data.get("type")
                        if msg_type == "connected":
                            peers = data.get("peers_online", [])
                            for h in data.get("history", []):
                                if h.get("type") == "message":
                                    self.transcript.append(h)
                            await self.on_connect(peers)
                            continue
                        if msg_type == "system":
                            await self.on_system(data.get("message", ""))
                            continue
                        if msg_type == "message":
                            sender = data.get("from", "")
                            content = data.get("content", "")
                            meta = data.get("meta")
                            if sender == self.role:
                                continue
                            if meta in ("typing_indicator", "stream_start", "stream_chunk"):
                                continue
                            self.transcript.append({"from": sender, "content": content})
                            await self.on_message(sender, content, data)
            except websockets.exceptions.ConnectionClosed:
                log.warning("Relay disconnected. Reconnecting in 3s...")
            except ConnectionRefusedError:
                log.warning("Relay not available. Retrying in 5s...")
                await asyncio.sleep(5)
                continue
            except Exception as e:
                log.error(f"Bridge error: {e}. Reconnecting in 3s...")
            self.ws = None
            await asyncio.sleep(3)


class AIBridge(BaseBridge):
    """Base class for AI backend bridges. Subclass and implement _sync_generate()."""

    def __init__(self, system_prompt: str = "", **kwargs):
        super().__init__(**kwargs)
        self.system_prompt = system_prompt

    @abstractmethod
    async def generate_response(self, prompt: str, context: str) -> str:
        pass

    async def on_message(self, sender: str, content: str, data: dict):
        if content.strip() == "[RESET]":
            self.transcript.clear()
            log.info("Session reset")
            return
        if not self.is_addressed(content):
            return
        prompt = self.strip_tags(content)
        if not prompt:
            return
        await self.send_typing()
        context = self.format_transcript()

        async def generate_with_typing():
            loop = asyncio.get_event_loop()
            task = loop.run_in_executor(None, self._sync_generate, prompt, context)
            while not task.done():
                await asyncio.sleep(4)
                if not task.done():
                    await self.send_typing()
            return await task

        try:
            response = await generate_with_typing()
        except Exception as e:
            log.error(f"Generation failed: {e}")
            response = f"[{self.display_name} error: {e}]"
        self.transcript.append({"from": self.role, "content": response})
        await self.send(response)
        log.info(f"Responded: {response[:100]}")

    def _sync_generate(self, prompt: str, context: str) -> str:
        raise NotImplementedError("Implement _sync_generate in your bridge subclass")
