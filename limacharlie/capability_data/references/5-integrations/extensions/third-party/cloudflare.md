# Cloudflare

The Cloudflare LimaCharlie Extension exposes the incident-response and investigation surface of a Cloudflare account/zone (the Cloudflare v4 API) to D&R rules and AI agents. It enables automated edge and Zero Trust containment directly from detections — block a malicious source at the WAF, revoke a Zero Trust Access user's sessions, push IOCs onto a Gateway block list, purge cache, or fix a hijacked DNS record — without bouncing through a separate SOAR.

The extension provides two layers:

- **Typed actions** for the common containment, triage, and investigation workflows, with friendly parameter names and built-in safety rails.
- A generic **`api_call`** passthrough for any Cloudflare v4 endpoint not covered by a typed action, including non-enveloped surfaces like the GraphQL Analytics API.

Authentication is a scoped **API Token** (Bearer) or the legacy **Global API Key** — both static, no user interaction.

## Setup

### 1. Create an API Token

In the Cloudflare dashboard (**My Profile → API Tokens**, or **Account Home → Manage Account → API Tokens**), create a token and grant only the permission groups for the actions you will use, scoped to the specific account and/or zone rather than "all accounts / all zones". The least-privilege set per capability:

| Capability | Permission group (Read/Edit) | Scope |
| --- | --- | --- |
| IP Access Rules (account) | Account Firewall Access Rules — Edit | Account |
| IP Access Rules (zone) | Firewall Services — Edit | Zone |
| WAF custom rules / rulesets | Account WAF / Zone WAF + Rulesets — Edit | Account / Zone |
| Zero Trust Access (users, sessions, policies) | Access: Apps and Policies + Access: Organizations, Identity Providers, and Groups — Edit | Account |
| Gateway lists & rules | Zero Trust — Edit | Account |
| DNS read / edit | DNS — Read / Edit | Zone |
| Cache purge | Cache Purge — Purge | Zone |
| Audit log | Logs — Read | Account |
| Firewall events (GraphQL) | Account Analytics — Read | Account |
| Account members | Account Membership — Edit | Account |

Only add what you will use — a valid token missing a permission group returns `403` on that endpoint (that is a scope problem, not a bad token). Resolve current permission-group names/IDs at setup via `GET /accounts/{account_id}/tokens/permission_groups`.

A legacy **Global API Key** works too (your account email plus the key), but it has full account access and **cannot be scoped** — prefer a token.

### 2. Subscribe to the extension

Subscribe to `ext-cloudflare` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### 3. Store the secret

In **Secrets Manager**, create a new secret (for example `cloudflare-api-token`) and paste the API token (or Global API Key) as its value.

### 4. Configure the extension

In **Extensions → ext-cloudflare → Configuration**, fill in:

| Field | Required | Value |
| --- | --- | --- |
| `api_token` | one auth mode | Reference to the API token secret, e.g. `hive://secret/cloudflare-api-token`. |
| `email` | legacy only | Account email for legacy Global API Key auth (paired with `api_key`). |
| `api_key` | legacy only | Reference to the Global API Key secret (paired with `email`). |
| `account_id` | no | Default account id for account-scoped actions. Any action can override it. |
| `zone_id` | no | Default zone id for zone-scoped actions. Any action can override it. |

Provide **either** `api_token` **or** `email` + `api_key`, not both.

## Scoping: account vs zone

Cloudflare resources are either **account-scoped** or **zone-scoped**. Set default `account_id` / `zone_id` in the config; any action can override them per-request.

- **Account-scoped:** Zero Trust Access, Gateway, account members, the audit log.
- **Zone-scoped:** DNS records, cache purge.
- **Either:** IP Access Rules and WAF custom rules accept `account_id` **or** `zone_id` — account scope applies across *all* the account's zones, zone scope to one zone. Pass exactly one; passing both is rejected as ambiguous, and with neither set the config defaults are used, **preferring the zone** (the narrower blast radius).

## Actions

Every action that targets an entity requires an explicit selector (an `ip` / `asn` / `country`, a `rule_id`, an `email`, a `list_id` + `values`, a `dns_record_id`, a `member_id`, …) — the extension refuses to run without one, preventing an accidental account-wide response. `purge_cache` additionally refuses unless exactly one purge mode is chosen.

