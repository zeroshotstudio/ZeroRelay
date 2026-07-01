#!/usr/bin/env python3
"""
Codex CLI <-> ZeroRelay bridge for the main VPS workspace.

Connects as vps_codex. When @vpscodex or @codexvps is detected,
calls `codex exec` in /home/claude/ZeroVPS and keeps a persistent
Codex thread id so Telegram follow-ups behave like a real chat.

Also keeps file-based I/O for manual override:
  Inbox:  /opt/zerorelay/codex.inbox
  Outbox: /opt/zerorelay/codex.outbox
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import re
from datetime import datetime

import websockets

import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.relay_auth import relay_headers, relay_uri

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("codex-bridge")

CODEX_TAG_PATTERN = re.compile(r"@(?:vpscodex|codexvps)\b", re.IGNORECASE)

RELAY_URL = "ws://100.127.106.41:8765"
ROLE = "vps_codex"
WORKDIR = "/home/claude/ZeroVPS"
INBOX = "/opt/zerorelay/codex.inbox"
OUTBOX = "/opt/zerorelay/codex.outbox"
OUTBOX_DONE = "/opt/zerorelay/codex.outbox.sent"
STOP_SIGNAL_FILE = "/opt/zerorelay/codex-stop"
SESSION_FILE = "/opt/zerorelay/codex-session-id"

RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
SEARCH_ENABLED = os.environ.get("CODEX_SEARCH", "1").lower() not in {"0", "false", "no"}
CLI_TIMEOUT_SEC = int(os.environ.get("CODEX_TIMEOUT_SEC", "1800"))
SESSION_IDLE_RESET_SEC = int(os.environ.get("CODEX_SESSION_IDLE_SEC", "1800"))
TYPING_INTERVAL_SEC = 4

CODEX_CONTEXT = """You are Codex, running on Jimmy's VPS via the Codex CLI.
You are part of a ZeroRelay chat with Jimmy (Telegram), Claude, Zee, and the content pipeline.

Identity:
- You are the general VPS Codex agent, connected as `vps_codex`.
- Your working repo is /home/claude/ZeroVPS.
- Follow the repo's AGENTS.md and local docs as your operating instructions.
- You can inspect code, make changes, run commands, and help with VPS/dev tasks from that workspace.

Boundaries:
- Keep your primary work rooted in /home/claude/ZeroVPS unless the task clearly requires another path.
- The content pipeline has its own dedicated relay worker. If Jimmy wants blog-pipeline work, tell him to tag @content.
- If Jimmy asks you to message another agent, include the actual @tag in your reply so the relay delivers it.

