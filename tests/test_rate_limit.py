"""Rate limit tests for ZeroRelay broker."""

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
BROKER_PATH = REPO_ROOT / "core" / "zerorelay.py"
RATE_MAX = 20


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


class RateLimitTest(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        self.token = secrets.token_hex(16)
        self.env = os.environ.copy()
        self.env["RELAY_TOKEN"] = self.token
        self.env["ZERORELAY_ROLES"] = "sender,receiver"
        self.env["ZERORELAY_RATE_MAX"] = str(RATE_MAX)
        self.env["ZERORELAY_RATE_WINDOW"] = "60"
        self.tmpdir = tempfile.mkdtemp(prefix="zerorelay-rate-")
        self.log_path = Path(self.tmpdir) / "broker.log"
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(BROKER_PATH), "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=REPO_ROOT,
            env=self.env,
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        asyncio.run(wait_for_port("127.0.0.1", self.port))

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.log_file.close()

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def test_rate_limit_drops_excess_messages(self):
        async def run():
            uri = f"ws://127.0.0.1:{self.port}?role=receiver"
            async with websockets.connect(uri, additional_headers=self.headers()) as receiver:
                await receiver.recv()  # connected

                sender_uri = f"ws://127.0.0.1:{self.port}?role=sender"
                async with websockets.connect(sender_uri, additional_headers=self.headers()) as sender:
                    await sender.recv()  # connected
                    await receiver.recv()  # system: sender joined

                    for i in range(RATE_MAX + 1):
                        await sender.send(json.dumps({"content": f"msg-{i}"}))

                    received = 0
                    deadline = time.monotonic() + 3.0
                    while time.monotonic() < deadline:
                        try:
                            msg = json.loads(
                                await asyncio.wait_for(receiver.recv(), timeout=0.3)
                            )
                        except asyncio.TimeoutError:
                            break
                        if msg.get("type") == "message" and msg.get("from") == "sender":
                            received += 1

                    self.assertEqual(received, RATE_MAX)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
