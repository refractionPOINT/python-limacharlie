# Anthropic

Collects your Anthropic organization as an AI-security surface: the member
directory (including pending invites — staged seats that have never logged in),
workspaces, and API keys from the Console plane, plus — for Claude
Enterprise organizations — enforced security settings and a per-key/per-user
activity feed that powers dormancy findings.

**Auth model:** two independent credential planes, **either of which can stand
alone**:

| Plane | Credential | Gives |
|---|---|---|
| **Console Admin API** | Admin key `sk-ant-admin01-…` | Members, workspaces, API keys |
| **Enterprise Compliance API** | Compliance key `sk-ant-api01-…` with read-only scopes | Enforced-settings posture, activity feed (last-used per key/user) |

Connect one or both. Findings degrade gracefully to whatever plane is
connected.

## Prerequisites

- For the Console plane: the **admin** role in the Anthropic Console
  organization.
- For the Compliance plane: a **Claude Enterprise** organization (the
  Compliance API is not available on Team or Pro plans) and your
  **organization UUID**.

!!! info "Two products, two places to create a key"
    Keys are created in different consoles depending on the product. A key
    created in one organization cannot manage another — if your company uses
    both Claude Console and Claude Enterprise, create one key in each.

## Create the Console Admin key

1. Sign in as an organization **admin** and open
   **Claude Console → Settings → Admin keys**
   (`https://platform.claude.com/settings/admin-keys`).
2. Click **Create key**, give it a name, choose a key expiration, and click
   **Create**.
3. Copy the value (`sk-ant-admin01-…`) — the full secret is shown once.

!!! warning "Console Admin keys are not scopeable"
    Claude Console Admin keys have no selectable scopes — every key carries
    full access to all endpoints that accept Admin API keys. The collector
    uses it **strictly read-only** and stores it only as a secret reference,
    but there is no narrower Console key to issue. If that is not acceptable,
    connect the Compliance plane alone.

## Create the Compliance key (Claude Enterprise)

1. Sign in to **claude.ai → Organization settings → API**
   (`https://claude.ai/admin-settings/api-access`) and find the **Keys**
   section.
2. Click **+ Create key**, name it, and select the scopes below.
3. Copy the value (`sk-ant-api01-…`) — shown once.

The **primary owner** of the parent organization can create a key reaching
every linked organization; an **organization owner** can create one carrying
Compliance scopes only, restricted to their own organization.

| Scope | Unlocks |
|---|---|
| `read:compliance_org_data` | Enforced organization security settings |
| `read:compliance_activities` | The activity feed — per-key and per-user last-used, which drives dormancy findings |

Those two are the whole ask. Anthropic's `read:analytics` scope is **not used by
this connector today** — no usage-analytics endpoint is called, so adding it
unlocks nothing here.

!!! tip "The broad audit scope also works"
    Anthropic offers `read:org_audit`, a single read-only scope covering the
    Admin API read endpoints plus every Compliance API read endpoint, intended
    for security-audit integrations. A Compliance key carrying it works fine
    here. Be aware that only its *Compliance* coverage is exercised: this
    connector reaches the Console plane exclusively through the Admin key on
    `credentials`, so `read:org_audit` on a Compliance key is not a substitute
    for connecting the Console plane.

!!! warning "Scopes are fixed at creation"
    To add a scope later you must create a new key. The Compliance API must
    also be **enabled for your organization** before a key carrying Compliance
    scopes will work.

You will also need the **organization UUID** (8-4-4-4-12 hex), which addresses
the Compliance API.

## Create the credentials secret(s)

**Console plane** — `anthropic-admin`:

```json
{"admin_api_key": "sk-ant-admin01-..."}
```

**Compliance plane** — a *separate* secret, `anthropic-compliance`:

```json
{"compliance_api_key": "sk-ant-api01-..."}
```

Bare key strings are accepted for both and wrapped into these shapes
automatically, so the simplest path is to store the key verbatim:

