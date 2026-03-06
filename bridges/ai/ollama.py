#!/usr/bin/env python3
"""ZeroRelay bridge: Ollama (local models). No SDK needed — uses REST API.
Env: OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TAGS, OLLAMA_ROLE"""

import asyncio, json, logging, os, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

class OllamaBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("OLLAMA_TAGS", "@ollama,@local").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("OLLAMA_ROLE", "ollama"),
            tags=tags, display_name=f"Ollama ({MODEL})",
            system_prompt=os.environ.get("OLLAMA_SYSTEM_PROMPT",
                "You are a local AI in a multi-party relay chat. Keep responses short and conversational."), **kw)
        self.history = []

    def _sync_generate(self, prompt, context):
        self.history.append({"role": "user", "content": prompt})
        if len(self.history) > 40: self.history = self.history[-30:]
        try:
            payload = json.dumps({"model": MODEL, "stream": False,
                "messages": [{"role": "system", "content": f"{self.system_prompt}\n\nConversation:\n{context}"}, *self.history]}).encode()
            req = urllib.request.Request(f"{HOST}/api/chat", data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            text = data.get("message", {}).get("content", "")
            if text: self.history.append({"role": "assistant", "content": text})
            return text or "[Ollama returned empty response]"
        except urllib.error.URLError as e: return f"[Ollama error: is it running at {HOST}?]"
        except Exception as e: return f"[Ollama error: {e}]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]": self.history.clear(); self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(OllamaBridge(relay_url=p.parse_args().relay).run())
