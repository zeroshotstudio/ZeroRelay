"""Tests for the local AGY OpenAI-compatible gateway."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY = REPO_ROOT / "services" / "openai_gateway.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(host: str, port: int, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"gateway did not bind {host}:{port}")


class OpenAIGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="zerorelay-gw-"))
        self.port = free_port()
        self.key = "zr-test-secret-do-not-log"
        fake_agy = self.home / "fake-agy"
        fake_agy.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "prompt=''\n"
            "args=sys.argv[1:]\n"
            "for i,a in enumerate(args):\n"
            "    if a in ('-p','--print','--prompt') and i+1 < len(args):\n"
            "        prompt=args[i+1]\n"
            "        break\n"
            "print(prompt or 'FAKE_AGY_EMPTY')\n",
            encoding="utf-8",
        )
        fake_agy.chmod(0o755)
        env = os.environ.copy()
        env.update(
            {
                "ZERORELAY_HOME": str(self.home),
                "ZERORELAY_OPENAI_KEY": self.key,
                "ZERORELAY_OPENAI_HOST": "127.0.0.1",
                "ZERORELAY_OPENAI_PORT": str(self.port),
                "ZERORELAY_AGY_BIN": str(fake_agy),
                "ZERORELAY_AGY_CWD": str(self.home / "sandbox"),
                "ZERORELAY_AGY_TIMEOUT": "5",
            }
        )
        self.log = open(self.home / "gateway.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(GATEWAY), "--serve", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=REPO_ROOT,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_port("127.0.0.1", self.port)

    def tearDown(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.log.close()

    def request(self, method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {"content-type": "application/json"}
        if token is not None:
            headers["authorization"] = f"Bearer {token}"
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        conn.close()
        return res.status, json.loads(raw)

    def test_health_needs_no_key(self) -> None:
        status, payload = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_rejects_missing_bearer(self) -> None:
        status, payload = self.request(
            "POST",
            "/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        self.assertEqual(status, 401)
        self.assertIn("unauthorized", payload["error"]["message"])

    def test_chat_completions_calls_agy(self) -> None:
        status, payload = self.request(
            "POST",
            "/chat/completions",
            {"model": "operator", "messages": [{"role": "user", "content": "Diagnose lock file"}]},
            token=self.key,
        )
        self.assertEqual(status, 200)
        content = payload["choices"][0]["message"]["content"]
        self.assertIn("Diagnose lock file", content)
        self.assertNotIn(self.key, json.dumps(payload))

    def test_v1_path_also_works(self) -> None:
        status, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {"messages": [{"role": "user", "content": "ping"}]},
            token=self.key,
        )
        self.assertEqual(status, 200)
        self.assertIn("ping", payload["choices"][0]["message"]["content"])

    def test_v1_models_lists_agy(self) -> None:
        status, payload = self.request("GET", "/v1/models", token=self.key)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"][0]["id"], "agy")

    def test_v1_models_rejects_missing_bearer(self) -> None:
        status, payload = self.request("GET", "/v1/models")
        self.assertEqual(status, 401)
        self.assertIn("unauthorized", payload["error"]["message"])


class MintTest(unittest.TestCase):
    def test_mint_writes_env_and_prints_once(self) -> None:
        home = Path(tempfile.mkdtemp(prefix="zerorelay-mint-"))
        env = os.environ.copy()
        env["ZERORELAY_HOME"] = str(home)
        env.pop("ZERORELAY_OPENAI_KEY", None)
        env.pop("ZERORELAY_ADAPTER_PROVIDER", None)
        result = subprocess.run(
            [sys.executable, str(GATEWAY), "--mint"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        minted = json.loads(result.stdout)
        self.assertTrue(minted["base_url"].startswith("http://127.0.0.1:"))
        self.assertTrue(minted["key"].startswith("zr-"))
        env_path = Path(minted["env_file"])
        self.assertTrue(env_path.is_file())
        self.assertEqual(oct(env_path.stat().st_mode & 0o777), "0o600")
        self.assertIn("ZERORELAY_OPENAI_KEY=", env_path.read_text(encoding="utf-8"))
        self.assertIn("ZERORELAY_ADAPTER_PROVIDER=agy", env_path.read_text(encoding="utf-8"))


class ClaudeGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="zerorelay-gw-claude-"))
        self.port = free_port()
        self.key = "zr-test-secret-do-not-log"
        fake_claude = self.home / "fake-claude"
        fake_claude.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "print(sys.stdin.read().strip() or 'FAKE_CLAUDE_EMPTY')\n",
            encoding="utf-8",
        )
        fake_claude.chmod(0o755)
        env = os.environ.copy()
        env.update(
            {
                "ZERORELAY_HOME": str(self.home),
                "ZERORELAY_OPENAI_KEY": self.key,
                "ZERORELAY_OPENAI_HOST": "127.0.0.1",
                "ZERORELAY_OPENAI_PORT": str(self.port),
                "ZERORELAY_ADAPTER_PROVIDER": "claude",
                "ZERORELAY_CLAUDE_BIN": str(fake_claude),
                "ZERORELAY_CLAUDE_TIMEOUT": "5",
            }
        )
        self.log = open(self.home / "gateway.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(GATEWAY), "--serve", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=REPO_ROOT,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_port("127.0.0.1", self.port)

    def tearDown(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.log.close()

    def request(self, method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {"content-type": "application/json"}
        if token is not None:
            headers["authorization"] = f"Bearer {token}"
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        conn.close()
        return res.status, json.loads(raw)

    def test_chat_completions_calls_claude(self) -> None:
        status, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {"model": "claude", "messages": [{"role": "user", "content": "hello from adapter"}]},
            token=self.key,
        )
        self.assertEqual(status, 200)
        content = payload["choices"][0]["message"]["content"]
        self.assertIn("hello from adapter", content)
        self.assertNotIn(self.key, json.dumps(payload))

    def test_v1_models_lists_claude(self) -> None:
        status, payload = self.request("GET", "/v1/models", token=self.key)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"][0]["id"], "claude")


if __name__ == "__main__":
    unittest.main()
