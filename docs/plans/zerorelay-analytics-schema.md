# ZeroRelay Analytics Event Schema

**Date**: 2026-06-30  
**Status**: Draft v1 — implements PRD §6.4  
**Consumers**: Cloud control plane, optional OSS opt-in telemetry, dashboard metrics  

---

## Principles

1. **No LLM content in events by default** — log lengths, roles, tool names, not prompts/responses.
2. **Workspace-scoped** — every cloud event includes `workspace_id`.
3. **OSS opt-in only** — `ZERORELAY_TELEMETRY=1` sends anonymized install pings; no transcript data.
4. **Retention** — raw events 90 days; monthly rollups indefinite.

---

## Common Envelope

```json
{
  "event": "relay.message.sent",
  "ts": "2026-06-30T12:00:00.000Z",
  "schema_version": 1,
  "workspace_id": "uuid-or-null-for-oss",
  "install_id": "anonymous-uuid-for-oss",
  "properties": {}
}
```

---

## Event Catalog

### Relay session lifecycle

| Event | Properties | When |
|-------|------------|------|
| `relay.session.started` | `relay_version`, `host_mode` (`self_host` \| `cloud`) | Broker process start |
| `relay.session.ended` | `duration_sec`, `reason` | Broker shutdown |
| `relay.agent.connected` | `role`, `bridge_type` (`anthropic_api`, `telegram`, …) | WebSocket connect |
| `relay.agent.disconnected` | `role`, `duration_sec` | WebSocket disconnect |

### Messaging

| Event | Properties | When |
|-------|------------|------|
| `relay.message.sent` | `sender_role`, `tagged_roles[]`, `content_length`, `channel` (`chat`) | Broadcast message |
| `relay.message.rate_limited` | `sender_role`, `limit_window` | Rate limit hit |

### MCP Tool Broker

| Event | Properties | When |
|-------|------------|------|
| `relay.mcp.tool_registered` | `owner`, `tool_count` | `mcp_register` |
| `relay.mcp.tool_call` | `caller`, `owner`, `tool_name`, `success`, `latency_ms` | Call completed |
| `relay.mcp.tool_error` | `caller`, `owner`, `tool_name`, `error_class` | Call failed |
| `relay.mcp.tool_timeout` | `caller`, `owner`, `tool_name`, `timeout_sec` | Timeout |

### Cloud product

| Event | Properties | When |
|-------|------------|------|
| `cloud.user.signup` | `auth_provider` | First login |
| `cloud.workspace.created` | `tier`, `slug` | Workspace row created |
| `cloud.workspace.provisioned` | `duration_ms` | Container healthy |
| `cloud.workspace.suspended` | `reason` (`limit`, `billing`, `admin`) | Suspended |
| `cloud.token.rotated` | `workspace_id` | Token rotate |
| `cloud.subscription.started` | `tier`, `stripe_price_id` | Checkout complete |
| `cloud.subscription.canceled` | `tier` | Cancel |
| `cloud.limit.warning` | `metric`, `percent` | 90% of limit |
| `cloud.limit.exceeded` | `metric` | 100% of limit |

### GTM / OSS (optional telemetry)

| Event | Properties | When |
|-------|------------|------|
| `oss.install.setup_completed` | `profile`, `bridge_count`, `python_version` | `setup.py` success |
| `oss.install.upgrade` | `from_version`, `to_version` | `setup.py --upgrade` |

---

## Derived Metrics (dashboard / north star)

| Metric | SQL / aggregation |
|--------|-------------------|
| **WARS** (north star) | Distinct `workspace_id` with ≥1 `relay.message.sent` from human role AND ≥2 `relay.agent.connected` in 7d window |
| Agent slots used | Max concurrent `relay.agent.connected` per workspace per day |
| MCP success rate | `tool_call.success=true` / total tool_call |
| Provisioning p95 | p95 of `cloud.workspace.provisioned.duration_ms` |
| Free → paid | `subscription.started` / `workspace.created` cohort |

---

## PII Policy

| Field | Allowed? |
|-------|----------|
| Email | Cloud user table only — never in event stream |
| Telegram user ID | Hashed if needed for abuse detection |
| Message content | **No** in analytics; optional encrypted audit table separate |
| API keys | **Never** |

---

## Implementation Notes

| Consumer | Implementation step |
|----------|---------------------|
| Cloud ingest | `zerorelay-cloud-implementation-plan.md` Step C6 |
| Cloud dashboard | Overview cards read rollups from `usage_counters` |
| OSS opt-in | `setup.py` POST single `oss.install.setup_completed` if env set |
| Product analytics | Export to PostHog/Plausible later — schema stable first |

---

## Open Items

- [ ] Choose analytics backend (PostHog vs self-hosted ClickHouse) — defer to Cloud Step C13
- [ ] Confirm `install_id` generation for OSS (persist in `~/.config/zerorelay/install_id`)
- [ ] Legal copy for telemetry opt-in in README

---

*Implements PRD §6.4. Update when adding Team tier RBAC events.*
