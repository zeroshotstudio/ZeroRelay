# ZeroRelay OpenAI gateway (macOS)

LaunchAgent for the local Personal Adapter. Loopback only (`127.0.0.1:8767`).

1. Confirm the plist `ProgramArguments` path matches this checkout.
2. `mkdir -p "$HOME/Library/Logs/zerorelay"`
3. Copy the plist into `~/Library/LaunchAgents/` and `launchctl load` it.

See [docs/personal-adapter.md](../../docs/personal-adapter.md).
