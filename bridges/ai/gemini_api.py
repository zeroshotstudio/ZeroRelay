#!/usr/bin/env python3
"""ZeroRelay bridge: Google Gemini API. Env: GOOGLE_API_KEY (or GEMINI_API_KEY), GEMINI_MODEL, GEMINI_TAGS"""

import asyncio, logging, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOKENS = int(os.environ.get("GEMINI_MAX_TOKENS", "1024"))
if not os.environ.get("GOOGLE_API_KEY"):
    k = os.environ.get("GEMINI_API_KEY", "")
    if k: os.environ["GOOGLE_API_KEY"] = k

class GeminiBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("GEMINI_TAGS", "@gemini,@gem").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("GEMINI_ROLE", "gemini"),
            tags=tags, display_name=f"Gemini ({MODEL})",
            system_prompt=os.environ.get("GEMINI_SYSTEM_PROMPT") or None, **kw)
        from google import genai; self.client = genai.Client(); self.chat_history = []

    def _sync_generate(self, prompt, context):
        from google.genai import types
        self.chat_history.append({"role": "user", "parts": [{"text": prompt}]})
        if len(self.chat_history) > 40: self.chat_history = self.chat_history[-30:]
        try:
            r = self.client.models.generate_content(model=MODEL, contents=self.chat_history,
                config=types.GenerateContentConfig(
                    system_instruction=f"{self.system_prompt}\n\nConversation context:\n{context}",
                    max_output_tokens=MAX_TOKENS))
            text = r.text; self.chat_history.append({"role": "model", "parts": [{"text": text}]}); return text
        except Exception as e: return f"[Gemini API error: {e}]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]": self.chat_history.clear(); self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765")
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        logging.getLogger("gemini-bridge").error("GOOGLE_API_KEY (or GEMINI_API_KEY) not set. Set it in .env or environment."); sys.exit(1)
    asyncio.run(GeminiBridge(relay_url=p.parse_args().relay).run())
