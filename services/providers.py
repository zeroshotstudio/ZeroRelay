"""Personal Adapter completion providers.

Official CLIs only. One provider is active per gateway process.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

DEFAULT_AGY_TIMEOUT_SEC = 120
DEFAULT_CLAUDE_TIMEOUT_SEC = 120
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_SESSION_IDLE_RESET_SEC = 1800
DEFAULT_AGY_PREAMBLE = (
    "You are the Operator OS worker brain. Diagnose and propose. "
    "Do not edit git or the working tree. Keep the answer usable as a next action."
)
DEFAULT_HOME = Path.home() / ".zerorelay"


def config_dir() -> Path:
    override = os.environ.get("ZERORELAY_HOME")
    return Path(override) if override else DEFAULT_HOME


class CompletionProvider(Protocol):
    name: str

    def generate(self, messages: list[dict[str, Any]], model: str) -> str: ...


def messages_to_prompt(
    messages: list[dict[str, Any]],
    preamble: str = "",
) -> str:
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        if content:
            parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def agy_preamble() -> str:
    if "ZERORELAY_SYSTEM_PREAMBLE" in os.environ:
        return os.environ.get("ZERORELAY_SYSTEM_PREAMBLE", "")
    return DEFAULT_AGY_PREAMBLE


class AgyProvider:
    name = "agy"

    def generate(self, messages: list[dict[str, Any]], model: str) -> str:
        prompt = messages_to_prompt(messages, preamble=agy_preamble())
        return call_agy(prompt)


def call_agy(prompt: str) -> str:
    binary = os.environ.get("ZERORELAY_AGY_BIN") or "agy"
    cwd = os.environ.get("ZERORELAY_AGY_CWD") or str(config_dir() / "agy-brain-sandbox")
    Path(cwd).mkdir(mode=0o700, parents=True, exist_ok=True)
    timeout = int(os.environ.get("ZERORELAY_AGY_TIMEOUT", str(DEFAULT_AGY_TIMEOUT_SEC)))
    cmd = [
        binary,
        "--sandbox",
        "--disable-slash-commands",
        "--output-format",
        "text",
        "--print-timeout",
        f"{timeout}s",
        "-p",
        prompt,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout + 15,
        cwd=cwd,
        check=False,
    )
    text = (result.stdout or "").strip()
    if result.returncode != 0 and not text:
        err = (result.stderr or "agy failed").strip()
        raise RuntimeError(err.splitlines()[-1][:500])
    if not text:
        raise RuntimeError("agy returned empty response")
    return text


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


class ClaudeCodeProvider:
    name = "claude"

    def __init__(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.session_established = False
        self.last_activity = datetime.now()

    def _session_enabled(self) -> bool:
        return _truthy(os.environ.get("ZERORELAY_CLAUDE_SESSION"))

    def _preamble(self) -> str:
        return os.environ.get("ZERORELAY_SYSTEM_PREAMBLE", "")

    def _check_idle_reset(self) -> None:
        if not self._session_enabled():
            return
        idle = (datetime.now() - self.last_activity).total_seconds()
        if idle > CLAUDE_SESSION_IDLE_RESET_SEC:
            self.session_id = str(uuid.uuid4())
            self.session_established = False

    def generate(self, messages: list[dict[str, Any]], model: str, *, _retry: int = 0) -> str:
        if not self._session_enabled():
            self.session_id = str(uuid.uuid4())
            self.session_established = False
        else:
            self._check_idle_reset()
        self.last_activity = datetime.now()

        prompt = messages_to_prompt(messages, preamble=self._preamble())
        binary = os.environ.get("ZERORELAY_CLAUDE_BIN") or "claude"
        timeout = int(os.environ.get("ZERORELAY_CLAUDE_TIMEOUT", str(DEFAULT_CLAUDE_TIMEOUT_SEC)))
        claude_model = os.environ.get("ZERORELAY_CLAUDE_MODEL") or model or DEFAULT_CLAUDE_MODEL
        use_resume = self._session_enabled() and self.session_established
        mode = "--resume" if use_resume else "--session-id"
        cmd = [binary, "-p", "--model", claude_model, mode, self.session_id]
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        text = (result.stdout or "").strip()
        if result.returncode != 0 and not text:
            err = (result.stderr or "claude failed").strip()
            if "already in use" in err and _retry < 5:
                self.session_id = str(uuid.uuid4())
                self.session_established = False
                return self.generate(messages, model, _retry=_retry + 1)
            raise RuntimeError(err.splitlines()[-1][:500] if err else "claude failed")
        if not text:
            raise RuntimeError("claude returned empty response")
        self.session_established = True
        return text


_PROVIDERS = {
    "agy": AgyProvider,
    "claude": ClaudeCodeProvider,
}


def get_provider(name: str | None = None) -> CompletionProvider:
    chosen = (name or os.environ.get("ZERORELAY_ADAPTER_PROVIDER") or "agy").strip().lower()
    factory = _PROVIDERS.get(chosen)
    if factory is None:
        raise ValueError(f"unknown adapter provider: {chosen}")
    return factory()

