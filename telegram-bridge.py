#!/usr/bin/env python3
"""
ZeroRelay Telegram Bridge — Jimmy chats from Telegram.

Connects to the relay as 'jimmy' role and bridges messages
to/from a Telegram bot conversation.

Config via environment or /opt/zerorelay/telegram.env:
  TELEGRAM_BOT_TOKEN  — Bot token from @BotFather
  TELEGRAM_CHAT_ID    — Your chat ID (get via @userinfobot)
  TELEGRAM_USER_ID    — Your user ID for sender verification
"""

import asyncio
import json
import logging
import os
import re
import subprocess

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("telegram-bridge")

# Load config from env file if present
ENV_FILE = "/opt/zerorelay/telegram.env"
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))
RELAY_URL = "ws://100.127.106.41:8765"
ROLE = "jimmy"

# Relay auth token
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

# Sender display formatting for Telegram
SENDER_ICONS = {
    "vps_claude": "\U0001f9e0 Claude",
    "content_codex": "\U0001f4dd Content",
    "zee": "\u26a1 Zee",
    "jimmy": "\U0001f3cd Jimmy",
}

# Telegram Bot API via httpx (lighter than polling framework)
import httpx

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def html_escape(text: str) -> str:
    """Escape HTML special chars for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def tg_typing():
    """Show 'typing...' indicator in Telegram chat header."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{TG_API}/sendChatAction", json={
            "chat_id": CHAT_ID,
            "action": "typing",
        })


TG_MAX_LENGTH = 4096


def _chunk_text(text: str, max_len: int = TG_MAX_LENGTH) -> list[str]:
    """Split text into chunks that fit Telegram message size limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        else:
            cut += 1

        chunks.append(remaining[:cut])
        remaining = remaining[cut:]

    return chunks


async def tg_send(text: str, parse_mode: str = "HTML") -> int | None:
    """Send a message to Jimmy on Telegram. Returns message_id of last chunk."""
    chunks = _chunk_text(text)
    last_msg_id = None

    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            resp = await client.post(f"{TG_API}/sendMessage", json={
                "chat_id": CHAT_ID,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            })
            if resp.status_code == 200:
                last_msg_id = resp.json().get("result", {}).get("message_id")
                continue
            log.warning(f"Telegram send failed ({resp.status_code}), retrying plain")
            resp2 = await client.post(f"{TG_API}/sendMessage", json={
                "chat_id": CHAT_ID,
                "text": chunk,
                "disable_web_page_preview": True,
            })
            if resp2.status_code == 200:
                last_msg_id = resp2.json().get("result", {}).get("message_id")
            else:
                log.error(f"Telegram chunk failed ({len(chunk)} chars): {resp2.status_code}")

    return last_msg_id


async def tg_edit(message_id: int, text: str, parse_mode: str = "HTML"):
    """Edit an existing Telegram message."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{TG_API}/editMessageText", json={
            "chat_id": CHAT_ID,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        })
        if resp.status_code != 200:
            # Fallback without formatting
            await client.post(f"{TG_API}/editMessageText", json={
                "chat_id": CHAT_ID,
                "message_id": message_id,
                "text": text,
                "disable_web_page_preview": True,
            })


async def tg_poll(offset: int) -> tuple[list, int]:
    """Poll Telegram for new messages from Jimmy."""
    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.post(f"{TG_API}/getUpdates", json={
            "offset": offset,
            "timeout": 30,
            "allowed_updates": ["message"],
        })
        data = resp.json()
        updates = data.get("result", [])
        new_offset = offset
        messages = []
        for u in updates:
            new_offset = max(new_offset, u["update_id"] + 1)
            msg = u.get("message", {})
            # Only accept messages from our chat AND from the verified user
            if msg.get("chat", {}).get("id") == CHAT_ID and msg.get("text"):
                sender_id = msg.get("from", {}).get("id")
                if USER_ID and sender_id != USER_ID:
                    log.warning(f"Rejected message from unauthorized user_id={sender_id}")
                    continue
                messages.append(msg["text"])
        return messages, new_offset


