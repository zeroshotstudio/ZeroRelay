#!/usr/bin/env python3
"""ZeroRelay bridge: Claude Code CLI. Uses `claude -p` with persistent sessions.
Requires Claude Code CLI installed. Env: CLAUDE_MODEL, CLAUDE_TAGS, CLAUDE_ROLE, CLAUDE_TIMEOUT"""

import asyncio, logging, os, subprocess, sys, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("claude-code-bridge")

MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
CLI_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
DEFAULT_PROMPT = "You are Claude in a multi-party relay chat. Keep responses short and conversational."

class ClaudeCodeBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("CLAUDE_TAGS", "@claude,@c").split(",")]
        super().__init__(relay_url=relay_url, role=os.environ.get("CLAUDE_ROLE", "claude"),
            tags=tags, display_name="Claude (Code CLI)",
            system_prompt=os.environ.get("CLAUDE_SYSTEM_PROMPT", DEFAULT_PROMPT), **kw)
        self.session_id = str(uuid.uuid4())

    def _sync_generate(self, prompt, context):
        full = f"{self.system_prompt}\n\n--- Conversation ---\n{context}\n---\n\nMessage: {prompt}"
        try:
            r = subprocess.run(["claude", "-p", "--model", MODEL, "--session-id", self.session_id],
                input=full, capture_output=True, text=True, timeout=CLI_TIMEOUT)
            if r.returncode != 0 and not r.stdout.strip():
                return f"[Claude Code error: {(r.stderr.strip() or 'Unknown')[:200]}]"
            return r.stdout.strip() or "[Empty response]"
        except subprocess.TimeoutExpired: return "[Claude Code timed out]"
        except FileNotFoundError: return "[Error: claude CLI not found]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]":
            self.session_id = str(uuid.uuid4()); self.transcript.clear(); return
        await super().on_message(sender, content, data)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser(); p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(ClaudeCodeBridge(relay_url=p.parse_args().relay).run())
