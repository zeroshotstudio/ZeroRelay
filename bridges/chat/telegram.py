#!/usr/bin/env python3
"""
ZeroRelay bridge: Telegram Bot.

Security: sender verification (TELEGRAM_USER_ID), relay token auth,
sudo systemctl for non-root service user, exponential backoff.

Env:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (required)
  TELEGRAM_USER_ID (recommended — sender verification)
  TELEGRAM_ROLE, TELEGRAM_SENDER_ICONS, TELEGRAM_TAG_PATTERNS
  TELEGRAM_AI_SERVICES, RELAY_TOKEN, TELEGRAM_ENV_FILE
"""

import asyncio, json, logging, os, re, subprocess, sys
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("telegram-bridge")

ENV_FILE = os.environ.get("TELEGRAM_ENV_FILE", "./.env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))  # H4: sender verification
RELAY_URL = os.environ.get("ZERORELAY_URL", "ws://localhost:8765")
ROLE = os.environ.get("TELEGRAM_ROLE", "jimmy")
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
USE_SUDO = os.environ.get("TELEGRAM_USE_SUDO", "true").lower() in ("1", "true", "yes")

SENDER_ICONS = {}
si = os.environ.get("TELEGRAM_SENDER_ICONS", "")
if si:
    for pair in si.split(","):
        if "=" in pair: k, v = pair.split("=", 1); SENDER_ICONS[k.strip()] = v.strip()

AI_SERVICES = [s.strip() for s in os.environ.get("TELEGRAM_AI_SERVICES", "").split(",") if s.strip()]

TAG_RE = None; STICKY_TAGS = {}
tp = os.environ.get("TELEGRAM_TAG_PATTERNS", "")
if tp:
    parts = []
    for group in tp.split(";"):
        if ":" in group:
            name, tags = group.split(":", 1)
            for tag in tags.split(","):
                tag = tag.strip().lstrip("@"); parts.append(tag)
                STICKY_TAGS[tag.lower()] = name.strip()
    if parts:
        TAG_RE = re.compile(rf"@(?:{'|'.join(re.escape(p) for p in parts)})\b", re.IGNORECASE)

sticky = {"agent": None}

import httpx
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def html_escape(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def get_label(role): return SENDER_ICONS.get(role, role)
def systemctl_cmd(action, svc):
    cmd = ["sudo", "systemctl", action, svc] if USE_SUDO else ["systemctl", action, svc]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)

async def tg_typing():
    async with httpx.AsyncClient() as c:
        await c.post(f"{TG_API}/sendChatAction", json={"chat_id": CHAT_ID, "action": "typing"})

async def tg_send(text, parse_mode="HTML"):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{TG_API}/sendMessage", json={"chat_id": CHAT_ID, "text": text,
            "parse_mode": parse_mode, "disable_web_page_preview": True})
        if r.status_code == 200: return r.json().get("result", {}).get("message_id")
        r2 = await c.post(f"{TG_API}/sendMessage", json={"chat_id": CHAT_ID, "text": text,
            "disable_web_page_preview": True})
        return r2.json().get("result", {}).get("message_id") if r2.status_code == 200 else None

async def tg_edit(mid, text, parse_mode="HTML"):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{TG_API}/editMessageText", json={"chat_id": CHAT_ID, "message_id": mid,
            "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True})
        if r.status_code != 200:
            await c.post(f"{TG_API}/editMessageText", json={"chat_id": CHAT_ID, "message_id": mid,
                "text": text, "disable_web_page_preview": True})

async def tg_poll(offset):
    async with httpx.AsyncClient(timeout=35) as c:
        r = await c.post(f"{TG_API}/getUpdates", json={"offset": offset, "timeout": 30,
            "allowed_updates": ["message"]})
        updates = r.json().get("result", [])
        new_offset = offset; messages = []
        for u in updates:
            new_offset = max(new_offset, u["update_id"] + 1)
            msg = u.get("message", {})
            if msg.get("chat", {}).get("id") == CHAT_ID and msg.get("text"):
                # H4: sender verification
                sender_id = msg.get("from", {}).get("id")
                if USER_ID and sender_id != USER_ID:
                    log.warning(f"Rejected message from unauthorized user_id={sender_id}")
                    continue
                messages.append(msg["text"])
        return messages, new_offset

