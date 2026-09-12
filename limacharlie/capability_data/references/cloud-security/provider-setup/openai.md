# OpenAI

Collects your OpenAI platform organization as an AI-security surface: projects,
members (including pending invites — staged seats that have never logged in)
and service accounts, API keys (with last-used timestamps, so dormant
and over-scoped keys surface), org Admin API keys, mTLS certificates, and
audit-log availability posture.

**Auth model:** an **Admin API key** created with the read-only
`api.management.read` scope, calling the OpenAI Administration API.

## Prerequisites

- **Organization Owner** on the OpenAI platform account — only owners can
  create Admin API keys.

## Create the Admin API key

1. Go to **platform.openai.com → Settings → Organization → Admin keys**
   (`https://platform.openai.com/settings/organization/admin-keys`).
2. Click **Create admin key**.
3. **Select the `api.management.read` scope at creation time.**
4. Copy the key (`sk-admin-…`) — it is displayed once.

!!! danger "Scope the key when you create it"
    Grant `api.management.read` **during creation**. Keys whose scopes are
    edited after the fact have been observed to keep failing with
    *"Missing scopes: api.management.read"*. If a key misbehaves, delete it and
    create a fresh one with the scope selected up front.

!!! tip "Read-only by design"
    `api.management.read` is a true read-only scope. The collector never writes
    to your organization; it only lists projects, users, keys, certificates,
    and audit-log availability.

## Optional: enable audit logging

The org audit log is a separate toggle in the OpenAI organization settings.
It is not required for the connection, but without it there is no
configuration-change forensics — the `audit_logs` check reports that.

## Create the credentials secret

The secret's shape is:

```json
{"admin_api_key": "sk-admin-..."}
```

You may also store the bare key string; it is wrapped into this shape
automatically, which makes it a one-liner:

```bash
limacharlie secret set --key openai-admin-key \
    --value 'sk-admin-...' --enabled
```

`secret set` wraps whatever you pass in `--value` into the secret record's
`{"secret": "..."}` shape for you.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: openai
credentials: hive://secret/openai-admin-key
internal_domains: [example.com]
refresh: 6h
```

`openai_org_id` (`org-…`) is **optional**: the Admin key already implies its
organization, which the collector discovers. Setting it turns that into an
assertion — a mismatch fails the connection immediately rather than silently
sweeping the wrong organization. Useful when one team manages several OpenAI
orgs.

In the web app: **Add provider → OpenAI**, then set **Credentials** and
**Refresh interval**. The optional **Organization ID** field is the same
assertion as `openai_org_id`; leave it blank to have the organization
discovered.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The Admin key was rejected, or lacks `api.management.read`. Nothing else is probed. |
| `projects` | ✅ | Project enumeration denied — the sweep has no accounts to walk. |
| `project_keys` | ✅ | Per-project API-key inventory denied — no key hygiene (dormant/over-scoped keys). Passes with a note if the org has no projects yet. |
| `admin_keys` | — | Org Admin-API-key hygiene (dormant / never-expiring admin keys) unavailable. |
| `certificates` | — | mTLS certificate hygiene unavailable. Passes with a note when the org uses no certificates. |
| `audit_logs` | — | Audit-log availability posture unavailable. Passes with a note when audit logging is simply not enabled. |

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails: *Missing scopes: api.management.read* | The key was created without the scope, or the scope was added afterwards | Create a **new** Admin key with the scope selected at creation |
| `auth` fails: 401 | Not an Admin key (a project key `sk-…` was used), or the key was revoked | Create an Admin key (`sk-admin-…`) as an Organization Owner |
| Connection fails with an org mismatch | `openai_org_id` does not match the key's organization | Correct or remove `openai_org_id` |
| Key inventory looks empty | The organization has no projects, or keys live in projects the key cannot see | Confirm projects exist under **Settings → Organization → Projects** |

## Known limitations

MFA/SSO enforcement, IP allow-lists, and the connector registry are
console-only settings with no Administration API surface, so they are not
collected. Data-plane objects (vector stores, files, assistants) require a
separate per-project credential and are not part of this connector.
