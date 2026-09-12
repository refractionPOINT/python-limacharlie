# Auth0

Collects the Auth0 tenant as identity posture: the user directory (with MFA
state), roles and role membership, applications and their machine (M2M)
identities, client grants as entitlement edges, APIs (resource servers), and
inbound connections / identity providers. Tenant-level posture includes MFA
policy, attack protection, and session lifetimes.

**Auth model:** a **Machine-to-Machine application** authorized against the
**Auth0 Management API** with read-only scopes, using client credentials.

!!! info "Auth0 Organizations are not collected"
    **Auth0 Organizations (B2B)** — organizations, their members, and
    organization-scoped role assignments — are outside the current coverage. On
    a tenant that uses them, users, roles and applications are still
    inventoried tenant-wide; what is missing is the per-organization
    membership and role scoping. Granting extra scopes does not change this.

## Prerequisites

- Auth0 tenant admin access.
- Your **canonical tenant domain**, e.g. `example.us.auth0.com` (or the legacy
  `example.auth0.com`).

!!! danger "Custom domains are not usable"
    The Management API audience must be the **canonical** `*.auth0.com`
    domain. A custom domain (`login.example.com`) is rejected. Use the tenant
    domain shown in **Settings → Custom Domains → your Auth0 domain**, or in
    the application's *Domain* field.

## Required scopes

Authorized on the M2M application against the **Auth0 Management API**:

| Scope | Why | Preflight check |
|---|---|---|
| `read:users` | The user directory (identity nodes) | `read:users` |
| `read:clients` | Applications and machine (NHI) identities | `read:clients` |
| `read:connections` | Inbound identity-provider / social-trust posture | `read:connections` |
| `read:roles` | Roles and role membership | `read:roles` |

## Optional scopes

| Scope | Unlocks | Preflight check |
|---|---|---|
| `read:client_grants` | Machine-identity entitlement edges (which API each M2M app can call) | `read:client_grants` |
| `read:resource_servers` | The API (resource-server) inventory | `read:resource_servers` |
| `read:tenant_settings` | Tenant session-lifetime posture | `read:tenant_settings` |
| `read:attack_protection` | Breached-password / brute-force / suspicious-IP posture | `read:attack_protection` |
| `read:guardian_factors` | MFA factor posture | `read:guardian_factors` |
| `read:mfa_policies` | Org MFA-required posture | `read:mfa_policies` |

!!! info "Secret-bearing scopes are deliberately never requested"
    `read:client_keys`, `read:client_credentials`, and
    `read:connections_options` return client secrets and connection secrets.
    The collector never asks for them, so no secret material is ever fetched.
    Do **not** grant them.

## Create the M2M application

1. **Auth0 Dashboard → Applications → Applications → Create Application** →
   choose **Machine to Machine Applications** → **Create**.
2. Select the **Auth0 Management API** as the API to authorize.
3. In the scope picker, select the four required scopes plus any optional ones.
   Filter on `read:` and pick them individually — do **not** select all.
4. Create, then copy the **Client ID** and **Client Secret** from the
   application's *Settings* tab.

To change scopes later: **Applications → APIs → Auth0 Management API →
Machine to Machine Applications** tab → expand your application → adjust the
checkboxes → **Update**.

!!! danger "Do not use the API Explorer's test-application button"
    The Management API's **API Explorer** tab offers *Create & Authorize a Test
    Application*. That shortcut grants the application **every** Management API
    scope — including the write and secret-bearing ones this connector
    deliberately avoids. Create the application from the Applications page and
    pick scopes explicitly.

## Create the credentials secret

```json
{"client_id": "<m2m-client-id>", "client_secret": "<m2m-client-secret>"}
```

```bash
limacharlie secret set --key auth0-m2m \
    --value "$(cat auth0-secret.json)" --enabled
```

`secret set` wraps the value into the secret record's `{"secret": "..."}`
envelope for you.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: auth0
auth0_domain: "example.us.auth0.com"
credentials: hive://secret/auth0-m2m
internal_domains: [example.com]
refresh: 6h
```

In the web app: **Add provider → Auth0**, then set **Tenant domain**,
**Credentials**, and **Refresh interval**.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

The report contains one check per scope, named `Scope read:<name>`, plus:

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The client credentials were rejected, or the domain is wrong — no token could be minted. |
| `reachability` | ✅ | A token was minted but the Management API is not reachable/usable. |
| `read:users` | ✅ | The user directory cannot be enumerated. |
| `read:clients` | ✅ | Applications and machine identities cannot be enumerated. |
| `read:connections` | ✅ | Inbound identity-provider posture unavailable. |
| `read:roles` | ✅ | Roles and role membership cannot be enumerated. |
| `read:client_grants` | — | Entitlement edges unavailable. |
| `read:resource_servers` | — | API inventory unavailable. |
| `read:tenant_settings` | — | Session-lifetime posture unavailable. |
| `read:attack_protection` | — | Attack-protection posture unavailable. |
| `read:guardian_factors` | — | MFA factor posture unavailable. |
| `read:mfa_policies` | — | Org MFA-required posture unavailable. |

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails: `access_denied` / `unauthorized_client` | The application is not authorized on the **Auth0 Management API** | Authorize it under *APIs → Auth0 Management API → Machine to Machine Applications* |
| `auth` fails: `service not found` | Wrong domain — usually a custom domain, or a missing region segment (`example.us.auth0.com`) | Use the canonical tenant domain |
| A scope check fails while `auth` passes | That scope is not selected on the M2M authorization | Add it in the scope picker and **Update** |
| Sweeps are slow on a free tenant | Free Auth0 tenants are rate-limited to roughly 2 requests/second tenant-wide | Expected; the collector paces itself. Raise `refresh` if needed |
| Large directories | The Management API caps `/users` results per query; the collector segments the directory by creation time to read past the cap | No action needed — a segment it cannot split is reported as an error rather than silently truncated |
