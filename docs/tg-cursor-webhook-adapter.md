# Telegram → Cursor webhook adapter

Thin localhost adapter for GrowthLabs near-realtime Telegram wakes into a Cursor automation webhook.

Telegram Bot API `setWebhook` can POST JSON to an HTTPS URL and optionally send `X-Telegram-Bot-Api-Secret-Token`. Cursor’s automation webhook requires `Authorization: Bearer <crsr_…>` (panel sender key). Telegram cannot send Bearer, so a direct `setWebhook` to Cursor fails with `getWebhookInfo last_error=401 Unauthorized`.

This service sits on the ZeroRelay VPS (`vps-zee`, `/opt/zerorelay`). Telegram `setWebhook`s to the **Tailscale Funnel HTTPS URL**. Funnel terminates public TLS and proxies to localhost. The adapter validates Telegram’s secret header and re-POSTs the same JSON body to Cursor with Bearer.

```
Telegram Bot API
    POST https://vps-zee.<TAILNET>.ts.net/
    X-Telegram-Bot-Api-Secret-Token: <secret>
        │
        ▼
Tailscale Funnel on vps-zee  (public TLS, port 443)
        │  proxy http://127.0.0.1:8787
        ▼
tg-cursor-webhook-adapter  (127.0.0.1:8787 only)
        │  Authorization: Bearer <crsr_…>
        │  Content-Type: application/json
        ▼
Cursor automation webhook
```

Same ingress pattern as Hektor Operator Funnel: process binds loopback, Funnel is the only public HTTPS edge.

This adapter does **not** join the ZeroRelay WebSocket mesh and does **not** change `telegram-bridge` polling.

## Localhost bind — Funnel is the public edge

The unit listens on **`127.0.0.1:8787` only**. It is not an HTTPS server and must not bind `0.0.0.0`.

Public Telegram traffic reaches the adapter only through **Tailscale Funnel on `vps-zee`**, which terminates TLS and reverse-proxies to `http://127.0.0.1:8787`. Funnel forwards request headers (including `X-Telegram-Bot-Api-Secret-Token`) and the raw POST body.

On-box health (no Funnel, no secret):

```bash
curl -fsS http://127.0.0.1:8787/health
```

## Tailscale Funnel on vps-zee

Run these on **`vps-zee`**, not on ZeroMini.

Tailscale 1.52+ one-liner (persistent background proxy of localhost:8787):

```bash
sudo tailscale funnel --bg 8787
sudo tailscale funnel status
```

Equivalent explicit target:

```bash
sudo tailscale funnel --bg http://127.0.0.1:8787
```

`serve` + Funnel is the same outcome **only if Funnel is on**. `tailscale serve --bg 8787` is **tailnet-only** — Telegram’s servers cannot reach it. Production must show Funnel in `tailscale funnel status`, for example:

```
https://vps-zee.<TAILNET>.ts.net
|-- / proxy http://127.0.0.1:8787
```

Public Funnel listen ports are `443` (default), `8443`, or `10000`. The adapter stays on loopback `8787`. Default mount is `/`, which matches `POST /` and `GET /health`.

Do **not** `tailscale funnel` ZeroMini or reopen **ZM 3050/3051**. Leave those ports as they are.

### Tailnet policy (zeroshotstudio)

Funnel requires MagicDNS, HTTPS certificates, and a `funnel` **nodeAttr** in the zeroshotstudio tailnet ACL. Keep the **existing** Funnel `nodeAttrs` already used for Hektor Operator Funnel. Do not broaden them, and do not add Funnel/ACL for ZeroMini 3050/3051.

Typical (already present — do not duplicate unless missing):

```json
"nodeAttrs": [
  {
    "target": ["autogroup:member"],
    "attr": ["funnel"]
  }
]
```

If `tailscale funnel` errors with a node-attribute / ACL denial, an Owner/Admin should confirm that existing Funnel attr still covers `vps-zee`. Do not invent a second Funnel policy for this adapter.

## Generate `secret_token`

Telegram allows 1–256 chars: `A-Z`, `a-z`, `0-9`, `_`, `-`.

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep the value only in the env file and in the `setWebhook` call. Do not commit it.

## Env file

On `vps-zee`:

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

## Verify Funnel from a non-tailnet host

Before `setWebhook`, prove the Funnel URL is on the public internet. From a host **not** on the zeroshotstudio tailnet (phone LTE, coffee-shop laptop, or a throwaway VPS):

```bash
curl -fsS https://vps-zee.<TAILNET>.ts.net/health
```

Expect `ok` and HTTP 200. No Bearer, no Telegram secret.

If that curl only works on the tailnet, Funnel is off (Serve-only) or DNS/ACL is wrong. Do not `setWebhook` until the non-tailnet `/health` check succeeds. Public DNS for `*.ts.net` can lag a few minutes after the first Funnel enable.

Optional: from the same off-tailnet host, a POST without `X-Telegram-Bot-Api-Secret-Token` must be `401` — that confirms Telegram hits the adapter, not some other origin.

## setWebhook

`url` **is** the Funnel HTTPS URL Telegram can reach (the same host you curled `/health` on). Replace placeholders only.

```bash
curl -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  --data-urlencode "url=https://vps-zee.<TAILNET>.ts.net/" \
  --data-urlencode "secret_token=<TELEGRAM_SECRET_TOKEN>"
```

`secret_token` must match `TELEGRAM_SECRET_TOKEN` in the env file. If Funnel uses `--set-path`, include that path in `url`.

## getWebhookInfo

```bash
curl -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

Expect `url` equal to the Funnel HTTPS URL and `last_error_message` / `last_error_date` empty (or absent). A pending `last_error` of `401 Unauthorized` means Bearer never reached Cursor — adapter down, Funnel not proxying `127.0.0.1:8787`, or `CURSOR_WEBHOOK_BEARER` is wrong.

On `vps-zee`:

```bash
sudo tailscale funnel status
journalctl -u tg-cursor-webhook-adapter -n 50 --no-pager
curl -fsS http://127.0.0.1:8787/health
```

Send a Telegram message to the bot. The adapter should return Cursor’s HTTP status (or `502` if Cursor is unreachable). Journals must not contain the Bearer key or `secret_token`.

## Rollback (`deleteWebhook`)

Point Telegram away from the Funnel URL:

```bash
curl -sS "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/deleteWebhook"
```

Confirm with `getWebhookInfo` that `url` is empty. Then optionally:

```bash
sudo tailscale funnel reset
sudo systemctl disable --now tg-cursor-webhook-adapter
```

`tailscale funnel reset` only on `vps-zee` for this proxy. Do not touch other Funnel configs (Hektor Operator) or ZeroMini 3050/3051.

`telegram-bridge` polling is independent; leave it running unless you intend to stop Jimmy’s bridge.

## First-time deploy note

`./scripts/deploy-vps.sh` installs the unit even when `/opt/zerorelay/tg-cursor-adapter.env` is missing, but it **does not start** the adapter until that file exists (systemd `EnvironmentFile=` would otherwise fail and the crash loop would fail the whole deploy). Create the env file, enable the unit, enable Funnel on `vps-zee`, then deploy or `systemctl restart tg-cursor-webhook-adapter`.
