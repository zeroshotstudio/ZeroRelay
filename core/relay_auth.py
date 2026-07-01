"""Shared relay authentication helpers for server and client bridges."""

from __future__ import annotations

import logging
import os
import secrets

log = logging.getLogger("relay_auth")


def relay_token() -> str:
    return os.environ.get("RELAY_TOKEN", "")


def relay_uri(relay_url: str, role: str) -> str:
    return f"{relay_url}?role={role}"


def relay_headers(token: str | None = None) -> dict[str, str]:
    token = relay_token() if token is None else token
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def extract_handshake_token(websocket, query: dict) -> tuple[str | None, bool]:
    """Return (token, used_deprecated_query_string)."""
    request = getattr(websocket, "request", None)
    headers = getattr(request, "headers", None)
    if headers:
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip(), False
        x_token = headers.get("X-Relay-Token")
        if x_token:
            return x_token.strip(), False

    token = query.get("token", [None])[0]
    return token, bool(token)


def token_is_valid(token: str | None, expected: str) -> bool:
    if not expected:
        return True
    if not token:
        return False
    return secrets.compare_digest(token, expected)
