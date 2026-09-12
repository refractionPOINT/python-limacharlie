# Provider Setup

[Getting Started](../getting-started.md) walks the end-to-end flow with a
Google Cloud example. This section is the per-provider companion: for **every**
supported platform, the exact scopes and permissions the collector needs, the
click-by-click steps to create the credential in that platform, the
credential-secret format, and the first-run failures with their fixes.

It assumes the organization is already subscribed to the `ext-cloud-security`
extension (step 1 of
[Getting Started](../getting-started.md#1-enable-cloud-security)).

## Pick your platform

| Platform | Surface | What onboarding takes |
|---|---|---|
| [Google Cloud](gcp.md) | Cloud infra | Service account + Viewer & Security Reviewer at the org/folder/project |
| [Amazon Web Services](aws.md) | Cloud infra | IAM user that assumes a read-only role, external-ID gated |
| [Microsoft Azure](azure.md) | Cloud infra | App registration + Reader on the subscription + Graph consent |
| [Microsoft Entra ID](entra.md) | Identity | App registration + Graph consent (directory only, no Azure needed) |
| [Okta](okta.md) | Identity | API Services app (private-key JWT) + 5 read scopes + a read-only admin role |
| [Google Workspace](google-workspace.md) | Identity | Service account with domain-wide delegation impersonating a super admin |
| [1Password](onepassword.md) | Identity | SCIM bridge URL + bearer token (optionally a Connect server) |
| [Auth0](auth0.md) | Identity | M2M application authorized on the Management API with read scopes |
| [Cloudflare](cloudflare.md) | SaaS | One scoped read-only API token + the account ID |
| [GitHub](github.md) | SaaS | A GitHub App installed on the org, read-only permission set |
| [OpenAI](openai.md) | AI | An Admin API key created with `api.management.read` |
| [Anthropic](anthropic.md) | AI | A Console Admin key and/or an Enterprise Compliance key |
| [LimaCharlie](limacharlie.md) | LimaCharlie | An org or user API key with read permissions |

[Connecting Providers](../providers.md) is the conceptual overview of the same
thirteen connectors — what each collects and why.

## The common model

Every provider connection is **two Hive records**:

| Piece | Hive | Holds |
|---|---|---|
| **Provider record** | `cloudsec_provider` | Non-secret config (scope, account/subscription IDs, regions) plus a **reference** to the credential. |
| **Credential secret** | `secret` | The actual credential (key/token). Referenced from the provider record as `hive://secret/<name>` — **never inlined**. |

The full field reference for the provider record is in
[Configuration](../configuration.md#cloudsec_provider).

Store the credential first, then reference it. The
[secret](../../7-administration/config-hive/secrets.md) record's value is the
credential blob:

```bash
limacharlie hive set --hive-name secret --key <name> \
    --input-file secret.json --enabled
```

where `secret.json` is `{"secret": "<the credential JSON, as a string>"}`.

The `secret set` shortcut does that wrapping for you, so you can hand it the
credential itself — `credential.json` below is the provider's credential JSON,
with no `{"secret": …}` envelope:

```bash
limacharlie secret set --key <name> --value "$(cat credential.json)" --enabled
```

!!! note "`--value` lands in your shell history"
    Anything passed on the command line is visible in the process list and in
    shell history. To avoid that, pipe the record on stdin instead —
    `echo '{"secret": "…"}' | limacharlie secret set --key <name> --enabled` —
    or use `--input-file`.

!!! tip "Bare keys are accepted for single-key providers"
    For [OpenAI](openai.md), [Anthropic](anthropic.md), and
    [LimaCharlie](limacharlie.md) you may store the raw key string instead of a
    JSON object — it is wrapped into the documented shape automatically. Every
    other provider needs the JSON object exactly as its page documents.

### Always preflight before saving

`provider test` connects with the credential *ephemerally* (it is never stored)
and probes every permission surface a sweep needs:

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

The response is a per-check report; each check carries `id`, `name`,
`required`, `ok`, and a human-readable `detail`. **`report.ok` is the verdict
over the required checks only.** A failed **optional** check means that surface
degrades gracefully — an inventory type goes unobserved — rather than the
connection failing, and its `detail` names exactly what you lose.

Every provider page lists its platform-specific check IDs and what each one
means, on top of the two common checks below.

Once a record passes preflight, save it:

```bash
limacharlie hive set --hive-name cloudsec_provider --key <name> \
    --input-file provider.yaml --enabled
```

!!! note "In the web app"
    Everything here can also be done under **Cloud Security → Settings →
    Providers → Add provider**, with secrets managed under **Organization
    Settings → Secrets Manager**. The **Test Provider** button runs the same
    preflight.

### The two checks every provider reports first

Before any provider-specific probe runs, the report always contains these two
**required** checks. They are identical for all thirteen connectors, which is
why the per-provider tables in this section start at `auth`:

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `config` | ✅ | The provider record itself is malformed — a field required for this `provider_type` is missing or ill-formed (a scope that is not in the expected shape, an ARN that does not parse, and so on). Nothing is contacted. |
| `credential` | ✅ | The `hive://secret/<name>` reference could not be resolved — no such secret, or it is disabled — or the secret's contents are not the JSON shape that provider documents. Nothing is contacted. |

Only once both pass does `auth` actually reach the platform.

!!! warning "Unknown fields on the provider record are rejected, not ignored"
    The provider record is parsed **strictly**, both by `provider test` and on
    the Hive write: an unrecognized key is an error rather than something
    silently dropped. A misspelled field name therefore fails outright, with the
    offending key named, instead of quietly leaving a setting unapplied — use the
    exact names from [Configuration](../configuration.md#cloudsec_provider).
    Credential secrets are **not** strict in the same way: an unrecognized key
    there is dropped without complaint, which is why a mistyped credential field
    surfaces later as an authentication failure instead. Each provider page
    documents its exact credential keys.

## Fields every provider accepts

| Field | Purpose |
|---|---|
| `internal_domains` | Your own email domains. A human identity outside them is classified **external**, and external access to sensitive resources is one of the highest-signal finding classes. The collector discovers the primary cloud-org domain by itself; **secondary domains must be listed here** or your own staff are falsely flagged external. |
| `refresh` | Re-enumeration cadence as a Go duration (`6h`, `24h`). Minimum `5m`; empty uses the service default. |
| `sync_now` | Any opaque value; **changing it** triggers an immediate re-sweep. |
| `feed_subscription` | Optional Pub/Sub subscription (`projects/{p}/subscriptions/{s}`) carrying a change feed, for seconds-latency updates between full sweeps. |

## Principles that apply everywhere

- **Read-only.** Every credential documented here is read-only, except where a
  platform offers no read-only surface for something — those cases are called
  out explicitly on the provider's page.
- **Least privilege.** Grant the required set first, confirm with
  `provider test`, then add optional grants only for the surfaces you want.
- **Nothing is stored inline.** Credentials live in the `secret` hive and are
  referenced. The provider record never holds key material, and credentials are
  never written to logs.
- **Partial grants are supported.** A denied optional surface leaves that
  inventory type *unobserved*; it never fails the sweep or deletes
  previously-collected rows.

## Credential-secret quick reference

| Provider | `secret` value |
|---|---|
| [Google Cloud](gcp.md) | The service-account key JSON |
| [AWS](aws.md) | `{"access_key_id": "...", "secret_access_key": "..."}` |
| [Azure](azure.md) | `{"client_id": "...", "client_secret": "..."}` |
| [Entra ID](entra.md) | `{"client_id": "...", "client_secret": "..."}` |
| [Okta](okta.md) | `{"org_url": "...", "client_id": "...", "private_key": {…JWK…}}`, or `{"org_url": "...", "api_token": "..."}` |
| [Google Workspace](google-workspace.md) | `{"service_account_json": {…SA key…}, "admin_email": "...", "domain": "..."}` |
| [1Password](onepassword.md) | `{"scim_url": "...", "scim_token": "..."}` *(optional `connect_url`, `connect_token`)* |
| [Auth0](auth0.md) | `{"client_id": "...", "client_secret": "..."}` |
| [Cloudflare](cloudflare.md) | `{"api_token": "..."}` *(optional `user_api_token`)* |
| [GitHub](github.md) | `{"private_key": "-----BEGIN RSA PRIVATE KEY-----…"}` |
| [OpenAI](openai.md) | `{"admin_api_key": "sk-admin-..."}` |
| [Anthropic](anthropic.md) | `{"admin_api_key": "sk-ant-admin01-..."}` and/or `{"compliance_api_key": "sk-ant-api01-..."}` |
| [LimaCharlie](limacharlie.md) | `{"api_key": "..."}` |
