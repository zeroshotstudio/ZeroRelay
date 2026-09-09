#!/usr/bin/env python3
"""Telegram → Cursor webhook auth adapter.

Telegram Bot API can POST updates to an HTTPS URL and optionally send
``X-Telegram-Bot-Api-Secret-Token``. Cursor automation webhooks require
``Authorization: Bearer <crsr_…>``, which Telegram cannot set. This process
accepts Telegram on localhost and re-POSTs the same JSON body to Cursor
with the Bearer key.

Public TLS is Tailscale Funnel on vps-zee (same pattern as Hektor Operator
Funnel). This service binds localhost only (default ``127.0.0.1:8787``);
it is not an internet-facing HTTPS server.

Config via environment or ``/opt/zerorelay/tg-cursor-adapter.env`` (mode 600):

  CURSOR_WEBHOOK_URL       Cursor automation webhook URL
  CURSOR_WEBHOOK_BEARER    Panel sender key (never logged)
  TELEGRAM_SECRET_TOKEN    setWebhook ``secret_token=`` value
  LISTEN_HOST              Bind address (default 127.0.0.1)
  LISTEN_PORT              Bind port (default 8787)
  ALLOWED_CHAT_IDS         Optional comma-separated Telegram chat IDs
  UPSTREAM_TIMEOUT_SEC     Cursor POST timeout in seconds (default 10)
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple

log = logging.getLogger("tg-cursor-webhook-adapter")

ENV_FILE = "/opt/zerorelay/tg-cursor-adapter.env"
TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
MAX_BODY_BYTES = 1_048_576
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_TIMEOUT = 10.0
HEALTH_BODY = b"ok\n"

_CHAT_KEYS = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "business_message",
    "edited_business_message",
)


class AdapterConfig(NamedTuple):
    cursor_webhook_url: str
    cursor_webhook_bearer: str
    telegram_secret_token: str
    listen_host: str
    listen_port: int
    allowed_chat_ids: frozenset[int]
    upstream_timeout_sec: float


class ConfigError(ValueError):
    """Raised when required adapter env is missing or invalid."""


def load_env_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def parse_allowed_chat_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.add(int(part))
    return frozenset(ids)


def load_config(environ: dict[str, str] | None = None) -> AdapterConfig:
    env = os.environ if environ is None else environ
    url = env.get("CURSOR_WEBHOOK_URL", "").strip()
    bearer = env.get("CURSOR_WEBHOOK_BEARER", "").strip()
    secret = env.get("TELEGRAM_SECRET_TOKEN", "").strip()
    if not url or not bearer or not secret:
        raise ConfigError(
            "Missing required config: CURSOR_WEBHOOK_URL, "
            "CURSOR_WEBHOOK_BEARER, TELEGRAM_SECRET_TOKEN"
        )
    host = env.get("LISTEN_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    try:
        port = int(env.get("LISTEN_PORT", str(DEFAULT_PORT)))
    except ValueError as exc:
        raise ConfigError("LISTEN_PORT must be an integer") from exc
    try:
        allowed = parse_allowed_chat_ids(env.get("ALLOWED_CHAT_IDS", ""))
    except ValueError as exc:
        raise ConfigError("ALLOWED_CHAT_IDS must be comma-separated integers") from exc
    try:
        timeout = float(env.get("UPSTREAM_TIMEOUT_SEC", str(DEFAULT_TIMEOUT)))
    except ValueError as exc:
        raise ConfigError("UPSTREAM_TIMEOUT_SEC must be a number") from exc
    if timeout <= 0:
        raise ConfigError("UPSTREAM_TIMEOUT_SEC must be positive")
    return AdapterConfig(
        cursor_webhook_url=url,
        cursor_webhook_bearer=bearer,
        telegram_secret_token=secret,
        listen_host=host,
        listen_port=port,
        allowed_chat_ids=allowed,
        upstream_timeout_sec=timeout,
    )


def secret_token_is_valid(provided: str | None, expected: str) -> bool:
    if not expected or provided is None:
        return False
    return secrets.compare_digest(provided, expected)


def _chat_id_from_mapping(mapping: object) -> int | None:
    if not isinstance(mapping, dict):
        return None
    chat = mapping.get("chat")
    if not isinstance(chat, dict) or "id" not in chat:
        return None
    try:
        return int(chat["id"])
    except (TypeError, ValueError):
        return None


def extract_chat_id(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in _CHAT_KEYS:
        chat_id = _chat_id_from_mapping(payload.get(key))
        if chat_id is not None:
            return chat_id
    callback = payload.get("callback_query")
    if isinstance(callback, dict):
        chat_id = _chat_id_from_mapping(callback.get("message"))
        if chat_id is not None:
            return chat_id
    return None


def chat_id_allowed(chat_id: int | None, allowed: frozenset[int]) -> bool:
    if not allowed:
        return True
    return chat_id is not None and chat_id in allowed


def forward_to_cursor(body: bytes, config: AdapterConfig) -> tuple[int, bytes, bool]:
    """POST raw body to Cursor. Returns (status, body, local_failure)."""
    request = urllib.request.Request(
        config.cursor_webhook_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.cursor_webhook_bearer}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=config.upstream_timeout_sec
        ) as response:
            return response.status, response.read(), False
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), False
    except (urllib.error.URLError, TimeoutError, OSError):
        log.warning("cursor webhook upstream failure")
        return 502, b"upstream failure\n", True


class WebhookHandler(BaseHTTPRequestHandler):
    config: AdapterConfig
    server_version = "tg-cursor-webhook-adapter/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Request-line only. Do not dump headers (secret token lives there).
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        if self._route() != "/health":
            self._send(404, b"not found\n")
            return
        self._send(200, HEALTH_BODY)

    def do_POST(self) -> None:
        if self._route() != "/":
            self._send(404, b"not found\n")
            return
        provided = self.headers.get(TELEGRAM_SECRET_HEADER)
        if not secret_token_is_valid(provided, self.config.telegram_secret_token):
            self._send(401, b"unauthorized\n")
            return
        length = self._content_length()
        if length is None:
            self._send(400, b"missing content-length\n")
            return
        if length > MAX_BODY_BYTES:
            self._send(413, b"payload too large\n")
            return
        body = self.rfile.read(length)
        if self.config.allowed_chat_ids:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, b"invalid json\n")
                return
            chat_id = extract_chat_id(payload)
            if not chat_id_allowed(chat_id, self.config.allowed_chat_ids):
                self._send(403, b"forbidden\n")
                return
        status, upstream_body, local_failure = forward_to_cursor(body, self.config)
        content_type = (
            "text/plain; charset=utf-8" if local_failure else "application/json"
        )
        self._send(status, upstream_body, content_type)

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    def _content_length(self) -> int | None:
        raw = self.headers.get("Content-Length")
        if raw is None:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        if value < 0:
            return None
        return value

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(config: AdapterConfig) -> ThreadingHTTPServer:
    class BoundWebhookHandler(WebhookHandler):
        pass

    BoundWebhookHandler.config = config
    return ThreadingHTTPServer((config.listen_host, config.listen_port), BoundWebhookHandler)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    env_file = os.environ.get("TG_CURSOR_ADAPTER_ENV_FILE", ENV_FILE)
    load_env_file(env_file)
    try:
        config = load_config()
    except ConfigError as exc:
        log.error("%s", exc)
        raise SystemExit(1) from exc
    log.info(
        "listening on %s:%s (localhost bind; TLS terminates at Tailscale Funnel)",
        config.listen_host,
        config.listen_port,
    )
    server = make_server(config)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
