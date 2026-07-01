#!/usr/bin/env python3
"""ZeroRelay bridge: Gemini CLI.
Env: GEMINI_MODEL, GEMINI_TAGS, GEMINI_ROLE, GEMINI_TIMEOUT"""

import asyncio, json, logging, os, subprocess, sys, uuid
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("gemini-cli-bridge")

MODEL = os.environ.get("GEMINI_MODEL", "")
CLI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "1200"))
SESSION_IDLE_RESET_SEC = int(os.environ.get("GEMINI_SESSION_IDLE_SEC", "1800"))
DEFAULT_PROMPT = """You are Gemini in a multi-party relay chat called ZeroRelay.
Keep responses short and conversational. No headers or formatting unless asked."""

class GeminiCliBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        tags = [t.strip() for t in os.environ.get("GEMINI_TAGS", "@gemini,@gem").split(",")]
        super().__init__(
            relay_url=relay_url,
            role=os.environ.get("GEMINI_ROLE", "gemini"),
            tags=tags,
            display_name="Gemini (CLI)",
            system_prompt=os.environ.get("GEMINI_SYSTEM_PROMPT", DEFAULT_PROMPT),
            **kw
        )
        self.session_id = str(uuid.uuid4())
        self.session_established = False
        self.last_activity = datetime.now()
        # Initialize session with system prompt
        self._sync_generate(self.system_prompt, "", is_system=True)

    def _check_idle_reset(self):
        idle = (datetime.now() - self.last_activity).total_seconds()
        if idle > SESSION_IDLE_RESET_SEC:
            self.session_id = str(uuid.uuid4())
            self.session_established = False
            self.transcript.clear()
            log.info(f"Session auto-reset (idle {idle:.0f}s). New: {self.session_id[:8]}...")
            self._sync_generate(self.system_prompt, "", is_system=True)

    def _sync_generate(self, prompt, context, _retry=0, is_system=False):
        is_stateless = False
        if "[STATELESS]" in prompt:
            is_stateless = True
            prompt = prompt.replace("[STATELESS]", "").strip()

        if "[HARD_WIPE]" in prompt:
            self.session_id = str(uuid.uuid4())
            self.session_established = False
            self.transcript.clear()
            prompt = prompt.replace("[HARD_WIPE]", "").strip()
            log.info(f"Manual HARD WIPE requested. New session: {self.session_id[:8]}...")
            self._sync_generate(self.system_prompt, "", is_system=True)
            
        if not is_system and not is_stateless:
            self._check_idle_reset()
            
        if not is_stateless:
            self.last_activity = datetime.now()

        full_prompt = f"--- Conversation ---\n{context}\n---\n\nMessage: {prompt}" if context else prompt
        
        if is_stateless:
            # Use a fresh random session ID for every stateless call to ensure no overlap
            stateless_id = str(uuid.uuid4())
            cmd = ["gemini", "--prompt=", "--yolo", "--session-id", stateless_id, "-o", "json"]
            log.info(f"Executing STATELESS generation pass with fresh ID {stateless_id[:8]}...")
        else:
            mode = "--session-id" if not self.session_established else "--resume"
            cmd = ["gemini", "--prompt=", "--yolo", mode, self.session_id, "-o", "json"]
            
        if MODEL:
            cmd.extend(["-m", MODEL])

        try:
            # Run in a sandbox directory to prevent it from loading unrelated files as context
            sandbox_dir = "/Users/zero/.gemini/tmp/bridge_sandbox"
            os.makedirs(sandbox_dir, exist_ok=True)
            r = subprocess.run(
                cmd, input=full_prompt, capture_output=True, text=True, timeout=CLI_TIMEOUT,
                cwd=sandbox_dir
            )
            stdout_text = r.stdout.strip()
            stderr_text = r.stderr.strip()
            
            # Handle session collision
            if r.returncode != 0 and "already exists" in stderr_text and not self.session_established:
                log.warning(f"Session {self.session_id[:8]} already exists. Switching to resume mode.")
                self.session_established = True
                return self._sync_generate(prompt, context, is_system=is_system)

            response_text = "[Gemini returned empty response]"
            
            # Find all potential JSON blocks and try to parse the last valid one
            # The CLI might print errors containing '{' before the actual JSON output
            import time
            import re
            
            # The final JSON block from gemini CLI typically starts with '{' on a new line
            # and ends with '}' at the very end of stdout.
            
            blocks = []
            depth = 0
            start = -1
            for i, char in enumerate(stdout_text):
                if char == '{' or char == '[':
                    if depth == 0:
                        start = i
                    depth += 1
                elif char == '}' or char == ']':
                    depth -= 1
                    if depth == 0 and start != -1:
                        blocks.append(stdout_text[start:i+1])
            
            # Reverse order to prefer the last output block
            api_error = None
            for block in reversed(blocks):
                try:
                    data = json.loads(block)
                    
                    # Intercept Gaxios/API errors formatted as arrays of dicts
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "error" in data[0]:
                        api_error = data[0]["error"].get("message", "Capacity/Rate Limit Error")
                        break
                        
                    # Intercept direct dict errors
                    if isinstance(data, dict):
                        if "error" in data and isinstance(data["error"], dict):
                             api_error = data["error"].get("message", "Capacity/Rate Limit Error")
                             break
                        if "response" in data:
                            response_text = data["response"]
                            break
                except json.JSONDecodeError:
                    continue
                    
            if api_error:
                log.error(f"Upstream API Error detected: {api_error}")
                if "capacity" in api_error.lower() or "quota" in api_error.lower() or "429" in api_error:
                    # Let the caller or Libriscribe's retry handler deal with it, but we MUST raise an exception
                    # so Libriscribe doesn't think it succeeded.
                    raise RuntimeError(f"API Rate Limit / Capacity Exhausted: {api_error}")
                raise RuntimeError(f"Gemini API Error: {api_error}")

            if response_text == "[Gemini returned empty response]" and r.stdout.strip():
                 raw_lines = [l for l in stdout_text.split('\n') if not l.startswith("YOLO mode") and "Ripgrep" not in l and not l.startswith("Warning")]
                 if raw_lines:
                     response_text = "\n".join(raw_lines)

            if r.returncode != 0 and not r.stdout.strip():
                stderr = r.stderr.strip() or "Unknown error"
                if "Invalid session identifier" in stderr:
                    log.warning(f"Session {self.session_id} was lost. Resetting.")
                    self.session_established = False
                    self.session_id = str(uuid.uuid4())
                    # Attempt recovery automatically
                    return self._sync_generate(prompt, context, is_system=is_system)
                return f"[Gemini CLI error — check server logs: {stderr}]"

            self.session_established = True
            return response_text

        except subprocess.TimeoutExpired:
            return "[Gemini CLI timed out]"
        except FileNotFoundError:
            return "[Error: gemini CLI not found]"

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="ZeroRelay Gemini CLI Bridge")
    p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(GeminiCliBridge(relay_url=p.parse_args().relay).run())
