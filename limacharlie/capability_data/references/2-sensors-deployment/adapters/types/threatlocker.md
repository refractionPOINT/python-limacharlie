# ThreatLocker

## Overview

This Adapter ingests events from the [ThreatLocker](https://threatlocker.com) Portal API into LimaCharlie. Events are forwarded in their original ThreatLocker JSON form — the adapter does not reshape payloads.

The adapter is **generic by design**. The ThreatLocker Portal API is uniform: every queryable resource exposes a `<Resource>GetByParameters` endpoint that takes a `POST` with a JSON filter body. The adapter models each such endpoint as a *feed* — adding a new event type is a configuration change, not a code change.

It pairs naturally with the [ThreatLocker extension](../../../5-integrations/extensions/third-party/threatlocker.md): the adapter delivers Application Control approval-request events into LimaCharlie, and the extension provides the actions an AI agent (or a Playbook) calls to enrich those events and write the decision back.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `threatlocker`

| Key | Required | Description |
| --- | --- | --- |
| `api_key` | yes | ThreatLocker API token (see [Authentication](#authentication) below). Sent verbatim in the `Authorization` header — no `Bearer` prefix. |
| `instance` | yes* | ThreatLocker instance letter (`b`, `c`, …, `g`, `h`, …). *Required unless `base_url` is set. |
| `base_url` | no | Full API root override, e.g. `https://portalapi.g.threatlocker.com/portalapi`. Use to point the adapter at a non-standard endpoint; otherwise prefer `instance`. |
| `managed_organization_id` | no | UUID of the managed (child) organization. Sent as the `managedOrganizationId` header — used by MSP **parent** tokens to scope every request to a specific child tenant. |
| `feeds` | no | List of feeds to poll (see [Feed fields](#feed-fields) below). When omitted the adapter polls the three default feeds described under [Default feeds](#default-feeds). |
| `page_size` | no | Records per page. Default `100`, maximum `1000`. |
| `poll_interval` | no | Wait between polls of a feed, as a Go duration in **nanoseconds**. Default `60000000000` (1 minute). |
| `dedupe_ttl` | no | How long a record id is remembered to suppress re-shipping. Default 7 days. |
| `retry_base_delay` / `max_retry_delay` / `max_retry_attempts` | no | Transient-failure retry tuning. |

### Feed fields

Each entry in `feeds` describes one ThreatLocker `*GetByParameters` endpoint to poll.

| Key | Required | Description |
| --- | --- | --- |
| `name` | yes | Labels the feed and becomes the `EventType` of every shipped event. Must be unique within `feeds`. |
| `url` | yes | API path of the `*GetByParameters` endpoint, **relative to the API root** (e.g. `ApprovalRequest/ApprovalRequestGetByParameters`). |
| `parameters` | no | JSON object merged into the request body — resource-specific filters such as `statusId`, `showChildOrganizations`, ThreatLocker query DTOs. |
| `order_by` | no | Sort field. Default `dateTime`. The default request is newest-first (`isAscending = false`). |
| `items_path` | no | Key holding the records array when the response is an object envelope. Auto-detected (`data`, `pageItems`, …) when empty. |
| `timestamp_field` | no | Path to the record's event time, supports `/`-separated nested paths. Default `dateTime`. |
| `id_field` | no | Path to the record's stable identifier, used for deduplication. Falls back to common id fields, then a content hash. |
| `max_pages` | no | Caps pages fetched per poll. Default `100`. |
| `window` | no | When set (e.g. `5m`), rewrites `startDate` / `endDate` in the request body on every poll to a rolling `[now-window-poll_interval, now]` range. **Required** for endpoints that mandate a date range (`ActionLog`, `SystemAudit`). The overlap with the previous poll is absorbed by the deduper. |
| `start_date_field` / `end_date_field` | no | Override the request-body field names used by `window`. Defaults: `startDate` / `endDate`. |

### Default feeds

With no `feeds` configured, the adapter polls three feeds that together cover ThreatLocker's primary telemetry surfaces:

| Default feed | ThreatLocker endpoint | What it carries |
| --- | --- | --- |
| `approval_request` | `ApprovalRequest/ApprovalRequestGetByParameters` (`statusId = 1`) | Pending Application Control whitelist requests — one event per new request, shipped exactly once. The intended input to AI-driven triage via the [ThreatLocker extension](../../../5-integrations/extensions/third-party/threatlocker.md). |
| `unified_audit` | `ActionLog/ActionLogGetByParametersV2` | The **Unified Audit** — ThreatLocker's combined event stream of `execute` / `install` / `network` / `registry` / `read` / `write` / `move` / `delete` / `baseline` / `powershell` / `elevate` / web activity across every module. Polled on a 5-minute rolling window. |
| `system_audit` | `SystemAudit/SystemAuditGetByParameters` | Portal / administrator activity — logins, policy edits, approval decisions, organization changes. Polled on a 5-minute rolling window. |

`unified_audit` and `system_audit` both *require* a `startDate`/`endDate` filter on every request; the adapter sets those automatically via the feed's `window`. The overlap between consecutive windows is absorbed by the per-feed deduper, preserving at-least-once delivery semantics.

## Authentication

Create an API token under **Portal → Administration → API Users** in the ThreatLocker Portal. The token is sent verbatim in the `Authorization` header — there is no `Bearer` prefix and no OAuth handshake.

### Finding your instance

ThreatLocker hosts each tenant on one of several lettered instances (`b`, `c`, `d`, …, `g`, `h`, …) and API tokens are scoped to the instance that minted them. To find yours, open the ThreatLocker Portal, click the **Help** button in the top-right corner of any page, and read the letter in parentheses next to **ThreatLocker Access** (e.g. `ThreatLocker Access (C)` → `instance: c`).

> ⚠️ **A token from one instance returns `403 TOKEN_REVOKED` on every other instance** — the API does not distinguish "wrong instance" from a genuinely revoked token. If you are confident the token is active and still see `TOKEN_REVOKED`, double-check the instance letter before assuming the token was revoked. An authentication failure stops the adapter so the misconfiguration is surfaced loudly.

## How polling works

On every poll the adapter walks a feed's pages (`pageNumber` / `pageSize`) until the result set is exhausted (a short or empty page) or the feed's `max_pages` cap is reached. An in-memory deduper, keyed per feed, guarantees each record is shipped to LimaCharlie exactly once even though pages are re-fetched on every poll.

Transient API failures (HTTP 5xx, 429, network errors) are retried with exponential backoff. An authentication failure (401/403) stops the adapter rather than burning the token via repeated retries.

The adapter deliberately re-walks every page rather than stopping at the first page of already-seen records: the Portal API paginates by offset over a live, mutable list, so a record can shift across a page boundary between two page fetches. Re-walking costs more requests but is correct.

For a large or high-churn feed, bound each poll's work with the feed's `parameters` (e.g. a date-range filter) and a `max_pages` that comfortably exceeds the feed's expected size. Querying newest-first (`isAscending = false`, the default) keeps the most recent records when `max_pages` truncates.

## CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page. The defaults are usually sufficient — supplying `api_key` and `instance` is enough to pull the three default feeds.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter threatlocker \
  client_options.identity.oid=$OID \
  client_options.identity.installation_key=$INSTALLATION_KEY \
  client_options.platform=json \
  client_options.sensor_seed_key=threatlocker \
  api_key=$THREATLOCKER_API_TOKEN \
  instance=g
```

## Infrastructure as Code Deployment

```yaml
# For cloud sensor deployment, store credentials as hive secrets:
#
#   api_key: "hive://secret/threatlocker-api-token"

sensor_type: "threatlocker"
threatlocker:
  api_key: "hive://secret/threatlocker-api-token"
  instance: "g"
  # Optional: MSP parent tokens — scope every request to a child tenant
  # managed_organization_id: "00000000-0000-0000-0000-000000000000"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_THREATLOCKER"
    hostname: "threatlocker-adapter"
    platform: "json"
    sensor_seed_key: "threatlocker-sensor"
    mapping:
      event_type_path: "_lc_threatlocker_feed"
      event_time_path: "dateTime"
    indexing: []
```

### Custom feeds

Override `feeds` to add new feeds or replace the defaults entirely. The list is **replacing**, not merging — re-declare the defaults you want to keep alongside any custom feed.

The example below keeps the three defaults and adds a fourth feed that ships *denied* approval requests:

```yaml
threatlocker:
  api_key: "hive://secret/threatlocker-api-token"
  instance: "g"
  feeds:
    - name: approval_request
      url: ApprovalRequest/ApprovalRequestGetByParameters
      parameters:
        statusId: 1            # pending
        showChildOrganizations: false
      id_field: approvalRequestId
    - name: unified_audit
      url: ActionLog/ActionLogGetByParametersV2
      window: 5m
      parameters:
        paramsFieldsDto: []
        groupBys: []
        exportMode: false
        showTotalCount: false
        showChildOrganizations: false
        onlyTrueDenies: false
        simulateDeny: false
      id_field: actionLogId
    - name: system_audit
      url: SystemAudit/SystemAuditGetByParameters
      window: 5m
      parameters:
        viewChildOrganizations: false
      id_field: systemAuditId
    - name: approval_request_denied
      url: ApprovalRequest/ApprovalRequestGetByParameters
      parameters:
        statusId: 3            # denied
        showChildOrganizations: false
      id_field: approvalRequestId
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_THREATLOCKER"
    platform: "json"
    sensor_seed_key: "threatlocker-sensor"
```

## Configuring a ThreatLocker Adapter in the Web UI

Within the LimaCharlie web application, select `+ Add Sensor`, then choose **ThreatLocker**.

Pick or create an Installation Key for this adapter, then fill in:

| Field | Value |
| --- | --- |
| API Key | ThreatLocker Portal API token (from *Administration → API Users*). |
| Instance | Single instance letter from *Help → ThreatLocker Access (X)*, e.g. `g`. |
| Managed Organization ID | *(optional)* Child-tenant UUID for MSP parent tokens. |
| Feeds | *(optional)* JSON / YAML array of custom feeds. Leave empty to use the three defaults. |

Click `Complete Cloud Installation`. LimaCharlie will authenticate against the Portal and begin polling.

## Sample Rule

The adapter ships each record under an `EventType` matching the feed's `name`. For the default feed set, that gives `approval_request`, `unified_audit`, and `system_audit` — so D&R rules can route directly on the feed:

```yaml
# Detection — flag every new pending approval request so an AI agent
# can pick it up and call the ext-threatlocker enrichment actions.
event: approval_request

# Response
- action: report
  name: ThreatLocker Approval Request
```

To chain enrichment + decision from a rule on this event, dispatch to a [Playbook](../../../5-integrations/extensions/limacharlie/playbook.md) or an AI agent — the [ThreatLocker extension](../../../5-integrations/extensions/third-party/threatlocker.md) page walks through the action surface.

## API Docs

- ThreatLocker Portal Swagger: `https://portalapi.<instance>.threatlocker.com/swagger` (replace `<instance>` with your tenant's instance letter).
