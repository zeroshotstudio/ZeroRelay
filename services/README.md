# systemd Service Templates

Copy and customize. For hardened deployment, create a dedicated user:

```bash
# Create service user (recommended)
useradd -r -s /usr/sbin/nologin -d /opt/zerorelay zerorelay
usermod -aG docker zerorelay  # if using OpenClaw/Docker bridges
chown -R zerorelay:zerorelay /opt/zerorelay/
chmod 700 /opt/zerorelay/
chmod 600 /opt/zerorelay/.env

# Sudoers for Telegram bridge service management
cat > /etc/sudoers.d/zerorelay << 'EOF'
zerorelay ALL=(root) NOPASSWD: /usr/bin/systemctl stop zerorelay-*, /usr/bin/systemctl start zerorelay-*, /usr/bin/systemctl is-active zerorelay-*
EOF
```

## Relay

```ini
# /etc/systemd/system/zerorelay.service
[Unit]
Description=ZeroRelay WebSocket Broker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=zerorelay
Group=zerorelay
ExecStart=/usr/bin/python3 /opt/zerorelay/core/zerorelay.py --host YOUR_BIND_IP --port 8765
WorkingDirectory=/opt/zerorelay
EnvironmentFile=/opt/zerorelay/.env
Restart=on-failure
RestartSec=3
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadWritePaths=/opt/zerorelay

[Install]
WantedBy=multi-user.target
```

## AI Bridge (example: Claude)

```ini
# /etc/systemd/system/zerorelay-claude.service
[Unit]
Description=ZeroRelay Claude Bridge
After=zerorelay.service

[Service]
Type=simple
User=zerorelay
Group=zerorelay
ExecStart=/usr/bin/python3 /opt/zerorelay/bridges/ai/anthropic_api.py --relay ws://YOUR_BIND_IP:8765
WorkingDirectory=/opt/zerorelay
EnvironmentFile=/opt/zerorelay/.env
Restart=on-failure
RestartSec=5
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadWritePaths=/opt/zerorelay

[Install]
WantedBy=multi-user.target
```

## Chat Bridge (example: Telegram)

```ini
# /etc/systemd/system/zerorelay-telegram.service
[Unit]
Description=ZeroRelay Telegram Bridge
After=zerorelay.service

[Service]
Type=simple
User=zerorelay
Group=zerorelay
ExecStart=/usr/bin/python3 /opt/zerorelay/bridges/chat/telegram.py --relay ws://YOUR_BIND_IP:8765
WorkingDirectory=/opt/zerorelay
EnvironmentFile=/opt/zerorelay/.env
Restart=on-failure
RestartSec=5
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadWritePaths=/opt/zerorelay

[Install]
WantedBy=multi-user.target
```

## Deploy

```bash
cp *.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now zerorelay zerorelay-claude zerorelay-telegram
```
