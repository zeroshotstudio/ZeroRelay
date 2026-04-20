#!/usr/bin/env python3
"""
Claude Code <-> ZeroRelay bridge.

Connects as vps_claude role. When @claude or @c is detected,
calls `claude -p` CLI to generate a response automatically.

Also keeps file-based I/O for manual override:
  Inbox:  /opt/zerorelay/inbox   (log of all messages)
  Outbox: /opt/zerorelay/outbox  (write here -> sent to relay, bypasses AI)
"""

import asyncio
import fcntl
import json
import logging
import os
import re
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
SESSION_IDLE_RESET_SEC = 30 * 60  # Reset session after 30 min idle
STOP_SIGNAL_FILE = "/opt/zerorelay/stop-signal"

# Relay auth token
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

CLAUDE_CONTEXT = """You are vps_claude in a 3-party relay chat called ZeroRelay, running on Jimmy's VPS via claude -p (Claude Code CLI).

Who's here:
- Jimmy — Human operator. Final say on everything. Talks via Telegram.
- Zee — OpenClaw Main Agent. Zee runs ONLY inside his OpenClaw Docker container. He can run commands, write code, and manage things within that container, but he has ZERO access to the VPS host — no nginx, no systemd, no other Docker containers, no host filesystem. If Zee needs something done outside his container, he must ask you or Jimmy.
- You (Claude) — You are the star of the show, and Jimmy's right-hand man. You run as a dedicated `claude` user on the VPS (not root) with scoped sudo for privileged operations. You have full access to Docker (via group membership), and can manage nginx, systemd, firewall, and other apps via sudo. You can access any Docker container including Zee's. You think proactively to save time for Jimmy. You run using the ZeroVPS workflow which has a CLAUDE.md file with lots of information. You think things through, give recommendations, solve problems, review plans, write code, and action changes anywhere on the server. You are security minded and always ensure environments are hardened and secure. You are NOT a browser artifact — you run as a systemd service (`claude-bridge`). When Zee needs host-level support, you step in.

How to talk to others:
- Your reply is broadcast to everyone.
- To reach Zee, you MUST include a @z or @zee tag, this will route the message directly to Zee.
- To reach Jimmy, just talk normally.
- IMPORTANT: If asked to message someone, actually include their @tag. Don't say "Done, I messaged them" without writing the real message. You do not have the ability to message anyone outside of the telegram chat.

CRITICAL: Anytime you direct a message TO another agent (Zee), you MUST include their @tag (@z or @zee) in EVERY such message — not just the first one. No exceptions.

How the relay works:
- You only receive messages when someone tags @claude or @c.
- The transcript shows recent context.
- Jimmy sees all messages. Zee and you only see messages when tagged.

Response style: Short and conversational. No headers/preamble unless asked."""


def get_session_id():
    """Get existing session ID from file, or None if no session yet."""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            sid = f.read().strip()
            if sid:
                return sid
    return None


def new_session_id():
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
    return bool(CLAUDE_TAG_PATTERN.search(content))



def check_stop_signal():
    """Check if a stop signal has been sent and consume it."""
    if os.path.exists(STOP_SIGNAL_FILE):
        try:
            os.remove(STOP_SIGNAL_FILE)
        except OSError:
            pass
        return True
    return False

def strip_claude_tag(content: str) -> str:
    return CLAUDE_TAG_PATTERN.sub("", content).strip()


TYPING_INTERVAL_SEC = 4


async def call_claude(prompt: str, ws, session_id: str, is_new_session: bool):
    """Call claude CLI. Uses --session-id for new sessions, --resume for existing ones.

    Returns (response_text, session_id, session_is_established).
    """
    mode = "--session-id" if is_new_session else "--resume"
    log.info(f"Calling claude -p {mode} (session={session_id[:8]}...)...")

    # Clear any stale stop signal
    check_stop_signal()

    try:
        cmd = [
            "claude", "-p",
            "--model", "claude-opus-4-6",
            "--add-dir", "/",
            mode, session_id,
        ]
        # Only pass system prompt on first message (session creation)
        if is_new_session:
            cmd.extend(["--system-prompt", CLAUDE_CONTEXT])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        accumulated = ""
        last_typing_time = asyncio.get_event_loop().time()

        while True:
            # Check for stop signal from /stop command
            if check_stop_signal():
                log.warning("Stop signal received — killing Claude subprocess")
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return "[Task stopped by Jimmy]", session_id, True

            try:
                chunk = await asyncio.wait_for(
                    proc.stdout.read(512),
                    timeout=TYPING_INTERVAL_SEC
                )
            except asyncio.TimeoutError:
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
                break

            accumulated += chunk.decode("utf-8", errors="replace")

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

            if "already in use" in stderr:
                # Session is stuck — rotate to a brand new session
                new_sid = new_session_id()
                log.warning(f"Session locked, rotating to new session: {new_sid[:8]}...")
                return await call_claude(prompt, ws, new_sid, is_new_session=True)

            return "[Claude error: internal failure]", session_id, not is_new_session

        if not response:
            log.warning("claude -p returned empty response")
            return "[Claude returned no response]", session_id, not is_new_session

        # Session is now established (created or resumed successfully)
        return response, session_id, True

    except FileNotFoundError:
        log.error("claude CLI not found")
        return "[Error: claude CLI not found on this system]", session_id, not is_new_session


