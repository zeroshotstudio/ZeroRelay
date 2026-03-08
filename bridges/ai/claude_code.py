#!/usr/bin/env python3
"""ZeroRelay bridge: Claude Code CLI.
Fixed session handling: --session-id for creation, --resume for subsequent calls.
Idle session auto-reset after 30 min. Auto-recovery on "already in use" errors.

Env: CLAUDE_MODEL, CLAUDE_TAGS, CLAUDE_ROLE, CLAUDE_TIMEOUT, CLAUDE_ADD_DIR"""

import asyncio, json, logging, os, subprocess, sys, uuid
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("claude-code-bridge")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLI_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
ADD_DIR = os.environ.get("CLAUDE_ADD_DIR", "")  # e.g. "/" for full filesystem access
SESSION_IDLE_RESET_SEC = int(os.environ.get("CLAUDE_SESSION_IDLE_SEC", "1800"))  # 30 min


class ClaudeCodeBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("CLAUDE_TAGS", "@claude,@c").split(",")]
        super().__init__(
            relay_url=relay_url,
            role=os.environ.get("CLAUDE_ROLE", "claude"),
            tags=tags,
            display_name="Claude (Code CLI)",
            system_prompt=os.environ.get("CLAUDE_SYSTEM_PROMPT") or None,
            **kw
        )
        self.session_id = str(uuid.uuid4())
        self.session_established = False  # True after first successful call
        self.last_activity = datetime.now()

    def _check_idle_reset(self):
        """Reset session if idle too long."""
        idle = (datetime.now() - self.last_activity).total_seconds()
        if idle > SESSION_IDLE_RESET_SEC:
            self.session_id = str(uuid.uuid4())
            self.session_established = False
            self.transcript.clear()
            log.info(f"Session auto-reset (idle {idle:.0f}s). New: {self.session_id[:8]}...")

    def _sync_generate(self, prompt, context, _retry=0):
        self._check_idle_reset()
        self.last_activity = datetime.now()

        # Build command: --session-id for new, --resume for existing
        mode = "--session-id" if not self.session_established else "--resume"
        cmd = ["claude", "-p", "--model", MODEL, mode, self.session_id]

        if ADD_DIR:
            cmd.extend(["--add-dir", ADD_DIR])

        # Only pass system prompt on session creation
        sys_prompt = self._build_full_system_prompt()
        if not self.session_established:
            cmd.extend(["--system-prompt", sys_prompt])

        full_prompt = f"{sys_prompt}\n\n--- Conversation ---\n{context}\n---\n\nMessage: {prompt}" if not self.session_established else prompt

        try:
            r = subprocess.run(
                cmd, input=full_prompt, capture_output=True, text=True, timeout=CLI_TIMEOUT
            )

            if r.returncode != 0 and not r.stdout.strip():
                stderr = r.stderr.strip() or "Unknown error"
                # Handle "already in use" by rotating session (max 3 retries)
                if "already in use" in stderr and _retry < 3:
                    log.warning(f"Session locked, rotating (attempt {_retry + 1}/3)...")
                    self.session_id = str(uuid.uuid4())
                    self.session_established = False
                    return self._sync_generate(prompt, context, _retry=_retry + 1)
                return f"[Claude Code error \u2014 check server logs]"

            response = r.stdout.strip()
            if not response:
                return "[Claude returned empty response]"

            # Session is now established
            self.session_established = True
            return response

        except subprocess.TimeoutExpired:
            return "[Claude Code timed out]"
        except FileNotFoundError:
            return "[Error: claude CLI not found]"

    async def on_message(self, sender, content, data):
        if content.strip() == "[RESET]":
            if sender == self.operator_role:
                self.session_id = str(uuid.uuid4())
                self.session_established = False
                self.transcript.clear()
                log.info(f"Session reset: {self.session_id[:8]}...")
            return
        await super().on_message(sender, content, data)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="ZeroRelay Claude Code Bridge")
    p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(ClaudeCodeBridge(relay_url=p.parse_args().relay).run())