async def relay_to_telegram(ws):
    """Read relay messages and forward to Telegram."""
    # Track streaming messages: sender -> telegram message_id
    stream_msg_ids: dict[str, int] = {}

    async for raw in ws:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg_type = data.get("type")

        if msg_type == "connected":
            peers = data.get("peers_online", [])
            log.info(f"Relay confirmed. Peers: {peers}")
            online = ", ".join(SENDER_ICONS.get(p, p) for p in peers)
            await tg_send(f"\U0001f517 <b>ZeroRelay connected</b>\nOnline: {html_escape(online or 'none')}")
            continue

        if msg_type == "system":
            sysmsg = data.get("message", "")
            log.info(f"System: {sysmsg}")
            # Suppress AI agent join/leave — they're always-on services
            if any(role in sysmsg for role in ("vps_claude", "content_codex", "zee")):
                continue
            # Use friendly names for any remaining system messages
            for role, icon in SENDER_ICONS.items():
                sysmsg = sysmsg.replace(role, icon)
            await tg_send(f"<i>\u2014 {html_escape(sysmsg)} \u2014</i>")
            continue

        if msg_type == "message":
            sender = data.get("from", "?")
            content = data.get("content", "")
            meta = data.get("meta")

            # On typing indicators, show Telegram typing action
            if meta == "typing_indicator":
                await tg_typing()
                continue

            # Skip own messages (they came from Telegram)
            if sender == ROLE:
                continue

            log.info(f"To Telegram [{sender}]: ({len(content)} chars)")

            # Update sticky target when an agent responds
            if sender == "vps_claude":
                sticky["agent"] = "claude"
            elif sender == "content_codex":
                sticky["agent"] = "content"
            elif sender == "zee":
                sticky["agent"] = "zee"

            label = SENDER_ICONS.get(sender, sender)

            # Handle streaming
            if meta == "stream_start":
                # Create new message, save its ID for edits
                log.info(f"Stream start [{sender}]")
                msg_text = f"<b>{html_escape(label)}</b>\n{html_escape(content)} \u258d"
                msg_id = await tg_send(msg_text)
                if msg_id:
                    stream_msg_ids[sender] = msg_id
                continue

            if meta == "stream_chunk":
                # Edit existing message with accumulated content
                msg_id = stream_msg_ids.get(sender)
                if msg_id:
                    msg_text = f"<b>{html_escape(label)}</b>\n{html_escape(content)} \u258d"
                    await tg_edit(msg_id, msg_text)
                continue

            if meta == "stream_end":
                # Final edit — remove cursor, clean up
                msg_id = stream_msg_ids.pop(sender, None)
                if msg_id:
                    msg_text = f"<b>{html_escape(label)}</b>\n{html_escape(content)}"
                    await tg_edit(msg_id, msg_text)
                else:
                    # No stream was started (short response), send normally
                    await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")
                continue

            # Regular (non-streaming) message
            await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")


TAG_PATTERN = re.compile(r"@(?:content|codex|c(?:laude)?|z(?:ee)?)\b", re.IGNORECASE)
CLAUDE_TAG = re.compile(r"@c(?:laude)?\b", re.IGNORECASE)
CONTENT_TAG = re.compile(r"@(?:content|codex)\b", re.IGNORECASE)
ZEE_TAG = re.compile(r"@z(?:ee)?\b", re.IGNORECASE)

# Sticky addressing state — shared between relay_to_telegram and telegram_to_relay
sticky = {"agent": None}  # "claude" | "content" | "zee"


