# Connecting Providers

--8<-- "includes/email-security-beta.md"

A mail connection is one `mailsec_provider` Hive record plus one credential in
the [secret](../7-administration/config-hive/secrets.md) Hive. Two providers are
supported, and an organization may hold **one connection of each**:

| Provider | `provider` | Auth model | Setup |
|---|---|---|---|
| Microsoft 365 / Exchange Online | `m365` | Entra ID app registration (client credentials) with Microsoft Graph **application** permissions | [Microsoft 365](provider-setup/microsoft-365.md) |
| Google Workspace / Gmail | `gworkspace` | Google Cloud service account with **domain-wide delegation**, plus Pub/Sub in the same project | [Google Workspace](provider-setup/google-workspace.md) |

!!! info "One enabled record per provider"
    Creating a second enabled record for a provider that already has one is
    refused at write time. Notifications carry a mailbox and a subscription, not
    a credential, so two same-provider connections in one organization would
    make it ambiguous which tenant's credential should fetch a given message.
    An M365 connection **and** a Workspace connection in the same organization
    is fully supported and runs concurrently; a campaign can span both.

## The connection record

```yaml
provider: m365 | gworkspace
credentials: hive://secret/<name>

scope:
  include_addresses: []
  exclude_addresses: []
  include_groups: []
  domains: []

ingest:
  mode: auto | push | poll
  backfill_days: 14

features:
  outbound_observation: true
  reports_mailbox: ""
  pubsub_topic: ""          # Google Workspace only
  pubsub_subscription: ""   # Google Workspace only
```

The record is decoded strictly: an unknown key is **refused**, not ignored. A
typo in a security control that silently does nothing is the worst available
failure mode, so a rejected record is preferred to an ignored field.

### `credentials`

Always a `hive://secret/<name>` reference. The credential is resolved in the
collector's memory only; a decoded connection record carries no secret material,
which is what makes it safe to read through the API, mirror and log.

### `scope`

Which mailboxes the connection covers.

| Field | Meaning |
|---|---|
| `include_addresses` | Exact mailbox addresses to cover. **Empty means every discovered mailbox** — the intended default. |
| `exclude_addresses` | Mailboxes never to cover. Excludes always win over includes. |
| `include_groups` | Directory groups to expand into addresses before discovery. |
| `domains` | Restrict to mailboxes in these domains. |

Addresses and domains are lowercased on save.

!!! warning "Group expansion is fail-closed on the connection, not on the scope"
    A group-scoped connection whose groups cannot be expanded is treated as a
    **connection error** rather than proceeding — because an unexpanded group
    scope would silently widen to every mailbox.

### `ingest`

| Field | Meaning |
|---|---|
| `mode` | `auto` (default) picks push where the provider supports it, `push` requires it, `poll` forces periodic polling. |
| `backfill_days` | Historical **metadata-only** bootstrap window, 0–90, default **14**. It seeds sender profiles and campaign statistics; it computes no verdicts and performs no actions. `0` disables it, at the cost of first-contact signals being uninformative for the first weeks. |

Push is the normal mode for both providers. Polling exists for small tenants and
as a failure fallback; at scale it spends provider quota continuously whether or
not any mail arrived.

### `features`

| Field | Meaning |
|---|---|
| `outbound_observation` | Ingest Sent mail as `direction: outbound`, observation-only — it is never remediated. **Defaults on**: outbound is where account takeover shows itself. |
| `reports_mailbox` | The abuse mailbox to ingest as user reports. See [User Reports](user-reports.md). |
| `pubsub_topic` | Google Workspace only. The topic Gmail publishes notifications to. It **must** live in the service account's own Google Cloud project — Gmail rejects any other. |
| `pubsub_subscription` | Google Workspace only. The pull subscription the collector reads. Separate from the topic because a topic is write-only from Gmail's side. |

