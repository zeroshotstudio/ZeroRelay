#!/usr/bin/env python3
"""
ZeroRelay bridge: Telegram Bot.

Human interface via Telegram with @-mention routing, sticky addressing,
typing indicators, and operator commands (/status, /start, /reset, /killswitch).

Requires: pip install httpx websockets

Environment:
  TELEGRAM_BOT_TOKEN     - Bot token from @BotFather (required)
  TELEGRAM_CHAT_ID       - Your chat ID (required, get via @userinfobot)
  TELEGRAM_ROLE          - Relay role (default: jimmy)
  TELEGRAM_SENDER_ICONS  - Display names: role=Label,role2=Label2
  TELEGRAM_TAG_PATTERNS  - Routing: agent:@tag1,@tag2;agent2:@tag3
  TELEGRAM_AI_SERVICES   - systemd services for /start and /killswitch
  TELEGRAM_ENV_FILE      - Path to env file (default: ./telegram.env)
"""

import asyncio, json, logging, os, re, subprocess, sys
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("telegram-bridge")

# Load env file
ENV_FILE = os.environ.get("TELEGRAM_ENV_FILE", "./telegram.env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
RELAY_URL = os.environ.get("ZERORELAY_URL", "ws://localhost:8765")
ROLE = os.environ.get("TELEGRAM_ROLE", "jimmy")

# Sender display names
SENDER_ICONS = {}
si = os.environ.get("TELEGRAM_SENDER_ICONS", "")
if si:
    for pair in si.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            SENDER_ICONS[k.strip()] = v.strip()

# AI services for /start and /killswitch
AI_SERVICES = [s.strip() for s in os.environ.get("TELEGRAM_AI_SERVICES", "").split(",") if s.strip()]

# Tag routing patterns
TAG_RE = None
STICKY_TAGS = {}
tp = os.environ.get("TELEGRAM_TAG_PATTERNS", "")
if tp:
    parts = []
    for group in tp.split(";"):
        if ":" in group:
            name, tags = group.split(":", 1)
            for tag in tags.split(","):
                tag = tag.strip().lstrip("@")
                parts.append(tag)
                STICKY_TAGS[tag.lower()] = name.strip()
    if parts:
        TAG_RE = re.compile(rf"@(?:{'|'.join(re.escape(p) for p in parts)})\b", re.IGNORECASE)

sticky = {"agent": None}

import httpx
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def html_escape(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_label(role):
    return SENDER_ICONS.get(role, role)


async def tg_typing():
    async with httpx.AsyncClient() as c:
        await c.post(f"{TG_API}/sendChatAction", json={"chat_id": CHAT_ID, "action": "typing"})


async def tg_send(text, parse_mode="HTML"):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{TG_API}/sendMessage", json={
            "chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode,
            "disable_web_page_preview": True})
        if r.status_code == 200:
            return r.json().get("result", {}).get("message_id")
        r2 = await c.post(f"{TG_API}/sendMessage", json={
            "chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True})
        return r2.json().get("result", {}).get("message_id") if r2.status_code == 200 else None


async def tg_edit(mid, text, parse_mode="HTML"):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{TG_API}/editMessageText", json={
            "chat_id": CHAT_ID, "message_id": mid, "text": text,
            "parse_mode": parse_mode, "disable_web_page_preview": True})
        if r.status_code != 200:
            await c.post(f"{TG_API}/editMessageText", json={
                "chat_id": CHAT_ID, "message_id": mid, "text": text,
                "disable_web_page_preview": True})


async def tg_poll(offset):
    async with httpx.AsyncClient(timeout=35) as c:
        r = await c.post(f"{TG_API}/getUpdates", json={
            "offset": offset, "timeout": 30, "allowed_updates": ["message"]})
        updates = r.json().get("result", [])
        new_offset = offset
        messages = []
        for u in updates:
            new_offset = max(new_offset, u["update_id"] + 1)
            msg = u.get("message", {})
            if msg.get("chat", {}).get("id") == CHAT_ID and msg.get("text"):
                messages.append(msg["text"])
        return messages, new_offset


