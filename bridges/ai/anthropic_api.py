#!/usr/bin/env python3
"""ZeroRelay bridge: Anthropic API. Env: ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_TAGS, ANTHROPIC_ROLE"""

import asyncio, logging, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "1024"))

class AnthropicBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("ANTHROPIC_TAGS", "@claude,@c").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("ANTHROPIC_ROLE", "claude"),
            tags=tags, display_name=f"Claude ({MODEL})",
            system_prompt=os.environ.get("ANTHROPIC_SYSTEM_PROMPT",
                "You are Claude in a multi-party relay chat. Keep responses short and conversational."), **kw)
        import anthropic; self.client = anthropic.Anthropic(); self.history = []

    def _sync_generate(self, prompt, context):
        self.history.append({"role": "user", "content": prompt})
        if len(self.history) > 40: self.history = self.history[-30:]
        try:
            r = self.client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                system=f"{self.system_prompt}\n\nConversation context:\n{context}", messages=self.history)
            text = r.content[0].text; self.history.append({"role": "assistant", "content": text}); return text
        except Exception as e: return f"[Anthropic API error: {e}]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]": self.history.clear(); self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(AnthropicBridge(relay_url=p.parse_args().relay).run())
