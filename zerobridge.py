#!/usr/bin/env python3
"""
ZeroBridge — Connects OpenClaw (Z) to ZeroRelay via SSH to ZeroMini.

Architecture:
  ZeroRelay (ws) <-> ZeroBridge <-> ssh zeromini openclaw CLI <-> Z

v1: CLI shell-out via docker exec (deprecated - OpenClaw moved off VPS)
v2: SSH to ZeroMini where OpenClaw runs natively

Run on the VPS alongside zerorelay.py:
  python3 zerobridge.py --relay ws://TAILSCALE_IP:8765
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime

import re

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("zerobridge")

# OpenClaw defaults
DEFAULT_AGENT_ID = "main"
SESSION_KEY_PREFIX = "agent:main:zerorelay"
AGENT_TIMEOUT_MS = 120_000
CLI_TIMEOUT_SEC = 130  # Slightly longer than agent timeout
SESSION_IDLE_RESET_SEC = 30 * 60  # Reset session after 30 min idle

# Addressing — Z only responds when tagged
Z_TAG_PATTERN = re.compile(r"@z(?:ee)?\b", re.IGNORECASE)
MAX_TRANSCRIPT_LINES = 30

# Relay auth token
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

# SSH target for ZeroMini where OpenClaw runs natively
ZEROMINI_SSH = os.environ.get("ZEROMINI_SSH", "zeromini")

# Zee outbox on ZeroMini (polled via SSH)
ZEE_OUTBOX_REMOTE = "/home/zeroshot/.openclaw/relay-outbox"
ZEE_OUTBOX_LOG = "/opt/zerorelay/zee-outbox.sent"

RELAY_CONTEXT = """You are Zee (Z), the OpenClaw Main Agent in a 3-party relay chat called ZeroRelay.

Who's here:
- Jimmy — Human operator. Final say on everything. Talks via Telegram.
- Claude — Jimmy's right-hand AI. Runs as a dedicated `claude` user on the VPS with scoped sudo for privileged operations. Has Docker group access and can manage any container (including yours), nginx, systemd, firewall, and other apps via sudo. When you need something done outside your container, Claude is the one who can help.
- You (Zee / Z) — OpenClaw Main Agent. You run ONLY inside the OpenClaw Docker container. You can run commands, write code, and manage things WITHIN your container, but you have ZERO access to the VPS host — no nginx, no systemd, no other Docker containers, no host filesystem. If something needs doing outside your container, you MUST ask Claude (@claude) or Jimmy to do it for you.

How to talk to others:
- Your reply is broadcast to everyone.
- To reach Claude, you MUST include a @claude or @c tag, this will route the message directly to Claude.
- To reach Jimmy, just talk normally.
- IMPORTANT: If asked to message someone, actually include their @tag. Don't say "Done, I messaged them" without writing the real message. You do not have the ability to message anyone outside of the telegram chat.

CRITICAL: Anytime you direct a message TO another agent (Claude), you MUST include their @tag (@claude or @c) in EVERY such message — not just the first one. No exceptions.

How the relay works:
- You only receive messages when someone tags @z or @zee.
- The transcript shows recent context.
- Jimmy sees all messages. Claude and you only see messages when tagged.

Your strengths:
- Running commands and scripts on ZeroMini
- Managing OpenClaw config, agents, cron jobs, and plugins
- Writing and editing code/config files within your workspace
- Checking your own logs, session history, and diagnostics
- Executing plans that Claude or Jimmy have outlined

Leave to Claude:
- Anything on the VPS (nginx, systemd, Docker, other apps)
- Server security, firewall, SSH config
- Changes that require VPS host access

