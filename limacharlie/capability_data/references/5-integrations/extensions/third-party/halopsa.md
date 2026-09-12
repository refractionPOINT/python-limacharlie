# HaloPSA

[HaloPSA](https://halopsa.com/) is a professional services automation platform used by MSPs for ticketing, asset management, and time tracking.

The HaloPSA LimaCharlie Extension exposes outbound HaloPSA actions to D&R rules and AI agents: ticket lifecycle (create/update/search), notes and billable time entries, asset linkage from LC sensor telemetry to the MSP CMDB, and client/site lookup.

## Setup

### 1. Create a HaloPSA API application

In HaloPSA, create an API application (under **Configuration → Integrations → HaloPSA API**) and configure it for the OAuth2 `client_credentials` flow:

- **Authentication Method:** Client ID and Secret (Services)
- **Login Type:** Log on as **Agent** — pick the HaloPSA agent that should own the tickets, actions, and assets this extension creates.
- **Permissions:** grant `edit:tickets`, `edit:assets`, `read:customers`

These three scopes are the verified least-privilege set for the six actions below:

- `edit:tickets` covers `create_ticket`, `update_ticket`, `search_tickets`, and `add_action`. Actions are a HaloPSA ticket sub-resource — there is no separate `read:actions` or `edit:actions` scope (the HaloPSA token endpoint rejects them as `invalid_scope`).
- `edit:assets` covers asset lookup and the create-if-missing path in `link_asset_to_ticket`.
- `read:customers` covers `lookup_client_site` for both clients *and* sites (sites are a customer sub-resource). The extension never writes clients or sites, so `edit:customers` is not required.

If you'd rather not enumerate scopes, the extension's default of `all` also works.

Copy the **Client ID** and **Client Secret** — you will need them in the next step. Refer to HaloPSA's own product documentation for the current UI path; the labels above may differ slightly across HaloPSA versions.

### 2. Subscribe to the extension

Subscribe to `ext-halopsa` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### 3. Store the client secret

In **Secrets Manager**, create a new secret (for example `halopsa-client-secret`) and paste the HaloPSA Client Secret as its value.

### 4. Configure the extension

In **Extensions → ext-halopsa → Configuration**, fill in:

| Field | Value |
| --- | --- |
| `instance_url` | Your HaloPSA tenant URL, e.g. `https://acme.halopsa.com` |
| `client_id` | The Client ID from step 1 |
| `client_secret` | A reference to the secret created in step 3, e.g. `hive://secret/halopsa-client-secret` |
| `tenant` | (optional) Tenant identifier — only needed on shared-auth hosted deployments |
| `scope` | (optional) OAuth2 scopes (space-separated). Defaults to `all`. |

The configuration is validated at save time against `instance_url`, `client_id`, and `client_secret`. If the OAuth2 token cannot be obtained, requests will surface a `401` from the upstream HaloPSA API.

## Actions

The extension exposes six actions, all accepting a JSON request body when invoked from a D&R rule via `extension request`.

### `create_ticket`

Open a new ticket. Only `summary` is required.

| Field | Type | Notes |
| --- | --- | --- |
| `summary` | string | **Required.** Ticket subject line. |
| `details` | string | Ticket body. |
| `client_id` | int | HaloPSA client (company) id. |
| `site_id` | int | HaloPSA site id. |
| `user_id` | int | End-user id (ticket requester). |
| `agent_id` | int | Agent id (assignee). |
| `team` | string | Team name. |
| `tickettype_id` | int | Ticket type id (Incident, Change, …). |
| `priority_id` | int | Priority id. |
| `status_id` | int | Initial status id. |
| `impact` | int | ITIL impact (1=high … 4=low). |
| `urgency` | int | ITIL urgency (1=high … 4=low). |
| `category_1` | string | Top-level category. |
| `parent_id` | int | Parent ticket id (for sub-tickets). |
| `asset_ids` | list of int | Asset ids to attach. |
| `customfields` | list of object | Each entry `{name\|id, value}`. |
| `extra` | object | Raw HaloPSA ticket fields to merge into the request — escape hatch for fields not modeled above. |

Returns the created ticket, including its assigned `id`.

### `update_ticket`

Update an existing ticket. Use to change status (which drives HaloPSA status → outcome → workflow transitions), reassign, set priority, or set the linked assets.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | int | **Required.** Ticket id to update. |
| `summary` | string | New summary. |
| `details` | string | New body. |
| `status_id` | int | New status id. |
| `agent_id` | int | New assignee. |
| `priority_id` | int | New priority. |
| `asset_ids` | list of int | **Replaces** the ticket's asset list. Use `link_asset_to_ticket` to merge a new asset into the existing list. |
| `customfields` | list of object | Custom fields to set. |
| `extra` | object | Raw HaloPSA ticket fields to merge. |

### `search_tickets`

Search/list tickets. Useful to deduplicate before creating, or to look up existing work for an asset.

| Field | Type | Notes |
| --- | --- | --- |
| `search` | string | Free-text search across ticket summary/details. |
| `client_id` | int | Restrict to a client. |
| `agent_id` | int | Restrict to an assignee. |
| `status_ids` | string | Comma-separated status ids. |
| `tickettype_id` | int | Restrict to a ticket type. |
| `page_size` | int | Default `50`. |
| `page_no` | int | Default `1` (1-based). |
| `order` | string | Order-by field (e.g. `id`). |
| `orderdesc` | bool | Descending order. |

Returns `{ "record_count": N, "tickets": [...] }`.

### `add_action`

Append a HaloPSA Action to a ticket: a private note (agents only) or a public reply (visible to the end-user), optionally with billable time. Useful for AI agents to record triage findings and log work time.

| Field | Type | Notes |
| --- | --- | --- |
| `ticket_id` | int | **Required.** Ticket id to append to. |
| `note` | string | **Required.** Note/reply content. |
| `hiddenfromuser` | bool | `true` (default) = private; `false` = public reply. |
| `timetaken` | int | Time taken on this action (whole hours only). For fractional hours, pass via `extra.timetaken`. |
| `actionchargehours` | int | Billable hours (whole hours only). For fractional hours, pass via `extra.actionchargehours`. |
| `outcome` | string | Outcome label (drives HaloPSA workflow transitions). Defaults to `Note`. |
| `extra` | object | Raw HaloPSA action fields to merge. |

> Defaults to **private** (`hiddenfromuser=true`) to avoid accidentally pushing security notes to end-users. Set `hiddenfromuser: false` explicitly for a public reply.

### `link_asset_to_ticket`

Resolve a hostname to a HaloPSA asset under the given client/site, optionally creating the asset if missing, and attach it to the ticket. Bridges LC sensor telemetry to the MSP CMDB.

| Field | Type | Notes |
| --- | --- | --- |
| `ticket_id` | int | **Required.** Ticket id to link the asset to. |
| `hostname` | string | **Required.** Hostname to resolve (matched via `inventory_number` / `key_field`). |
| `client_id` | int | Required when the asset must be created. |
| `site_id` | int | Used on asset create. |
| `asset_type_id` | int | Required when the asset must be created (HaloPSA rejects asset creates without an asset type). |
| `create_if_missing` | bool | If `true` (default), create the asset when no match is found. |

Returns `{ "asset_id": N, "asset_created": bool, "asset": {...}, "ticket": {...} }`. The link is idempotent — re-running against an already-linked asset will not produce duplicates.

### `lookup_client_site`

Resolve a HaloPSA client or site id from a name. Useful as plumbing for AI agents that need to map an LC org to a Halo client.

| Field | Type | Notes |
| --- | --- | --- |
| `type` | enum | **Required.** `client` or `site`. |
| `search` | string | Name match. |
| `client_id` | int | Restrict sites to a client (only when `type=site`). |
| `page_size` | int | Default `50`. |
| `page_no` | int | Default `1`. |

Returns `{ "record_count": N, "clients": [...] }` or `{ "record_count": N, "sites": [...] }` depending on `type`.

## Detection & Response

Example response action that opens a HaloPSA ticket for a detection:

```yaml
- action: extension request
  extension action: create_ticket
  extension name: ext-halopsa
  extension request:
    summary: '{{ .cat }} - {{ .routing.hostname }}'
    details: '{{ .event }}'
    client_id: 12
    site_id: 18
    tickettype_id: 1
    priority_id: 3
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context, so the freshly-created ticket id is not available to a subsequent action in the same rule. Workflows that need to chain (open a ticket, then link an asset, then add a note) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold the ticket id between calls.

To append triage findings on an existing ticket (for example from a Playbook or AI agent that already knows the ticket id), use `add_action`:

```yaml
- action: extension request
  extension action: add_action
  extension name: ext-halopsa
  extension request:
    ticket_id: 2884
    note: '{{ .routing.hostname }}: suspicious process tree observed. See LC for details.'
    hiddenfromuser: true
    timetaken: 1
    outcome: '{{ "Note" }}'
```

## Notes

- The OAuth2 access token returned by HaloPSA is cached per `(org, instance_url, client_id, secret)` for the lifetime of a client. Rotating the secret in the Secrets Manager evicts the cached client on the next surfaced `401`.
- `actionchargehours` will only result in a billable charge if the tenant has a charge rate configured for the agent posting the action; otherwise HaloPSA accepts the value but reports `Charge Rate: No Charge`.
- HaloPSA represents a ticket's main body as the first entry in its action timeline — `update_ticket.details` replaces that first entry rather than mutating a separate body field.
