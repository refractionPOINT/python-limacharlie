# Check Point Harmony

## Overview

This Adapter ingests events from [Check Point Harmony](https://www.checkpoint.com/harmony/) into LimaCharlie via the Infinity Portal APIs. Two independent sources are supported:

- **Infinity Events** — the unified Logs-as-a-Service stream covering Harmony Endpoint, Harmony Email & Collaboration, Harmony Mobile, Harmony Connect, and Harmony Browse.
- **Entities** — polls the Harmony Email & Collaboration (HEC) `search/query` entity API. A single source that runs a list of *named queries*: each query is one server-side-filtered feed. Restore requests on quarantined mail, recipient/subject/DLP watches, and the unfiltered email firehose are all expressed as different queries on the same engine — no Go code changes needed to add a new scenario.

Both sources share a single set of Infinity Portal API credentials. At least one source must be enabled or the adapter will refuse to start.

A previous `emails` firehose source has been folded into `entities` as a preset. See [Migrating from `emails`](#migrating-from-emails) below.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `harmony`

**Top-level credentials (always required):**

- `client_id`: Infinity Portal Client ID. Create under *Global Settings → API Keys*. For Infinity Events the key must include the *Logs as a Service* service; for the Entities source it must include the *Harmony Email & Collaboration* service. A single key with both services attached is supported.
- `access_key`: Infinity Portal Access Key paired with the Client ID above.
- `url` *(optional)*: Infinity Portal gateway base URL. Defaults to `https://cloudinfra-gw.portal.checkpoint.com`. Use the regional variant (for example `https://cloudinfra-gw-us.portal.checkpoint.com`) if your tenant lives in a regional data center. Both `/app/laas-logs-api` and `/app/hec-api` share the same hostname per region.

All duration fields below are parsed with [`time.ParseDuration`](https://pkg.go.dev/time#ParseDuration) — for example `"60s"`, `"5m"`, `"1h30m"`, `"360h"`.

**`events` block — Infinity Events source:**

- `events.enabled`: set to `true` to turn the source on.
- `events.cloud_services` *(optional)*: list of cloud services to pull events for. Names must match the gateway exactly — the Email service is `Harmony Email & Collaboration` (ampersand, not the word "and"), and the gateway rejects the "and" spelling. Defaults to the full Harmony suite: `Harmony Endpoint`, `Harmony Email & Collaboration`, `Harmony Mobile`, `Harmony Connect`, `Harmony Browse`.
- `events.filter` *(optional)*: Infinity Events query filter applied to every cloud service.
- `events.poll_interval` *(optional)*: polling cadence. Defaults to `60s`.
- `events.page_limit` *(optional)*: page size for the records-retrieval API. Defaults to `100`. The gateway rejects values below `10` with HTTP 400.
- `events.limit` *(optional)*: cap on records returned per cloud service per poll. Defaults to `5000`.

If a configured `cloud_service` is not provisioned for the tenant the gateway returns the query in state `Canceled`; the adapter logs one warning per poll and keeps going (it does not surface as an error). Remove the service from `cloud_services` to silence the warning.

**`entities` block — HEC entity-query source:**

- `entities.enabled`: set to `true` to turn the source on.
- `entities.queries`: list of named queries. Each entry is one independent feed with its own dedup state and its own `_lc_harmony_query` annotation downstream.

Each `entities.queries` entry supports the following fields:

| Field | Default | Notes |
| --- | --- | --- |
| `name` | — (required) | Identifier for the feed. Must be unique within `entities.queries`. Appears in errors and as `_lc_harmony_query`. |
| `saas` | `[office365_emails, google_mail]` | SaaS platforms to query, each independently. Only `office365_emails` and `google_mail` are supported. |
| `filter` | `[]` | List of `{attr, op, value}` predicates passed through as `entityExtendedFilter`. ANDed by the gateway. Empty is allowed (then the query is bounded only by the entity window and, in cursor mode, the injected cursor predicate). |
| `cursor_field` | `""` | Empty → window mode. Set to `entityPayload.<k>` or `entityInfo.<k>` (must reference a timestamp-typed field) → cursor mode. See [Two cursor modes](#two-cursor-modes) below. |
| `include_splits` | `false` | If `true`, ship `entityPayload.emailSplit == "split"` master records alongside their child copies (firehose semantics). Default skips them so a single email isn't double-emitted per query. |
| `lookback` | `1h` (window) / `360h` (cursor) | Floor on `entityFilter.startDate` (received time). Duration string. |
| `initial_lookback` | `1h` | Cursor mode only: how far back the cursor starts on the first poll. Duration string. |
| `poll_interval` | `5m` | Time between polls. Duration string. |

Each predicate in `filter` is one server-side `entityExtendedFilter` clause:

```yaml
filter:
  - {attr: <saasAttrName>, op: <saasAttrOp>, value: "<saasAttrValue>"}
```

`attr` is a Check Point [saasAttrName](https://sc1.checkpoint.com/documents/Harmony_Email_and_Collaboration_API_Reference/Topics-HEC-Avanan-API-Reference-Guide/Managing-Secured-Entities/Search-query.htm) (e.g. `entityPayload.subject`, `entityPayload.recipients`, `entityPayload.isRestoreRequested`). `op` is one of `is`, `isNot`, `contains`, `notContains`, `startsWith`, `isEmpty`, `isNotEmpty`, `greaterThan`, `lessThan`. `value` is a string; booleans are spelled as the string `"true"` / `"false"`. Unknown ops are rejected at startup so a typo fails loudly instead of silently matching nothing.

#### Two cursor modes

| Mode | When to use | `entityFilter` sent | Cursor |
| --- | --- | --- | --- |
| **Window mode** (`cursor_field` empty) | The matching email is itself recent — content/recipient/detection filters, or the unfiltered firehose. | `saas` + `startDate` + `endDate` + `saasEntity` (received-time window). | Rolling window + dedup. |
| **Cursor mode** (`cursor_field` set) | The event of interest is decoupled in time from the email's receipt — e.g. a restore request on an old quarantined email. | `saas` + wide `startDate` only — no `endDate`, no `saasEntity`. | Adapter auto-injects `{cursor_field} greaterThan {cursor}` and advances `cursor` to the newest value seen. |

A *filtered* query (non-empty `filter`) is bounded server-side by the predicates, so it scales independently of total mail volume. The **unfiltered firehose preset** (window mode, no `filter`, `include_splits: true`) is the exception: it is bounded only by the received-time window, so on a very high-volume tenant a long `lookback` can hit the gateway's per-query record ceiling (~10,000 records, oldest-first). Keep `lookback` short for that preset (the 1h default is intentional), or use a filtered query.

> **Restore requests require cursor mode.** A window-mode query (or the firehose preset) cannot surface a restore request. The window filters on the email's *received* time, but the underlying quarantined email may have been received hours, days, or months before the restore was requested — so it isn't in any recent received-time window. Use the `restore_requests` preset below.

#### Annotations

Every record carries adapter-added annotations to make routing easy downstream:

- `_lc_harmony_source` — `infinity_events` or `entities`.
- `_lc_harmony_service` — the Infinity Events cloud service (events source only).
- `_lc_harmony_query` — the entities query's `name` (entities source only).
- `_lc_harmony_saas` — the HEC SaaS platform (entities source only).

#### Example presets

Quarantined-email restore requests — canonical cursor-mode preset, mirrors Check Point's own XSOAR `restore_requests`:

```yaml
harmony:
  entities:
    enabled: true
    queries:
      - name: restore_requests
        saas: [office365_emails, google_mail]
        filter:
          - {attr: entityPayload.isRestoreRequested, op: is, value: "true"}
        cursor_field: entityPayload.restoreRequestTime
        lookback: 360h          # 15 days — how old the underlying email may be
        initial_lookback: 1h    # how far back the cursor starts on first poll
        poll_interval: 5m
```

Email firehose (window mode, no filter, splits included) — equivalent to the old `emails` source:

```yaml
harmony:
  entities:
    enabled: true
    queries:
      - name: emails
        saas: [office365_emails, google_mail]
        include_splits: true
        lookback: 1h
        poll_interval: 5m
```

Subject / sender watch (window mode):

```yaml
harmony:
  entities:
    enabled: true
    queries:
      - name: invoice_subject_watch
        saas: [office365_emails]
        filter:
          - {attr: entityPayload.subject,    op: contains, value: "INVOICE"}
          - {attr: entityPayload.fromDomain, op: is,       value: "example.com"}
        lookback: 1h
        poll_interval: 5m
```

Multiple queries can be listed under one source — each runs independently, with its own dedup state and its own `_lc_harmony_query` annotation.

### CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page. The adapter accepts dot-notation flags for the nested `events.*` and `entities.*` fields; `entities.queries` is passed as a single JSON string.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter harmony client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
client_id=$CHECKPOINT_CLIENT_ID \
access_key=$CHECKPOINT_ACCESS_KEY \
events.enabled=true \
'events.cloud_services=Harmony Endpoint,Harmony Email & Collaboration' \
entities.enabled=true \
'entities.queries=[{"name":"restore_requests","filter":[{"attr":"entityPayload.isRestoreRequested","op":"is","value":"true"}],"cursor_field":"entityPayload.restoreRequestTime","lookback":"360h","initial_lookback":"1h","poll_interval":"5m"}]'
```

### Infrastructure as Code Deployment

```yaml
# For cloud sensor deployment, store credentials as hive secrets:
#
#   client_id: "hive://secret/checkpoint-harmony-client-id"
#   access_key: "hive://secret/checkpoint-harmony-access-key"

sensor_type: "harmony"
harmony:
  client_id: "hive://secret/checkpoint-harmony-client-id"
  access_key: "hive://secret/checkpoint-harmony-access-key"
  # Optional: regional gateway (defaults to the global one if omitted)
  # url: "https://cloudinfra-gw-us.portal.checkpoint.com"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_HARMONY"
    hostname: "checkpoint-harmony-adapter"
    platform: "json"
    sensor_seed_key: "checkpoint-harmony-sensor"
    mapping:
      event_type_path: "_lc_harmony_source"
      event_time_path: "time"
    indexing: []
  events:
    enabled: true
    # Optional — defaults to the full Harmony suite if omitted
    cloud_services:
      - "Harmony Endpoint"
      - "Harmony Email & Collaboration"
      - "Harmony Mobile"
      - "Harmony Connect"
      - "Harmony Browse"
  entities:
    enabled: true
    queries:
      - name: restore_requests
        saas: [office365_emails, google_mail]
        filter:
          - {attr: entityPayload.isRestoreRequested, op: is, value: "true"}
        cursor_field: entityPayload.restoreRequestTime
        lookback: 360h
        initial_lookback: 1h
        poll_interval: 5m
```

## Configuring a Check Point Harmony Adapter in the Web UI

### Preparing Infinity Portal credentials

1. Sign in to the [Infinity Portal](https://portal.checkpoint.com/) with an account that can manage API keys.
2. Navigate to *Global Settings → API Keys → New*.
3. Attach the services your adapter needs:
    - *Logs as a Service* for the Infinity Events source.
    - *Harmony Email & Collaboration* for the Entities source.
    - A single key with both services attached is fine.
4. Copy the resulting **Client ID** and **Access Key**. The Access Key is shown only once — save it somewhere safe.
5. Note the **Authentication URL** shown next to the key. If it points at a regional gateway (`cloudinfra-gw-us.portal.checkpoint.com`, `cloudinfra-gw-eu.portal.checkpoint.com`, etc.) you will need to supply that hostname as the adapter's `url` value.

### Setting up the Adapter

Within the LimaCharlie web application, select `+ Add Sensor`, and then choose **Check Point Harmony**.

Pick or create an Installation Key for this adapter, then fill in the form:

| Field | Value |
| --- | --- |
| Client ID | Infinity Portal Client ID |
| Access Key | Infinity Portal Access Key |
| URL | *(optional)* Regional gateway base URL, if your tenant is not on the global gateway |
| Events Enabled | Toggle on to ingest Infinity Events. Defaults to on. |
| Events Cloud Services | *(optional)* Comma-separated cloud services. Leave blank for the full Harmony suite. |
| Events Filter | *(optional)* Infinity Events query filter |
| Entities Enabled | Toggle on to poll the HEC entity-query source |
| Entities Queries | *(optional)* JSON array of named entity queries — see [Adapter-specific Options](#adapter-specific-options) above for the schema and presets. |

At least one of *Events Enabled* or *Entities Enabled* must be on or the adapter will refuse to start.

Click `Complete Cloud Installation`. LimaCharlie will authenticate against the Infinity Portal and begin polling.

## Sample Rule

When ingested, Harmony events can be referenced directly in D&R rules. The adapter annotates every record with `_lc_harmony_source` so you can pivot on the originating API, and entities records additionally carry `_lc_harmony_query` so you can route per query:

```yaml
# Detection — flag restore requests from the entities source
event: harmony_record
op: and
rules:
  - op: is
    path: event/_lc_harmony_source
    value: entities
  - op: is
    path: event/_lc_harmony_query
    value: restore_requests

# Response
- action: report
  name: Harmony Restore Request
```

For the unfiltered firehose query, narrow the detection on the verdict/lifecycle fields carried inline on each entity (under `event/entityInfo` and the entity payload) to match only the cases you care about — for example a quarantined message or a declined restore request.

## Migrating from `emails`

The previous `emails` source has been removed. Adapter configs carrying `harmony.emails: {enabled: true}` will fail Validate at startup with a clear message pointing to this guide.

**Before:**

```yaml
harmony:
  emails:
    enabled: true
    saas: [office365_emails, google_mail]
    lookback: 1h
    poll_interval: 5m
```

**After:**

```yaml
harmony:
  entities:
    enabled: true
    queries:
      - name: emails              # pick any name; appears as _lc_harmony_query
        saas: [office365_emails, google_mail]
        include_splits: true      # matches the old firehose semantics
        lookback: 1h
        poll_interval: 5m
```

Downstream rules / dashboards that filter on `_lc_harmony_source: emails` need to be updated to filter on `_lc_harmony_source: entities` (plus optionally `_lc_harmony_query: emails` if you want to scope to this specific feed).

## API Docs

- Infinity Events (Logs-as-a-Service): [Check Point Infinity Events Reference](https://app.swaggerhub.com/apis-docs/Check-Point/infinity-events)
- Harmony Email & Collaboration entity API: [HEC API Reference](https://sc1.checkpoint.com/documents/Infinity_Portal/WebAdminGuides/EN/Harmony-Email-and-Collaboration-Admin-Guide/Default.htm)
- HEC `search/query` endpoint: [Search query reference](https://sc1.checkpoint.com/documents/Harmony_Email_and_Collaboration_API_Reference/Topics-HEC-Avanan-API-Reference-Guide/Managing-Secured-Entities/Search-query.htm)
- Infinity Portal authentication: [Infinity Portal API Authentication](https://app.swaggerhub.com/apis-docs/Check-Point/infinity-portal-auth/1.0)
