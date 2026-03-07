# Contributing to ZeroRelay

Thanks for your interest in contributing! ZeroRelay is a small, focused project and we welcome contributions of all kinds.

## Ways to Contribute

- **New bridges** — AI backends or chat platforms we don't support yet
- **Bug fixes** — found something broken? PRs welcome
- **Documentation** — typos, unclear instructions, missing examples
- **Tests** — more coverage is always good

## Getting Started

```bash
git clone https://github.com/zeroshotstudio/ZeroRelay.git
cd ZeroRelay
pip install websockets
python3 setup.py --check   # verify environment
```

## Development Setup

1. **Python 3.12+** required
2. Install core dependency: `pip install websockets`
3. Install optional deps for the bridges you're working on (see `requirements.txt`)
4. Run the relay locally: `python3 core/zerorelay.py --host 127.0.0.1`

## Project Structure

```
core/               # Relay broker + base bridge class
bridges/ai/         # AI backend bridges (one per model/provider)
bridges/chat/       # Chat interface bridges (Telegram, Discord, etc.)
services/           # systemd unit templates
```

## Writing a New Bridge

Subclass `AIBridge` from `core/base_bridge.py` and implement `_sync_generate()`:

```python
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.base_bridge import AIBridge

class MyBridge(AIBridge):
    def __init__(self, relay_url, **kw):
        super().__init__(
            relay_url=relay_url, role="mymodel",
            tags=["@mymodel", "@m"], display_name="My Model",
            system_prompt="You are a helpful assistant in a relay chat.", **kw)

    def _sync_generate(self, prompt, context):
        # Call your API here
        return "response text"

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--relay", default="ws://localhost:8765")
    asyncio.run(MyBridge(relay_url=p.parse_args().relay).run())
```

The base class handles WebSocket connection, reconnection, @-mention routing, transcript tracking, typing indicators, and loop prevention.

## Code Style

- Keep it minimal — no frameworks, no abstractions for single-use code
- Follow existing patterns in the codebase
- One file per bridge
- Use environment variables for all configuration
- Include a module docstring with required env vars

## Submitting Changes

1. Fork the repo and create a branch: `git checkout -b feature/my-bridge`
2. Make your changes
3. Test locally with the relay + CLI bridge
4. Submit a PR with a clear description of what and why

## Testing

Run the relay and connect a CLI client to verify your changes:

```bash
python3 core/zerorelay.py --host 127.0.0.1 &
python3 bridges/chat/cli.py --relay ws://127.0.0.1:8765 --role operator
```

CI runs syntax checks and relay integration tests on every PR.

## Reporting Issues

Open a GitHub issue with:
- What you expected vs what happened
- Steps to reproduce
- Python version and OS
- Relevant logs (bridge + relay output)

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
