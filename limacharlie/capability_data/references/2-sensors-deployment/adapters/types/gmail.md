# Gmail

## Overview

This Adapter collects telemetry from one or many Gmail mailboxes using the [Gmail REST API](https://developers.google.com/workspace/gmail/api/reference/rest). Beyond incoming-email telemetry, it can collect the mailbox configuration and change signals most relevant to **Business Email Compromise (BEC)** — the mail rules, forwarding, aliases, delegates, protocol access, and deletions an intruder uses to persist, exfiltrate mail, and cover their tracks.

Each signal is an independent, opt-in **capability** that ships its own event type. They are all readable with the default `gmail.readonly` scope.

With the service-account flow the adapter can watch **many mailboxes at once** — an explicit list, or every mailbox in a Google Workspace domain via auto-discovery — and ships each mailbox to its own LimaCharlie sensor.

## Capabilities

Enable any combination with the `collect_*` flags. If you set none, the adapter defaults to message telemetry only (`collect_messages`).

| Flag | Event type(s) | What it gives you |
| --- | --- | --- |
| `collect_messages` | `gmail_message` | Incoming email as telemetry — the raw signal for phishing/lure detection. |
| `collect_filters` | `gmail_filter` | Mail rules. Attackers create rules that auto-delete, auto-forward, or hide replies about invoices/wires. |
| `collect_forwarding` | `gmail_forwarding_address`, `gmail_auto_forwarding` | Forwarding destinations and the account-wide auto-forward toggle — a classic mail-exfiltration vector. |
| `collect_send_as` | `gmail_send_as` | Send-as / "from" identities. An added identity is an impersonation/persistence signal. |
| `collect_delegates` | `gmail_delegate` | Mailbox delegates — granting a delegate is persistence. **Workspace only** (see note below). |
| `collect_imap_pop` | `gmail_imap`, `gmail_pop` | IMAP/POP access settings. Enabling these allows bulk mailbox download via a desktop client. |
| `collect_vacation` | `gmail_vacation` | The vacation responder, occasionally abused for harvesting/social engineering. |
| `collect_history` | `gmail_history` | Mailbox changes: message **deletions** and **label changes** (marking a security alert read, trashing the fraud thread). |

> **Delegates are Workspace-only.** Google exposes the delegates listing only to service-account clients with domain-wide delegation. On a consumer account (or without delegation) the call returns an error, which the adapter logs and skips — it does not stop the adapter or affect the other capabilities.

The configuration-state capabilities (filters, forwarding, send-as, delegates, IMAP/POP, vacation) are **change-only**: an item is shipped when it first appears or its content changes, and suppressed otherwise. On adapter restart the in-memory dedupe state is empty, so the current state is re-emitted once as a fresh baseline — write detections against the *state* in these events rather than treating every event as a brand-new change.

## Authentication

Choose one of two modes.

### OAuth 2.0 refresh token (a single mailbox)

For collecting one user's mailbox. Create an OAuth client (Desktop or Web) in the Google Cloud console, enable the Gmail API, and complete the authorization-code flow once to obtain a refresh token for the `gmail.readonly` scope.

| Field | Description |
| --- | --- |
| `client_id` | OAuth client id |
| `client_secret` | OAuth client secret |
| `refresh_token` | Long-lived refresh token for the mailbox owner |

### Service account with domain-wide delegation (Google Workspace)

For monitoring Workspace mailboxes without per-user consent. Create a service account, enable domain-wide delegation, and in the Workspace Admin console authorize its client id for the `https://www.googleapis.com/auth/gmail.readonly` scope.

| Field | Description |
| --- | --- |
| `service_account_credentials` | The service account JSON key, inline |
| `service_account_file` | Path to the service account JSON key file (alternative to the inline form) |
| `subject` | A single mailbox owner to impersonate, e.g. `user@yourdomain.com` |

Provide the mailbox(es) with `subject` (one), `subjects` (a list), and/or `discover_mailboxes` (the whole domain). At least one of these is required.

## Multiple mailboxes

With the service-account flow, each mailbox is impersonated independently and **shipped to its own sensor**: when more than one mailbox is collected, the sensor seed key is derived as `<sensor_seed_key>/<mailbox-address>` and the sensor hostname is set to the mailbox address.

There are two ways to enumerate mailboxes, and they can be combined (the union is collected):

- **Static list** (`subjects`): list the mailboxes explicitly — good for a fixed set of high-value mailboxes (executives, finance, AP).
- **Auto-discovery** (`discover_mailboxes`): enumerate the Workspace domain's mailboxes via the Admin SDK Directory API, re-run on `discovery_interval` (default 1h) so newly-provisioned mailboxes are picked up and deprovisioned ones dropped automatically. Suspended accounts are skipped unless `include_suspended` is set.

Auto-discovery has two extra requirements beyond the Gmail collection itself:

1. `admin_subject` — a Workspace admin user the service account impersonates for the Directory call.
2. An extra delegated scope — authorize the service account's client id for `https://www.googleapis.com/auth/admin.directory.user.readonly` in the Workspace Admin console.

If a discovery pass fails or comes back empty while mailboxes are already being collected, the current set keeps collecting (with a warning logged) — discovery never tears down working mailboxes on a transient blip.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter:

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: `gmail`.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from.

### Adapter-specific Options

Adapter Type: `gmail`

| Key | Default | Description |
| --- | --- | --- |
| `client_id` / `client_secret` / `refresh_token` | — | OAuth refresh-token flow credentials (single mailbox). |
| `service_account_credentials` / `service_account_file` | — | Service-account flow credentials (Workspace). |
| `subject` | — | Single mailbox to impersonate (service-account flow). |
| `subjects` | — | Static list of mailboxes to impersonate. |
| `discover_mailboxes` | `false` | Enumerate the domain's mailboxes via the Directory API. |
| `admin_subject` | — | Admin user impersonated for the Directory API (required with `discover_mailboxes`). |
| `customer` | `my_customer` | Directory API customer id (mutually exclusive with `domain`). |
| `domain` | — | Restrict discovery to one domain of a multi-domain Workspace. |
| `discovery_query` | — | Optional Directory API user search filter, e.g. `orgUnitPath='/Finance'`. |
| `discovery_interval` | `1h` | How often discovery re-enumerates. |
| `include_suspended` | `false` | Also collect suspended mailboxes. |
| `max_concurrent_polls` | `10` | Cap on how many mailboxes poll the Gmail API at once. |
| `collect_messages` … `collect_history` | see [Capabilities](#capabilities) | Capability toggles. |
| `settings_poll_interval` | `15m` | Cadence for the configuration-state capabilities. |
| `user_id` | `me` | Mailbox path segment for the refresh-token flow. Ignored by the service-account flow. |
| `query` | `in:inbox` | Gmail [search query](https://support.google.com/mail/answer/7190) selecting messages. A time bound is appended automatically — do not add one. |
| `scopes` | `gmail.readonly` | OAuth scopes to request. |
| `format` | `full` | Message detail: `minimal`, `full`, `raw`, or `metadata`. |
| `metadata_headers` | — | Headers to keep when `format` is `metadata`. |
| `label_ids` | — | Only list messages carrying all of these label ids. |
| `include_spam_trash` | `false` | Include SPAM and TRASH messages. |
| `max_results` | `100` | Page size for the message listing (max 500). |
| `poll_interval` | `5m` | Wait between message/history polls. |
| `overlap` | `2m` | Window backdating to avoid gaps from late-indexed mail; re-listed messages are deduped. |
| `initial_lookback` | `0` | On startup, reach back this far to backfill recent mail. |
| `dedupe_ttl` | `168h` (7d) | How long a message id is remembered to suppress re-shipping. |
| `retry_base_delay` / `max_retry_delay` / `max_retry_attempts` | `5s` / `30s` / `3` | Transient-failure retry tuning. |

## How collection works

- **Messages**: each poll lists message ids matching `query` over a rolling time window, fetches each message at the configured `format`, and forwards the full message resource verbatim. A deduper keyed on the immutable Gmail message id guarantees each message ships exactly once despite overlapping windows. The event timestamp is the message's `internalDate`.
- **Configuration state**: polled on `settings_poll_interval`; only appearances and changes are shipped.
- **History**: the first run records a baseline `historyId` and ships nothing; later polls list forward from the cursor, filtered to deletions and label changes. Gmail retains history for roughly a week — if the cursor ages out, the adapter re-baselines and resumes rather than stopping.
- **Errors**: `401` triggers one transparent token refresh; `429`/`5xx`/`403` rate-limit errors are retried with backoff; persistently rejected credentials stop that mailbox's collector (other mailboxes are unaffected); a failing BEC capability is logged and skipped without affecting the others.

## CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter gmail \
  client_options.identity.oid=$OID \
  client_options.identity.installation_key=$INSTALLATION_KEY \
  client_options.platform=gmail \
  client_options.sensor_seed_key=gmail \
  client_id=$GMAIL_CLIENT_ID \
  client_secret=$GMAIL_CLIENT_SECRET \
  refresh_token=$GMAIL_REFRESH_TOKEN \
  query="in:inbox" \
  poll_interval=5m
```

## Infrastructure as Code Deployment

Full BEC monitoring of a Workspace mailbox — message telemetry plus the persistence, exfiltration, and tamper signals:

```yaml
# For cloud sensor deployment, store credentials as hive secrets:
#
#   service_account_credentials: "hive://secret/gmail-service-account"

sensor_type: "gmail"
gmail:
  service_account_credentials: "hive://secret/gmail-service-account"
  subject: "soc-mailbox@yourdomain.com"
  collect_messages: true
  collect_filters: true
  collect_forwarding: true
  collect_send_as: true
  collect_delegates: true
  collect_imap_pop: true
  collect_vacation: true
  collect_history: true
  poll_interval: 5m
  settings_poll_interval: 15m
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_GMAIL"
    platform: "gmail"
    sensor_seed_key: "gmail-sensor"
```

Domain-wide auto-discovery — every mailbox in the Workspace, each on its own sensor:

```yaml
sensor_type: "gmail"
gmail:
  service_account_credentials: "hive://secret/gmail-service-account"
  discover_mailboxes: true
  admin_subject: "admin@yourdomain.com"
  discovery_interval: 1h
  collect_messages: true
  collect_filters: true
  collect_forwarding: true
  collect_history: true
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_GMAIL"
    platform: "gmail"
    sensor_seed_key: "gmail-sensor"
```

## Sample Rule

The BEC capabilities ship each signal under its own event type, so D&R rules can route directly on the signal. For example, flag every change to the account-wide auto-forwarding setting:

```yaml
# Detection
event: gmail_auto_forwarding
op: is
path: event/enabled
value: true

# Response
- action: report
  name: Gmail auto-forwarding enabled
```

> **Note:** the `gmail.metadata` scope does not allow the `q` search parameter. If you restrict the adapter to that scope, leave `query` empty and rely on `label_ids` / `include_spam_trash` instead. The default `gmail.readonly` scope covers every capability; the narrower `gmail.metadata` scope cannot read the settings sub-resources, so a capability using them will be logged and skipped.

## API Docs

- Gmail API reference: [https://developers.google.com/workspace/gmail/api/reference/rest](https://developers.google.com/workspace/gmail/api/reference/rest)
- Admin SDK Directory API (`users.list`, used by auto-discovery): [https://developers.google.com/admin-sdk/directory/reference/rest/v1/users/list](https://developers.google.com/admin-sdk/directory/reference/rest/v1/users/list)