async def relay_to_telegram(ws):
    stream_ids = {}
    async for raw in ws:
        try: data = json.loads(raw)
        except Exception: continue
        mt = data.get("type")
        if mt == "connected":
            peers = data.get("peers_online", [])
            await tg_send(f"<b>ZeroRelay connected</b>\nOnline: {html_escape(', '.join(get_label(p) for p in peers) or 'none')}")
            continue
        if mt == "system":
            sysmsg = data.get("message", "")
            if any(svc in sysmsg for svc in AI_SERVICES): continue
            for role, icon in SENDER_ICONS.items(): sysmsg = sysmsg.replace(role, icon)
            await tg_send(f"<i>{html_escape(sysmsg)}</i>"); continue
        if mt == "message":
            sender, content, meta = data.get("from", "?"), data.get("content", ""), data.get("meta")
            if meta == "typing_indicator": await tg_typing(); continue
            if sender == ROLE: continue
            for tl, an in STICKY_TAGS.items():
                if sender == an or sender in SENDER_ICONS: sticky["agent"] = an; break
            label = get_label(sender)
            log.info(f"To Telegram [{sender}] ({len(content)} chars)")
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
                t = f"<b>{html_escape(label)}</b>\n{html_escape(content)}"
                (await tg_edit(mid, t)) if mid else (await tg_send(t)); continue
            await tg_send(f"<b>{html_escape(label)}</b>\n{html_escape(content)}")

async def telegram_to_relay(ws):
    offset = 0
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{TG_API}/getUpdates", json={"offset": -1})
        updates = r.json().get("result", [])
        if updates: offset = updates[-1]["update_id"] + 1
    while True:
        try:
            messages, offset = await tg_poll(offset)
            for text in messages:
                log.info(f"From Telegram ({len(text)} chars)")
                cmd = text.strip().lower()
                if cmd == "/killswitch" and AI_SERVICES:
                    stopped = [s for s in AI_SERVICES if systemctl_cmd("stop", s).returncode == 0]
                    await tg_send(f"<b>KILLSWITCH</b>\nStopped: {', '.join(stopped) or 'none'}")
                    await ws.send(json.dumps({"content": "[KILLSWITCH]"})); continue
                if cmd == "/start" and AI_SERVICES:
                    started = [s for s in AI_SERVICES if systemctl_cmd("start", s).returncode == 0]
                    lines = "\n".join(f"{'Y' if s in started else 'N'} {s}" for s in AI_SERVICES)
                    await tg_send(f"<b>STARTED</b>\n{lines}"); continue
                if cmd == "/status":
                    svcs = AI_SERVICES + ["telegram-bridge"] if AI_SERVICES else ["telegram-bridge"]
                    lines = [f"{'Y' if systemctl_cmd('is-active', s).stdout.strip()=='active' else 'N'} {s}" for s in svcs]
                    await tg_send(f"<b>Status</b>\n" + "\n".join(lines)); continue
                if cmd == "/reset":
                    sticky["agent"] = None
                    await ws.send(json.dumps({"content": "[RESET]"})); await tg_send("<b>RESET</b>"); continue
                if TAG_RE and TAG_RE.search(text):
                    tag_text = TAG_RE.search(text).group(0).lstrip("@").lower()
                    if tag_text in STICKY_TAGS: sticky["agent"] = STICKY_TAGS[tag_text]
                    await tg_typing(); await ws.send(json.dumps({"content": text}))
                elif sticky["agent"] and not cmd.startswith("/"):
                    tag = next((f"@{t}" for t, n in STICKY_TAGS.items() if n == sticky["agent"]), None)
                    if tag: await tg_typing(); await ws.send(json.dumps({"content": f"{tag} {text}"}))
                    else: await ws.send(json.dumps({"content": text}))
                else: await ws.send(json.dumps({"content": text}))
        except Exception as e: log.error(f"Poll error: {e}"); await asyncio.sleep(5)

async def main():
    if not BOT_TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required"); return
    if USER_ID: log.info(f"Sender verification: user_id={USER_ID}")
    else: log.warning("TELEGRAM_USER_ID not set \u2014 no sender verification!")

    async with httpx.AsyncClient() as c:
        await c.post(f"{TG_API}/setMyCommands", json={"commands": [
            {"command": "status", "description": "Bridge status"},
            {"command": "start", "description": "Start AI bridges"},
            {"command": "reset", "description": "Clear sessions"},
            {"command": "killswitch", "description": "Stop AI bridges"},
        ]})

    backoff = 3
    while True:
        try:
            token_param = f"&token={RELAY_TOKEN}" if RELAY_TOKEN else ""
            uri = f"{RELAY_URL}?role={ROLE}{token_param}"
            async with websockets.connect(uri) as ws:
                backoff = 3
                r_task = asyncio.create_task(relay_to_telegram(ws))
                t_task = asyncio.create_task(telegram_to_relay(ws))
                done, pend = await asyncio.wait([r_task, t_task], return_when=asyncio.FIRST_COMPLETED)
                for t in pend: t.cancel()
        except websockets.exceptions.ConnectionClosed: log.warning(f"Disconnected.")
        except ConnectionRefusedError: pass
        except Exception as e: log.error(f"Error: {e}")
        await asyncio.sleep(backoff); backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--relay", default="ws://localhost:8765")
    RELAY_URL = p.parse_args().relay; asyncio.run(main())