Response style: Short and conversational. No headers/preamble unless asked."""

# Gateway connection — token from env
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "")


def extract_json(text: str) -> str:
    """Extract JSON object from CLI output that may contain banner/warning lines."""
    # Find the first '{' and take everything from there
    idx = text.find("{")
    if idx == -1:
        return text.strip()
    # Find the matching closing brace
    depth = 0
    for i in range(idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[idx:i + 1]
    return text[idx:]


def call_openclaw_agent(message: str, agent_id: str, session_key: str) -> str:
    """
    Send a message to Z via SSH to ZeroMini's openclaw CLI.
    Returns Z's text response.
    """
    idempotency_key = str(uuid.uuid4())

    agent_params = json.dumps({
        "agentId": agent_id,
        "sessionKey": session_key,
        "message": message,
        "idempotencyKey": idempotency_key
    })

    log.info(f"Calling Z via SSH to {ZEROMINI_SSH} (agent={agent_id})...")

    try:
        cmd = [
            "ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
            ZEROMINI_SSH,
            "openclaw", "gateway", "call", "agent",
            "--params", agent_params,
            "--token", GATEWAY_TOKEN,
            "--expect-final", "--timeout", str(CLI_TIMEOUT_SEC * 1000)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SEC
        )

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            log.error(f"Agent call failed: {error}")
            return "[OpenClaw error: agent call failed]"

        try:
            data = json.loads(extract_json(result.stdout))
            payload = data.get("payload", data)

            # Check for error status
            if payload.get("status") == "error":
                error = payload.get("error", "Unknown error")
                log.error(f"Agent error: {error}")
                return "[Z error: agent returned error]"

            # Extract response text from result.payloads[].text
            result_obj = payload.get("result", {})
            payloads = result_obj.get("payloads", [])
            if payloads:
                texts = [p.get("text", "") for p in payloads if p.get("text")]
                if texts:
                    return "\n".join(texts)

            # Fallback: try common keys
            for key in ("response", "message", "text", "content"):
                if payload.get(key):
                    return str(payload[key])

            log.warning(f"Unexpected payload shape")
            return json.dumps(payload, indent=2)

        except json.JSONDecodeError:
            return result.stdout.strip()

    except subprocess.TimeoutExpired:
        log.error(f"Agent call timed out ({CLI_TIMEOUT_SEC}s)")
        return "[Z is still thinking... timed out waiting for response]"
    except FileNotFoundError:
        log.error("ssh not found")
        return "[OpenClaw error: ssh not found]"


def is_z_addressed(content: str) -> bool:
    """Check if message is addressed to Z via @z or @zee tag."""
    return bool(Z_TAG_PATTERN.search(content))


def strip_z_tag(content: str) -> str:
    """Remove @z/@zee tag from message, leaving the rest."""
    return Z_TAG_PATTERN.sub("", content).strip()


def format_transcript(transcript: list[dict]) -> str:
    """Format recent transcript as context for Z."""
    if not transcript:
        return "(no prior messages)"
    lines = []
    for msg in transcript[-MAX_TRANSCRIPT_LINES:]:
        sender = msg.get("from", "system")
        content = msg.get("content", "")
        # Truncate long messages in transcript
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"[{sender}]: {content}")
    return "\n".join(lines)


async def watch_zee_outbox(ws):
    """Poll Zee's outbox on ZeroMini via SSH for messages he wants to send.
    Zee writes to /home/zeroshot/.openclaw/relay-outbox on ZeroMini."""
    while True:
        await asyncio.sleep(3)  # Poll every 3s (SSH has overhead vs local file)
        try:
            read_and_clear = (
                f"content=$(cat {ZEE_OUTBOX_REMOTE} 2>/dev/null); "
                f'if [ -n "$content" ]; then echo "$content"; '
                f"echo -n > {ZEE_OUTBOX_REMOTE}; fi"
            )
            result = subprocess.run(
                [
                    "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                    ZEROMINI_SSH, "bash", "-c", read_and_clear
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            content = result.stdout.strip()
            if content:
                ts = datetime.now().strftime("%H:%M:%S")
                log.info(f"Zee outbox: ({len(content)} chars)")

                with open(ZEE_OUTBOX_LOG, "a") as f:
                    f.write(f"[{ts}] {content}\n")

                await ws.send(json.dumps({"content": content}))

        except subprocess.TimeoutExpired:
            log.debug("Zee outbox SSH poll timed out")
        except Exception as e:
            log.debug(f"Zee outbox watch error: {e}")

async def bridge(relay_url: str, agent_id: str, session_key_prefix: str):
    """Main bridge loop — relay ←→ OpenClaw CLI with @z addressing."""
    token_param = f"&token={RELAY_TOKEN}" if RELAY_TOKEN else ""
    uri = f"{relay_url}?role=zee{token_param}"
    transcript: list[dict] = []
    session_counter = [0]  # Mutable for reset
    last_activity = [datetime.now()]

    def current_session_key():
        return f"{session_key_prefix}:{session_counter[0]}"

    def check_session_reset():
        """Reset session if idle too long."""
        idle = (datetime.now() - last_activity[0]).total_seconds()
        if idle > SESSION_IDLE_RESET_SEC:
            session_counter[0] += 1
            transcript.clear()
            log.info(f"Session auto-reset (idle {idle:.0f}s). New session: {current_session_key()}")
            return True
        return False

    backoff = 3
    while True:
        try:
            log.info(f"Connecting to relay")
            async with websockets.connect(uri) as ws:
                log.info("Connected to relay as zee")
                backoff = 3  # Reset on successful connect

                # Start outbox watcher so Zee can initiate messages
                outbox_task = asyncio.create_task(watch_zee_outbox(ws))

                try:
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = data.get("type")

                        if msg_type == "connected":
                            peers = data.get("peers_online", [])
                            log.info(f"Relay confirmed. Peers online: {peers}")
                            # Load history into transcript
                            for h in data.get("history", []):
                                if h.get("type") == "message":
                                    transcript.append(h)
                            continue

                        if msg_type == "system":
                            log.info(f"System: {data.get('message')}")
                            continue

                        if msg_type == "message":
                            sender = data.get("from", "")
                            content = data.get("content", "")

                            # Skip our own messages, typing indicators, and stream chunks
                            meta = data.get("meta")
                            if sender == "zee" or meta in ("typing_indicator", "stream_start", "stream_chunk"):
                                continue

                            log.info(f"From {sender}: ({len(content)} chars)")

                            # Handle session reset command (only from jimmy)
                            if content.strip() == "[RESET]" and sender == "jimmy":
                                session_counter[0] += 1
                                transcript.clear()
                                log.info(f"Session manually reset. New: {current_session_key()}")
                                continue

                            # Always add to transcript for context
                            transcript.append({"from": sender, "content": content})
                            # Trim transcript to max size
                            transcript[:] = transcript[-MAX_TRANSCRIPT_LINES:]

                            # Only call Z when addressed
                            if not is_z_addressed(content):
                                log.info(f"Not addressed to Z, added to transcript only")
                                continue

                            # Check for idle session reset
                            check_session_reset()
                            last_activity[0] = datetime.now()

                            # Strip the @z tag for the actual prompt
                            prompt = strip_z_tag(content)
                            if not prompt:
                                continue

                            # Signal typing indicator
                            try:
                                await ws.send(json.dumps({
                                    "content": "", "meta": "typing_indicator"
                                }))
                            except Exception:
                                pass

                            # Build context-enriched message for Z
                            context_transcript = format_transcript(transcript[:-1])  # exclude current msg
                            sk = current_session_key()
                            full_prompt = (
                                f"{RELAY_CONTEXT}\n\n"
                                f"--- Recent conversation ---\n{context_transcript}\n"
                                f"--- End conversation ---\n\n"
                                f"{sender} says to you: {prompt}"
                            )

                            # Call OpenClaw with periodic typing keepalive
                            async def call_with_typing():
                                loop = asyncio.get_event_loop()
                                task = loop.run_in_executor(
                                    None,
                                    call_openclaw_agent,
                                    full_prompt,
                                    agent_id,
                                    sk
                                )
                                while not task.done():
                                    await asyncio.sleep(4)
                                    if not task.done():
                                        try:
                                            await ws.send(json.dumps({
                                                "content": "", "meta": "typing_indicator"
                                            }))
                                        except Exception:
                                            pass
                                return await task

                            response = await call_with_typing()

                            log.info(f"Z responded ({len(response)} chars)")

                            # Add Z's response to transcript
                            transcript.append({"from": "zee", "content": response})
                            # Trim transcript
                            transcript[:] = transcript[-MAX_TRANSCRIPT_LINES:]

                            await ws.send(json.dumps({
                                "content": response
                            }))

                finally:
                    outbox_task.cancel()

        except websockets.exceptions.ConnectionClosed:
            log.warning(f"Relay connection closed. Reconnecting in {backoff}s...")
        except ConnectionRefusedError:
            log.warning(f"Relay not available. Retrying in {backoff}s...")
        except Exception as e:
            log.error(f"Bridge error: {e}. Reconnecting in {backoff}s...")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


def main():
    parser = argparse.ArgumentParser(description="ZeroBridge — OpenClaw ↔ ZeroRelay")
    parser.add_argument(
        "--relay",
        default="ws://localhost:8765",
        help="Relay WebSocket URL (use Tailscale IP if remote)"
    )
    parser.add_argument(
        "--agent-id",
        default=DEFAULT_AGENT_ID,
        help=f"OpenClaw agent ID (default: {DEFAULT_AGENT_ID})"
    )
    parser.add_argument(
        "--session-key",
        default=SESSION_KEY_PREFIX,
        help=f"OpenClaw session key prefix (default: {SESSION_KEY_PREFIX})"
    )
    args = parser.parse_args()

    log.info("ZeroBridge starting (SSH to ZeroMini mode)")
    log.info(f"Relay: {args.relay}")
    log.info(f"Agent: {args.agent_id} | Session: {args.session_key}")
    log.info(f"ZeroMini SSH target: {ZEROMINI_SSH}")
    asyncio.run(bridge(args.relay, args.agent_id, args.session_key))


if __name__ == "__main__":
    main()
