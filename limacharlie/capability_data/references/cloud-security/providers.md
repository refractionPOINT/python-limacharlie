# Connecting Providers

A provider connection is one `cloudsec_provider` Hive record: a `provider_type`,
the scope to enumerate, and a read-only credential. All collection is agentless.
The credential itself always lives in the [secret](../7-administration/config-hive/secrets.md)
Hive and is referenced by `hive://secret/<name>` from the `credentials` field —
it is never stored inline on the provider record.

Connect a provider in the console at **Cloud Security → Settings → Providers**
(the **Add provider** button), or as code with `limacharlie hive set --hive-name
cloudsec_provider` (see [Getting Started](getting-started.md#2-connect-a-provider)).
Either way, run the [credential test](getting-started.md#test-the-credential-before-saving)
first — it probes every permission a sweep needs and reports exactly which are
missing.

## The thirteen connectors

| `provider_type` | Surface | Scope field(s) | Credential (JSON stored in the secret) |
|---|---|---|---|
| [`gcp`](provider-setup/gcp.md) | Cloud infra | `gcp_scope` (`projects/{id}`, `folders/{id}`, or `organizations/{id}`) | Service-account key JSON |
| [`aws`](provider-setup/aws.md) | Cloud infra | `aws_role_arn` (+ `aws_external_id`, `aws_regions`, `aws_member_role_name`) | STS AssumeRole (secret optional) |
| [`azure`](provider-setup/azure.md) | Cloud infra | `azure_tenant_id` + `azure_subscription_id` (+ `azure_client_id`) | `{"client_secret": "...", "client_id": "..."}` |
| [`okta`](provider-setup/okta.md) | Identity | `okta_org_url` | `{"api_token": "..."}` (SSWS) or an API Services app |
| [`entra`](provider-setup/entra.md) | Identity | `entra_tenant_id` (+ `entra_client_id`) | `{"client_secret": "..."}` (service principal) |
| [`google_workspace`](provider-setup/google-workspace.md) | Identity | `workspace_customer_id` | SA key with domain-wide delegation + `admin_email` |
| [`1password`](provider-setup/onepassword.md) | Identity | `onepassword_scim_url` | `{"scim_url": "...", "scim_token": "..."}` |
| [`auth0`](provider-setup/auth0.md) | Identity | `auth0_domain` | `{"client_id": "...", "client_secret": "..."}` (M2M) |
| [`cloudflare`](provider-setup/cloudflare.md) | SaaS | `cloudflare_account_id` | `{"api_token": "...", "user_api_token": "..."}` |
| [`github`](provider-setup/github.md) | SaaS | `github_org` + `github_app_id` + `github_installation_id` | `{"private_key": "-----BEGIN..."}` (GitHub App) |
| [`openai`](provider-setup/openai.md) | AI | *(optional `openai_org_id`)* | `{"admin_api_key": "sk-admin-..."}` |
| [`anthropic`](provider-setup/anthropic.md) | AI | *(optional `anthropic_org_uuid`)* | `{"admin_api_key": "sk-ant-admin01-..."}` (+ optional compliance key) |
| [`limacharlie`](provider-setup/limacharlie.md) | LimaCharlie | one of `limacharlie_oid` or `limacharlie_uid` | `{"api_key": "..."}` |

Every record also accepts the shared fields common to all providers —
`internal_domains`, `sync_now`, `refresh`, and `feed_subscription` — documented
in [Configuration](configuration.md#cloudsec_provider).

## Cloud infrastructure

### Google Cloud (`gcp`)

**Setup guide:** [step-by-step onboarding](provider-setup/gcp.md).

Set `gcp_scope` to a single project (`projects/{id}`), a folder
(`folders/{id}`), or a whole organization (`organizations/{id}`); the collector
enumerates every project in scope. The credential is a service-account key JSON
with read-only roles across the resource surface (compute, storage, IAM,
networking, KMS, BigQuery, Cloud SQL, Secret Manager, Pub/Sub, …). The test
report names any missing role.

### AWS (`aws`)

**Setup guide:** [step-by-step onboarding](provider-setup/aws.md).

The collector assumes a read-only IAM role you designate in `aws_role_arn`,
using an `aws_external_id` for the confused-deputy guard. For a single account
that is all that's needed. For an **AWS Organization**, the collector chains from
the management role into each member account, assuming the role *named* by
`aws_member_role_name` in every member (defaults to the role name parsed from
`aws_role_arn` — the common StackSet pattern, e.g.
`OrganizationAccountAccessRole`). Restrict enumeration to specific regions with
`aws_regions`. The secret may carry base credentials for the initial assume, or
be omitted to use the collector's default chain.

### Azure (`azure`)

**Setup guide:** [step-by-step onboarding](provider-setup/azure.md).

Set `azure_tenant_id` and `azure_subscription_id`, and the app-registration
(service-principal) client id in `azure_client_id`. The credential secret carries
the client secret: `{"client_secret": "..."}`. For an Entra directory with **no**
Azure infrastructure to enumerate, use the standalone `entra` provider instead.

## Identity providers

Identity providers ingest a directory — users, groups, and app assignments —
into the identity graph rather than cloud infrastructure. Most of them unify
with cloud IAM principals **by email**, which is what makes cross-surface CIEM
("this Workspace user has admin on that GCP bucket") possible. The exception is
[Auth0](#auth0-auth0), which keys identities per connection instead — see its
section below.

### Okta (`okta`)

**Setup guide:** [step-by-step onboarding](provider-setup/okta.md).

Set `okta_org_url` to the org base URL (e.g. `https://acme.okta.com`). The
credential is either a user-owned SSWS token (`{"api_token": "..."}`) or an API
Services app using client credentials (`{"client_id": "...", "private_key":
"..."}` or `client_secret`), which is the recommended, non-user-bound option.

### Microsoft Entra ID (`entra`)

**Setup guide:** [step-by-step onboarding](provider-setup/entra.md).

A standalone directory-only connection for organizations that have M365/Entra
but no Azure subscription to enumerate. Set `entra_tenant_id` and the
app-registration client id in `entra_client_id`; the client secret goes in the
credential secret. It collects users, groups, service principals, and
conditional-access posture. If you also run an `azure` connection for the same
tenant, the Azure connection defers its directory collection to the standalone
`entra` record so the directory is never collected twice.

### Google Workspace (`google_workspace`)

**Setup guide:** [step-by-step onboarding](provider-setup/google-workspace.md).

Set `workspace_customer_id` to `my_customer` (the delegated super-admin's own
account, the common case) or an explicit customer id. The credential is a GCP
service-account key with **domain-wide delegation**, plus the super-admin subject
to impersonate; store it as `{"service_account_json": "...", "admin_email":
"admin@acme.com"}`. It ingests users, groups, membership, and managed devices,
unifying by email with the GCP IAM principals it references.

### 1Password (`1password`)

**Setup guide:** [step-by-step onboarding](provider-setup/onepassword.md).

Set `onepassword_scim_url` to the account's SCIM bridge URL; the credential is
the SCIM bearer token: `{"scim_url": "...", "scim_token": "..."}`. It collects
users and groups into the identity graph.

### Auth0 (`auth0`)

**Setup guide:** [step-by-step onboarding](provider-setup/auth0.md).

Set `auth0_domain` to the tenant's canonical domain (e.g. `acme.us.auth0.com` or
the legacy `acme.auth0.com` — not a custom domain). The credential is a
Machine-to-Machine application authorized for the Management API with read-only
scopes: `{"client_id": "...", "client_secret": "..."}`. It collects users, roles,
applications, and connections.

!!! note "Auth0 identities are not unified by email"
    Unlike the other identity providers, Auth0 users are kept **scoped to the
    Auth0 tenant** and keyed on their stable Auth0 user id, which means one
    record per connection — the same person signing in through both a database
    connection and a social connection appears as two Auth0 identities. This is
    deliberate: Auth0 emails are per-connection and not necessarily verified or
    unique, so unifying on them would merge identities that are not the same
    principal.

## SaaS

### Cloudflare (`cloudflare`)

**Setup guide:** [step-by-step onboarding](provider-setup/cloudflare.md).

Set `cloudflare_account_id` to the 32-hex account id from the dashboard. The
credential is a read-only account-scoped API token: `{"api_token": "..."}`. An
optional `user_api_token` covers user-scoped endpoints (account members, API
token enumeration); without it those surfaces degrade to unobserved. It collects
zones, DNS posture, R2 buckets, members, API tokens, Access applications, and
Security Center insights.

### GitHub (`github`)

**Setup guide:** [step-by-step onboarding](provider-setup/github.md).

Auth is a **GitHub App installed on the organization** — an App, not a personal
access token — so access is org-scoped, read-only, and uses short-lived
installation tokens. Set `github_org` (the org login), `github_app_id`, and
`github_installation_id`; the App private key goes in the credential secret:
`{"private_key": "-----BEGIN RSA PRIVATE KEY-----..."}`. It collects org
settings/members/teams (identities), repositories (data stores), installed Apps /
webhooks / deploy keys / Actions secrets (non-human identities), and the Actions
OIDC subject configuration.

With the **Contents → Read-only** permission added, the same connection also
drives [Code Scanning](code-scanning.md) — dependencies, secrets,
infrastructure-as-code, container images and licenses, scanned in an ephemeral
sandbox and filed as ordinary findings. It is opt-in per repository through a
`code_scanning` policy; nothing is scanned until you write one.

## AI security (AISPM)

AI providers bring your model-platform organizations into the estate as
first-class subjects, with the same findings and the `nist-ai-rmf` and
`owasp-llm` compliance frameworks.

### OpenAI (`openai`)

**Setup guide:** [step-by-step onboarding](provider-setup/openai.md).

The credential is an **Admin API key** created *with* the `api.management.read`
scope at creation time (a freshly created key — scope-upgraded keys have had
missing-scope issues): `{"admin_api_key": "sk-admin-..."}`. `openai_org_id`
(`org-...`) is optional — the key already implies the org, but when set it is
verified against the discovered org so a mismatch fails the connection early. It
collects the organization, members, projects, and API keys.

### Anthropic (`anthropic`)

**Setup guide:** [step-by-step onboarding](provider-setup/anthropic.md).

Anthropic has two credential planes and either may stand alone:

- **Console** — an Admin key in `credentials`: `{"admin_api_key":
  "sk-ant-admin01-..."}`. Anthropic Console Admin keys carry no scopes (every
  Admin key is full read/write); the collector uses it strictly read-only.
- **Compliance / Analytics** — an optional second secret referenced by
  `compliance_credentials`: `{"compliance_api_key": "sk-ant-api01-..."}` with the
  read-only compliance/analytics scopes. This unlocks enforced-settings posture
  and the activity feed.

Set `anthropic_org_uuid` when connecting **only** the compliance plane (the
Compliance API is addressed by org uuid); with a Console key present it is
discovered automatically. The credential secret may also optionally carry an
`org_oauth_token` to reach the Workload Identity Federation admin plane. Findings
degrade gracefully to whatever plane is connected.

## LimaCharlie (`limacharlie`)

**Setup guide:** [step-by-step onboarding](provider-setup/limacharlie.md).

Inventory your **own** LimaCharlie tenancy as an estate — useful both directly
and as the CAASM source that unifies your sensors with the rest of your assets.
Set exactly one of:

- `limacharlie_oid` — an **org** API key, scoping collection to that one
  organization.
- `limacharlie_uid` — a **user** API key, which enumerates every organization
  the user reaches (the MSSP fleet case — one connection covers the fleet).

The API key goes in the credential secret: `{"api_key": "..."}`.

## Refresh and event-driven freshness

Every connection re-enumerates on the `refresh` cadence (a duration such as
`"6h"`; empty uses the service default) and on demand whenever `sync_now`
changes. For sub-sweep freshness on GCP, `feed_subscription` names a Pub/Sub
subscription carrying a cloud change feed, so targeted re-sweeps reflect changes
in seconds; the periodic sweep remains the safety net. See
[Configuration](configuration.md#cloudsec_provider) for these shared fields.