async def telegram_to_relay(ws):
    """Poll Telegram for Jimmy's messages and forward to relay."""
    offset = 0
    # Drain any pending updates on startup
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TG_API}/getUpdates", json={"offset": -1})
        data = resp.json()
        updates = data.get("result", [])
        if updates:
            offset = updates[-1]["update_id"] + 1

    log.info(f"Telegram polling started (offset={offset})")

    while True:
        try:
            messages, offset = await tg_poll(offset)
            for text in messages:
                log.info(f"From Telegram: ({len(text)} chars)")

                cmd = text.strip().lower()

                # /killswitch — stop all AI bridges immediately
                if cmd == "/killswitch":
                    log.warning("KILLSWITCH activated by Jimmy")
                    stopped = []
                    for svc in ["claude-bridge", "content-codex-bridge", "zerobridge"]:
                        r = subprocess.run(
                            ["sudo", "systemctl", "stop", svc],
                            capture_output=True, text=True, timeout=10
                        )
                        if r.returncode == 0:
                            stopped.append(svc)
                        else:
                            log.error(f"Failed to stop {svc}: {r.stderr}")
                    msg = f"\U0001f534 <b>KILLSWITCH</b>\nStopped: {', '.join(stopped) or 'none'}"
                    await tg_send(msg)
                    await ws.send(json.dumps({"content": "[KILLSWITCH] AI bridges stopped by Jimmy"}))
                    continue

                # /start — start all AI bridges
                if cmd == "/start":
                    log.info("START requested by Jimmy")
                    started = []
                    for svc in ["claude-bridge", "content-codex-bridge", "zerobridge"]:
                        r = subprocess.run(
                            ["sudo", "systemctl", "start", svc],
                            capture_output=True, text=True, timeout=10
                        )
                        if r.returncode == 0:
                            started.append(svc)
                        else:
                            log.error(f"Failed to start {svc}: {r.stderr}")
                    msg = f"\U0001f7e2 <b>STARTED</b>\n\U0001f9e0 Claude: {'\u2713' if 'claude-bridge' in started else '\u2717'}\n\U0001f4dd Content: {'\u2713' if 'content-codex-bridge' in started else '\u2717'}\n\u26a1 Zee: {'\u2713' if 'zerobridge' in started else '\u2717'}"
                    await tg_send(msg)
                    continue

                # /status — check which bridges are running
                if cmd == "/status":
                    lines = []
                    for svc, label in [("claude-bridge", "\U0001f9e0 Claude"), ("content-codex-bridge", "\U0001f4dd Content"), ("zerobridge", "\u26a1 Zee"), ("telegram-bridge", "\U0001f3cd Telegram")]:
                        r = subprocess.run(
                            ["sudo", "systemctl", "is-active", svc],
                            capture_output=True, text=True, timeout=5
                        )
                        state = r.stdout.strip()
                        icon = "\u2713" if state == "active" else "\u2717"
                        lines.append(f"{icon} {label}: {state}")
                    await tg_send(f"\U0001f4ca <b>ZeroRelay Status</b>\n" + "\n".join(lines))
                    continue

                # /reset — clear all agent sessions and sticky target
                if cmd == "/reset":
                    log.info("RESET requested by Jimmy")
                    sticky["agent"] = None
                    await ws.send(json.dumps({"content": "[RESET]"}))
                    await tg_send("\U0001f504 <b>RESET</b>\nSessions cleared, sticky target cleared.")
                    continue

                # /stop — interrupt current Claude or Content Codex task
                if cmd == "/stop":
                    log.info("STOP requested by Jimmy")
                    targets = []
                    try:
                        if sticky["agent"] == "content":
                            targets = [("/opt/zerorelay/content-codex-stop", "Content")]
                        elif sticky["agent"] == "claude":
                            targets = [("/opt/zerorelay/stop-signal", "Claude")]
                        else:
                            targets = [
                                ("/opt/zerorelay/stop-signal", "Claude"),
                                ("/opt/zerorelay/content-codex-stop", "Content"),
                            ]

                        labels = []
                        for stop_file, label in targets:
                            with open(stop_file, "w") as sf:
                                sf.write("stop")
                            labels.append(label)
                        await tg_send(f"\u270b <b>STOP</b>\nSent stop signal to {html_escape(', '.join(labels))}.")
                    except Exception as e:
                        await tg_send(f"\u26a0\ufe0f <b>STOP failed</b>\n{html_escape(str(e))}")
                    continue


                # Check for explicit @tags and update sticky target
                has_tag = TAG_PATTERN.search(text)
                if has_tag:
                    if CLAUDE_TAG.search(text):
                        sticky["agent"] = "claude"
                    if CONTENT_TAG.search(text):
                        sticky["agent"] = "content"
                    if ZEE_TAG.search(text):
                        sticky["agent"] = "zee"
                    await tg_typing()
                    await ws.send(json.dumps({"content": text}))
                elif sticky["agent"] and not cmd.startswith("/"):
                    # No @tag — auto-route to last agent
                    if sticky["agent"] == "claude":
                        tag = "@c"
                    elif sticky["agent"] == "content":
                        tag = "@content"
                    else:
                        tag = "@z"
                    await tg_typing()
                    await ws.send(json.dumps({"content": f"{tag} {text}"}))
                else:
                    # No sticky target yet — send as plain message
                    await ws.send(json.dumps({"content": text}))
        except Exception as e:
            log.error(f"Telegram poll error: {e}")
            await asyncio.sleep(5)


async def main():
    if not BOT_TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required")
        log.error(f"Set them in {ENV_FILE} or as environment variables")
        return

    log.info(f"Telegram bridge starting (chat_id={CHAT_ID})")
    if USER_ID:
        log.info(f"Sender verification enabled (user_id={USER_ID})")
    else:
        log.warning("TELEGRAM_USER_ID not set — no sender verification!")

    # Register bot menu commands
    async with httpx.AsyncClient() as client:
        await client.post(f"{TG_API}/setMyCommands", json={
            "commands": [
                {"command": "status", "description": "Show which bridges are running"},
                {"command": "start", "description": "Start Claude, Content, and Zee bridges"},
                {"command": "stop", "description": "Interrupt the current AI task"},
                {"command": "reset", "description": "Clear all sessions and context"},
                {"command": "killswitch", "description": "Stop all AI bridges immediately"},
            ]
        })
        log.info("Bot menu commands registered")

    backoff = 3
    while True:
        try:
            token_param = f"&token={RELAY_TOKEN}" if RELAY_TOKEN else ""
            uri = f"{RELAY_URL}?role={ROLE}{token_param}"
            log.info(f"Connecting to relay")
            async with websockets.connect(uri) as ws:
                log.info("Connected to relay as jimmy")
                backoff = 3  # Reset on successful connect

                # Run both directions concurrently
                relay_task = asyncio.create_task(relay_to_telegram(ws))
                tg_task = asyncio.create_task(telegram_to_relay(ws))

                done, pending = await asyncio.wait(
                    [relay_task, tg_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()
                for t in done:
                    if t.exception():
                        log.error(f"Task error: {t.exception()}")

        except websockets.exceptions.ConnectionClosed:
            log.warning(f"Relay disconnected. Reconnecting in {backoff}s...")
        except ConnectionRefusedError:
            log.warning(f"Relay not available. Retrying in {backoff}s...")
        except Exception as e:
            log.error(f"Bridge error: {e}. Reconnecting in {backoff}s...")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
