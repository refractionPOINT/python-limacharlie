# Getting Started with Email Security

--8<-- "includes/email-security-beta.md"

This guide takes an organization from zero to a populated Email Security queue:
enable the product, connect a mail tenant, verify the connection, and read the
first judged message. You can do all of it in the console or entirely as code —
both are shown.

## 1. Enable Email Security

Email Security is enabled per organization by subscribing to the
`ext-email-security` extension. The subscription is the enable gate: without it
every `/v1/mailsec/*` route is refused, and the console shows a subscribe screen
instead of the product.

```bash
limacharlie extension subscribe --name ext-email-security --oid $OID
```

Confirm it:

```bash
limacharlie extension list --oid $OID
```

Subscribing also seeds the recommended policy records — all in `alert_only`
mode, so nothing moves mail until you say so. See [Policy Reference](policy.md).

!!! info "Free trial: 14 days, 25 mailboxes"
    An organization on the LimaCharlie free tier gets Email Security in full for
    **14 days** and protects up to **25 mailboxes** while it does. Every feature
    is the same as on a paid plan; only the duration and the mailbox count
    differ. The clock starts the day you subscribe and **does not restart if you
    unsubscribe and resubscribe**, so point the 25 at the mailboxes that matter
    — start with the executives, finance and the abuse mailbox.

    When the trial ends, ingestion pauses and nothing is deleted; the data is
    removed 30 days later unless the organization moves off the free tier, and
    you are told before that happens. The full rules, and the exact fields to
    read the countdown from, are in
    [Plans, the free trial, and the mailbox cap](policy.md#plans-the-free-trial-and-the-mailbox-cap).

## 2. Grant the permissions

Email Security ships four permissions. A user or API key that will triage mail
typically needs `mailsec.get`, `mailsec.set` and `mailsec.act`; a read-only
analyst needs only `mailsec.get`. `mailsec.get.eml` is an escalation on top of
`mailsec.get` and should be granted deliberately — see
[Overview → Permissions](index.md#permissions).

Managing the connection itself additionally needs the Hive permissions for
`mailsec_provider` and `secret`.

## 3. Prepare the provider credential

The credential is created in your mail provider's admin console and stored in
the LimaCharlie [secret](../7-administration/config-hive/secrets.md) Hive. It is
always referenced, never inlined into the connection record.

| Provider | What you create | Full walkthrough |
|---|---|---|
| Microsoft 365 | An Entra ID app registration with **application** permissions and a client secret | [Microsoft 365](provider-setup/microsoft-365.md) |
| Google Workspace | A Google Cloud service account with **domain-wide delegation**, plus a Pub/Sub topic and subscription in the same project | [Google Workspace](provider-setup/google-workspace.md) |

!!! tip "The console renders your own setup guide"
    The setup steps, OAuth scopes and `gcloud` commands are served by the
    product rather than transcribed here, so they cannot go stale: the
    connection wizard renders them with **your** project id and service-account
    address already substituted, and each step names the connection-test check
    that proves it was done. These pages carry the narrative — what each grant
    buys and what breaks without it — and the wizard carries the values.

    The same guide is available headless:

    ```bash
    limacharlie mailsec onboarding --provider gworkspace --oid $OID
    limacharlie mailsec onboarding --provider m365 --oid $OID
    ```

## 4. Connect the mail tenant

### In the console

Open **Email Security → Settings** and add a connection. The wizard collects the
provider, the credential, the mailbox scope and — for Google Workspace — the
Pub/Sub topic and subscription, shows the personalized setup guide alongside,
and runs **Test Connection** against the real provider before you finish.
Failed saves are reported inline on the review step, with the validator's own
wording rather than a generic error.

Editing an existing connection is patch-preserving: fields the form does not
manage are left exactly as they were.

### As code

One `mailsec_provider` Hive record per connection. The record's existence (and
its Hive `enabled` flag) *is* the connection — there is no separate on switch.

```bash
cat > m365-credential.json <<'JSON'
{"tenant_id": "<tenant-id>", "client_id": "<application-client-id>", "client_secret": "<the-secret-value>"}
JSON

limacharlie secret set --key m365-mail \
  --value "$(cat m365-credential.json)" --enabled --oid $OID
```

`secret set` wraps the value into the secret record's `{"secret": "..."}`
envelope for you.

```yaml
# m365.yaml
provider: m365
credentials: hive://secret/m365-mail
ingest:
  mode: auto
  backfill_days: 14
features:
  outbound_observation: true
  reports_mailbox: phishing@corp.example
```

```bash
limacharlie hive set --hive-name mailsec_provider --key m365-prod \
  --input-file m365.yaml --enabled --oid $OID
```

!!! warning "New Hive records are created disabled"
    `hive set` creates a record disabled unless you pass `--enabled`. A
    disabled `mailsec_provider` record is not a connection — nothing is
    discovered, subscribed or ingested — so a first connection that appears to
    do nothing is usually this.

The full field reference — scope, ingest modes, features — is in
[Connecting Providers](providers.md).

## 5. Verify the connection

The connection test uses the credential the only way a credential can be
verified: by using it. Each requirement is reported independently, so a failure
names the step to fix rather than saying "connection failed".

```bash
limacharlie mailsec connection test m365-prod --oid $OID --output yaml
```

```yaml
ok: true
summary: Connection is fully configured.
checks:
  - id: credential
    name: Authenticate to Microsoft Graph
    required: true
    status: passed
  - id: mailbox_read
    name: List mailboxes in the tenant (24 found)
    required: true
    status: passed
  - id: mail_write
    name: "Modify mail (Mail.ReadWrite): quarantine, restore, banner"
    required: true
    status: passed
  - id: mail_send
    name: "Send mail (Mail.Send): reporter auto-replies"
    required: false
    status: skipped
    detail: Mail.Send is not granted; reporter auto-replies will be refused by name until it is
```

A failed **optional** check is not an error and `ok` stays `true`: a tenant that
deliberately declined the optional grant has a working connection, and the
product tells you by name which capability it does not have rather than
pretending it does. Every failed check carries a `remediation` string naming the
exact fix.

For Google Workspace, add `--include-watch` to verify notification delivery end
to end. It is the one probe with a side effect: it establishes a real Gmail
watch, which is idempotent and expires on its own.

## 6. Watch coverage fill in

```bash
limacharlie mailsec coverage --oid $OID --output yaml
```

Coverage is the product's honesty surface. It reports mailboxes in four separate
states — `protected`, `discovered`, `excluded`, `error` — and never collapses
them, because a broken subscription hiding behind a deliberate exclusion is
exactly how a coverage number starts lying. `connections.state` summarizes to
the **worst** connection, and an organization with no connection at all reads
`unconfigured`, never `ok`.

The same call reports message volume and the verdict funnel over a window, the
parse-degradation rate, backfill progress, the emission backlog, open reports,
active campaigns, and the effective automation mode.

It also carries an `entitlement` block: which plan the organization is on, when
a trial ends, how many mailboxes it may protect against how many it is
protecting, and — if one is scheduled — the date its Email Security data will be
deleted and what cancels it. On a trial organization this is where you check
that the 25 mailboxes are the 25 you meant:

```yaml
entitlement:
  plan: trial
  trial_ends_at: "2026-09-20T14:02:11Z"
  trial_days_remaining: 12
  mailbox_cap: 25
  mailboxes_active: 25
  mailboxes_over_cap: 118        # discovered, not protected
  mailbox_cap_reached: true
```

`mailboxes_over_cap` is the number that matters: those mailboxes were found and
are not being watched. Narrow the connection's `scope`, or move off the free
tier. See
[Plans, the free trial, and the mailbox cap](policy.md#plans-the-free-trial-and-the-mailbox-cap).

!!! note "Backfill is metadata-only"
    On connection, the collector walks up to `ingest.backfill_days` (14 by
    default) of existing mail to seed sender profiles and campaign statistics.
    It computes **no verdicts and takes no actions** on that history — its
    purpose is that "we have never heard from this sender" is a true statement
    on day two instead of day ninety. Progress is reported in `coverage`.

## 7. Read the first judged message

```bash
limacharlie mailsec message list --oid $OID --limit 10 --output table
limacharlie mailsec message get <msg_uuid> --oid $OID --output yaml
```

In the console, **Email Security → Messages** is the queue and the row opens a
drawer with the verdict, the signals that produced it, authentication results,
links, attachments, the sender profile, the action timeline and the remediation
controls. See [Messages & Triage](messages.md).

## 8. Decide whether the product may act

Everything up to here is read-only. Automations ship in `alert_only`, which
means a rule is evaluated, its intent is recorded, and **the mailbox is not
touched**. Analyst-initiated actions from the console, CLI or API always execute
— `alert_only` withholds automation, not people.

Turning enforcement on is a deliberate edit to a `mailsec_policy/automations`
record. Read [Policy Reference](policy.md#automations) before you do, in
particular this consequence:

!!! danger "Enforcement is currently an organization-level switch"
    The remediation executor authorizes automated action when **any** automation
    rule in the organization is in `enforce` mode. Which rule dispatches an
    action is still decided per rule, but the executor's consent check is not
    per rule — so putting one rule into `enforce` enables automated action for
    the organization's automated paths generally. Enable it when you mean the
    organization to start moving mail.

## Next steps

- Tune what is judged: [Detections & Verdicts](detections.md)
- Write your own rules: [Custom Rules](custom-rules.md)
- Turn the abuse mailbox into an SLA queue: [User Reports](user-reports.md)
- Correlate mail with the rest of your telemetry:
  [Events & Automation](automation.md)
