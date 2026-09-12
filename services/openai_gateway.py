#!/usr/bin/env python3
"""ZeroRelay OpenAI-compatible Personal Adapter gateway.

Mints a local `zr-` key and serves `POST /chat/completions` on 127.0.0.1
so OpenAI-compatible tools can use an already-logged-in official CLI.

Bind 127.0.0.1 only. Key never logged.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from providers import get_provider

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
DEFAULT_HOME = Path.home() / ".zerorelay"
ENV_FILE_NAME = "openai-gateway.env"
PID_FILE = Path("/tmp/zerorelay-openai-gateway.pid")

_active_provider = None


def config_dir() -> Path:
    override = os.environ.get("ZERORELAY_HOME")
    return Path(override) if override else DEFAULT_HOME


def env_file() -> Path:
    return config_dir() / ENV_FILE_NAME


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    body = "\n".join(f"{k}={v}" for k, v in values.items()) + "\n"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)


def minted_key() -> str:
    existing = os.environ.get("ZERORELAY_OPENAI_KEY", "").strip()
    if existing:
        return existing
    return "zr-" + secrets.token_urlsafe(32)


def adapter_provider_name() -> str:
    return (os.environ.get("ZERORELAY_ADAPTER_PROVIDER") or "agy").strip().lower()


def active_provider():
    global _active_provider
    if _active_provider is None:
        _active_provider = get_provider(adapter_provider_name())
    return _active_provider


def completion_payload(content: str, model: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-zerorelay",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def write_pid() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid() -> None:
    try:
        if PID_FILE.is_file() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        pass


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "ZeroRelayOpenAI/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = os.environ.get("ZERORELAY_OPENAI_KEY", "")
        if not expected:
            return False
        header = self.headers.get("authorization") or ""
        if not header.lower().startswith("bearer "):
            return False
        return header[7:].strip() == expected

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/health", "/v1/health"):
            self._send(200, {"status": "ok", "service": "zerorelay-openai-gateway"})
            return
        if path in ("/models", "/v1/models"):
            if not self._authorized():
                self._send(401, {"error": {"message": "unauthorized", "type": "invalid_request_error"}})
                return
            provider = active_provider()
            self._send(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": provider.name,
                            "object": "model",
                            "owned_by": "zerorelay",
                        }
                    ],
                },
            )
            return
        self._send(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/chat/completions", "/v1/chat/completions"):
            self._send(404, {"error": {"message": "not found", "type": "invalid_request_error"}})
            return
        if not self._authorized():
            self._send(401, {"error": {"message": "unauthorized", "type": "invalid_request_error"}})
            return
        length = int(self.headers.get("content-length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": {"message": "invalid json", "type": "invalid_request_error"}})
            return
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            self._send(400, {"error": {"message": "messages required", "type": "invalid_request_error"}})
            return
        provider = active_provider()
        model = str(body.get("model") or provider.name)
        try:
            content = provider.generate(messages, model)
        except subprocess.TimeoutExpired:
            self._send(504, {"error": {"message": f"{provider.name} timed out", "type": "api_error"}})
            return
        except FileNotFoundError:
            self._send(502, {"error": {"message": f"{provider.name} not installed", "type": "api_error"}})
            return
        except Exception as exc:
            self._send(502, {"error": {"message": str(exc), "type": "api_error"}})
            return
        self._send(200, completion_payload(content, model))


def serve(host: str, port: int) -> None:
    write_pid()
    httpd = ThreadingHTTPServer((host, port), GatewayHandler)

    def shutdown(*_args: Any) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"zerorelay openai gateway http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        clear_pid()


def mint() -> dict[str, str]:
    load_env_file(env_file())
    host = os.environ.get("ZERORELAY_OPENAI_HOST", DEFAULT_HOST)
    port = str(int(os.environ.get("ZERORELAY_OPENAI_PORT", str(DEFAULT_PORT))))
    key = minted_key()
    provider = adapter_provider_name()
    write_env_file(
        env_file(),
        {
            "ZERORELAY_OPENAI_HOST": host,
            "ZERORELAY_OPENAI_PORT": port,
            "ZERORELAY_OPENAI_KEY": key,
            "ZERORELAY_ADAPTER_PROVIDER": provider,
        },
    )
    os.environ["ZERORELAY_OPENAI_KEY"] = key
    os.environ["ZERORELAY_ADAPTER_PROVIDER"] = provider
    base_url = f"http://{host}:{port}"
    return {"base_url": base_url, "key": key, "env_file": str(env_file())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ZeroRelay OpenAI-compatible Personal Adapter")
    parser.add_argument("--mint", action="store_true", help="mint base_url + key and write ~/.zerorelay/openai-gateway.env")
    parser.add_argument("--serve", action="store_true", help="run the HTTP gateway")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    load_env_file(env_file())
    if args.mint or not args.serve:
        minted = mint()
        print(json.dumps(minted))
        if not args.serve and args.mint:
            return 0
        if not args.serve:
            return 0

    host = args.host or os.environ.get("ZERORELAY_OPENAI_HOST", DEFAULT_HOST)
    port = args.port or int(os.environ.get("ZERORELAY_OPENAI_PORT", str(DEFAULT_PORT)))
    if not os.environ.get("ZERORELAY_OPENAI_KEY"):
        mint()
    serve(host, port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
