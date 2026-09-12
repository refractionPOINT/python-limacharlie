# SentinelOne

[SentinelOne](https://www.sentinelone.com/) is an endpoint protection platform. The SentinelOne LimaCharlie Extension exposes the SentinelOne Management API to D&R rules and AI agents: list and act on agents (isolate, scan), triage threats (mitigate, verdict, incident status, notes), blocklist file hashes, and read the tenant's org hierarchy and activity log.

The extension provides two layers:

- **Typed actions** for the common EDR/SecOps workflows, with friendly parameter names and built-in safety rails.
- A generic **`api_call`** passthrough for any SentinelOne endpoint not covered by a typed action.

## Setup

### 1. Create a SentinelOne API token

In the SentinelOne management console, create an API token. A **Service User** token (Settings → Users → Service Users) is recommended: it is an API-only credential with a configurable expiry, unlike regular user tokens which expire after 30 days. Scope it to the sites/accounts the extension should manage.

### 2. Subscribe to the extension

Subscribe to `ext-sentinelone` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### 3. Store the API token

In **Secrets Manager**, create a new secret (for example `sentinelone-api-token`) and paste the API token as its value.

### 4. Configure the extension

In **Extensions → ext-sentinelone → Configuration**, fill in:

| Field | Required | Value |
| --- | --- | --- |
| `console_url` | yes | Your SentinelOne management console URL, e.g. `https://usea1-partners.sentinelone.net` |
| `api_token` | yes | Reference to the secret created in step 3, e.g. `hive://secret/sentinelone-api-token` |
| `api_version` | no | API version path segment. Defaults to `v2.1`. |
| `site_ids` | no | List of SentinelOne site ids. When set, **every** call is restricted to these sites. See [Org scoping](#org-scoping). |
| `account_ids` | no | List of SentinelOne account ids. When set, every call is restricted to these accounts (combined with `site_ids` when both are set). |

The token is sent as `Authorization: ApiToken <token>` on every request. Rotating the secret in Secrets Manager takes effect on the next request after a surfaced `401`.

## Org scoping

For the MSSP / multi-tenant pattern — where one SentinelOne console holds many customers, split across **accounts** and **sites** — set `site_ids` and/or `account_ids` in the configuration to pin a single LimaCharlie organization to a single SentinelOne customer. Every call the organization makes is then restricted to that scope. For example, `list_agents` returns only that customer's endpoints, and a mitigation can only act within it.

The scope is a **hard cap**, not a default:

- **List actions** (`list_agents`, `list_threats`, `list_activities`, `list_sites` / `list_accounts` / `list_groups`) apply the scope to the `site_ids` / `account_ids` filters. A per-request `site_ids` / `account_ids` is **intersected** with the configured scope — a request can narrow within the scope but never widen past it, and a request that targets ids wholly outside the scope is **rejected**.
- **Mutating actions** (isolate / scan / mitigate / verdict / incident / note) inject the scope into the action's target filter, so an entity selected purely by id is still confined to the configured sites/accounts — you cannot act on another tenant's agent or threat by guessing its id.
- **`blocklist_hash`** cannot be applied `tenant`-wide for a scoped organization; the configured scope is used automatically when no scope is given on the request.
- **`api_call`** (the generic passthrough): a **write** (`POST` / `PUT` / `DELETE`) that carries no target `filter` cannot be constrained and is **refused** for a scoped organization — use a typed action or include a filter. A **read** (`GET`) has the scope injected into the query; a read of a single resource by path (for example `sites/<id>`) cannot be constrained this way, so the typed actions are the fully-enforced surface.

!!! note "Scope by the right dimension"
    Scope by `account_ids` when a customer maps to a SentinelOne *account*, and by `site_ids` when it maps to a *site*. The hierarchy-list actions can only filter by a dimension the endpoint supports: `list_accounts` filters by `account_ids` only (an account has no parent site), so an organization scoped by `site_ids` alone does not constrain `list_accounts`. Prefer `account_ids` (or set both) if listing the account hierarchy must also be scoped. The API token itself should also be scoped to the intended sites/accounts in SentinelOne — the configuration scope is enforced on top of the token's own permissions, not instead of them.

## Actions

Every action that mutates state (isolate, scan, mitigate, verdict, incident, note) selects its targets with either an explicit id list (`agent_ids` / `threat_ids`) or a raw SentinelOne `filter` object. **An empty selector is refused** — the extension will not run an action that would target every entity in the tenant.

List actions return one page plus a cursor: `{data: [...], pagination: {nextCursor, totalItems}}`. Pass `cursor` back (together with the same filters) to fetch the next page. `limit` defaults to `100` (max `1000`).

### Generic

#### `api_call`

Call any SentinelOne Management API endpoint — the escape hatch for endpoints without a typed action.

| Field | Type | Notes |
| --- | --- | --- |
| `method` | enum | `GET` (default), `POST`, `PUT`, `DELETE`. |
| `path` | string | **Required.** Endpoint path relative to `/web/api/<version>`, e.g. `agents`, `threats/mitigate/kill`, `system/info`. |
| `query` | object | Query-string parameters as a flat object. |
| `body` | object | JSON request body for `POST`/`PUT`. Action endpoints expect `{filter: {...}, data: {...}}`. |

Returns the full SentinelOne response envelope.

### Agents

#### `list_agents`

List/search agents (endpoints).

| Field | Type | Notes |
| --- | --- | --- |
| `query` | string | Free-text search (computer name, IP, …). |
| `computer_name` | string | Substring match on computer name. |
| `uuid` | string | Filter by agent UUID. |
| `is_active` | bool | Only active (`true`) / inactive (`false`) agents. |
| `network_status` | enum | `connected`, `connecting`, `disconnected`, `disconnecting`. |
| `infected` | bool | Only agents with (`true`) / without (`false`) active threats. |
| `os_types` | list of enum | `windows`, `linux`, `macos`, `windows_legacy`. |
| `site_ids` / `group_ids` / `account_ids` | list of string | Restrict to sites / groups / accounts. |
| `limit` / `cursor` | int / string | Pagination. |
| `extra_query` | object | Raw query params merged into the request (escape hatch). |

#### `isolate_agent` / `deisolate_agent` / `scan_agent`

Network-isolate (disconnect), reconnect, or start a full-disk scan on selected agents.

| Field | Type | Notes |
| --- | --- | --- |
| `agent_ids` | list of string | Agent ids to act on (the common case). |
| `filter` | object | Raw SentinelOne agent filter (advanced alternative to `agent_ids`). |
| `data` | object | Extra fields merged into the action's data payload. |

At least one of `agent_ids` or `filter` is required. Returns `{data: {affected: N}}`.

### Threats

#### `list_threats`

List/search threats.

| Field | Type | Notes |
| --- | --- | --- |
| `query` | string | Free-text search (file path, hash, computer name, …). |
| `content_hashes` | list of string | Filter by file SHA-1 hashes. |
| `mitigation_statuses` | list of string | e.g. `mitigated`, `active`, `blocked`, `suspicious`. |
| `incident_statuses` | list of string | `unresolved`, `in_progress`, `resolved`. |
| `analyst_verdicts` | list of string | `true_positive`, `false_positive`, `suspicious`, `undefined`. |
| `classifications` | list of string | e.g. `Malware`, `PUA`, `Ransomware`. |
| `resolved` | bool | Only resolved (`true`) / unresolved (`false`) threats. |
| `created_at__gte` / `created_at__lte` | string | ISO-8601 UTC bounds, e.g. `2026-06-01T00:00:00.000000Z`. |
| `site_ids` / `account_ids` | list of string | Restrict to sites / accounts. |
| `limit` / `cursor` / `extra_query` | — | Pagination and raw-params escape hatch. |

#### `mitigate_threat`

Apply a mitigation action to selected threats.

| Field | Type | Notes |
| --- | --- | --- |
| `action` | enum | **Required.** `kill`, `quarantine`, `remediate`, `rollback-remediation`, `un-quarantine`, `network-quarantine`. |
| `threat_ids` | list of string | Threat ids to mitigate. |
| `filter` | object | Raw SentinelOne threat filter (advanced alternative). |
| `data` | object | Extra fields merged into the action's data payload. |

#### `set_threat_verdict`

Set the analyst verdict on selected threats.

| Field | Type | Notes |
| --- | --- | --- |
| `verdict` | enum | **Required.** `true_positive`, `false_positive`, `suspicious`, `undefined`. |
| `threat_ids` / `filter` | — | Target selection, at least one required. |

#### `set_threat_incident`

Set the incident status on selected threats.

| Field | Type | Notes |
| --- | --- | --- |
| `status` | enum | **Required.** `unresolved`, `in_progress`, `resolved`. |
| `threat_ids` / `filter` | — | Target selection, at least one required. |

#### `add_threat_note`

Append a note to selected threats — useful for AI agents to record triage findings in the SentinelOne console.

| Field | Type | Notes |
| --- | --- | --- |
| `text` | string | **Required.** Note text. |
| `threat_ids` / `filter` | — | Target selection, at least one required. |

### Blocklist

#### `blocklist_hash`

Add a SHA-1 file hash to the SentinelOne blocklist.

| Field | Type | Notes |
| --- | --- | --- |
| `hash` | string | **Required.** SHA-1 hash to block. |
| `os_type` | enum | **Required.** `windows`, `windows_legacy`, `macos`, `linux`. |
| `description` | string | Reason for the blocklist entry. |
| `tenant` | bool | Apply tenant-wide. Default `false`. |
| `site_ids` / `group_ids` / `account_ids` | list of string | Scope the entry when `tenant` is not set. |
| `data` | object | Extra fields merged into the restriction's data payload. |

A scope is required: set `tenant: true` or at least one of `site_ids` / `group_ids` / `account_ids`.

### Tenant reads

#### `list_sites` / `list_accounts` / `list_groups`

List the org hierarchy — useful to resolve the ids used by the scoping parameters above.

| Field | Type | Notes |
| --- | --- | --- |
| `query` | string | Free-text name match. |
| `site_ids` / `account_ids` | list of string | Restrict by id. |
| `limit` / `cursor` / `extra_query` | — | Pagination and raw-params escape hatch. |

#### `list_activities`

List the activity / audit log.

| Field | Type | Notes |
| --- | --- | --- |
| `activity_types` | list of string | Numeric activity type codes (see the SentinelOne `/activities/types` endpoint). |
| `agent_ids` / `site_ids` | list of string | Restrict by agent / site. |
| `created_at__gte` / `created_at__lte` | string | ISO-8601 UTC bounds. |
| `limit` / `cursor` / `extra_query` | — | Pagination and raw-params escape hatch. |

## Detection & Response

Example response action that network-isolates the SentinelOne agent named in a detection:

```yaml
- action: extension request
  extension action: isolate_agent
  extension name: ext-sentinelone
  extension request:
    agent_ids:
      - '{{ .event/agent_id }}'
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context. Workflows that need to chain (find the agent, isolate it, annotate the threat) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold ids between calls.

## Notes

- The token is sent as `Authorization: ApiToken <token>` — SentinelOne API tokens are static, not OAuth, and are not refreshable. A `401` is surfaced as a real auth failure; the extension then evicts its cached client so the next request re-reads the (possibly rotated) secret.
- SentinelOne cursors are not self-contained: re-send the same filters along with `cursor` on every page.
- `console_url` may be pasted with or without a trailing `/web/api[/version]` suffix — the extension normalizes it either way.
- Errors are surfaced as `sentinelone api <status> on <path>: <message>`, with SentinelOne's error envelope flattened into the message.
- Unsubscribing from the extension preserves its saved configuration; re-subscribing restores it without reconfiguration.
