#!/usr/bin/env python3
"""ZeroRelay bridge: OpenClaw Gateway via docker exec CLI or WebSocket.

Connects an OpenClaw agent to the ZeroRelay multi-party chat. Supports
tag-based routing (@z, @zee), session management with idle auto-reset,
and an optional outbox file watcher so OpenClaw can initiate messages.

Environment Variables:
    OPENCLAW_CONTAINER      Docker container name (default: openclaw-openclaw-gateway-1)
    OPENCLAW_AGENT_ID       Agent ID to call (default: main)
    OPENCLAW_SESSION        Session key prefix (default: agent:main:zerorelay)
    OPENCLAW_GATEWAY        Gateway WebSocket URL (default: ws://127.0.0.1:18789)
    OPENCLAW_TOKEN          Gateway auth token (default: empty)
    OPENCLAW_TIMEOUT        CLI call timeout in seconds (default: 130)
    OPENCLAW_TAGS           Comma-separated @-tags to respond to (default: @z,@zee)
    OPENCLAW_ROLE           Relay role name (default: zee)
    OPENCLAW_SYSTEM_PROMPT  Override the default system prompt
    OPENCLAW_MODE           Connection mode: cli or websocket (default: cli)
    OPENCLAW_OUTBOX         Path to outbox file for proactive messages (optional)
    SESSION_IDLE_RESET_SEC  Seconds idle before session auto-resets (default: 1800)
"""

import asyncio, fcntl, json, logging, os, subprocess, sys, uuid
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("openclaw-bridge")

# --- Configuration from environment ---
CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw-openclaw-gateway-1")
AGENT_ID = os.environ.get("OPENCLAW_AGENT_ID", "main")
SESSION_PREFIX = os.environ.get("OPENCLAW_SESSION", "agent:main:zerorelay")
GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY", "ws://127.0.0.1:18789")
GATEWAY_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")
CLI_TIMEOUT = int(os.environ.get("OPENCLAW_TIMEOUT", "130"))
MODE = os.environ.get("OPENCLAW_MODE", "cli")  # "cli" or "websocket"
OUTBOX_PATH = os.environ.get("OPENCLAW_OUTBOX", "")  # empty = disabled
SESSION_IDLE_RESET_SEC = int(os.environ.get("SESSION_IDLE_RESET_SEC", "1800"))


