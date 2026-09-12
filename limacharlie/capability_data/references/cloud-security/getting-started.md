# Getting Started with Cloud Security

This guide takes an organization from zero to a populated Cloud Security
dashboard: enable the product, connect a provider, run the first sweep, and
declare what matters. You can do all of it in the console or entirely as code —
both are shown.

## 1. Enable Cloud Security

Cloud Security is enabled per organization by subscribing to the
`ext-cloud-security` extension — the subscription is both the enable gate and
the billing hook.

Subscribe from the console with the **Subscribe** button on
**Extensions → Cloud Security**, or in one command:

```bash
limacharlie extension subscribe --name ext-cloud-security --oid $OID
```

Subscribing requires the `billing.ctrl` and `user.ctrl` permissions.

Confirm the organization is enabled:

```bash
limacharlie extension list --oid $OID
```

Until the organization is subscribed, every Cloud Security API route returns
`403`. The **Cloud Security** workspace is always listed in the organization
sidebar, but its pages show an "enable Cloud Security" screen — with a link to
**Extensions** — rather than the product.

!!! tip "The workspace opens gradually"
    Before the first provider is connected there is nothing to show, so the
    workspace deliberately exposes only **Settings** (and **Give Feedback**);
    the other pages redirect there. The full set of pages appears once a
    provider exists and its first sweep has data.

### Free tier and trial

Organizations on the free tier (a configured sensor quota of 2 or fewer) can
trial Cloud Security without upgrading: up to **2 provider connections**, with
collection running for **14 days** from the day Cloud Security was enabled.
The Overview page shows the trial banner, and
[`GET /free-tier`](api-reference.md) reports the standing and limits.

When the trial ends (or a third provider is added), the affected collection
pauses rather than erroring: the reason appears as the provider's status in
**Settings → Providers** and in `scan-status`. Nothing is deleted immediately
and none of your configuration is touched — provider records, credentials, and
policies all survive — so upgrading resumes collection where it left off within
minutes. Trial data does age out eventually if the organization stays on the
free tier.

## 2. Connect a provider

A provider connection is one `cloudsec_provider` record. Each provider needs a
scope (which account/tenant/org to enumerate) and a read-only credential. The
[Connecting Providers](providers.md) page has the full per-provider setup — the
steps below use Google Cloud as the worked example.

### In the console

Open **Cloud Security → Settings → Providers** and click **+ Add provider**.
The wizard has five steps:

1. **Name & type** — name the connection and pick the provider type.
2. **Configuration** — the type-specific connection fields (for GCP, the
   scope: a project, folder, or organization).
3. **Permissions** — the credential, plus the list of grants the collector
   needs and per-OS command-line tabs that create them in the target platform.
   Reference an existing [secret](../7-administration/config-hive/secrets.md)
   by `hive://secret/<name>`, or paste the credential to have the console store
   it as a new secret for you. Credentials are always stored as a secret and
   referenced — never inlined into the provider record.
4. **Sync cadence** — how often to re-enumerate, from 30 minutes to daily, or
   a custom interval.
5. **Summary** — review, then click **Add provider**. Saving an enabled
   connection starts collection, and the closing screen reports the status of
   that first scan.

**Test Provider** sits in the wizard footer on every step, so you can run the
read-only preflight (see below) as soon as the credential is in place rather
than waiting until the end.

The provider list then shows one row per connection with its **Source**,
**Connection**, **Scope**, **Status**, **Resources**, and **Last sync**, plus
per-row actions: **Sync now**, **Edit**, **Delete**, and — once the connection
has reported what it can collect — **What you're getting**.

### As code

The credential lives in the secret Hive; the provider record references it:

```bash
# Store the collector credential as a secret (hive set reads the record
# data from --input-file or piped stdin).
echo '{"secret": "<service-account-key-json>"}' | \
  limacharlie hive set --hive-name secret --key gcp-collector-sa \
    --oid $OID --enabled

# Connect the provider.
cat > provider.json <<EOF
{
  "provider_type": "gcp",
  "gcp_scope": "organizations/123456789",
  "credentials": "hive://secret/gcp-collector-sa",
  "internal_domains": ["acme.com", "acme.io"]
}
EOF

limacharlie hive set --hive-name cloudsec_provider --key acme-gcp \
  --oid $OID --input-file provider.json --enabled
```