Reply style:
- Short and conversational for Telegram.
- No headers unless asked.
- Prefer doing the work over long planning.
"""


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def write_inbox(line: str) -> None:
    with open(INBOX, "a") as f:
        f.write(line + "\n")


def is_codex_addressed(content: str) -> bool:
    return bool(CODEX_TAG_PATTERN.search(content))


def strip_codex_tag(content: str) -> str:
    return CODEX_TAG_PATTERN.sub("", content).strip()


def check_stop_signal() -> bool:
    if os.path.exists(STOP_SIGNAL_FILE):
        try:
            os.remove(STOP_SIGNAL_FILE)
        except OSError:
            pass
        return True
    return False


def load_session_id() -> str | None:
    if not os.path.exists(SESSION_FILE):
        return None
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        session_id = f.read().strip()
    return session_id or None


def save_session_id(session_id: str | None) -> None:
    if not session_id:
        clear_session_id()
        return
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        f.write(session_id)


def clear_session_id() -> None:
    try:
        os.remove(SESSION_FILE)
    except FileNotFoundError:
        pass


def parse_codex_events(stdout: str, fallback_session: str | None) -> tuple[str, str | None]:
    session_id = fallback_session
    messages: list[str] = []

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "thread.started":
            session_id = event.get("thread_id") or session_id
            continue

        if event.get("type") != "item.completed":
            continue

        item = event.get("item") or {}
        if item.get("type") != "agent_message":
            continue

        text = (item.get("text") or "").strip()
        if text:
            messages.append(text)

    response = messages[-1] if messages else ""
    return response, session_id


async def call_codex(prompt: str, ws, session_id: str | None) -> tuple[str, str | None, bool]:
    check_stop_signal()

    cmd = ["codex", "-C", WORKDIR]
    if SEARCH_ENABLED:
        cmd.append("--search")
    cmd.append("--dangerously-bypass-approvals-and-sandbox")

    if session_id:
        cmd.extend(["exec", "resume", "--json", session_id, "-"])
    else:
        cmd.extend(["exec", "--json", "-"])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=WORKDIR,
        )

        assert proc.stdin is not None
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        deadline = asyncio.get_event_loop().time() + CLI_TIMEOUT_SEC
        while proc.returncode is None:
            if check_stop_signal():
                log.warning("Stop signal received — terminating Codex subprocess")
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return "[Codex task stopped by Jimmy]", None, True

            try:
                await asyncio.wait_for(proc.wait(), timeout=TYPING_INTERVAL_SEC)
            except asyncio.TimeoutError:
                if asyncio.get_event_loop().time() >= deadline:
                    proc.kill()
                    await proc.wait()
                    log.error("codex exec timed out after %s seconds", CLI_TIMEOUT_SEC)
                    return "[Codex timed out]", None, False
                try:
                    await ws.send(json.dumps({"content": "", "meta": "typing_indicator"}))
                except Exception:
                    pass
                continue

        stdout = (await proc.stdout.read()).decode("utf-8", errors="replace")
        stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        response, resolved_session_id = parse_codex_events(stdout, session_id)

        if proc.returncode != 0 and not response:
            log.error("codex exec failed (rc=%s): %s", proc.returncode, stderr[:400] or "<no stderr>")
            return "[Codex error: internal failure]", None, False

        if stderr:
            log.warning("codex exec stderr: %s", stderr[:400])

        if not response:
            log.warning("codex exec returned no agent message")
            return "[Codex returned no response]", resolved_session_id, False

        return response, resolved_session_id, False
    except FileNotFoundError:
        log.error("codex CLI not found")
        return "[Error: codex CLI not found on this system]", None, False


async def watch_outbox(ws):
    while True:
        await asyncio.sleep(0.5)
        try:
            fd = os.open(OUTBOX, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                with os.fdopen(fd, "r", encoding="utf-8") as f:
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

                with open(OUTBOX_DONE, "a", encoding="utf-8") as f:
                    f.write(f"[{ts()}] {content}\n")
                await ws.send(json.dumps({"content": content}))
                write_inbox(f"[{ts()}] YOU (manual): {content}")
        except FileNotFoundError:
            pass
        except Exception as e:
            log.debug("Outbox watch error: %s", e)


async def main():
    os.makedirs("/opt/zerorelay", exist_ok=True)
    with open(INBOX, "w", encoding="utf-8") as f:
        f.write(f"--- Codex Bridge started at {ts()} ---\n")
    with open(OUTBOX, "w", encoding="utf-8") as f:
        f.write("")

    session_id = load_session_id()
    last_activity = datetime.now()
    backoff = 3

    while True:
        try:
            uri = relay_uri(RELAY_URL, ROLE)
            log.info("Connecting to relay")
            write_inbox(f"[{ts()}] Connecting to relay...")

            async with websockets.connect(uri, additional_headers=relay_headers()) as ws:
                log.info("Connected as %s", ROLE)
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
                            write_inbox(f"[{ts()}] Peers online: {', '.join(peers) or 'none'}")
                            if data.get("history"):
                                write_inbox(f"[{ts()}] ({len(data['history'])} history messages)")
                            continue

                        if msg_type == "system":
                            message = data.get("message", "")
                            log.info("System: %s", message)
                            write_inbox(f"[{ts()}] * {message}")
                            continue

                        if msg_type != "message":
                            continue

                        sender = data.get("from", "?")
                        content = data.get("content", "")
                        meta = data.get("meta")

                        if sender == ROLE or meta in ("typing_indicator", "stream_start", "stream_chunk"):
                            continue

                        if content.strip() == "[RESET]" and sender == "jimmy":
                            session_id = None
                            clear_session_id()
                            last_activity = datetime.now()
                            write_inbox(f"[{ts()}] Session reset requested")
                            continue

                        if not is_codex_addressed(content):
                            write_inbox(f"[{ts()}] {sender}: ({len(content)} chars)")
                            continue

                        idle_sec = (datetime.now() - last_activity).total_seconds()
                        if session_id and idle_sec > SESSION_IDLE_RESET_SEC:
                            log.info("Session idle-reset after %.0fs", idle_sec)
                            session_id = None
                            clear_session_id()

                        prompt = strip_codex_tag(content)
                        if not prompt:
                            continue

                        write_inbox(f"[{ts()}] >>> @CODEX from {sender}: ({len(prompt)} chars)")

                        if session_id:
                            full_prompt = (
                                f"Relay sender: {sender}\n"
                                f"Telegram message: {prompt}\n\n"
                                "Reply for Telegram in a short conversational style."
                            )
                        else:
                            full_prompt = (
                                f"{CODEX_CONTEXT}\n\n"
                                f"Relay sender: {sender}\n"
                                f"Telegram message: {prompt}\n\n"
                                "Reply for Telegram in a short conversational style."
                            )

                        try:
                            await ws.send(json.dumps({"content": "", "meta": "typing_indicator"}))
                        except Exception:
                            pass

                        response, next_session_id, stopped = await call_codex(full_prompt, ws, session_id)
                        if stopped:
                            session_id = None
                            clear_session_id()
                        elif next_session_id:
                            session_id = next_session_id
                            save_session_id(session_id)

                        last_activity = datetime.now()
                        log.info("Codex responded (%s chars)", len(response))
                        await ws.send(json.dumps({"content": response}))
                        write_inbox(f"[{ts()}] YOU (auto): ({len(response)} chars)")
                finally:
                    outbox_task.cancel()
        except websockets.exceptions.ConnectionClosed:
            log.warning("Disconnected. Reconnecting in %ss...", backoff)
            write_inbox(f"[{ts()}] Disconnected. Reconnecting in {backoff}s...")
        except ConnectionRefusedError:
            log.warning("Relay not available. Retrying in %ss...", backoff)
            write_inbox(f"[{ts()}] Relay not available. Retrying in {backoff}s...")
        except Exception as e:
            log.error("Bridge error: %s. Reconnecting in %ss...", e, backoff)
            write_inbox(f"[{ts()}] Error: {e}. Reconnecting in {backoff}s...")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
