#!/usr/bin/env python3
"""ZeroRelay bridge: OpenAI API. Also works with compatible APIs (Together, Groq, etc.)
Env: OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL, OPENAI_TAGS, OPENAI_ROLE"""

import asyncio, logging, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "1024"))

class OpenAIBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("OPENAI_TAGS", "@gpt,@g").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("OPENAI_ROLE", "gpt"),
            tags=tags, display_name=f"GPT ({MODEL})",
            system_prompt=os.environ.get("OPENAI_SYSTEM_PROMPT",
                "You are an AI assistant in a multi-party relay chat. Keep responses short and conversational."), **kw)
        from openai import OpenAI
        client_kw = {}; base = os.environ.get("OPENAI_BASE_URL")
        if base: client_kw["base_url"] = base
        self.client = OpenAI(**client_kw); self.history = []

    def _sync_generate(self, prompt, context):
        self.history.append({"role": "user", "content": prompt})
        if len(self.history) > 40: self.history = self.history[-30:]
        try:
            msgs = [{"role": "system", "content": f"{self.system_prompt}\n\nConversation context:\n{context}"}, *self.history]
            r = self.client.chat.completions.create(model=MODEL, messages=msgs, max_tokens=MAX_TOKENS)
            text = r.choices[0].message.content; self.history.append({"role": "assistant", "content": text}); return text
        except Exception as e: return f"[OpenAI API error: {e}]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]": self.history.clear(); self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(OpenAIBridge(relay_url=p.parse_args().relay).run())