async def watch_outbox(ws):
    """Poll outbox file for manual messages to send."""
    while True:
        await asyncio.sleep(0.5)
        try:
            fd = os.open(OUTBOX, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                with os.fdopen(fd, "r") as f:
                    content = f.read().strip()
            except Exception:
                os.close(fd)
                raise

            if content:
                fd_w = os.open(OUTBOX, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
                try:
                    fcntl.flock(fd_w, fcntl.LOCK_EX)
                    os.close(fd_w)
                except Exception:
                    os.close(fd_w)
                    raise

                with open(OUTBOX_DONE, "a") as f:
                    f.write(f"[{ts()}] {content}\n")
                await ws.send(json.dumps({"content": content}))
                write_inbox(f"[{ts()}] YOU (manual): {content}")
        except FileNotFoundError:
            pass
        except Exception as e:
            log.debug(f"Outbox watch error: {e}")


async def main():
    with open(INBOX, "w") as f:
        f.write(f"--- Claude Bridge started at {ts()} ---\n")
    with open(OUTBOX, "w") as f:
        f.write("")

    session_id = get_session_id()
    # Track whether this session has been created (first message sent)
    session_established = session_id is not None

    if session_id is None:
        session_id = new_session_id()
        session_established = False

    log.info(f"Session: {session_id} (established={session_established})")

    last_activity = datetime.now()
    backoff = 3

    while True:
        try:
            token_param = f"&token={RELAY_TOKEN}" if RELAY_TOKEN else ""
            uri = f"{RELAY_URL}?role={ROLE}{token_param}"
            log.info(f"Connecting to relay")
            write_inbox(f"[{ts()}] Connecting to relay...")

            async with websockets.connect(uri) as ws:
                log.info(f"Connected as {ROLE}")
                write_inbox(f"[{ts()}] Connected as {ROLE}")
                backoff = 3

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

                            meta = data.get("meta")
                            if sender == ROLE or meta in ("typing_indicator", "stream_start", "stream_chunk"):
                                continue
                            if meta == "stream_end":
                                pass

                            log.info(f"From {sender}: ({len(content)} chars)")

                            # Handle session reset (only from jimmy)
                            if content.strip() == "[RESET]" and sender == "jimmy":
                                session_id = new_session_id()
                                session_established = False
                                log.info(f"Session reset. New: {session_id}")
                                continue

                            if not is_claude_addressed(content):
                                write_inbox(f"[{ts()}] {sender}: ({len(content)} chars)")
                                continue

                            write_inbox(f"[{ts()}] >>> @CLAUDE from {sender}: ({len(content)} chars)")

                            prompt = strip_claude_tag(content)
                            if not prompt:
                                continue

                            # Check for idle session reset
                            idle_sec = (datetime.now() - last_activity).total_seconds()
                            if idle_sec > SESSION_IDLE_RESET_SEC:
                                session_id = new_session_id()
                                session_established = False
                                log.info(f"Session auto-reset (idle {idle_sec:.0f}s). New: {session_id}")

                            last_activity = datetime.now()

                            try:
                                await ws.send(json.dumps({
                                    "content": "", "meta": "typing_indicator"
                                }))
                            except Exception:
                                pass

                            full_prompt = f"{sender}: {prompt}"

                            response, session_id, session_established = await call_claude(
                                full_prompt, ws, session_id,
                                is_new_session=not session_established
                            )

                            log.info(f"Claude responded ({len(response)} chars)")

                            await ws.send(json.dumps({"content": response}))
                            write_inbox(f"[{ts()}] YOU (auto): ({len(response)} chars)")

                finally:
                    outbox_task.cancel()

        except websockets.exceptions.ConnectionClosed:
            log.warning(f"Disconnected. Reconnecting in {backoff}s...")
            write_inbox(f"[{ts()}] Disconnected. Reconnecting in {backoff}s...")
        except ConnectionRefusedError:
            log.warning(f"Relay not available. Retrying in {backoff}s...")
            write_inbox(f"[{ts()}] Relay not available. Retrying in {backoff}s...")
        except Exception as e:
            log.error(f"Bridge error: {e}. Reconnecting in {backoff}s...")
            write_inbox(f"[{ts()}] Error: {e}. Reconnecting in {backoff}s...")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
