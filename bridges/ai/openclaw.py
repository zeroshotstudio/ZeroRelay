#!/usr/bin/env python3
"""ZeroRelay bridge: OpenClaw Gateway via docker exec CLI.
Env: OPENCLAW_CONTAINER, OPENCLAW_AGENT_ID, OPENCLAW_TOKEN, OPENCLAW_TAGS, OPENCLAW_ROLE"""

import asyncio, json, logging, os, subprocess, sys, uuid
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("openclaw-bridge")
CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw-openclaw-gateway-1")
AGENT_ID = os.environ.get("OPENCLAW_AGENT_ID", "main")
SESSION_PREFIX = os.environ.get("OPENCLAW_SESSION", "agent:main:zerorelay")
GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY", "ws://127.0.0.1:18789")
GATEWAY_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")
CLI_TIMEOUT = int(os.environ.get("OPENCLAW_TIMEOUT", "130"))

def extract_json(text):
    idx = text.find("{")
    if idx == -1: return text.strip()
    depth = 0
    for i in range(idx, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}": depth -= 1; 
        if depth == 0: return text[idx:i+1]
    return text[idx:]

class OpenClawBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("OPENCLAW_TAGS", "@z,@zee").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("OPENCLAW_ROLE", "zee"),
            tags=tags, display_name="Zee (OpenClaw)",
            system_prompt=os.environ.get("OPENCLAW_SYSTEM_PROMPT",
                "You are Zee, an execution AI in a multi-party relay chat. Keep responses concise."), **kw)
        self.session_counter = 0

    def _current_session_key(self): return f"{SESSION_PREFIX}:{self.session_counter}"

    def _sync_generate(self, prompt, context):
        full_msg = f"{self.system_prompt}\n\n--- Conversation ---\n{context}\n---\n\nMessage: {prompt}"
        params = json.dumps({"agentId": AGENT_ID, "sessionKey": self._current_session_key(),
            "message": full_msg, "idempotencyKey": str(uuid.uuid4())})
        try:
            cmd = ["docker", "exec", CONTAINER, "openclaw", "gateway", "call", "agent",
                "--params", params, "--url", GATEWAY_URL, "--expect-final", "--timeout", str(CLI_TIMEOUT * 1000)]
            if GATEWAY_TOKEN: cmd.extend(["--token", GATEWAY_TOKEN])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT)
            if r.returncode != 0: return f"[OpenClaw error: {(r.stderr.strip() or r.stdout.strip() or 'Unknown')[:200]}]"
            data = json.loads(extract_json(r.stdout)); payload = data.get("payload", data)
            if payload.get("status") == "error": return f"[Zee error: {payload.get('error', 'Unknown')}]"
            payloads = payload.get("result", {}).get("payloads", [])
            if payloads:
                texts = [p.get("text", "") for p in payloads if p.get("text")]
                if texts: return "\n".join(texts)
            for k in ("response", "message", "text", "content"):
                if payload.get(k): return str(payload[k])
            return json.dumps(payload, indent=2)
        except subprocess.TimeoutExpired: return "[Zee timed out]"
        except FileNotFoundError: return "[Error: docker/openclaw CLI not found]"
        except json.JSONDecodeError: return r.stdout.strip() if r.stdout else "[Unparseable response]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]":
            self.session_counter += 1; self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(OpenClawBridge(relay_url=p.parse_args().relay).run())
