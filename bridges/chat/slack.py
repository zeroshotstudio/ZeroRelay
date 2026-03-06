#!/usr/bin/env python3
"""ZeroRelay bridge: Slack (Socket Mode). No public endpoints needed.
Requires: pip install slack-bolt
Env: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID, SLACK_ROLE
Setup: Create Slack App > Enable Socket Mode > Add chat:write + channels:history scopes > Invite bot to channel"""

import asyncio, json, logging, os, sys, threading
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("slack-bridge")

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")
RELAY_URL = os.environ.get("ZERORELAY_URL", "ws://localhost:8765")
ROLE = os.environ.get("SLACK_ROLE", "operator")

SENDER_ICONS = {}
s = os.environ.get("SLACK_SENDER_ICONS", "")
if s:
    for p in s.split(","):
        if "=" in p: k, v = p.split("=", 1); SENDER_ICONS[k.strip()] = v.strip()

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
except ImportError:
    print("Install slack-bolt: pip install slack-bolt"); sys.exit(1)

app = App(token=BOT_TOKEN)
ws_ref = {"ws": None}
bot_user_id = None

@app.event("message")
def handle_message(event, say):
    if event.get("user") == bot_user_id or event.get("channel") != CHANNEL_ID or event.get("subtype"): return
    text = event.get("text", "").strip()
    if not text: return
    log.info(f"Slack > Relay: {text[:80]}")
    ws = ws_ref.get("ws")
    if ws: asyncio.run_coroutine_threadsafe(ws.send(json.dumps({"content": text})), relay_loop)

def send_to_slack(text):
    try: app.client.chat_postMessage(channel=CHANNEL_ID, text=text, unfurl_links=False)
    except Exception as e: log.error(f"Slack send failed: {e}")

async def relay_listener():
    while True:
        try:
            async with websockets.connect(f"{RELAY_URL}?role={ROLE}") as ws:
                ws_ref["ws"] = ws; send_to_slack("*ZeroRelay connected*")
                async for raw in ws:
                    try: data = json.loads(raw)
                    except: continue
                    mt = data.get("type")
                    if mt == "connected":
                        send_to_slack(f"Online: {', '.join(data.get('peers_online', [])) or 'none'}"); continue
                    if mt == "system": send_to_slack(f"_{data.get('message', '')}_"); continue
                    if mt == "message":
                        sender, content, meta = data.get("from","?"), data.get("content",""), data.get("meta")
                        if meta in ("typing_indicator", "stream_start", "stream_chunk") or sender == ROLE: continue
                        send_to_slack(f"*{SENDER_ICONS.get(sender, sender)}*\n{content}")
        except websockets.exceptions.ConnectionClosed: log.warning("Relay disconnected.")
        except ConnectionRefusedError: await asyncio.sleep(5); continue
        except Exception as e: log.error(f"Error: {e}")
        ws_ref["ws"] = None; await asyncio.sleep(3)

relay_loop = None
def start_relay():
    global relay_loop; relay_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(relay_loop); relay_loop.run_until_complete(relay_listener())

if __name__ == "__main__":
    if not BOT_TOKEN or not APP_TOKEN or not CHANNEL_ID:
        log.error("SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID required"); sys.exit(1)
    auth = app.client.auth_test(); bot_user_id = auth["user_id"]
    threading.Thread(target=start_relay, daemon=True).start()
    SocketModeHandler(app, APP_TOKEN).start()