Typed list actions return `{data: [...], pagination: {...}}`, where `pagination` carries Cloudflare's `result_info` verbatim — offset fields (`page`, `per_page`, `total_pages`, …) or a `cursor`. Page by incrementing `page` until `page == total_pages`, or by passing the `cursor` back. `per_page` is clamped to 100.

### Generic

#### `api_call`

Generic passthrough to any Cloudflare v4 endpoint.

| Field | Type | Notes |
| --- | --- | --- |
| `method` | enum | `GET` (default), `POST`, `PUT`, `PATCH`, `DELETE`. |
| `path` | string | **Required.** Path relative to `https://api.cloudflare.com/client/v4` (e.g. `zones/{zone_id}/dns_records`, or `graphql` for the GraphQL Analytics API) or a full URL. |
| `query` | object | Query-string parameters. |
| `headers` | object | Extra request headers. |
| `body` | object | JSON body for `POST`/`PUT`/`PATCH`. |

Returns the whole response body verbatim — the `{success, errors, result, result_info}` envelope, or the raw shape for non-enveloped endpoints like GraphQL.

### Investigation (reads)

| Action | Parameters | What it does |
| --- | --- | --- |
| `verify_token` | — | Verify the configured API token (health check); returns the token status. |
| `list_accounts` | `name`, `page`, `per_page`, `extra_query` | List accounts the credential can see — find an `account_id`. |
| `list_zones` | `name`, `account_id`, `status`, `page`, `per_page`, `extra_query` | List/search zones — find a `zone_id`. |
| `list_ip_access_rules` | `account_id`/`zone_id`, `target`, `value`, `mode`, `page`, `per_page` | List IP Access Rules; use a returned rule id with `remove_ip_access_rule`. |
| `list_dns_records` | `zone_id`, `type`, `name`, `content`, `page`, `per_page` | List a zone's DNS records; use a returned id with `edit_dns_record` / `delete_dns_record`. |
| `list_access_users` | `account_id`, `email`, `name`, `search`, `page`, `per_page` | List Zero Trust Access users. |
| `get_access_user_activity` | `account_id`, `user_id`, `kind` | An Access user's `active_sessions`, `last_seen_identity`, or `failed_logins`. |
| `list_gateway_lists` | `account_id`, `page`, `per_page` | List Zero Trust Gateway lists — find a `list_id`. |
| `list_members` | `account_id`, `status`, `page`, `per_page` | List account members — use a returned membership id (`result[].id`, **not** `user.id`) with `remove_member`. |
| `get_audit_logs` | `account_id`, `since`, `before`, `action_type`, `actor_email`, `limit`, `cursor`, `direction` | Query the account audit log (v2, cursor-paginated). The v2 API requires a `since`+`before` window; if omitted it defaults to the last 7 days. Pass the same explicit window across pages for stable pagination. |
| `search_firewall_events` | `zone_id`, `since`, `until`, `client_ip`, `action`, `limit` | Search a zone's WAF/firewall events via the GraphQL Analytics API (`firewallEventsAdaptive`). Counts are sampled; the window is plan-dependent (~31 days). |
| `get_waf_custom_ruleset` | `account_id`/`zone_id` | Fetch the `http_request_firewall_custom` phase ruleset — its id is the `ruleset_id` for `add_waf_custom_rule`. |

### Edge / WAF containment

| Action | Parameters | What it does |
| --- | --- | --- |
| `block_ip` | `ip`, `account_id`/`zone_id`, `mode`, `notes` | Block a single IP (v4/v6) via an IP Access Rule. |
| `block_ip_range` | `range`, `account_id`/`zone_id`, `mode`, `notes` | Block a CIDR range (IPv4 /16 or /24; IPv6 /32, /48, /64). |
| `block_asn` | `asn`, `account_id`/`zone_id`, `mode`, `notes` | Block an ASN (bare AS number, no `AS` prefix). |
| `block_country` | `country`, `account_id`/`zone_id`, `mode`, `notes` | Block a country (ISO-3166-1 alpha-2). |
| `remove_ip_access_rule` | `rule_id`, `account_id`/`zone_id` | Delete an IP Access Rule (undo a block) at the scope it was created. |
| `add_waf_custom_rule` | `expression`, `account_id`/`zone_id`, `action`, `description`, `ruleset_id` | Add a WAF custom rule (wirefilter `expression`, e.g. `(ip.src eq 198.51.100.4)`); resolves the custom-phase ruleset for you if `ruleset_id` is omitted. |

