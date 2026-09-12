"""Unit tests for Personal Adapter completion providers."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES = REPO_ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from providers import (  # noqa: E402
    AgyProvider,
    ClaudeCodeProvider,
    get_provider,
    messages_to_prompt,
)


def _fake_agy(home: Path) -> Path:
    binary = home / "fake-agy"
    binary.write_text(
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
    binary.chmod(0o755)
    return binary


class GetProviderTest(unittest.TestCase):
    def test_agy_is_default_provider(self) -> None:
        provider = get_provider("agy")
        self.assertEqual(provider.name, "agy")
        self.assertTrue(callable(provider.generate))

    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            get_provider("not-a-backend")
        self.assertIn("not-a-backend", str(ctx.exception))

    def test_claude_provider(self) -> None:
        provider = get_provider("claude")
        self.assertEqual(provider.name, "claude")
        self.assertIsInstance(provider, ClaudeCodeProvider)


class MessagesToPromptTest(unittest.TestCase):
    def test_includes_preamble_and_roles(self) -> None:
        prompt = messages_to_prompt(
            [{"role": "user", "content": "hello"}],
            preamble="PREAMBLE",
        )
        self.assertIn("PREAMBLE", prompt)
        self.assertIn("user: hello", prompt)

    def test_skips_empty_preamble(self) -> None:
        prompt = messages_to_prompt(
            [{"role": "user", "content": "hello"}],
            preamble="",
        )
        self.assertEqual(prompt, "user: hello")


class AgyProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="zerorelay-agy-"))
        self.binary = _fake_agy(self.home)
        self._old = {
            key: os.environ.get(key)
            for key in (
                "ZERORELAY_HOME",
                "ZERORELAY_AGY_BIN",
                "ZERORELAY_AGY_CWD",
                "ZERORELAY_AGY_TIMEOUT",
                "ZERORELAY_SYSTEM_PREAMBLE",
            )
        }
        os.environ["ZERORELAY_HOME"] = str(self.home)
        os.environ["ZERORELAY_AGY_BIN"] = str(self.binary)
        os.environ["ZERORELAY_AGY_CWD"] = str(self.home / "sandbox")
        os.environ["ZERORELAY_AGY_TIMEOUT"] = "5"
        os.environ.pop("ZERORELAY_SYSTEM_PREAMBLE", None)

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_generate_echoes_user_content_with_default_preamble(self) -> None:
        content = AgyProvider().generate(
            [{"role": "user", "content": "Diagnose lock file"}],
            "agy",
        )
        self.assertIn("Diagnose lock file", content)
        self.assertIn("Operator OS worker brain", content)

    def test_empty_preamble_env_disables_operator_prompt(self) -> None:
        os.environ["ZERORELAY_SYSTEM_PREAMBLE"] = ""
        content = AgyProvider().generate(
            [{"role": "user", "content": "Diagnose lock file"}],
            "agy",
        )
        self.assertIn("Diagnose lock file", content)
        self.assertNotIn("Operator OS worker brain", content)


def _fake_claude(home: Path, *, fail_first: bool = False) -> Path:
    binary = home / "fake-claude"
    log = home / "claude-argv.json"
    body = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "entries = json.loads(log.read_text()) if log.exists() else []\n"
        "stdin = sys.stdin.read()\n"
        "entries.append({'argv': sys.argv[1:], 'stdin': stdin})\n"
        "log.write_text(json.dumps(entries))\n"
    )
    if fail_first:
        body += (
            "if len(entries) == 1:\n"
            "    print('session already in use', file=sys.stderr)\n"
            "    sys.exit(1)\n"
        )
    body += "print(stdin.strip() or 'ok')\n"
    binary.write_text(body, encoding="utf-8")
    binary.chmod(0o755)
    return binary


class ClaudeCodeProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="zerorelay-claude-"))
        self.log = self.home / "claude-argv.json"
        self.binary = _fake_claude(self.home)
        self._old = {
            key: os.environ.get(key)
            for key in (
                "ZERORELAY_CLAUDE_BIN",
                "ZERORELAY_CLAUDE_TIMEOUT",
                "ZERORELAY_CLAUDE_MODEL",
                "ZERORELAY_CLAUDE_SESSION",
                "ZERORELAY_SYSTEM_PREAMBLE",
            )
        }
        os.environ["ZERORELAY_CLAUDE_BIN"] = str(self.binary)
        os.environ["ZERORELAY_CLAUDE_TIMEOUT"] = "5"
        os.environ["ZERORELAY_CLAUDE_MODEL"] = "claude-sonnet-4-20250514"
        os.environ.pop("ZERORELAY_CLAUDE_SESSION", None)
        os.environ.pop("ZERORELAY_SYSTEM_PREAMBLE", None)

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _calls(self) -> list[dict]:
        return json.loads(self.log.read_text(encoding="utf-8"))

    def test_stateless_generate_uses_session_id_and_stdin(self) -> None:
        content = ClaudeCodeProvider().generate(
            [{"role": "user", "content": "ping claude"}],
            "claude",
        )
        self.assertIn("user: ping claude", content)
        self.assertNotIn("Operator OS worker brain", content)
        argv = self._calls()[0]["argv"]
        self.assertIn("-p", argv)
        self.assertIn("--session-id", argv)
        self.assertNotIn("--resume", argv)

    def test_session_mode_resumes_on_second_call(self) -> None:
        os.environ["ZERORELAY_CLAUDE_SESSION"] = "1"
        provider = ClaudeCodeProvider()
        provider.generate([{"role": "user", "content": "first"}], "claude")
        provider.generate([{"role": "user", "content": "second"}], "claude")
        calls = self._calls()
        self.assertIn("--session-id", calls[0]["argv"])
        self.assertIn("--resume", calls[1]["argv"])
        self.assertNotIn("--session-id", calls[1]["argv"])

    def test_already_in_use_rotates_session(self) -> None:
        self.binary = _fake_claude(self.home, fail_first=True)
        os.environ["ZERORELAY_CLAUDE_BIN"] = str(self.binary)
        os.environ["ZERORELAY_CLAUDE_SESSION"] = "1"
        content = ClaudeCodeProvider().generate(
            [{"role": "user", "content": "retry me"}],
            "claude",
        )
        self.assertIn("user: retry me", content)
        self.assertGreaterEqual(len(self._calls()), 2)


if __name__ == "__main__":
    unittest.main()

