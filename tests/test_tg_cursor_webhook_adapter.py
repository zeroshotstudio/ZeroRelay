"""Tests for the Telegram → Cursor webhook auth adapter."""

from __future__ import annotations

import importlib.util
import io
import logging
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "tg_cursor_webhook_adapter",
    REPO_ROOT / "tg-cursor-webhook-adapter.py",
)
assert _SPEC is not None and _SPEC.loader is not None
tg_cursor_webhook_adapter = importlib.util.module_from_spec(_SPEC)
sys.modules["tg_cursor_webhook_adapter"] = tg_cursor_webhook_adapter
_SPEC.loader.exec_module(tg_cursor_webhook_adapter)

AdapterConfig = tg_cursor_webhook_adapter.AdapterConfig
ConfigError = tg_cursor_webhook_adapter.ConfigError
TELEGRAM_SECRET_HEADER = tg_cursor_webhook_adapter.TELEGRAM_SECRET_HEADER
chat_id_allowed = tg_cursor_webhook_adapter.chat_id_allowed
extract_chat_id = tg_cursor_webhook_adapter.extract_chat_id
forward_to_cursor = tg_cursor_webhook_adapter.forward_to_cursor
load_config = tg_cursor_webhook_adapter.load_config
make_server = tg_cursor_webhook_adapter.make_server
secret_token_is_valid = tg_cursor_webhook_adapter.secret_token_is_valid

FAKE_BEARER = "crsr_test_bearer_not_real"
FAKE_SECRET = "tg-test-secret-token"
FAKE_URL = "http://127.0.0.1:9/automations/webhook/test"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def sample_config(**overrides: object) -> AdapterConfig:
    values: dict[str, object] = {
        "cursor_webhook_url": FAKE_URL,
        "cursor_webhook_bearer": FAKE_BEARER,
        "telegram_secret_token": FAKE_SECRET,
        "listen_host": "127.0.0.1",
        "listen_port": 0,
        "allowed_chat_ids": frozenset(),
        "upstream_timeout_sec": 2.0,
    }
    values.update(overrides)
    return AdapterConfig(**values)  # type: ignore[arg-type]


class SecretValidationTest(unittest.TestCase):
    def test_matching_secret_is_valid(self):
        self.assertTrue(secret_token_is_valid(FAKE_SECRET, FAKE_SECRET))

    def test_missing_header_is_rejected(self):
        self.assertFalse(secret_token_is_valid(None, FAKE_SECRET))

    def test_wrong_secret_is_rejected(self):
        self.assertFalse(secret_token_is_valid("nope", FAKE_SECRET))

    def test_empty_expected_is_rejected(self):
        self.assertFalse(secret_token_is_valid(FAKE_SECRET, ""))

    def test_wrong_length_is_rejected(self):
        self.assertFalse(secret_token_is_valid("short", FAKE_SECRET))


class ChatIdTest(unittest.TestCase):
    def test_extracts_message_chat_id(self):
        payload = {"update_id": 1, "message": {"chat": {"id": -100123}, "text": "hi"}}
        self.assertEqual(extract_chat_id(payload), -100123)

    def test_extracts_callback_chat_id(self):
        payload = {"callback_query": {"message": {"chat": {"id": 42}}}}
        self.assertEqual(extract_chat_id(payload), 42)

    def test_empty_allowlist_permits_any(self):
        self.assertTrue(chat_id_allowed(None, frozenset()))
        self.assertTrue(chat_id_allowed(1, frozenset()))

    def test_allowlist_rejects_unknown(self):
        self.assertFalse(chat_id_allowed(1, frozenset({2})))
        self.assertFalse(chat_id_allowed(None, frozenset({2})))
        self.assertTrue(chat_id_allowed(2, frozenset({2})))


class LoadConfigTest(unittest.TestCase):
    def test_requires_all_secrets(self):
        with self.assertRaises(ConfigError):
            load_config(
                {
                    "CURSOR_WEBHOOK_URL": FAKE_URL,
                    "CURSOR_WEBHOOK_BEARER": "",
                    "TELEGRAM_SECRET_TOKEN": FAKE_SECRET,
                }
            )


class MockUpstream(BaseHTTPRequestHandler):
    captured: list[dict] = []
    status: int = 202
    body: bytes = b'{"ok":true}'

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        type(self).captured.append(
            {
                "authorization": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
                "body": raw,
                "path": self.path,
            }
        )
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)


