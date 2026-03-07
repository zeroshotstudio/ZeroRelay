#!/usr/bin/env python3
"""ZeroRelay bridge: CLI Terminal. Simple terminal chat for testing.
Usage: python3 cli.py --relay ws://localhost:8765 --role jimmy
Commands: /quit, /reset, /status, /help"""

import asyncio, json, logging, os, sys
import websockets

logging.basicConfig(level=logging.WARNING)
RELAY_URL = os.environ.get("ZERORELAY_URL", "ws://localhost:8765")
ROLE = os.environ.get("CLI_ROLE", "operator")

C = {"reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
     "blue": "\033[34m", "green": "\033[32m", "yellow": "\033[33m",
     "red": "\033[31m", "magenta": "\033[35m", "cyan": "\033[36m"}
SC = ["blue", "green", "magenta", "cyan", "yellow"]
scm = {}; ci = 0

def gc(s):
    global ci
    if s not in scm: scm[s] = SC[ci % len(SC)]; ci += 1
    return scm[s]

def cp(t, c="reset", b=False):
    p = C.get(c, ""); 
    if b: p = C["bold"] + p
    print(f"{p}{t}{C['reset']}")

async def display(ws):
    async for raw in ws:
        try: data = json.loads(raw)
        except Exception: continue
        mt = data.get("type")
        if mt == "connected":
            peers = data.get("peers_online", [])
            cp(f"  Connected as {data.get('role', ROLE)}. Peers: {', '.join(peers) or 'none'}", "dim")
            for h in data.get("history", [])[-10:]:
                if h.get("type") == "message":
                    cp(f"  [{h.get('from','?')}] {h.get('content','')}", gc(h.get('from','?')))
            cp("  ---", "dim"); continue
        if mt == "system": cp(f"  \u2014 {data.get('message', '')} \u2014", "dim"); continue
        if mt == "message":
            s, c, m = data.get("from","?"), data.get("content",""), data.get("meta")
            if s == ROLE: continue
            if m == "typing_indicator":
                print(f"\r  {C['dim']}[{s} typing...]{C['reset']}  ", end="", flush=True); continue
            if m in ("stream_start", "stream_chunk"): continue
            print(f"\r{' '*40}\r", end="")
            cp(f"  [{s}] {c}", gc(s))

async def inp(ws):
    loop = asyncio.get_event_loop()
    while True:
        try: line = await loop.run_in_executor(None, lambda: input(""))
        except (EOFError, KeyboardInterrupt): print(); break
        line = line.strip()
        if not line: continue
        if line == "/quit": break
        if line == "/reset": await ws.send(json.dumps({"content": "[RESET]"})); cp("  Reset.", "yellow"); continue
        if line == "/status": cp(f"  Role: {ROLE} | Relay: {RELAY_URL}", "dim"); continue
        if line == "/help": cp("  /quit /reset /status /help | Use @tags for agents", "dim"); continue
        await ws.send(json.dumps({"content": line}))

async def main():
    cp("\n  ZeroRelay CLI", "bold")
    cp(f"  Connecting to {RELAY_URL} as {ROLE}...\n", "dim")
    while True:
        try:
            async with websockets.connect(f"{RELAY_URL}?role={ROLE}") as ws:
                d, i = asyncio.create_task(display(ws)), asyncio.create_task(inp(ws))
                done, pend = await asyncio.wait([d, i], return_when=asyncio.FIRST_COMPLETED)
                for t in pend: t.cancel()
                for t in done:
                    if t == i: cp("\n  Goodbye!", "dim"); return
        except websockets.exceptions.ConnectionClosed: cp("  Disconnected. Reconnecting...", "red")
        except ConnectionRefusedError: cp("  Relay unavailable. Retrying...", "red"); await asyncio.sleep(5); continue
        except Exception as e: cp(f"  Error: {e}", "red")
        await asyncio.sleep(3)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765"); p.add_argument("--role", default="operator")
    a = p.parse_args(); RELAY_URL = a.relay; ROLE = a.role; asyncio.run(main())
