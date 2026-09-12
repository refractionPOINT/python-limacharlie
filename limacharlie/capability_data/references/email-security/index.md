# Email Security

--8<-- "includes/email-security-beta.md"

LimaCharlie Email Security protects Microsoft 365 and Google Workspace mailboxes
from inside the same tenant, permission model, telemetry lake and automation
surface as the rest of LimaCharlie. It connects to your mail provider's API —
**no MX change, no mail routing change, nothing in the delivery path** — reads
every message that arrives, judges it, explains the judgement, and can remediate
it at the provider.

!!! tip "In one sentence"
    Connect a mail tenant with an API credential, and every message is parsed,
    judged with an explainable verdict, indexed for search, and one click (or one
    D&R rule) away from being quarantined, trashed or bannered — with the whole
    thing available as events, API and Infrastructure-as-Code.

## What it does

| Capability | What you get |
|---|---|
| **Ingestion** | Every delivered message in every protected mailbox, fetched as raw MIME and parsed into a normalized **Message Data Model (MDM)**: headers, decomposed sender and recipients, thread-segmented body, links, attachments, authentication results and the `Received` chain. Sent mail is ingested as observation-only. |
| **Verdicts** | One explainable verdict per message — `malicious`, `suspicious`, `graymail` or `benign` — from a weighted managed rule pack plus your own rules. Every non-benign verdict carries the signals that produced it and their weights. |
| **Enrichments** | Sender and sender-domain history, VIP and lookalike-domain impersonation, sender-domain registration age, static link features, and attachment explosion — archives unpacked recursively, macros extracted, embedded QR codes decoded, and files identified by content rather than by the extension the sender claimed. |
| **Remediation** | Typed, idempotent, audited actions performed at the provider: quarantine, trash, move to spam, restore, apply and remove a warning banner. Available by policy automation, from the console, from a D&R rule, from the API and from the CLI. |
| **Campaigns** | Messages the engine attributed to one attack are clustered, so a campaign that hit forty mailboxes is triaged once and swept once. |
| **User reports** | An abuse mailbox becomes an SLA queue: reports are joined back to the original message across the whole tenant, robots that mail the abuse address are auto-resolved out of the queue, and reporters can be sent a templated acknowledgement. |
| **Telemetry** | `EMAIL_MESSAGE`, `EMAIL_VERDICT` (every verdict decision — the engine's own at ingest, then each override), `EMAIL_ACTION`, `EMAIL_USER_REPORT` and `EMAIL_INGEST_ERROR` land in the same lake as your EDR, cloud and identity telemetry — so "phish delivered, then that user's endpoint ran a new binary" is one D&R rule. |
| **Configuration as data** | Connections, policy and custom rules are Hive records, so everything is API-first and git-syncable from day one. |

## What it does not do

Stated plainly, because a mail security product's boundaries decide how you
deploy it:

- **It is post-delivery.** Messages are analyzed after the provider delivers
  them, typically within seconds. Nothing is held, and mail is never blocked
  before it lands. Remediation removes a message from the inbox after the fact.
- **It does not replace your provider's own filtering.** It sits behind Exchange
  Online Protection / Defender or Gmail's own filters and judges what they let
  through.
- **It does not modify mail by default.** Automations ship in `alert_only` mode,
  banners are off, and reporter replies are off. See
  [Policy Reference](policy.md).

## How it works

1. **Enable** the organization for the `ext-email-security` extension — the
   subscription is the product's enable gate, and every `/v1/mailsec/*` route is
   refused without it.
2. **Connect a mail tenant**: one `mailsec_provider` Hive record per connection,
   referencing a credential held in the [secret](../7-administration/config-hive/secrets.md)
   Hive. A connection test probes every permission the collector needs and
   reports each one independently. See [Connecting Providers](providers.md).
3. **Mailboxes are discovered and subscribed.** The collector enumerates the
   directory, subscribes to change notifications (Microsoft Graph subscriptions,
   Gmail watch → your own Pub/Sub topic), and runs a metadata-only historical
   backfill so sender-history signals work on day two rather than day ninety.
4. **Each message is judged.** Fetch → parse → enrich → evaluate signal rules →
   score → verdict → campaign clustering → policy automations → persist and emit.
5. **You work the queue** in **Messages**, **Campaigns** and **User Reports**,
   or you automate it with policy automations and D&R rules.

## Two seats for rules

This distinction is worth learning early, because it decides where you write
what:

| | Signal rules | Platform D&R rules |
|---|---|---|
| **Where they run** | In the collector, *before* the verdict is emitted | In the platform, on the emitted `EMAIL_*` events |
| **What they do** | Contribute weighted evidence to the verdict, or dispatch a mail action right after it | The full response arsenal: `report`, `extension request`, `start ai agent`, Outputs, cross-domain correlation |
| **Where they live** | The `dr-mail` Hive, plus the managed pack | The `dr-general` Hive, like every other detection you write |
| **Syntax** | Standard D&R detect blocks over the MDM | Standard D&R rules over `EMAIL_*` events |

See [Custom Rules](custom-rules.md) and [Events & Automation](automation.md).

## Permissions

Four permissions rather than the usual get/set pair, because the product asks to
be trusted with four separable things:

| Permission | Covers |
|---|---|
| `mailsec.get` | Read the product's own view: the message queue and drawer, campaigns, sender profiles, the action audit, reports, coverage, rule validation and backtests |
| `mailsec.set` | Change triage state — resolving a user report |
| `mailsec.act` | Remediate live mail at the provider, and run the connection test |
| `mailsec.get.eml` | Download a message's original bytes. Requires `mailsec.get` **as well**, plus a logged justification |

`mailsec.get.eml` is separate on purpose: opening the drawer shows you the
product's structured view of a message, while downloading the EML takes a
person's actual mail out of your tenant. Gating them identically would mean
typing a justification to look at the queue.

Managing connections and policy uses the ordinary Hive permissions for the
`mailsec_provider`, `mailsec_policy`, `dr-mail`, `secret` and `lookup` hives.

## Where to go next

| | |
|---|---|
| [How a Message Is Processed](pipeline.md) | The pipeline end to end: what is synchronous, what is stored, and how long it takes |
| [Getting Started](getting-started.md) | Subscribe, connect a tenant, see the first judged message |
| [Connecting Providers](providers.md) | The connection record, credentials, scope, ingest modes and the connection test |
| [Microsoft 365](provider-setup/microsoft-365.md) · [Google Workspace](provider-setup/google-workspace.md) | Per-provider setup |
| [Messages & Triage](messages.md) | The queue, the drawer, actions and the audit trail |
| [Bulk Remediation](remediation.md) | Acting on a set of messages you named: preview, confirm, execute, poll |
| [Campaigns](campaigns.md) | Clustering and campaign-wide sweeps |
| [User Reports](user-reports.md) | The abuse mailbox and the report SLA queue |
| [Detections & Verdicts](detections.md) | How a verdict is produced, and what the rules can read |
| [Custom Rules](custom-rules.md) | Writing, validating and backtesting your own mail rules |
| [IOC & Reputation Feeds](ioc-feeds.md) | Mirroring a threat feed into a lookup and matching messages against it |
| [Policy Reference](policy.md) | Every `mailsec_policy` record type |
| [Events & Automation](automation.md) | The `EMAIL_*` events and wiring them to D&R |
| [Command Line Interface](cli.md) · [API Reference](api-reference.md) | The programmable surface |
| [Troubleshooting](troubleshooting.md) | What each failure looks like, and where it is reported |