class AdapterHttpTest(unittest.TestCase):
    def setUp(self):
        self.upstream_port = free_port()
        MockUpstream.captured = []
        MockUpstream.status = 202
        MockUpstream.body = b'{"ok":true}'
        self.upstream = ThreadingHTTPServer(
            ("127.0.0.1", self.upstream_port), MockUpstream
        )
        self.upstream_thread = threading.Thread(
            target=self.upstream.serve_forever, daemon=True
        )
        self.upstream_thread.start()

        adapter_port = free_port()
        self.config = sample_config(
            cursor_webhook_url=f"http://127.0.0.1:{self.upstream_port}/webhook",
            listen_port=adapter_port,
        )
        self.adapter = make_server(self.config)
        self.adapter_thread = threading.Thread(
            target=self.adapter.serve_forever, daemon=True
        )
        self.adapter_thread.start()
        self.base = f"http://127.0.0.1:{adapter_port}"

    def tearDown(self):
        self.adapter.shutdown()
        self.adapter.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def _post(
        self,
        body: bytes,
        secret: str | None = FAKE_SECRET,
        path: str = "/",
    ):
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers[TELEGRAM_SECRET_HEADER] = secret
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            return urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            return exc

    def test_health_ok_without_secrets(self):
        with urllib.request.urlopen(self.base + "/health", timeout=3) as response:
            body = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(body, b"ok\n")
            self.assertNotIn(FAKE_BEARER.encode(), body)
            self.assertNotIn(FAKE_SECRET.encode(), body)

    def test_missing_secret_is_401_and_does_not_forward(self):
        err = self._post(b'{"update_id":1}', secret=None)
        self.assertIsInstance(err, urllib.error.HTTPError)
        self.assertEqual(err.code, 401)
        self.assertEqual(MockUpstream.captured, [])

    def test_wrong_secret_is_401_and_does_not_forward(self):
        err = self._post(b'{"update_id":1}', secret="wrong-token")
        self.assertIsInstance(err, urllib.error.HTTPError)
        self.assertEqual(err.code, 401)
        self.assertEqual(MockUpstream.captured, [])

    def test_forwards_raw_body_with_bearer_and_json_content_type(self):
        payload = b'{"update_id":99,"message":{"chat":{"id":1},"text":"wake"}}'
        response = self._post(payload)
        self.assertNotIsInstance(response, urllib.error.HTTPError)
        self.assertEqual(response.status, 202)
        self.assertEqual(response.read(), b'{"ok":true}')
        response.close()
        self.assertEqual(len(MockUpstream.captured), 1)
        captured = MockUpstream.captured[0]
        self.assertEqual(captured["authorization"], f"Bearer {FAKE_BEARER}")
        self.assertEqual(captured["content_type"], "application/json")
        self.assertEqual(captured["body"], payload)
        self.assertEqual(captured["path"], "/webhook")

    def test_returns_upstream_error_status(self):
        MockUpstream.status = 401
        MockUpstream.body = b'{"error":"unauthorized"}'
        err = self._post(b'{"update_id":2}')
        self.assertIsInstance(err, urllib.error.HTTPError)
        self.assertEqual(err.code, 401)
        self.assertEqual(err.read(), b'{"error":"unauthorized"}')

    def test_upstream_down_returns_502(self):
        dead_port = free_port()
        closed = sample_config(
            cursor_webhook_url=f"http://127.0.0.1:{dead_port}/missing",
            listen_port=free_port(),
        )
        server = make_server(closed)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{closed.listen_port}/",
                data=b'{"update_id":3}',
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    TELEGRAM_SECRET_HEADER: FAKE_SECRET,
                },
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(request, timeout=3)
            err = ctx.exception
            self.assertEqual(err.code, 502)
            self.assertEqual(err.read(), b"upstream failure\n")
            err.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_allowlist_rejects_other_chats(self):
        self.adapter.shutdown()
        self.adapter.server_close()
        port = free_port()
        self.config = sample_config(
            cursor_webhook_url=f"http://127.0.0.1:{self.upstream_port}/webhook",
            listen_port=port,
            allowed_chat_ids=frozenset({111}),
        )
        self.adapter = make_server(self.config)
        self.adapter_thread = threading.Thread(
            target=self.adapter.serve_forever, daemon=True
        )
        self.adapter_thread.start()
        self.base = f"http://127.0.0.1:{port}"
        err = self._post(b'{"message":{"chat":{"id":222},"text":"nope"}}')
        self.assertIsInstance(err, urllib.error.HTTPError)
        self.assertEqual(err.code, 403)
        self.assertEqual(MockUpstream.captured, [])

    def test_logs_do_not_contain_secrets(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        logger = logging.getLogger("tg-cursor-webhook-adapter")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            response = self._post(b'{"update_id":4}')
            if not isinstance(response, urllib.error.HTTPError):
                response.close()
        finally:
            logger.removeHandler(handler)
        text = buf.getvalue()
        self.assertNotIn(FAKE_BEARER, text)
        self.assertNotIn(FAKE_SECRET, text)


class ForwardHeadersUnitTest(unittest.TestCase):
    def test_forward_sets_authorization_bearer(self):
        captured: dict[str, object] = {}

        class DummyResponse:
            status = 204

            def read(self) -> bytes:
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def fake_urlopen(request: urllib.request.Request, timeout: float = 0):
            captured["url"] = request.full_url
            captured["data"] = request.data
            captured["timeout"] = timeout
            captured["authorization"] = request.get_header("Authorization")
            captured["content_type"] = request.get_header("Content-type")
            return DummyResponse()

        body = b'{"update_id":5}'
        with patch("tg_cursor_webhook_adapter.urllib.request.urlopen", fake_urlopen):
            status, resp_body, local_failure = forward_to_cursor(body, sample_config())
        self.assertEqual(status, 204)
        self.assertEqual(resp_body, b"")
        self.assertFalse(local_failure)
        self.assertEqual(captured["authorization"], f"Bearer {FAKE_BEARER}")
        self.assertEqual(captured["content_type"], "application/json")
        self.assertEqual(captured["data"], body)
        self.assertEqual(captured["url"], FAKE_URL)
        self.assertEqual(captured["timeout"], 2.0)


if __name__ == "__main__":
    unittest.main()
