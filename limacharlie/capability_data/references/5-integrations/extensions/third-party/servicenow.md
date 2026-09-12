# ServiceNow

[ServiceNow](https://www.servicenow.com/) is an IT service management (ITSM) and security operations platform used for ticketing, change/problem management, CMDB asset tracking, and security incident response.

The ServiceNow LimaCharlie Extension is primarily an **API bridge**: it lets LimaCharlie-side automation (D&R rules, AI agents) drive a ServiceNow instance as it sees fit — create/read/update/delete records on *any* table, append journal entries, manage attachments, count and query, and resolve CMDB items. On top of that bridge it ships typed incident conveniences and one optional, fully-configurable **Case-mirroring** recipe (LimaCharlie Cases ⇄ ServiceNow records).

Nothing pins the extension to the stock ITSM `incident` table. Security teams on Security Incident Response (`sn_si_incident`), change/problem workflows, or custom tables are all first-class: pass a `table` (or configure the mirror target) and the same actions apply.

The sync model is stateless on the LimaCharlie side:

- **LC → ServiceNow**: `mirror_case` idempotently upserts a ServiceNow record from a LimaCharlie Case, anchored on the record's standard `correlation_id` / `correlation_display` fields. Repeated calls update the same record.
- **ServiceNow → LC**: `pull_incident_changes` returns records updated since a watermark, normalized for feeding back into Cases. Changes made by the integration's own user are excluded, breaking echo loops.

## Setup

### 1. Create a ServiceNow integration user

Create a dedicated ServiceNow **integration user** for the extension and grant it the roles needed for the tables and operations you intend to drive (e.g. `itil` for incidents, `sn_si.analyst` for Security Incident Response, plus `rest_api_explorer`/table ACLs as appropriate). The integration user's ACLs govern everything the extension can read, write, or delete.

Using a dedicated user matters for the Case-mirroring puller: `pull_incident_changes` filters out the extension's own writes by this user to break echo loops (see [Case mirroring](#case-mirroring-optional)).

### 2. Choose an authentication mode

The extension supports three modes (set `auth_mode`):

| Mode | Requires | Notes |
| --- | --- | --- |
| `basic` | `username`, `password` | Username/password sent on every request. Simplest for ServiceNow. |
| `oauth_password` | `client_id`, `client_secret`, `username`, `password` | OAuth2 Resource Owner Password Credentials grant, then `refresh_token` to renew. |
| `oauth_client_credentials` | `client_id`, `client_secret` | True server-to-server grant (no end-user password). Needs extra instance-side setup — see below. |

For the OAuth modes, register an OAuth application in ServiceNow (**System OAuth → Application Registry**) and copy its Client ID and Client Secret.

The **client credentials** grant needs two extra pieces of instance-side setup beyond the client registration:

1. Set the system property `glide.oauth.inbound.client.credential.grant_type.enabled` to `true` (create it under **System Properties** if it doesn't exist). Without it the token endpoint returns `access_denied` / `server_error`.
2. On the OAuth application record, set the **OAuth Application User** (the `user` field) to your integration user. The grant issues tokens **as this user**, so it must hold the roles the actions need (e.g. `itil` / `sn_incident_write` for incident writes). Without it the token endpoint returns `unauthorized_client` ("integration user is not configured"). Set `integration_user` (below) to this same username so SN → LC polling can de-echo the extension's own writes.

The **basic** and **OAuth password** modes don't need this — they authenticate as the `username` you configure directly.

### 3. Subscribe to the extension

Subscribe to `ext-servicenow` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### 4. Store the credentials

In **Secrets Manager**, create secrets for the sensitive values — the `password` and `client_secret` fields are resolved as secret references at request time. For example create a `servicenow-password` secret and reference it as `hive://secret/servicenow-password`.

### 5. Configure the extension

In **Extensions → ext-servicenow → Configuration**, fill in:

| Field | Required | Value |
| --- | --- | --- |
| `instance_url` | yes | ServiceNow instance base URL, e.g. `https://acme.service-now.com`. |
| `auth_mode` | no | `basic` (default), `oauth_password`, or `oauth_client_credentials`. |
| `username` | conditional | Required for `basic` / `oauth_password`. |
| `password` | conditional | Secret reference. Required for `basic` / `oauth_password`. |
| `client_id` | conditional | Required for `oauth_password` / `oauth_client_credentials`. |
| `client_secret` | conditional | Secret reference. Required for `oauth_password` / `oauth_client_credentials`. |
| `integration_user` | no | The ServiceNow user the extension authenticates as. `pull_incident_changes` excludes changes made by this user. Set it to enable the echo-loop guard. |
| `correlation_display` | no | Label stamped on mirrored records' `correlation_display` field (default `LimaCharlie`). Scopes upserts and SN→LC polling, so multiple integrations can coexist. |
| `close_code` | no | `close_code` applied when mirroring a case into Resolved/Closed (default `Solution provided`). Must be a value in your instance's `close_code` choice list, which varies by ServiceNow version — the legacy `Solved (Permanently)` is not present on current releases. An invalid value is silently dropped by ServiceNow, which then trips the mandatory-resolution-code data policy. |
| `mirror_table` | no | Target table for case mirroring (default `incident`; set `sn_si_incident` for Security Incident Response, or any task-derived table). |
| `mirror_subject_prefix` | no | Prefix for the mirrored record's `short_description` (default `LimaCharlie Case`). |
| `mirror_state_map` | no | Override of case-status→record-state mapping, e.g. `{"new":1,"in_progress":2,"resolved":6,"closed":7}`. Used in both directions. |
| `mirror_severity_map` | no | Override of case-severity→`{urgency,impact}` mapping, e.g. `{"critical":{"urgency":1,"impact":1}}`. |

Only `instance_url` is strictly required; the credential fields are validated at request time against the selected `auth_mode`. The extension is stateless — mirroring state lives in ServiceNow (`correlation_id`) and the returned `watermark`, so there is no database to provision.

## Actions

All actions accept a JSON request body when invoked from a D&R rule via `extension request`. The typed actions and the mirroring recipe are conveniences — a customer who models ServiceNow differently can ignore them and drive `create_record` / `update_record` / `query_table` directly.

### Generic Table API bridge (any table)

These actions operate against *any* table and never assume `incident`.

#### `create_record`

Insert a record into any table with an arbitrary field map. The generic write counterpart to `query_table` — use it for `change_request`, `problem`, `sc_task`, custom tables, etc.

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | **Required.** Table name. |
| `fields` | object | **Required.** Field name→value map to set on the new record. |

#### `get_record`

Fetch a single record from any table by `sys_id` or by its `number` field.

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | **Required.** Table name. |
| `sys_id` | string | Record sys_id. |
| `number` | string | Record number (alternative to `sys_id`). |
| `fields` | string | Comma-separated fields to return (`sysparm_fields`). |
| `display_value` | enum | `false` (raw, default), `true` (labels), or `all`. |

#### `update_record`

Patch a record on any table by `sys_id` with an arbitrary field map (unspecified fields are left untouched).

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | **Required.** Table name. |
| `sys_id` | string | **Required.** Record sys_id to update. |
| `fields` | object | **Required.** Field name→value map to change. |

#### `delete_record`

Delete a record on any table by `sys_id`. Irreversible — the integration user's ACLs govern what can be deleted.

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | **Required.** Table name. |
| `sys_id` | string | **Required.** Record sys_id to delete. |

#### `query_table`

Read-only Table API query against any table (`incident`, `problem`, `change_request`, `cmdb_ci`, `sys_user`, …). An escape hatch for AI agents that need data the typed actions don't cover, and the way to resolve display names to the sys_ids the write actions expect.

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | **Required.** Table name. |
| `query` | string | ServiceNow encoded query (`sysparm_query`). |
| `fields` | string | Comma-separated fields to return. |
| `limit` | int | Max records (default `50`). |
| `offset` | int | Pagination offset. |
| `display_value` | enum | `false` / `true` / `all`. |

Returns `{ "count": N, "records": [...] }`.

#### `count_records`

Return the number of records matching an encoded query, via the Aggregate API (no rows pulled). E.g. count open criticals before deciding to escalate.

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | **Required.** Table name. |
| `query` | string | Encoded query (optional; empty counts all). |

### Typed incident conveniences

Table-aware shortcuts that default to `incident`; set `table` to e.g. `sn_si_incident` to operate on Security Incident Response records. Beyond the fields below, each accepts an `extra` object to merge raw ServiceNow fields the typed schema doesn't model.

#### `create_incident`

Open a record with typed subject/body, urgency/impact, and assignment. Returns the created record including its `sys_id` and `number`.

| Field | Type | Notes |
| --- | --- | --- |
| `short_description` | string | **Required.** Incident subject line. |
| `table` | string | Table to create in (default `incident`). |
| `description` | string | Incident body / description. |
| `state` | int | Incident state (1 New, 2 In Progress, 3 On Hold, 6 Resolved, 7 Closed, 8 Canceled). |
| `urgency` | int | Urgency (1 High … 3 Low). |
| `impact` | int | Impact (1 High … 3 Low). |
| `priority` | int | Usually derived from urgency×impact; set to override. |
| `category` | string | Category. |
| `assignment_group` | string | Assignment group **sys_id** (reference; display names are not auto-resolved). |
| `assigned_to` | string | Assignee user **sys_id**. |
| `caller_id` | string | Caller user **sys_id**. |
| `correlation_id` | string | External correlation id (e.g. an LC case id). |
| `correlation_display` | string | External system label (e.g. `LimaCharlie`). |
| `extra` | object | Raw ServiceNow fields to merge. |

#### `update_incident`

Update a record by `sys_id`. Set `state` to drive workflow transitions, reassign, or append a work note/comment.

| Field | Type | Notes |
| --- | --- | --- |
| `sys_id` | string | **Required.** Record sys_id to update. |
| `table` | string | Table to update (default `incident`). |
| `work_note` | string | Internal (IT-only) work note to append. |
| `comment` | string | Customer-visible comment to append. |
| `short_description`, `description`, `state`, `urgency`, `impact`, `priority`, `category`, `assignment_group`, `assigned_to`, `caller_id`, `extra` | | Same typed incident fields as `create_incident`. |

#### `get_incident`

Fetch a single record by `sys_id` or by human number (e.g. `INC0010023`, `SIR0001001`).

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | Table to read (default `incident`). |
| `sys_id` | string | Record sys_id. |
| `number` | string | Record number (e.g. `INC0010023`). |
| `fields` | string | Comma-separated fields to return. |
| `display_value` | enum | `false` / `true` / `all`. |

#### `search_incidents`

Search with a ServiceNow encoded query (`sysparm_query`), e.g. `active=true^state=2^ORDERBYDESCsys_updated_on`. Use to dedup before create or to look up existing work.

| Field | Type | Notes |
| --- | --- | --- |
| `table` | string | Table to search (default `incident`). |
| `query` | string | ServiceNow encoded query. |
| `fields` | string | Comma-separated fields to return. |
| `limit` | int | Max records (default `50`). |
| `offset` | int | Pagination offset. |
| `display_value` | enum | `false` / `true` / `all`. |

Returns `{ "count": N, "incidents": [...] }`.

### Journal, attachments, CMDB

#### `add_note`

Append an internal work note and/or a customer-visible comment to a record (default table `incident`). Journal fields **append** — they never overwrite.

| Field | Type | Notes |
| --- | --- | --- |
| `sys_id` | string | **Required.** Record sys_id. |
| `table` | string | Table name (default `incident`). |
| `note` | string | Internal (IT-only) work note. |
| `comment` | string | Customer-visible additional comment. |

#### `add_attachment`

Upload a file as an attachment on a record (default table `incident`). Set `content_base64=true` to send binary content.

| Field | Type | Notes |
| --- | --- | --- |
| `sys_id` | string | **Required.** Record sys_id. |
| `file_name` | string | **Required.** Attachment file name. |
| `table` | string | Table name (default `incident`). |
| `content_type` | string | MIME type (default `application/octet-stream`). |
| `content` | string | File content (text, or base64 when `content_base64=true`). |
| `content_base64` | bool | `true` if `content` is base64-encoded binary. |

#### `list_attachments`

List a record's attachment metadata (default table `incident`). Returns each attachment's `sys_id`, `file_name`, size and content type; pass an attachment `sys_id` to `get_attachment` to download it.

| Field | Type | Notes |
| --- | --- | --- |
| `sys_id` | string | **Required.** Record sys_id. |
| `table` | string | Table name (default `incident`). |

#### `get_attachment`

Download an attachment's bytes by its attachment `sys_id` (from `list_attachments`). Returns `content_base64`, `content_type` and `size_bytes`.

| Field | Type | Notes |
| --- | --- | --- |
| `attachment_sys_id` | string | **Required.** sys_id of the attachment record (`sys_attachment`), not the parent record. |

#### `lookup_ci`

Resolve a CMDB configuration item (asset) by name or a custom encoded query — bridges LC sensor hostnames to the ServiceNow CMDB so incidents can reference the right asset.

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | CI name to match (LIKE). |
| `query` | string | Custom encoded query (overrides `name`). |
| `class` | string | CMDB table/class (default `cmdb_ci`). |
| `limit` | int | Max records (default `50`). |

Returns `{ "count": N, "cis": [...] }`.

### Case mirroring (optional)

A bidirectional, fully-configurable recipe that keeps a [LimaCharlie Case](../limacharlie/index.md) and a ServiceNow record in sync. Mirroring is anchored on ServiceNow's purpose-built external-link fields: `correlation_id` holds the LimaCharlie case id and `correlation_display` holds the per-integration label (default `LimaCharlie`).

#### `mirror_case`

**LC → ServiceNow.** Idempotently upsert a ServiceNow record from an LC Case. Looks the record up by `correlation_id=case_id` (scoped to this integration's `correlation_display`), so repeated calls update the same record rather than creating duplicates. Wire this to a D&R rule on case events.

| Field | Type | Notes |
| --- | --- | --- |
| `case_id` | string | **Required.** LimaCharlie case id (stored as `correlation_id`). |
| `case_number` | int | LimaCharlie case number (used in the record subject, `LimaCharlie Case #N: …`). |
| `status` | enum | `new`, `in_progress`, `resolved`, `closed`. Maps to `state` (configurable via `mirror_state_map`). |
| `severity` | enum | `critical`, `high`, `medium`, `low`, `info`. Maps to `urgency`/`impact` (configurable via `mirror_severity_map`; ServiceNow derives `priority`). |
| `classification` | string | Case classification (`true_positive`, `false_positive`, `pending`); appended to the description. |
| `summary` | string | Case summary (becomes the record subject — first line, truncated to 160 chars — and description). |
| `conclusion` | string | Case conclusion (appended to description, used as `close_notes` on terminal states). |
| `assignees` | list of string | Accepted, but not currently reflected on the record. |
| `tags` | list of string | Appended to the description. |
| `table` | string | Override the configured mirror target table for this call. |
| `correlation_display` | string | Override the `correlation_display` label for this mirror. |
| `sync_note` | string | Optional work note to record the sync on the record. |
| `extra` | object | Raw fields merged into (and overriding) the mapped record fields. |

Default mappings applied (all overridable via config):

- Status → `state`: `new` → 1, `in_progress` → 2, `resolved` → 6, `closed` → 7. Terminal states (Resolved/Closed) also set `close_code` (from config) and `close_notes`.
- Severity → `urgency`/`impact`: `critical` → 1/1, `high` → 1/2, `medium` → 2/2, `low` and `info` → 3/3.

Returns `{ "created": bool, "sys_id": "...", "number": "...", "incident": {...} }`.

#### `pull_incident_changes`

**ServiceNow → LC.** Return records (on the mirror table, scoped to this integration's `correlation_display`) updated at/after a watermark, normalized to `{case_id, case_status, …}` ready to apply back to LC Cases. It **excludes changes made by the `integration_user`** to break echo loops, and returns a fresh `watermark` to drive the next pull. Drive it from a D&R `schedule` rule (e.g. every 12h per org) and pass the watermark back as rule state.

| Field | Type | Notes |
| --- | --- | --- |
| `since` | string | ServiceNow datetime watermark (`YYYY-MM-DD HH:MM:SS`, UTC). Empty bootstraps from the most recent changes (newest first); pass the returned watermark back to move forward. |
| `limit` | int | Max records (default `100`). |
| `include_own_changes` | bool | Disable the echo-loop guard (include changes by the integration user). |

Returns `{ "count": N, "changes": [...], "watermark": "YYYY-MM-DD HH:MM:SS" }`. Each change carries `sys_id`, `number`, `case_id` (from `correlation_id`), `state`, a normalized `case_status` (`new` / `in_progress` / `resolved` / `closed` — On Hold maps to `in_progress`, Canceled to `closed`), `short_description`, `sys_updated_on`, and `sys_updated_by`.

> The watermark boundary is **inclusive** (≥ `since`), so de-dupe applied changes by `sys_id`, and keep `limit` above the largest expected same-second burst of updates.

#### Wiring up the bidirectional sync

Both directions are driven from D&R rules — the extension holds no schedule of its own:

- **LC → ServiceNow**: a D&R rule on Case events calls `mirror_case` with the case fields, pushing changes as they happen.
- **ServiceNow → LC**: a scheduled D&R rule periodically calls `pull_incident_changes`, passing back the watermark from the previous run, and applies the returned changes to Cases.

Because `pull_incident_changes` excludes the integration user's own writes, the LC → SN → LC round trip does not re-import what the extension itself mirrored.

## Detection & Response

Example response action that opens a ServiceNow incident for a detection:

```yaml
- action: extension request
  extension action: create_incident
  extension name: ext-servicenow
  extension request:
    short_description: '{{ .cat }} - {{ .routing.hostname }}'
    description: '{{ .event }}'
    urgency: 2
    impact: 2
    table: '{{ "incident" }}'
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context, so the freshly-created `sys_id` is not available to a subsequent action in the same rule. Workflows that need to chain (open a record, then attach a file, then add a note) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold the `sys_id` between calls.

To append triage findings on an existing record (for example from a Playbook or AI agent that already knows the `sys_id`), use `add_note`:

```yaml
- action: extension request
  extension action: add_note
  extension name: ext-servicenow
  extension request:
    sys_id: '{{ "a1b2c3d4e5f6..." }}'
    note: '{{ .routing.hostname }}: suspicious process tree observed. See LC for details.'
```

## Notes

- The extension is **stateless** — mirroring state lives in ServiceNow (`correlation_id`) and the returned `watermark`; there is no database.
- Reference fields (`assignment_group`, `assigned_to`, `caller_id`) take **sys_ids**, not display names — display names are not auto-resolved. Use `query_table` against `sys_user` / `sys_user_group` to resolve a name to its sys_id first.
- ServiceNow rate limiting (`429`) is honored once per request with a `Retry-After` cap of 5 seconds; a persistent `429` surfaces to the caller.
- A business rule or data policy abort surfaces as an error either way: ServiceNow may return a non-2xx status (e.g. `403`) or, for some aborts, HTTP `200` with a `{"status": "failure"}` envelope. The extension treats both as errors, never as success. (A common cause is resolving a record with a `close_code` that isn't in the instance's choice list — see the `close_code` config note above.)
- `correlation_id` and `correlation_display` values are sanitized (encoded-query delimiters stripped) on both the write and the lookup path, keeping upserts idempotent even for hostile values.
- The OAuth access token is cached and renewed via `refresh_token` (in `oauth_password` mode). Rotating the secret in Secrets Manager evicts the cached client on the next surfaced `401`.
- `pull_incident_changes` only breaks echo loops if `integration_user` is set to the user the extension authenticates as.
- Errors are surfaced as `servicenow api <status> on <path>: <message>`.
