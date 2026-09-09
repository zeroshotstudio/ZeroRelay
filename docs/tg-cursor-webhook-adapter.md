# Telegram → Cursor webhook adapter

Thin localhost adapter for GrowthLabs near-realtime Telegram wakes into a Cursor automation webhook.

Telegram Bot API `setWebhook` can POST JSON to an HTTPS URL and optionally send `X-Telegram-Bot-Api-Secret-Token`. Cursor’s automation webhook requires `Authorization: Bearer <crsr_…>` (panel sender key). Telegram cannot send Bearer, so a direct `setWebhook` to Cursor fails with `getWebhookInfo last_error=401 Unauthorized`.

This service sits on the ZeroRelay VPS next to the production stack (`/opt/zerorelay`). Telegram `setWebhook`s to **our** public HTTPS URL. Funnel/nginx terminates TLS and proxies to localhost. The adapter validates Telegram’s secret header and re-POSTs the same JSON body to Cursor with Bearer.

```
Telegram Bot API
    POST https://<public-host>/
    X-Telegram-Bot-Api-Secret-Token: <secret>
        │
        ▼
Funnel / nginx  (public TLS)
        │  proxy_pass http://127.0.0.1:8787
        ▼
tg-cursor-webhook-adapter  (127.0.0.1:8787 only)
        │  Authorization: Bearer <crsr_…>
        │  Content-Type: application/json
        ▼
Cursor automation webhook
```

This adapter does **not** join the ZeroRelay WebSocket mesh and does **not** change `telegram-bridge` polling.

## Localhost bind — TLS is elsewhere

The unit listens on `127.0.0.1:8787` by default. It is **not** an HTTPS server.

Public HTTPS must terminate at Funnel, nginx, Caddy, or equivalent, then proxy to `http://127.0.0.1:8787`. Do not bind `0.0.0.0` unless you know why.

Forward the Telegram secret header through the proxy (nginx forwards it by default; still pin it explicitly):

```nginx
server {
    listen 443 ssl;
    server_name <PUBLIC_HOST>;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;
        proxy_pass_request_body on;
    }
}
```

Health checks can hit `http://127.0.0.1:8787/health` on the VPS (no secret, no Bearer).

## Generate `secret_token`

Telegram allows 1–256 chars: `A-Z`, `a-z`, `0-9`, `_`, `-`.

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep the value only in the env file and in the `setWebhook` call. Do not commit it.

## Env file

On the VPS:

```bash
sudo install -m 600 /dev/null /opt/zerorelay/tg-cursor-adapter.env
sudo chown zerorelay:zerorelay /opt/zerorelay/tg-cursor-adapter.env
sudoedit /opt/zerorelay/tg-cursor-adapter.env
```

Use placeholders — never paste real keys into docs, tickets, or git:

```
CURSOR_WEBHOOK_URL=https://api2.cursor.sh/automations/webhook/<uuid>
CURSOR_WEBHOOK_BEARER=crsr_<panel-sender-key>
TELEGRAM_SECRET_TOKEN=<random-secret>
LISTEN_HOST=127.0.0.1
LISTEN_PORT=8787
```

Optional:

```
ALLOWED_CHAT_IDS=<chat-id>
UPSTREAM_TIMEOUT_SEC=10
```

Repo template: `tg-cursor-adapter.env.example`. The live env file is **not** deployed from git; `./scripts/deploy-vps.sh` preserves it the same way as `telegram.env`.

`CURSOR_WEBHOOK_BEARER` is the Cursor panel sender key. The adapter never logs or prints it.

## systemd

After the env file exists:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tg-cursor-webhook-adapter
sudo systemctl is-active tg-cursor-webhook-adapter
curl -fsS http://127.0.0.1:8787/health
```

Subsequent `./scripts/deploy-vps.sh` installs the unit and Python file, leaves `tg-cursor-adapter.env` in place, and restarts the adapter when that env file exists.

## setWebhook

Replace placeholders only. Do not put real bot tokens in the repo, shell history snippets, or tickets.

```bash
curl -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  --data-urlencode "url=https://<PUBLIC_HOST>/" \
  --data-urlencode "secret_token=<TELEGRAM_SECRET_TOKEN>"
```

`url` must be the public HTTPS URL that Funnel/nginx proxies to this adapter (`POST /`). `secret_token` must match `TELEGRAM_SECRET_TOKEN` in the env file.

## Verify

```bash
curl -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

Expect `url` set to the public HTTPS endpoint, `has_custom_certificate` as configured, and `last_error_message` / `last_error_date` empty (or absent). A pending `last_error` of `401 Unauthorized` means Bearer never reached Cursor — usually the adapter is down, the proxy is not hitting `127.0.0.1:8787`, or `CURSOR_WEBHOOK_BEARER` is wrong.

On the VPS:

```bash
journalctl -u tg-cursor-webhook-adapter -n 50 --no-pager
curl -fsS http://127.0.0.1:8787/health
```

Send a Telegram message to the bot. The adapter should return Cursor’s HTTP status (or `502` if Cursor is unreachable). Journals must not contain the Bearer key or `secret_token`.

## Rollback (`deleteWebhook`)

Point Telegram away from this URL:

```bash
curl -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/deleteWebhook"
```

Confirm with `getWebhookInfo` that `url` is empty. Then optionally:

```bash
sudo systemctl disable --now tg-cursor-webhook-adapter
```

`telegram-bridge` polling is independent; leave it running unless you intend to stop Jimmy’s bridge.

## First-time deploy note

`./scripts/deploy-vps.sh` installs the unit even when `/opt/zerorelay/tg-cursor-adapter.env` is missing, but it **does not start** the adapter until that file exists (systemd `EnvironmentFile=` would otherwise fail and the crash loop would fail the whole deploy). Create the env file, enable the unit, then deploy or `systemctl restart tg-cursor-webhook-adapter`.
