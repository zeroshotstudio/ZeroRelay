#!/usr/bin/env python3
"""
Codex <-> ZeroRelay bridge dedicated to ZeroContentPipeline.

Connects as content_codex role. When @content or @codex is detected,
calls `codex exec` in /home/claude/ZeroContentPipeline.

This bridge is intentionally sandboxed to the content repo only:
- workspace-write sandbox
- no VPS-wide write access
- web search enabled for research tasks
- fresh stateless run per tagged message
"""

import asyncio
import fcntl
import json
import logging
import os
import re
import tempfile
from datetime import datetime

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("content-codex-bridge")

CODEX_TAG_PATTERN = re.compile(r"@(?:content|codex)\b", re.IGNORECASE)

RELAY_URL = "ws://100.127.106.41:8765"
ROLE = "content_codex"
WORKDIR = "/home/claude/ZeroContentPipeline"
INBOX = "/opt/zerorelay/content-codex.inbox"
OUTBOX = "/opt/zerorelay/content-codex.outbox"
OUTBOX_DONE = "/opt/zerorelay/content-codex.outbox.sent"
STOP_SIGNAL_FILE = "/opt/zerorelay/content-codex-stop"

RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
TYPING_INTERVAL_SEC = 4

CODEX_CONTEXT = """You are content_codex in ZeroRelay.

You are dedicated to one workspace only: /home/claude/ZeroContentPipeline.

Mission:
- Run the standalone ZeroLabs content pipeline end to end.
- Turn Telegram ideas into research briefs, drafts, reviews, visuals plans, publish runs, and audits.
- Use the repo's own CLI, skills, templates, validators, logs, and config.

Hard boundaries:
- Do not work outside /home/claude/ZeroContentPipeline.
- Do not make VPS, Docker, nginx, systemd, firewall, or host-level changes.
- Do not edit other repos.
- If Jimmy asks for host/admin work, tell him to tag @claude instead.
- Do not use API keys; the environment uses ChatGPT login and the repo-local MCP token file.

Working style:
- Be concise, action-oriented, and transparent.
- Prefer doing the task over explaining the plan.
- Keep changes inside the content pipeline repo.
- If publishing is blocked, explain the blocker and write artifacts instead of forcing it.

Reply style:
- Short and conversational.
- No headers unless asked.
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


async def call_codex(prompt: str, ws) -> str:
    check_stop_signal()

    with tempfile.NamedTemporaryFile(prefix="content-codex-", suffix=".txt", delete=False) as tmp:
        output_file = tmp.name

    cmd = [
        "codex",
        "--search",
        "--dangerously-bypass-approvals-and-sandbox",
        "exec",
        "-C",
        WORKDIR,
        "-o",
        output_file,
        "-",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=WORKDIR,
        )

        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        last_typing_time = asyncio.get_event_loop().time()
        while proc.returncode is None:
            if check_stop_signal():
                log.warning("Stop signal received — killing Codex subprocess")
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return "[Task stopped by Jimmy]"

            try:
                await asyncio.wait_for(proc.wait(), timeout=TYPING_INTERVAL_SEC)
            except asyncio.TimeoutError:
                try:
                    await ws.send(json.dumps({"content": "", "meta": "typing_indicator"}))
                except Exception:
                    pass
                last_typing_time = asyncio.get_event_loop().time()
                continue

        stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        response = ""
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                response = f.read().strip()

        if proc.returncode != 0 and not response:
            log.error(f"codex exec failed (rc={proc.returncode}): {stderr}")
            return "[Content Codex error: internal failure]"

        if not response:
            log.warning("codex exec returned empty response")
            return "[Content Codex returned no response]"

        return response
    except FileNotFoundError:
        log.error("codex CLI not found")
        return "[Error: codex CLI not found on this system]"
    finally:
        try:
            os.remove(output_file)
        except OSError:
            pass


async def watch_outbox(ws):
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
    os.makedirs("/opt/zerorelay", exist_ok=True)
    with open(INBOX, "w") as f:
        f.write(f"--- Content Codex Bridge started at {ts()} ---\n")
    with open(OUTBOX, "w") as f:
        f.write("")

    backoff = 3

    while True:
        try:
            token_param = f"&token={RELAY_TOKEN}" if RELAY_TOKEN else ""
            uri = f"{RELAY_URL}?role={ROLE}{token_param}"
            log.info("Connecting to relay")
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

                            log.info(f"From {sender}: ({len(content)} chars)")

                            if content.strip() == "[RESET]" and sender == "jimmy":
                                write_inbox(f"[{ts()}] Session reset requested")
                                continue

                            if not is_codex_addressed(content):
                                write_inbox(f"[{ts()}] {sender}: ({len(content)} chars)")
                                continue

                            prompt = strip_codex_tag(content)
                            if not prompt:
                                continue

                            write_inbox(f"[{ts()}] >>> @CONTENT from {sender}: ({len(prompt)} chars)")

                            try:
                                await ws.send(json.dumps({"content": "", "meta": "typing_indicator"}))
                            except Exception:
                                pass

                            full_prompt = (
                                f"{CODEX_CONTEXT}\n\n"
                                f"Telegram operator: {sender}\n"
                                f"Instruction: {prompt}\n"
                            )
                            response = await call_codex(full_prompt, ws)
                            log.info(f"Content Codex responded ({len(response)} chars)")

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
