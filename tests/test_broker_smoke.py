import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import websockets


REPO_ROOT = Path(__file__).resolve().parents[1]
BROKER_PATH = REPO_ROOT / "zerorelay.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for {host}:{port}")


async def recv_until(ws, predicate, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        remaining = max(deadline - time.monotonic(), 0.1)
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        message = json.loads(raw)
        last = message
        if predicate(message):
            return message
    raise AssertionError(f"Did not receive expected message. Last message: {last!r}")


class BrokerSmokeTest(unittest.TestCase):
    def test_broker_startup_and_broadcast(self):
        port = free_port()
        token = secrets.token_hex(16)
        env = os.environ.copy()
        env["RELAY_TOKEN"] = token

        with tempfile.TemporaryDirectory(prefix="zerorelay-smoke-") as tmpdir:
            log_path = Path(tmpdir) / "broker.log"
            with open(log_path, "w", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    [sys.executable, str(BROKER_PATH), "--host", "127.0.0.1", "--port", str(port)],
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                try:
                    asyncio.run(wait_for_port("127.0.0.1", port))
                    asyncio.run(self.run_smoke_sequence(port, token))
                except Exception:
                    broker_log = log_path.read_text(encoding="utf-8")
                    self.fail(f"Broker smoke test failed.\n\nBroker log:\n{broker_log}")
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)

    async def run_smoke_sequence(self, port: int, token: str) -> None:
        uri = f"ws://127.0.0.1:{port}"

        async with websockets.connect(f"{uri}?role=jimmy&token={token}") as jimmy:
            connected = json.loads(await jimmy.recv())
            self.assertEqual(connected["type"], "connected")
            self.assertEqual(connected["role"], "jimmy")
            self.assertEqual(connected["peers_online"], [])

            bad = await websockets.connect(f"{uri}?role=vps_claude&token=wrong")
            try:
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await bad.recv()
                self.assertEqual(bad.close_code, 1008)
            finally:
                await bad.close()

            async with websockets.connect(f"{uri}?role=vps_claude&token={token}") as claude:
                claude_connected = json.loads(await claude.recv())
                self.assertEqual(claude_connected["type"], "connected")
                self.assertIn("jimmy", claude_connected["peers_online"])

                await recv_until(
                    jimmy,
                    lambda msg: msg["type"] == "system" and msg["message"] == "vps_claude joined",
                )

                duplicate = await websockets.connect(f"{uri}?role=vps_claude&token={token}")
                try:
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):
                        await duplicate.recv()
                    self.assertEqual(duplicate.close_code, 1008)
                finally:
                    await duplicate.close()

                payload = {"content": "hello from jimmy"}
                await jimmy.send(json.dumps(payload))
                broadcast = await recv_until(
                    claude,
                    lambda msg: msg["type"] == "message" and msg["from"] == "jimmy",
                )
                self.assertEqual(broadcast["content"], payload["content"])

                async with websockets.connect(f"{uri}?role=zee&token={token}") as zee:
                    zee_connected = json.loads(await zee.recv())
                    self.assertEqual(zee_connected["type"], "connected")
                    self.assertIn("jimmy", zee_connected["peers_online"])
                    self.assertIn("vps_claude", zee_connected["peers_online"])
                    self.assertTrue(
                        any(
                            msg.get("from") == "jimmy" and msg.get("content") == payload["content"]
                            for msg in zee_connected["history"]
                        )
                    )


if __name__ == "__main__":
    unittest.main()