def extract_json(text: str) -> str:
    """Extract the first complete JSON object from text that may contain banners/warnings."""
    idx = text.find("{")
    if idx == -1:
        return text.strip()
    depth = 0
    for i in range(idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[idx:i + 1]
    return text[idx:]


class OpenClawBridge(AIBridge):
    def __init__(self, relay_url: str, **kw):
        tags = [t.strip() for t in os.environ.get("OPENCLAW_TAGS", "@z,@zee").split(",")]
        super().__init__(
            relay_url=relay_url,
            role=os.environ.get("OPENCLAW_ROLE", "zee"),
            tags=tags,
            display_name="Zee (OpenClaw)",
            system_prompt=os.environ.get("OPENCLAW_SYSTEM_PROMPT") or None,
            **kw,
        )
        self.session_counter = 0
        self.last_activity = datetime.now()

    def _current_session_key(self) -> str:
        return f"{SESSION_PREFIX}:{self.session_counter}"

    def _check_idle_reset(self):
        """Reset session if idle longer than SESSION_IDLE_RESET_SEC."""
        idle = (datetime.now() - self.last_activity).total_seconds()
        if idle > SESSION_IDLE_RESET_SEC:
            self.session_counter += 1
            self.transcript.clear()
            log.info(f"Session auto-reset after {idle:.0f}s idle. New: {self._current_session_key()}")
            return True
        return False

    # --- Generation backends ---

    def _sync_generate(self, prompt: str, context: str) -> str:
        if MODE == "websocket":
            return self._generate_websocket(prompt, context)
        return self._generate_cli(prompt, context)

    def _generate_cli(self, prompt: str, context: str) -> str:
        """Call OpenClaw agent via docker exec CLI (default mode)."""
        full_msg = (
            f"{self._build_full_system_prompt()}\n\n"
            f"--- Recent conversation ---\n{context}\n"
            f"--- End conversation ---\n\n"
            f"Message: {prompt}"
        )
        params = json.dumps({
            "agentId": AGENT_ID,
            "sessionKey": self._current_session_key(),
            "message": full_msg,
            "idempotencyKey": str(uuid.uuid4()),
        })
        try:
            cmd = [
                "docker", "exec", CONTAINER,
                "openclaw", "gateway", "call", "agent",
                "--params", params,
                "--url", GATEWAY_URL,
                "--expect-final",
                "--timeout", str(CLI_TIMEOUT * 1000),
            ]
            # NOTE: --token is visible in 'ps aux'. Prefer setting OPENCLAW_TOKEN as a
            # container env var (via docker-compose) and using --token-env if supported.
            if GATEWAY_TOKEN:
                cmd.extend(["--token", GATEWAY_TOKEN])

            log.info(f"Calling agent (id={AGENT_ID}, session={self._current_session_key()})")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT)

            if r.returncode != 0:
                error = (r.stderr.strip() or r.stdout.strip() or "unknown error")[:300]
                log.error(f"CLI call failed (rc={r.returncode}): {error}")
                return f"[OpenClaw error: agent call failed -- {error[:200]}]"

            return self._parse_response(r.stdout)

        except subprocess.TimeoutExpired:
            log.error(f"CLI call timed out after {CLI_TIMEOUT}s")
            return "[OpenClaw timed out -- the agent is still processing. Try again shortly.]"
        except FileNotFoundError:
            log.error("docker or openclaw CLI not found on PATH")
            return "[OpenClaw error: docker/openclaw CLI not found. Is Docker installed?]"

    def _generate_websocket(self, prompt: str, context: str) -> str:
        """Connect directly to OpenClaw gateway via WebSocket.

        TODO: Implement direct WebSocket gateway protocol.
        This requires:
        - Opening a WS connection to OPENCLAW_GATEWAY
        - Sending the agent call request as a JSON-RPC message
        - Handling challenge-signing auth if GATEWAY_TOKEN is set
        - Receiving streamed or final response payloads
        """
        log.warning("WebSocket mode is not yet implemented, falling back to CLI")
        return self._generate_cli(prompt, context)

    def _parse_response(self, stdout: str) -> str:
        """Parse the JSON response from OpenClaw CLI output."""
        try:
            data = json.loads(extract_json(stdout))
            payload = data.get("payload", data)

            if payload.get("status") == "error":
                error = payload.get("error", "unknown")
                log.error(f"Agent returned error: {error}")
                return f"[OpenClaw agent error: {error}]"

            # Primary path: result.payloads[].text
            payloads = payload.get("result", {}).get("payloads", [])
            if payloads:
                texts = [p.get("text", "") for p in payloads if p.get("text")]
                if texts:
                    return "\n".join(texts)

            # Fallback: common response keys
            for key in ("response", "message", "text", "content"):
                if payload.get(key):
                    return str(payload[key])

            log.warning("Unexpected payload shape -- returning raw JSON")
            return json.dumps(payload, indent=2)

        except json.JSONDecodeError:
            return stdout.strip() if stdout.strip() else "[OpenClaw returned unparseable response]"

    # --- Message handling ---

    async def on_message(self, sender: str, content: str, data: dict):
        if content.strip() == "[RESET]":
            self.session_counter += 1
            self.transcript.clear()
            log.info(f"Session manually reset. New: {self._current_session_key()}")
            return

        # Check idle reset before processing
        self._check_idle_reset()
        self.last_activity = datetime.now()

        await super().on_message(sender, content, data)

    # --- Outbox file watcher ---

    async def _watch_outbox(self):
        """Poll an outbox file for proactive messages from the OpenClaw agent.

        The agent writes to this file (e.g. via cron or internal trigger) and
        this bridge picks it up and sends it to the relay. This lets the agent
        initiate conversations, not just respond to @-mentions.

        Uses file locking to safely read and clear the outbox.
        """
        outbox_log = OUTBOX_PATH + ".sent"
        log.info(f"Outbox watcher active: {OUTBOX_PATH}")

        while True:
            await asyncio.sleep(1)
            try:
                fd = os.open(OUTBOX_PATH, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    with os.fdopen(fd, "r") as f:
                        content = f.read().strip()
                except Exception:
                    os.close(fd)
                    raise

                if not content:
                    continue

                # Clear the file after reading
                fd_w = os.open(OUTBOX_PATH, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
                try:
                    fcntl.flock(fd_w, fcntl.LOCK_EX)
                    os.close(fd_w)
                except Exception:
                    os.close(fd_w)
                    raise

                ts = datetime.now().strftime("%H:%M:%S")
                log.info(f"Outbox message ({len(content)} chars)")

                # Log sent messages for debugging
                try:
                    with open(outbox_log, "a") as f:
                        f.write(f"[{ts}] {content}\n")
                except OSError:
                    pass

                await self.send(content)

            except FileNotFoundError:
                pass  # Outbox file does not exist yet -- normal
            except Exception as e:
                log.debug(f"Outbox watch error: {e}")

    # --- Main run loop ---

    async def run(self):
        """Override run() to add the outbox watcher task alongside the relay loop."""
        if not OUTBOX_PATH:
            await super().run()
            return

        # Run relay loop and outbox watcher concurrently
        relay_task = asyncio.create_task(super().run())
        outbox_task = asyncio.create_task(self._watch_outbox())

        try:
            await asyncio.gather(relay_task, outbox_task)
        except asyncio.CancelledError:
            relay_task.cancel()
            outbox_task.cancel()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="ZeroRelay OpenClaw Bridge")
    p.add_argument("--relay", default="ws://localhost:8765", help="Relay WebSocket URL")
    asyncio.run(OpenClawBridge(relay_url=p.parse_args().relay).run())
