#!/usr/bin/env python3
"""
ZeroRelay Telegram Bridge — Jimmy chats from Telegram.

Connects to the relay as 'jimmy' role and bridges messages
to/from a Telegram bot conversation.

Config via environment or /opt/zerorelay/telegram.env:
  TELEGRAM_BOT_TOKEN  — Bot token from @BotFather
  TELEGRAM_CHAT_ID    — Your chat ID (get via @userinfobot)
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
RELAY_URL = "ws://100.127.106.41:8765"
ROLE = "jimmy"

# Sender display formatting for Telegram
SENDER_ICONS = {
    "vps_claude": "🧠 Claude",
    "zee": "⚡ Zee",
    "jimmy": "🏍 Jimmy",
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


async def tg_send(text: str, parse_mode: str = "HTML") -> int | None:
    """Send a message to Jimmy on Telegram. Returns message_id."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{TG_API}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        })
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("message_id")
        # Fallback: send without formatting
        log.warning(f"Telegram send failed ({resp.status_code}), retrying plain")
        resp2 = await client.post(f"{TG_API}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        })
        if resp2.status_code == 200:
            return resp2.json().get("result", {}).get("message_id")
        return None


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
            # Only accept messages from our chat
            if msg.get("chat", {}).get("id") == CHAT_ID and msg.get("text"):
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
            await tg_send(f"🔗 <b>ZeroRelay connected</b>\nOnline: {html_escape(online or 'none')}")
            continue

        if msg_type == "system":
            sysmsg = data.get("message", "")
            log.info(f"System: {sysmsg}")
            # Suppress AI agent join/leave — they're always-on services
            if any(role in sysmsg for role in ("vps_claude", "zee")):
                continue
            # Use friendly names for any remaining system messages
            for role, icon in SENDER_ICONS.items():
                sysmsg = sysmsg.replace(role, icon)
            await tg_send(f"<i>— {html_escape(sysmsg)} —</i>")
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

            # Update sticky target when an agent responds
            if sender == "vps_claude":
                sticky["agent"] = "claude"
            elif sender == "zee":
                sticky["agent"] = "zee"

            label = SENDER_ICONS.get(sender, sender)

            # Handle streaming
            if meta == "stream_start":
                # Create new message, save its ID for edits
                log.info(f"Stream start [{sender}]: {content[:60]}...")
                msg_text = f"<b>{html_escape(label)}</b>\n{html_escape(content)} ▍"
                msg_id = await tg_send(msg_text)
                if msg_id:
                    stream_msg_ids[sender] = msg_id
                continue

            if meta == "stream_chunk":
                # Edit existing message with accumulated content
                msg_id = stream_msg_ids.get(sender)
                if msg_id:
                    log.info(f"Stream chunk [{sender}]: ...{content[-40:]}")
                    msg_text = f"<b>{html_escape(label)}</b>\n{html_escape(content)} ▍"
                    await tg_edit(msg_id, msg_text)
                continue

            if meta == "stream_end":
                # Final edit — remove cursor, clean up
                msg_id = stream_msg_ids.pop(sender, None)
                if msg_id:
                    log.info(f"Stream end [{sender}]: {content[:80]}")
                    msg_text = f"<b>{html_escape(label)}</b>\n{html_escape(content)}"
                    await tg_edit(msg_id, msg_text)
                else:
                    # No stream was started (short response), send normally
                    log.info(f"To Telegram [{sender}]: {content[:80]}")
                    await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")
                continue

            # Regular (non-streaming) message
            log.info(f"To Telegram [{sender}]: {content[:80]}")
            await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")


TAG_PATTERN = re.compile(r"@(?:c(?:laude)?|z(?:ee)?)\b", re.IGNORECASE)
CLAUDE_TAG = re.compile(r"@c(?:laude)?\b", re.IGNORECASE)
ZEE_TAG = re.compile(r"@z(?:ee)?\b", re.IGNORECASE)

# Sticky addressing state — shared between relay_to_telegram and telegram_to_relay
sticky = {"agent": None}  # "claude" or "zee"


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
                log.info(f"From Telegram: {text[:80]}")

                cmd = text.strip().lower()

                # /killswitch — stop both AI bridges immediately
                if cmd == "/killswitch":
                    log.warning("KILLSWITCH activated by Jimmy")
                    stopped = []
                    for svc in ["claude-bridge", "zerobridge"]:
                        r = subprocess.run(
                            ["systemctl", "stop", svc],
                            capture_output=True, text=True, timeout=10
                        )
                        if r.returncode == 0:
                            stopped.append(svc)
                        else:
                            log.error(f"Failed to stop {svc}: {r.stderr}")
                    msg = f"🔴 <b>KILLSWITCH</b>\nStopped: {', '.join(stopped) or 'none'}"
                    await tg_send(msg)
                    await ws.send(json.dumps({"content": "[KILLSWITCH] AI bridges stopped by Jimmy"}))
                    continue

                # /start — start both AI bridges
                if cmd == "/start":
                    log.info("START requested by Jimmy")
                    started = []
                    for svc in ["claude-bridge", "zerobridge"]:
                        r = subprocess.run(
                            ["systemctl", "start", svc],
                            capture_output=True, text=True, timeout=10
                        )
                        if r.returncode == 0:
                            started.append(svc)
                        else:
                            log.error(f"Failed to start {svc}: {r.stderr}")
                    msg = f"🟢 <b>STARTED</b>\n🧠 Claude: {'✓' if 'claude-bridge' in started else '✗'}\n⚡ Zee: {'✓' if 'zerobridge' in started else '✗'}"
                    await tg_send(msg)
                    continue

                # /status — check which bridges are running
                if cmd == "/status":
                    lines = []
                    for svc, label in [("claude-bridge", "🧠 Claude"), ("zerobridge", "⚡ Zee"), ("telegram-bridge", "🏍 Telegram")]:
                        r = subprocess.run(
                            ["systemctl", "is-active", svc],
                            capture_output=True, text=True, timeout=5
                        )
                        state = r.stdout.strip()
                        icon = "✓" if state == "active" else "✗"
                        lines.append(f"{icon} {label}: {state}")
                    await tg_send(f"📊 <b>ZeroRelay Status</b>\n" + "\n".join(lines))
                    continue

                # /reset — clear all agent sessions and sticky target
                if cmd == "/reset":
                    log.info("RESET requested by Jimmy")
                    sticky["agent"] = None
                    await ws.send(json.dumps({"content": "[RESET]"}))
                    await tg_send("🔄 <b>RESET</b>\nSessions cleared, sticky target cleared.")
                    continue

                # Check for explicit @tags and update sticky target
                has_tag = TAG_PATTERN.search(text)
                if has_tag:
                    if CLAUDE_TAG.search(text):
                        sticky["agent"] = "claude"
                    if ZEE_TAG.search(text):
                        sticky["agent"] = "zee"
                    await tg_typing()
                    await ws.send(json.dumps({"content": text}))
                elif sticky["agent"] and not cmd.startswith("/"):
                    # No @tag — auto-route to last agent
                    tag = "@c" if sticky["agent"] == "claude" else "@z"
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

    # Register bot menu commands
    async with httpx.AsyncClient() as client:
        await client.post(f"{TG_API}/setMyCommands", json={
            "commands": [
                {"command": "status", "description": "Show which bridges are running"},
                {"command": "start", "description": "Start Claude + Zee bridges"},
                {"command": "reset", "description": "Clear all sessions and context"},
                {"command": "killswitch", "description": "Stop all AI bridges immediately"},
            ]
        })
        log.info("Bot menu commands registered")

    while True:
        try:
            uri = f"{RELAY_URL}?role={ROLE}"
            log.info(f"Connecting to relay: {uri}")
            async with websockets.connect(uri) as ws:
                log.info("Connected to relay as jimmy")

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
            log.warning("Relay disconnected. Reconnecting in 3s...")
        except ConnectionRefusedError:
            log.warning("Relay not available. Retrying in 5s...")
            await asyncio.sleep(5)
            continue
        except Exception as e:
            log.error(f"Bridge error: {e}. Reconnecting in 3s...")

        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
