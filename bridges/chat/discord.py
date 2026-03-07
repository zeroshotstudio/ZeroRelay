#!/usr/bin/env python3
"""ZeroRelay bridge: Discord Bot. Env: DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, DISCORD_ROLE
Requires: pip install discord.py"""

import asyncio, json, logging, os, sys
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("discord-bridge")

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
RELAY_URL = os.environ.get("ZERORELAY_URL", "ws://localhost:8765")
ROLE = os.environ.get("DISCORD_ROLE", "operator")
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
ALLOWED_USERS = set()
_au = os.environ.get("DISCORD_ALLOWED_USERS", "")
if _au:
    ALLOWED_USERS = {int(uid.strip()) for uid in _au.split(",") if uid.strip()}

SENDER_ICONS = {}
s = os.environ.get("DISCORD_SENDER_ICONS", "")
if s:
    for p in s.split(","):
        if "=" in p: k, v = p.split("=", 1); SENDER_ICONS[k.strip()] = v.strip()

try:
    import discord
except ImportError:
    print("Install discord.py: pip install discord.py"); sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
ws_conn = None
relay_ch = None

@client.event
async def on_ready():
    global relay_ch
    log.info(f"Discord bot ready: {client.user}")
    relay_ch = client.get_channel(CHANNEL_ID)
    if not relay_ch: log.error(f"Channel {CHANNEL_ID} not found!"); return
    asyncio.create_task(relay_listener())

@client.event
async def on_message(message):
    if message.author == client.user or message.channel.id != CHANNEL_ID: return
    if ALLOWED_USERS and message.author.id not in ALLOWED_USERS:
        log.warning(f"Rejected message from unauthorized user_id={message.author.id}")
        return
    text = message.content.strip()
    if not text: return
    log.info(f"Discord > Relay: {text[:80]}")
    if ws_conn:
        try: await ws_conn.send(json.dumps({"content": text}))
        except Exception: await message.channel.send("Warning: Relay connection lost.")

async def relay_listener():
    global ws_conn
    while True:
        try:
            token_param = f"&token={RELAY_TOKEN}" if RELAY_TOKEN else ""
            uri = f"{RELAY_URL}?role={ROLE}{token_param}"
            async with websockets.connect(uri) as ws:
                ws_conn = ws; log.info("Connected to relay")
                if relay_ch: await relay_ch.send("**ZeroRelay connected**")
                async for raw in ws:
                    try: data = json.loads(raw)
                    except Exception: continue
                    mt = data.get("type")
                    if mt == "connected":
                        peers = data.get("peers_online", [])
                        if relay_ch: await relay_ch.send(f"Online: {', '.join(peers) or 'none'}")
                        continue
                    if mt == "system":
                        if relay_ch: await relay_ch.send(f"*{data.get('message', '')}*")
                        continue
                    if mt == "message":
                        sender, content, meta = data.get("from","?"), data.get("content",""), data.get("meta")
                        if meta == "typing_indicator":
                            if relay_ch:
                                async with relay_ch.typing(): await asyncio.sleep(0.1)
                            continue
                        if sender == ROLE or meta in ("stream_start", "stream_chunk"): continue
                        label = SENDER_ICONS.get(sender, sender)
                        if relay_ch:
                            msg = f"**{label}**\n{content}"
                            # Chunk messages exceeding Discord's 2000-char limit
                            for i in range(0, len(msg), 2000):
                                await relay_ch.send(msg[i:i+2000])
        except websockets.exceptions.ConnectionClosed: log.warning("Relay disconnected. Reconnecting...")
        except ConnectionRefusedError: log.warning("Relay unavailable. Retrying..."); await asyncio.sleep(5); continue
        except Exception as e: log.error(f"Relay error: {e}")
        ws_conn = None; await asyncio.sleep(3)

if __name__ == "__main__":
    if not BOT_TOKEN or not CHANNEL_ID: log.error("DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID required"); sys.exit(1)
    client.run(BOT_TOKEN)
