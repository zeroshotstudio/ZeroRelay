"""Tests for scripts/run-personal-adapter.sh (local + VPS driver)."""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run-personal-adapter.sh"


class RunPersonalAdapterScriptTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_help_explains_local_and_vps(self) -> None:
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("local", result.stdout)
        self.assertIn("vps", result.stdout)
        self.assertIn("my-vps-admin", result.stdout)

    def test_dry_run_local_prints_python_gateway(self) -> None:
        result = self.run_script("local", "--dry-run", "--mint")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("openai_gateway.py", result.stdout)
        self.assertIn("--mint", result.stdout)
        self.assertNotIn("ssh ", result.stdout)

    def test_dry_run_vps_uses_ssh_tunnel_and_claude(self) -> None:
        result = self.run_script("vps", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ssh", result.stdout)
        self.assertIn("my-vps-admin", result.stdout)
        self.assertIn("127.0.0.1:8767", result.stdout)
        self.assertIn("ZERORELAY_ADAPTER_PROVIDER=claude", result.stdout)
        self.assertIn("/opt/zerorelay/adapter", result.stdout)

    def test_dry_run_vps_honors_provider_and_host(self) -> None:
        result = self.run_script(
            "vps",
            "--dry-run",
            "--provider",
            "agy",
            "--host",
            "other-vps",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("other-vps", result.stdout)
        self.assertIn("ZERORELAY_ADAPTER_PROVIDER=agy", result.stdout)

    def test_local_serve_skips_when_health_already_ok(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", port), HealthHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            home = tempfile.mkdtemp(prefix="zerorelay-runner-")
            env = os.environ.copy()
            env["ZERORELAY_HOME"] = home
            result = subprocess.run(
                ["bash", str(SCRIPT), "local", "--serve", "--port", str(port)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env=env,
                timeout=8,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("already running", result.stdout)
            self.assertNotIn("--serve --host", result.stdout)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