async def relay_to_telegram(ws):
    stream_ids = {}
    async for raw in ws:
        try:
            data = json.loads(raw)
        except:
            continue
        mt = data.get("type")
        if mt == "connected":
            peers = data.get("peers_online", [])
            online = ", ".join(get_label(p) for p in peers)
            await tg_send(f"<b>ZeroRelay connected</b>\nOnline: {html_escape(online or 'none')}")
            continue
        if mt == "system":
            sysmsg = data.get("message", "")
            if any(svc in sysmsg for svc in AI_SERVICES):
                continue
            for role, icon in SENDER_ICONS.items():
                sysmsg = sysmsg.replace(role, icon)
            await tg_send(f"<i>{html_escape(sysmsg)}</i>")
            continue
        if mt == "message":
            sender, content, meta = data.get("from", "?"), data.get("content", ""), data.get("meta")
            if meta == "typing_indicator":
                await tg_typing(); continue
            if sender == ROLE:
                continue
            # Update sticky when agent responds
            for tl, an in STICKY_TAGS.items():
                if sender == an or sender in SENDER_ICONS:
                    sticky["agent"] = an; break
            label = get_label(sender)
            if meta == "stream_start":
                mid = await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")
                if mid: stream_ids[sender] = mid
                continue
            if meta == "stream_chunk":
                mid = stream_ids.get(sender)
                if mid: await tg_edit(mid, f"<b>{html_escape(label)}</b>\n{html_escape(content)}")
                continue
            if meta == "stream_end":
                mid = stream_ids.pop(sender, None)
                if mid:
                    await tg_edit(mid, f"<b>{html_escape(label)}</b>\n{html_escape(content)}")
                else:
                    await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")
                continue
            await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")


async def telegram_to_relay(ws):
    offset = 0
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{TG_API}/getUpdates", json={"offset": -1})
        updates = r.json().get("result", [])
        if updates:
            offset = updates[-1]["update_id"] + 1

    while True:
        try:
            messages, offset = await tg_poll(offset)
            for text in messages:
                cmd = text.strip().lower()

                if cmd == "/killswitch" and AI_SERVICES:
                    stopped = []
                    for svc in AI_SERVICES:
                        r = subprocess.run(["systemctl", "stop", svc], capture_output=True, text=True, timeout=10)
                        if r.returncode == 0: stopped.append(svc)
                    await tg_send(f"<b>KILLSWITCH</b>\nStopped: {', '.join(stopped) or 'none'}")
                    await ws.send(json.dumps({"content": "[KILLSWITCH]"}))
                    continue

                if cmd == "/start" and AI_SERVICES:
                    started = []
                    for svc in AI_SERVICES:
                        r = subprocess.run(["systemctl", "start", svc], capture_output=True, text=True, timeout=10)
                        if r.returncode == 0: started.append(svc)
                    lines = "\n".join(f"{'Y' if s in started else 'N'} {s}" for s in AI_SERVICES)
                    await tg_send(f"<b>STARTED</b>\n{lines}")
                    continue

                if cmd == "/status":
                    services = AI_SERVICES + ["telegram-bridge"] if AI_SERVICES else ["telegram-bridge"]
                    lines = []
                    for svc in services:
                        r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True, timeout=5)
                        lines.append(f"{'Y' if r.stdout.strip() == 'active' else 'N'} {svc}: {r.stdout.strip()}")
                    await tg_send(f"<b>Status</b>\n" + "\n".join(lines))
                    continue

                if cmd == "/reset":
                    sticky["agent"] = None
                    await ws.send(json.dumps({"content": "[RESET]"}))
                    await tg_send("<b>RESET</b>\nSessions cleared.")
                    continue

                # Check for explicit @tags
                if TAG_RE and TAG_RE.search(text):
                    match = TAG_RE.search(text)
                    tag_text = match.group(0).lstrip("@").lower()
                    if tag_text in STICKY_TAGS:
                        sticky["agent"] = STICKY_TAGS[tag_text]
                    await tg_typing()
                    await ws.send(json.dumps({"content": text}))
                elif sticky["agent"] and not cmd.startswith("/"):
                    tag = None
                    for t, name in STICKY_TAGS.items():
                        if name == sticky["agent"]: tag = f"@{t}"; break
                    if tag:
                        await tg_typing()
                        await ws.send(json.dumps({"content": f"{tag} {text}"}))
                    else:
                        await ws.send(json.dumps({"content": text}))
                else:
                    await ws.send(json.dumps({"content": text}))
        except Exception as e:
            log.error(f"Telegram poll error: {e}")
            await asyncio.sleep(5)


async def main():
    if not BOT_TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required"); return

    async with httpx.AsyncClient() as c:
        await c.post(f"{TG_API}/setMyCommands", json={"commands": [
            {"command": "status", "description": "Show bridge status"},
            {"command": "start", "description": "Start AI bridges"},
            {"command": "reset", "description": "Clear sessions"},
            {"command": "killswitch", "description": "Stop AI bridges"},
        ]})

    while True:
        try:
            async with websockets.connect(f"{RELAY_URL}?role={ROLE}") as ws:
                r_task = asyncio.create_task(relay_to_telegram(ws))
                t_task = asyncio.create_task(telegram_to_relay(ws))
                done, pend = await asyncio.wait([r_task, t_task], return_when=asyncio.FIRST_COMPLETED)
                for t in pend: t.cancel()
        except websockets.exceptions.ConnectionClosed: log.warning("Relay disconnected.")
        except ConnectionRefusedError: await asyncio.sleep(5); continue
        except Exception as e: log.error(f"Error: {e}")
        await asyncio.sleep(3)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--relay", default="ws://localhost:8765")
    RELAY_URL = p.parse_args().relay
    asyncio.run(main())