```bash
limacharlie secret set --key anthropic-admin \
    --value 'sk-ant-admin01-...' --enabled
limacharlie secret set --key anthropic-compliance \
    --value 'sk-ant-api01-...' --enabled
```

`secret set` wraps whatever you pass in `--value` into the secret record's
`{"secret": "..."}` shape for you. Pass the JSON object above instead of a bare
key when the secret needs a second field — see
[workload identity federation](#optional-workload-identity-federation-inventory).

Keep the two planes in separate secrets — the provider record references them
independently and they are merged at runtime.

## Create the provider record

Both planes:

```yaml
provider_type: anthropic
anthropic_org_uuid: "00000000-0000-0000-0000-000000000000"
credentials: hive://secret/anthropic-admin
compliance_credentials: hive://secret/anthropic-compliance
internal_domains: [example.com]
refresh: 6h
```

Console plane only:

```yaml
provider_type: anthropic
credentials: hive://secret/anthropic-admin
```

Compliance plane only (Enterprise organizations with no Console plane):

```yaml
provider_type: anthropic
anthropic_org_uuid: "00000000-0000-0000-0000-000000000000"
compliance_credentials: hive://secret/anthropic-compliance
```

| Field | Rule |
|---|---|
| `anthropic_org_uuid` | Optional when the Console key is present (it is discovered). **Required** for a Compliance-only connection — the Compliance API is addressed by org UUID. |
| `credentials` | The Console Admin key secret. May be omitted **only** when `compliance_credentials` is set. |
| `compliance_credentials` | The Compliance key secret. Only valid for `provider_type: anthropic`. |

In the web app: **Add provider → Anthropic**, then supply either or both
credentials plus the **Organization UUID** where required.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ *(Console)* | The Console Admin key was rejected, or it belongs to a different organization than the `anthropic_org_uuid` you set. This check covers the **Console plane only** and appears only when a Console key is configured — the rest of the Console plane is not probed after it fails. A Compliance-only connection has no `auth` row; `compliance_settings` is its gate. |
| `directory` | ✅ *(Console)* | Member directory unreadable. |
| `workspaces` | ✅ *(Console)* | Workspace inventory unreadable. |
| `api_keys` | ✅ *(Console)* | API-key inventory unreadable. |
| `compliance_settings` | ✅ only when Compliance is the **sole** plane | Enforced organization security-settings posture unavailable. |
| `activity_feed` | — | Per-key/per-user last-used (dormancy) unavailable. |
| `console` | — | Informational: reports that the Console plane is not configured and what that costs. |
| `compliance` | — | Informational: reports that the Compliance plane is not configured and what that costs. |

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails on the Console key | A workspace key (`sk-ant-api01-…`) was used as the Admin key | Create an Admin key (`sk-ant-admin01-…`) under *Claude Console → Settings → Admin keys* |
| Compliance checks fail with 401/403 | The key lacks a required scope, the scope set is fixed at creation, or the Compliance API is not enabled for the organization | A 403 lists the scopes the key has and the scopes the endpoint needs; create a new key with the missing scope |
| *"anthropic_org_uuid is required"* | Compliance-only connection with no org UUID | Set `anthropic_org_uuid` |
| Dormancy findings never appear | The activity feed is unavailable, or covers only part of the window | Connect the Compliance plane. A partial feed never asserts "unused" — absence of data is treated as unknown, not as dormant |

## Optional: workload identity federation inventory

The Console secret may additionally carry an `org_oauth_token` — an
`org:admin`-scoped OAuth bearer token that unlocks the workload identity
federation admin plane (service accounts, federation issuers and rules), which
Admin API keys cannot reach:

```json
{"admin_api_key": "sk-ant-admin01-...", "org_oauth_token": "..."}
```

These tokens are short-lived by design. Organizations that want this surface
keep it live by refreshing the secret from their own automation; an expired
token degrades the federation inventory to last-known values rather than
failing the sweep.
