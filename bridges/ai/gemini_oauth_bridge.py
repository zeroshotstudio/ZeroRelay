#!/usr/bin/env python3
"""ZeroRelay bridge: Gemini OAuth (Subscription Account Auth)
Uses the Libriscribe GeminiOAuthClient for auth.
"""

import asyncio, logging, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# Import Libriscribe's OAuth client directly
sys.path.insert(0, "/Users/zero/MaintenanceMode.sys-/src")
from libriscribe.utils.gemini_oauth import GeminiOAuthClient

from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")

class GeminiOAuthBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("GEMINI_TAGS", "@gemini,@gem").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("GEMINI_ROLE", "gemini"),
            tags=tags, display_name=f"Gemini OAuth ({MODEL})",
            system_prompt="You are Gemini in a multi-party relay chat. Keep responses short and conversational.", **kw)
        
        self.oauth_client = GeminiOAuthClient()
        if not self.oauth_client.is_authenticated():
            logging.error("Not authenticated! Run `libriscribe auth login` first.")
            sys.exit(1)
        self.chat_history = ""

    def _sync_generate(self, prompt, context):
        try:
            full_prompt = f"{self.system_prompt}\n\nContext:\n{context}\n\nUser: {prompt}"
            r = self.oauth_client.generate_content(model=MODEL, prompt=full_prompt)
            return r
        except Exception as e:
            return f"[Gemini OAuth API error: {e}]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]": self.chat_history = ""; self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(GeminiOAuthBridge(relay_url=p.parse_args().relay).run())