`mode` on the block actions defaults to `block`; override with `challenge`, `managed_challenge`, `js_challenge`, or `whitelist` (an allow-list entry). An account-scoped rule applies across *all* the account's zones.

### Zero Trust containment

| Action | Parameters | What it does |
| --- | --- | --- |
| `revoke_access_user` | `email`, `account_id`, `revoke_devices` (default `true`), `warp_session_reauth` | Revoke a Cloudflare Access user's sessions (by email); `revoke_devices` also drops device/WARP sessions. |
| `gateway_add_to_blocklist` | `list_id`, `values`, `account_id` | Append IOCs (domains, IPs, URLs, … per the list type) to a Zero Trust Gateway list. |
| `gateway_remove_from_blocklist` | `list_id`, `values`, `account_id` | Remove IOCs from a Gateway list (undo). |

`revoke_access_user` propagates in ~1 minute and does **not** disable the upstream IdP identity — pair it with an IdP-side disable or a `deny` Access policy (via `api_call`) for a durable block. Wire a Gateway list into a Gateway block rule for it to enforce.

### DNS / cache response

| Action | Parameters | What it does |
| --- | --- | --- |
| `edit_dns_record` | `dns_record_id`, `zone_id`, `content`, `name`, `type`, `ttl`, `proxied`, `comment` | Partially update a DNS record (only set fields change) — e.g. re-point a hijacked record to a sinkhole. |
| `delete_dns_record` | `dns_record_id`, `zone_id` | Delete a DNS record — e.g. remove an attacker-created record. |
| `purge_cache` | `zone_id`, `purge_everything`, `files`, `hosts`, `tags`, `prefixes` | Purge cache. Choose **exactly one** mode: `purge_everything=true`, or one of `files` / `hosts` / `tags` / `prefixes` (`hosts`/`tags`/`prefixes` are Enterprise-only). |

### Account containment

| Action | Parameters | What it does |
| --- | --- | --- |
| `remove_member` | `member_id`, `account_id` | Remove a member from the account. Use the membership id (`result[].id` from `list_members`, **not** `user.id`). To downgrade instead of remove, `api_call` a `PUT` with a read-only role. |

## Detection & Response

Example response action that blocks the source IP named in a detection at the Cloudflare edge:

```yaml
- action: extension request
  extension action: block_ip
  extension name: ext-cloudflare
  extension request:
    ip: '{{ .event/SOURCE_IP }}'
    zone_id: '{{ "<your-zone-id>" }}'
    notes: '{{ "Blocked by LimaCharlie D&R rule" }}'
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context. Workflows that chain (look up the zone, block the IP, then confirm) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold ids between calls.

## Notes

- **`success: false` is an error.** Cloudflare frequently answers `200` with `success: false` on a logical error; the extension treats that as a failure and surfaces the Cloudflare error code/message, so a typed action never reports a no-op as success.
- **IP Access Rule scope matters.** An account-scoped rule applies across *all* the account's zones; a zone-scoped rule to one zone. `remove_ip_access_rule` must delete at the same scope the rule was created.
- **`revoke_access_user` is not a durable block.** It kills current sessions but does not disable the IdP identity; pair with an IdP disable or a `deny` policy.
- **Purge is explicit.** `purge_cache` requires exactly one mode; `purge_everything` must be set to `true` deliberately. `tags`/`hosts`/`prefixes` are Enterprise-only.
- **User API tokens can't be revoked cross-member.** Cloudflare's token-revocation endpoint is user-scoped; to contain another member, `remove_member` (or downgrade them via `api_call`).
- **Secret rotation recovers automatically.** A `401` (or a `403`/`400` carrying Cloudflare's authentication error code `10000`) evicts the cached client and re-reads the secret from Secrets Manager on the next call; a `403` permission gap is *not* treated as an auth failure. Error messages are formatted `cloudflare api error <status> on <method> <path>: <code> <message>` (`cloudflare auth error …` for auth failures), with query strings redacted.
- Unsubscribing from the extension preserves its saved configuration; re-subscribing restores it without reconfiguration.