A Pub/Sub field on an `m365` record is refused rather than ignored: it means a
Workspace record was copied, and ignoring it would leave an operator believing
push was configured through a topic nothing reads.

## The connection test

The single most useful thing after saving a record. It reports each requirement
independently, so a UI (and a human) can say "step 4 is missing" instead of
"connection failed".

```bash
limacharlie mailsec connection test <record-name> --oid $OID --output yaml
```

Every check carries `id`, `name`, `required`, `status` and — when it fails — a
`detail` and a `remediation` naming the exact fix. `ok` is the AND of the
**required** checks only.

| Provider | Checks |
|---|---|
| Microsoft 365 | `credential` (authenticate to Graph), `mailbox_read` (list mailboxes), `mail_write` (`Mail.ReadWrite` — required), `mail_send` (`Mail.Send` — optional) |
| Google Workspace | `credential` (key well formed), `directory` (`admin.directory.user.readonly`), `mail_modify` (`gmail.modify`), `mail_full` (`https://mail.google.com/` — optional), `mailbox_read` (list mailboxes in the domain), `pubsub_pull` (read the subscription), `pubsub_watch` (Gmail can publish to the topic) |

Three properties are worth knowing:

- **It takes a record name, not a credential.** The obvious shape — post the key,
  get a verdict — would put a service-account private key in a request body,
  where it transits the gateway and lands in logs. The credential stays in the
  secret Hive; the test reads what is already there.
- **A failed optional check is not an error.** A tenant that granted only the
  narrow scopes has a working connection, and the missing capability is named
  rather than silently absent.
- **`--include-watch` has a side effect.** It establishes a real Gmail watch to
  verify notification delivery end to end. The watch is idempotent and expires on
  its own. Every other check is read-only.

It requires `mailsec.act`, because it makes real calls against your provider.

## Capability differences between providers

Provider mechanics differ, and the differences are surfaced rather than papered
over.

| | Microsoft 365 | Google Workspace |
|---|---|---|
| **Quarantine** | Move to a hidden `LC Quarantine` folder — restorable, invisible to the user | Remove `INBOX`, add an `LC Quarantine` label |
| **Trash** | Move to Recoverable Items — invisible to the user, recoverable by an admin. Distinct from Deleted Items | Add `TRASH` |
| **Move to spam** | Move to the Junk Email folder | Add `SPAM` |
| **Restore** | Move back to the folder we recorded, falling back to the Inbox | Invert the labels |
| **Banner** | Edited **in place**; the message keeps its provider id | Gmail cannot edit a stored message, so the message is **replaced** and gets a **new provider id**. Requires the optional `https://mail.google.com/` scope; without it the action is refused by name, never reported as a silent success |
| **Notification state** | Graph subscriptions can be listed, so reconciliation compares against the provider's own view | Gmail **cannot enumerate active watches**, so reconciliation uses stored state with correspondingly lower assurance. Every Workspace connection row says so |
| **Reporter replies** | Need the optional `Mail.Send` application permission | Need the optional `https://mail.google.com/` scope |

!!! note "Provider message ids are live handles"
    A move mints a new provider id and invalidates the old one. The product
    rewrites the stored handle after every action, which is why a restore days
    after a quarantine still addresses the right message. If you script against
    `provider_message_id`, re-read it rather than caching it.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Nothing is discovered or ingested | The Hive record was created disabled | `limacharlie hive enable --hive-name mailsec_provider --key <name>` |
| `coverage` shows mailboxes as `discovered` but not `protected` | Discovery ran, subscription has not yet been established for those mailboxes | Give the subscription sweep a pass; if it persists, run the connection test |
| Save refused with an unknown-field error | A key that is not in the record contract, or a Workspace-only field on an M365 record | Fix the key; the refusal names it |
| Second connection for the same provider refused | Only one enabled record per provider is supported | Edit the existing record instead |
| `connections.state` is `unconfigured` | No connection record exists, or none has completed a pass | Create/enable the record; an empty list is never reported as healthy |
