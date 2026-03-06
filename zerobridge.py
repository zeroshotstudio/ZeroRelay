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

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("zerobridge")

# OpenClaw defaults
DEFAULT_AGENT_ID = "main"
DEFAULT_SESSION_KEY = "agent:main:main"
AGENT_TIMEOUT_MS = 120_000
CLI_TIMEOUT_SEC = 130  # Slightly longer than agent timeout


def call_openclaw_agent(message: str, agent_id: str, session_key: str) -> str:
    """
    Send a message to Z via openclaw CLI and wait for response.
    Two-step: agent (submit) → agent.wait (get result).
    """
    idempotency_key = str(uuid.uuid4())

    # Step 1: Submit message
    agent_params = json.dumps({
        "agentId": agent_id,
        "sessionKey": session_key,
        "message": message,
        "idempotencyKey": idempotency_key
    })

    log.info(f"Submitting to Z (agent={agent_id})...")

    try:
        submit_result = subprocess.run(
            ["openclaw", "gateway", "call", "agent", "--params", agent_params],
            capture_output=True,
            text=True,
            timeout=30
        )

        if submit_result.returncode != 0:
            error = submit_result.stderr.strip() or submit_result.stdout.strip() or "Unknown error"
            log.error(f"Agent submit failed: {error}")
            return f"[OpenClaw error on submit: {error}]"

        # Parse the response to get runId
        try:
            submit_data = json.loads(submit_result.stdout.strip())
            # Handle both direct payload and nested response formats
            payload = submit_data.get("payload", submit_data)
            run_id = payload.get("runId")

            if not run_id:
                log.error(f"No runId in response: {submit_result.stdout[:200]}")
                return f"[OpenClaw error: no runId returned. Raw: {submit_result.stdout[:200]}]"

            log.info(f"Accepted, runId={run_id}. Waiting for completion...")

        except json.JSONDecodeError:
            log.error(f"Could not parse submit response: {submit_result.stdout[:200]}")
            return f"[OpenClaw error: unparseable response: {submit_result.stdout[:200]}]"

    except subprocess.TimeoutExpired:
        log.error("Agent submit timed out (30s)")
        return "[OpenClaw error: submit timed out]"
    except FileNotFoundError:
        log.error("openclaw CLI not found. Is it installed and in PATH?")
        return "[OpenClaw error: CLI not found]"

    # Step 2: Wait for completion
    wait_params = json.dumps({
        "runId": run_id,
        "timeoutMs": AGENT_TIMEOUT_MS
    })

    try:
        wait_result = subprocess.run(
            [
                "openclaw", "gateway", "call", "agent.wait",
                "--params", wait_params,
                "--timeout", str(CLI_TIMEOUT_SEC * 1000)
            ],
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SEC
        )

        if wait_result.returncode != 0:
            error = wait_result.stderr.strip() or wait_result.stdout.strip() or "Unknown error"
            log.error(f"Agent wait failed: {error}")
            return f"[OpenClaw error on wait: {error}]"

        # Extract Z's response
        try:
            wait_data = json.loads(wait_result.stdout.strip())
            payload = wait_data.get("payload", wait_data)

            # Try common response shapes — adjust based on actual OpenClaw output
            response = (
                payload.get("response")
                or payload.get("message")
                or payload.get("text")
                or payload.get("content")
                or payload.get("result")
            )

            if response:
                return str(response)

            # If none of the expected keys, return the full payload for debugging
            log.warning(f"Unexpected payload shape: {json.dumps(payload)[:300]}")
            return json.dumps(payload, indent=2)

        except json.JSONDecodeError:
            # Maybe it's just plain text
            return wait_result.stdout.strip()

    except subprocess.TimeoutExpired:
        log.error(f"Agent wait timed out ({CLI_TIMEOUT_SEC}s)")
        return "[Z is still thinking... timed out waiting for response]"


async def bridge(relay_url: str, agent_id: str, session_key: str):
    """Main bridge loop — relay ←→ OpenClaw CLI."""
    uri = f"{relay_url}?role=vps_claude"

    while True:
        try:
            log.info(f"Connecting to relay: {uri}")
            async with websockets.connect(uri) as ws:
                log.info("Connected to relay as vps_claude")

                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = data.get("type")

                    if msg_type == "connected":
                        peers = data.get("peers_online", [])
                        log.info(f"Relay confirmed. Peers online: {peers}")
                        continue

                    if msg_type == "system":
                        log.info(f"System: {data.get('message')}")
                        continue

                    if msg_type == "message" and data.get("from") in ("claude_ai", "jimmy"):
                        sender = data.get("from")
                        content = data.get("content", "")
                        log.info(f"From {sender}: {content[:100]}")

                        # Let the relay know Z is working on it
                        try:
                            await ws.send(json.dumps({
                                "content": f"[Z is thinking...]",
                                "meta": "typing_indicator"
                            }))
                        except Exception:
                            pass

                        # Call OpenClaw (blocking, run in thread pool)
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(
                            None,
                            call_openclaw_agent,
                            content,
                            agent_id,
                            session_key
                        )

                        log.info(f"Z responded: {response[:100]}")

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
        default=DEFAULT_SESSION_KEY,
        help=f"OpenClaw session key (default: {DEFAULT_SESSION_KEY})"
    )
    args = parser.parse_args()

    log.info("ZeroBridge starting")
    log.info(f"Relay: {args.relay}")
    log.info(f"Agent: {args.agent_id} | Session: {args.session_key}")
    asyncio.run(bridge(args.relay, args.agent_id, args.session_key))


if __name__ == "__main__":
    main()