The full field reference is in
[Configuration](configuration.md#cloudsec_provider), and every provider's scope
fields and credential shape are in [Connecting Providers](providers.md).
[Provider Setup](provider-setup/index.md) has a full onboarding walkthrough for
**every** supported platform — exact scopes, how to create the credential in
that platform, credential-secret formats, and first-run troubleshooting.

!!! tip "internal_domains matters for CIEM"
    List every email domain your own people use. A human identity whose domain
    is not in the internal set is classified *external*, and external access to
    sensitive resources is one of the highest-signal finding classes. The
    collector discovers the primary cloud-org domain on its own; secondary
    domains must be declared.

### Test the credential before saving

The provider test connects with the supplied credential and probes every
permission surface a sweep needs, without storing anything — the same check the
console's **Test Provider** button runs:

```bash
limacharlie cloudsec provider test --input-file provider.json
```

The response is a per-check report: each check carries `id`, `name`,
`required`, `ok`, and a human-readable `detail`. `report.ok` is the verdict
over the *required* checks only — a failed optional check means that surface
degrades gracefully (e.g. one inventory type missing) rather than the
connection failing.

!!! info "Permissions"
    The provider test requires `cloudsec.set` — testing a credential is as
    sensitive as saving one. For the test (and only the test) the credential
    may be passed inline instead of as a `hive://secret/` reference; it is
    used ephemerally and never stored or logged.

## 3. Watch the first sweep

Saving an enabled provider record starts collection. Check progress:

```bash
limacharlie cloudsec scan-status --provider gcp
```

The status carries whether a sweep is running, when the last one started and
completed, the diff stats of the last run, and any error. To force an immediate
re-enumeration later, change the record's `sync_now` value (any new value
triggers a sweep) or use **Sync now** on the provider row; `refresh` sets the
periodic cadence.

## 4. Declare what matters

Out of the box, **nothing is classified sensitive** — sensitivity is your
declaration, made with a `classification`-typed `cloudsec_policy` record (your
crown jewels). Rules match resources by account, name, resource type, label, or
tag and assign classes:

```bash
cat > classification.json <<EOF
{
  "policy_type": "classification",
  "classification": {
    "data_stores": [
      {"name_contains": ["customer", "pii"], "classes": ["pii"]}
    ]
  }
}
EOF

limacharlie hive set --hive-name cloudsec_policy --key classification \
  --oid $OID --input-file classification.json --enabled
```

Sensitivity drives the attack-path and CIEM analytics: "exposed workload that
can reach *sensitive* data" and "external identity with access to *sensitive*
store" both need to know what sensitive means in your estate.

!!! note "Content-based classification is not yet available"
    Classification rules accept a `content_class` dimension, intended to let
    detected data content drive sensitivity, but content detection is not live
    in the current release — declare your crown jewels by account, name,
    resource type, label, or tag. (The former `auto_classify` boolean has been
    retired in favour of these explicit, previewable rules.)

In the console, the same policy is authored on **Cloud Security → Policies →
Data classification**, where a live **Simulate** panel shows exactly which
resources a rule matches before you save it.

## 5. Look at the result

In the console, the **Overview** page is the at-a-glance risk layer and
**Risks** is the worklist. From the CLI:

```bash
# The composed risk overview: score, severity distribution, top paths.
limacharlie cloudsec overview

# The findings worklist, worst first.
limacharlie cloudsec finding list --severity CRITICAL --severity HIGH

# What you own.
limacharlie cloudsec inventory facets
```

From here, continue with [Findings & Triage](findings.md) for the day-to-day
workflow, [Connecting Providers](providers.md) to add more of your estate, or
[Automation & IaC](automation.md) to wire findings into Cases and onboard more
tenants as code.
