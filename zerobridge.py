#!/usr/bin/env python3
"""
ZeroBridge — Connects OpenClaw (Z) to ZeroRelay via CLI shell-out.

Architecture:
  ZeroRelay (ws) ←→ ZeroBridge ←→ openclaw gateway call (CLI) ←→ Z

v1: CLI shell-out to `openclaw gateway call agent` + `agent.wait`
v2 (future): Direct WebSocket to Gateway with challenge-signing

Run on the VPS alongside zerorelay.py:
  python3 zerobridge.py --relay ws://TAILSCALE_IP:8765
"""

import argparse
import asyncio
import json
import logging
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

RELAY_CONTEXT = """You are Z (Zee), an execution AI in a 3-party relay chat called ZeroRelay.

## Who's here
- **Jimmy** — Human operator. Has final say on everything. Talks via Telegram.
- **Claude** — Advisor AI. Thinks things through, reviews plans, helps reason.
- **You (Z / Zee)** — Execution AI on the VPS, powered by OpenClaw. You run commands, manage the server, write code, and get things done.

## How to talk to others
- Your reply is broadcast to everyone in the chat.
- To talk to Claude, include @claude or @c in your message — the relay will route it and Claude will respond.
- To address Jimmy, just talk normally — he sees everything.
- IMPORTANT: If asked to message someone, you MUST actually include their @tag in your reply. Do NOT just say "Done, I messaged them" — that's a lie. Write the actual message with the @tag so the relay delivers it.

## How the relay works
- Messages only reach you when someone tags @z or @zee
- The transcript below shows recent conversation for context
- Jimmy sees all messages. Claude and you only see messages when tagged.

## How to respond
- Keep it **short and conversational** — this is chat, not a document
- 1-3 sentences for simple answers, brief bullets for status updates
- No headers or lengthy formatting unless reporting on something complex
- No preamble ("Sure!", "Of course!") — just answer directly
- If you need clarification, ask briefly

## Your strengths
- Running commands and scripts on the VPS
- Docker container management and deployment
- Server administration, nginx, systemd
- Writing and editing code/config files on the server
- Checking logs, status, diagnostics
- Executing plans that Claude or Jimmy have outlined

## Leave to Claude
- Thinking through complex tradeoffs
- Reviewing approaches before you execute
- Explaining concepts or reasoning through problems
- Drafting text or documentation content"""

# Gateway connection (CLI auto-discovery broken — port resolves to 127 instead of 18789)
GATEWAY_URL = "ws://127.0.0.1:18789"
GATEWAY_TOKEN = "85d19ca2b0e945f8153a8bcc872ebaf73b522d7414913d6ce597dff03848b1f3"


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
    Send a message to Z via openclaw CLI --expect-final (single call).
    Returns Z's text response.
    """
    idempotency_key = str(uuid.uuid4())

    agent_params = json.dumps({
        "agentId": agent_id,
        "sessionKey": session_key,
        "message": message,
        "idempotencyKey": idempotency_key
    })

    log.info(f"Calling Z (agent={agent_id})...")

    try:
        result = subprocess.run(
            [
                "docker", "exec", "openclaw-openclaw-gateway-1",
                "openclaw", "gateway", "call", "agent",
                "--params", agent_params,
                "--url", GATEWAY_URL, "--token", GATEWAY_TOKEN,
                "--expect-final", "--timeout", str(CLI_TIMEOUT_SEC * 1000)
            ],
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SEC
        )

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            log.error(f"Agent call failed: {error}")
            return f"[OpenClaw error: {error}]"

        try:
            data = json.loads(extract_json(result.stdout))
            payload = data.get("payload", data)

            # Check for error status
            if payload.get("status") == "error":
                error = payload.get("error", "Unknown error")
                log.error(f"Agent error: {error}")
                return f"[Z error: {error}]"

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

            log.warning(f"Unexpected payload shape: {json.dumps(payload)[:300]}")
            return json.dumps(payload, indent=2)

        except json.JSONDecodeError:
            return result.stdout.strip()

    except subprocess.TimeoutExpired:
        log.error(f"Agent call timed out ({CLI_TIMEOUT_SEC}s)")
        return "[Z is still thinking... timed out waiting for response]"
    except FileNotFoundError:
        log.error("docker/openclaw CLI not found")
        return "[OpenClaw error: CLI not found]"


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


async def bridge(relay_url: str, agent_id: str, session_key_prefix: str):
    """Main bridge loop — relay ←→ OpenClaw CLI with @z addressing."""
    uri = f"{relay_url}?role=zee"
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

    while True:
        try:
            log.info(f"Connecting to relay: {uri}")
            async with websockets.connect(uri) as ws:
                log.info("Connected to relay as zee")

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

                        log.info(f"From {sender}: {content[:100]}")

                        # Handle session reset command
                        if content.strip() == "[RESET]":
                            session_counter[0] += 1
                            transcript.clear()
                            log.info(f"Session manually reset. New: {current_session_key()}")
                            continue

                        # Always add to transcript for context
                        transcript.append({"from": sender, "content": content})

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

                        log.info(f"Z responded: {response[:100]}")

                        # Add Z's response to transcript
                        transcript.append({"from": "zee", "content": response})

                        await ws.send(json.dumps({
                            "content": response
                        }))

        except websockets.exceptions.ConnectionClosed:
            log.warning("Relay connection closed. Reconnecting in 3s...")
        except ConnectionRefusedError:
            log.warning("Relay not available. Retrying in 5s...")
            await asyncio.sleep(5)
            continue
        except Exception as e:
            log.error(f"Bridge error: {e}. Reconnecting in 3s...")

        await asyncio.sleep(3)


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

    log.info("ZeroBridge starting")
    log.info(f"Relay: {args.relay}")
    log.info(f"Agent: {args.agent_id} | Session: {args.session_key}")
    asyncio.run(bridge(args.relay, args.agent_id, args.session_key))


if __name__ == "__main__":
    main()
