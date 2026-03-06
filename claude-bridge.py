#!/usr/bin/env python3
"""
Claude Code ↔ ZeroRelay bridge.

Connects as claude_ai role. When @claude or @c is detected,
calls `claude -p` CLI to generate a response automatically.

Also keeps file-based I/O for manual override:
  Inbox:  /opt/zerorelay/inbox   (log of all messages)
  Outbox: /opt/zerorelay/outbox  (write here → sent to relay, bypasses AI)
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("claude-bridge")

# Addressing — respond when tagged @claude or @c
CLAUDE_TAG_PATTERN = re.compile(r"@c(?:laude)?\b", re.IGNORECASE)

RELAY_URL = "ws://100.127.106.41:8765"
ROLE = "vps_claude"
INBOX = "/opt/zerorelay/inbox"
OUTBOX = "/opt/zerorelay/outbox"
OUTBOX_DONE = "/opt/zerorelay/outbox.sent"

CLI_TIMEOUT_SEC = 120
SESSION_FILE = "/opt/zerorelay/claude-session-id"

CLAUDE_CONTEXT = """You are Claude, running on Jimmy's VPS via the Claude Code CLI (`claude -p`). You are part of a 3-party relay chat called ZeroRelay.

## Who's here
- **Jimmy** — Human operator. Has final say on everything. Talks via Telegram.
- **Zee** — Execution AI also on the VPS, powered by OpenClaw. Can run commands, manage the server, write code.
- **You (Claude)** — Advisor AI, also running on the VPS via Claude Code CLI. You think things through, give recommendations, review plans, and help reason about problems. You are NOT a browser artifact — you run on the server as a systemd service (`claude-bridge`).

## Your identity
- You are `vps_claude` in the relay — because you ARE Claude running on the VPS
- You run on the VPS at server.zeroshot.studio via `claude -p`
- You have a persistent session — you remember the full conversation history across messages
- If conversation gets very long, your context will be automatically compressed

## How to talk to others
- Your reply is broadcast to everyone in the chat.
- To talk to Zee, include @z or @zee in your message — the relay will route it and Zee will respond.
- To address Jimmy, just talk normally — he sees everything.
- IMPORTANT: If asked to message someone, you MUST actually include their @tag in your reply. Do NOT just say "Done, I messaged them" — that's a lie. Write the actual message with the @tag so the relay delivers it.

## How the relay works
- Messages only reach you when someone tags @claude or @c
- The transcript below shows recent conversation for context
- Jimmy sees all messages. Zee and you only see messages when tagged.

## How to respond
- Keep it **short and conversational** — this is chat, not a document
- 1-3 sentences for simple questions, a short paragraph for complex ones
- No headers, no code blocks unless specifically asked for code
- No preamble ("Sure!", "Great question!") — just answer directly

## Your strengths
- Thinking through approaches and tradeoffs
- Reviewing plans before execution
- Explaining concepts or debugging logic
- Brainstorming and creative problem-solving
- Drafting text, messages, or documentation

