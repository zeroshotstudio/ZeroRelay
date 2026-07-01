"""Authentication tests for ZeroRelay broker (header + deprecated query token)."""

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


class AuthSecurityTest(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        self.token = secrets.token_hex(16)
        self.env = os.environ.copy()
        self.env["RELAY_TOKEN"] = self.token
        self.env["ZERORELAY_ROLES"] = "alice,bob"
        self.tmpdir = tempfile.mkdtemp(prefix="zerorelay-auth-")
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

    def uri(self, role: str) -> str:
        return f"ws://127.0.0.1:{self.port}?role={role}"

    def test_bearer_header_auth(self):
        async def run():
            headers = {"Authorization": f"Bearer {self.token}"}
            async with websockets.connect(self.uri("alice"), additional_headers=headers) as ws:
                msg = json.loads(await ws.recv())
                self.assertEqual(msg["type"], "connected")
                self.assertEqual(msg["role"], "alice")

        asyncio.run(run())

    def test_x_relay_token_header_auth(self):
        async def run():
            headers = {"X-Relay-Token": self.token}
            async with websockets.connect(self.uri("alice"), additional_headers=headers) as ws:
                msg = json.loads(await ws.recv())
                self.assertEqual(msg["type"], "connected")

        asyncio.run(run())

    def test_query_string_token_deprecated_still_works(self):
        async def run():
            async with websockets.connect(f"{self.uri('alice')}&token={self.token}") as ws:
                msg = json.loads(await ws.recv())
                self.assertEqual(msg["type"], "connected")

        asyncio.run(run())

    def test_invalid_token_rejected(self):
        async def run():
            headers = {"Authorization": "Bearer wrong-token"}
            async with websockets.connect(self.uri("alice"), additional_headers=headers) as ws:
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await ws.recv()

        asyncio.run(run())

    def test_missing_token_rejected(self):
        async def run():
            async with websockets.connect(self.uri("alice")) as ws:
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await ws.recv()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
