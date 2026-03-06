# systemd Service Templates

Copy and customize for your deployment.

## Relay

```ini
# /etc/systemd/system/zerorelay.service
[Unit]
Description=ZeroRelay WebSocket Broker
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/zerorelay/core/zerorelay.py --host YOUR_TAILSCALE_IP --port 8765
WorkingDirectory=/opt/zerorelay
EnvironmentFile=-/opt/zerorelay/.env
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## AI Bridge (example: Claude)

```ini
# /etc/systemd/system/claude-bridge.service
[Unit]
Description=ZeroRelay Claude Bridge
After=zerorelay.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/zerorelay/bridges/ai/claude_code.py --relay ws://YOUR_TAILSCALE_IP:8765
WorkingDirectory=/opt/zerorelay
EnvironmentFile=-/opt/zerorelay/.env
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Chat Bridge (example: Telegram)

```ini
# /etc/systemd/system/telegram-bridge.service
[Unit]
Description=ZeroRelay Telegram Bridge
After=zerorelay.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/zerorelay/bridges/chat/telegram.py --relay ws://YOUR_TAILSCALE_IP:8765
WorkingDirectory=/opt/zerorelay
EnvironmentFile=-/opt/zerorelay/.env
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Deploy

```bash
cp *.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now zerorelay claude-bridge telegram-bridge
```