## Leave to Zee
- Running commands on the VPS
- Docker/server management
- File editing and code changes on the server
- Anything requiring execution"""


def get_session_id():
    """Get or create a persistent session ID."""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            sid = f.read().strip()
            if sid:
                return sid
    return rotate_session_id()


def rotate_session_id():
    """Create a new session ID and save it."""
    sid = str(uuid.uuid4())
    with open(SESSION_FILE, "w") as f:
        f.write(sid)
    log.info(f"New session ID: {sid}")
    return sid


def ts():
    return datetime.now().strftime("%H:%M:%S")


def write_inbox(line):
    with open(INBOX, "a") as f:
        f.write(line + "\n")


def is_claude_addressed(content: str) -> bool:
    """Check if message is addressed to Claude via @claude or @c tag."""
    return bool(CLAUDE_TAG_PATTERN.search(content))


def strip_claude_tag(content: str) -> str:
    """Remove @claude/@c tag from message, leaving the rest."""
    return CLAUDE_TAG_PATTERN.sub("", content).strip()


TYPING_INTERVAL_SEC = 4  # Re-send typing indicator before Telegram's 5s expiry


async def stream_claude(prompt: str, ws, sender: str, session_id: str):
    """Call claude CLI with persistent session, keeping typing indicator alive."""
    log.info(f"Calling claude -p (session={session_id[:8]}...)...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p",
            "--model", "sonnet",
            "--session-id", session_id,
            "--system-prompt", CLAUDE_CONTEXT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Send prompt to stdin
        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        accumulated = ""
        last_typing_time = asyncio.get_event_loop().time()

        while True:
            try:
                chunk = await asyncio.wait_for(
                    proc.stdout.read(512),
                    timeout=TYPING_INTERVAL_SEC
                )
            except asyncio.TimeoutError:
                # No data yet but process still running — keep typing indicator alive
                if proc.returncode is None:
                    try:
                        await ws.send(json.dumps({
                            "content": "", "meta": "typing_indicator"
                        }))
                    except Exception:
                        pass
                    last_typing_time = asyncio.get_event_loop().time()
                    continue
                else:
                    break

            if not chunk:
                break  # EOF

            accumulated += chunk.decode("utf-8", errors="replace")

            # Keep typing indicator alive during generation
            now = asyncio.get_event_loop().time()
            if now - last_typing_time >= TYPING_INTERVAL_SEC:
                try:
                    await ws.send(json.dumps({
                        "content": "", "meta": "typing_indicator"
                    }))
                except Exception:
                    pass
                last_typing_time = now

        await proc.wait()
        response = accumulated.strip()

        if proc.returncode != 0 and not response:
            stderr = (await proc.stderr.read()).decode().strip()
            log.error(f"claude -p failed (rc={proc.returncode}): {stderr}")
            return f"[Claude error: {stderr[:200]}]"

        if not response:
            log.warning("claude -p returned empty response")
            return "[Claude returned no response]"

        return response

    except FileNotFoundError:
        log.error("claude CLI not found")
        return "[Error: claude CLI not found on this system]"


async def watch_outbox(ws):
    """Poll outbox file for manual messages to send."""
    while True:
        await asyncio.sleep(0.5)
        if os.path.exists(OUTBOX) and os.path.getsize(OUTBOX) > 0:
            with open(OUTBOX, "r") as f:
                content = f.read().strip()
            if content:
                with open(OUTBOX, "w") as f:
                    f.write("")
                with open(OUTBOX_DONE, "a") as f:
                    f.write(f"[{ts()}] {content}\n")
                await ws.send(json.dumps({"content": content}))
                write_inbox(f"[{ts()}] YOU (manual): {content}")


async def main():
    # Clear inbox on start
    with open(INBOX, "w") as f:
        f.write(f"--- Claude Bridge started at {ts()} ---\n")
    with open(OUTBOX, "w") as f:
        f.write("")

    session_id = get_session_id()
    log.info(f"Using session: {session_id}")

    while True:
        try:
            uri = f"{RELAY_URL}?role={ROLE}"
            log.info(f"Connecting to relay: {uri}")
            write_inbox(f"[{ts()}] Connecting to {RELAY_URL}...")

            async with websockets.connect(uri) as ws:
                log.info(f"Connected as {ROLE}")
                write_inbox(f"[{ts()}] Connected as {ROLE}")

                # Start outbox watcher for manual overrides
                outbox_task = asyncio.create_task(watch_outbox(ws))

                try:
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = data.get("type")

                        if msg_type == "connected":
                            peers = data.get("peers_online", [])
                            log.info(f"Relay confirmed. Peers: {peers}")
                            write_inbox(f"[{ts()}] Peers online: {', '.join(peers) or 'none'}")
                            if data.get("history"):
                                write_inbox(f"[{ts()}] ({len(data['history'])} history messages)")
                            continue

                        if msg_type == "system":
                            log.info(f"System: {data.get('message')}")
                            write_inbox(f"[{ts()}] * {data.get('message')}")
                            continue

                        if msg_type == "message":
                            sender = data.get("from", "?")
                            content = data.get("content", "")

                            # Skip own messages, typing indicators, and stream chunks
                            meta = data.get("meta")
                            if sender == ROLE or meta in ("typing_indicator", "stream_start", "stream_chunk"):
                                continue
                            # For stream_end, treat as a normal message (final content)
                            if meta == "stream_end":
                                pass  # fall through to normal processing

                            log.info(f"From {sender}: {content[:100]}")

                            # Handle session reset
                            if content.strip() == "[RESET]":
                                session_id = rotate_session_id()
                                log.info(f"Session reset. New: {session_id}")
                                continue

                            # Only respond when addressed
                            if not is_claude_addressed(content):
                                write_inbox(f"[{ts()}] {sender}: {content}")
                                continue

                            write_inbox(f"[{ts()}] >>> @CLAUDE from {sender}: {content}")

                            # Strip the tag for the actual prompt
                            prompt = strip_claude_tag(content)
                            if not prompt:
                                continue

                            # Signal typing to Telegram
                            try:
                                await ws.send(json.dumps({
                                    "content": "", "meta": "typing_indicator"
                                }))
                            except Exception:
                                pass

                            # Send to Claude with session context
                            full_prompt = f"{sender}: {prompt}"

                            # Stream claude response
                            response = await stream_claude(full_prompt, ws, sender, session_id)

                            log.info(f"Claude responded: {response[:100]}")

                            # Send final response
                            await ws.send(json.dumps({"content": response}))
                            write_inbox(f"[{ts()}] YOU (auto): {response}")

                finally:
                    outbox_task.cancel()

        except websockets.exceptions.ConnectionClosed:
            log.warning("Disconnected. Reconnecting in 3s...")
            write_inbox(f"[{ts()}] Disconnected. Reconnecting in 3s...")
        except ConnectionRefusedError:
            log.warning("Relay not available. Retrying in 5s...")
            write_inbox(f"[{ts()}] Relay not available. Retrying in 5s...")
            await asyncio.sleep(5)
            continue
        except Exception as e:
            log.error(f"Bridge error: {e}. Reconnecting in 3s...")
            write_inbox(f"[{ts()}] Error: {e}. Reconnecting in 3s...")

        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
