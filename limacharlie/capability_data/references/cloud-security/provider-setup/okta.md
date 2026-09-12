# Okta

Collects the Okta directory as identity posture: users (with MFA factors and
admin roles), groups and membership, application inventory and per-user app
assignments, and external identity providers (federation / social trust).
Optionally, org API-token hygiene and the AI-agent registry.

**Auth model:** an Okta **API Services** app integration using OAuth 2.0
client-credentials with **private-key JWT**. A user-owned **SSWS API token** is
also supported, but the service app is strongly preferred — it has no owning
person, no password/MFA lifecycle, and no 30-day-inactivity expiry.

## Prerequisites

- **Super Administrator** access to the Okta org (creating an API Services app
  and assigning it an admin role both require it).
- Your org base URL, e.g. `https://example.okta.com`. Use the URL you sign in
  to; note that an org's *name* and its *subdomain* can differ.

## Scopes

Granted on the app's **Okta API Scopes** tab. The collector requests all five
of these by default; the first four are required for the connection to be
usable.

| Scope | Required | Why | Preflight check |
|---|:--:|---|---|
| `okta.users.read` | ✅ | The user directory — the core identity inventory | `users` |
| `okta.groups.read` | ✅ | Groups and membership | `groups` |
| `okta.apps.read` | ✅ | Application inventory and assignments | `apps` |
| `okta.roles.read` | ✅ | Admin-role enrichment on every user | `roles` |
| `okta.idps.read` | — | External identity providers (federation/social trust). Leave it ungranted and only that surface is skipped | `idps` |

!!! danger "`okta.roles.read` is not optional"
    The user collector enriches every user with their admin roles inline and
    treats a roles denial as fatal. Without this scope **no users are
    inventoried at all** — not merely "users without roles".

Two further scopes are outside the default set entirely — granting them is not
enough, they are requested only when you list them explicitly (see
[Requesting extra scopes](#requesting-extra-scopes)):

| Scope | Unlocks | Preflight check |
|---|---|---|
| `okta.apiTokens.read` | Org API-token (standing SSWS credential) hygiene | `api_tokens` |
| `okta.aiAgents.read` | The Okta for AI Agents registry — source-asserted AI-agent classification. Requires the paid Okta for AI Agents subscription | `ai_agents` |

## Create the API Services app

1. **Admin console → Applications → Applications → Create App Integration →
   API Services.** Name it (e.g. `LimaCharlie Cloud Security`) and save.
2. On the app's **General** tab, set **Client authentication** to
   **Public key / Private key**.
3. Under **PUBLIC KEYS**, choose **Add key → Generate new key**, then copy the
   **private key in JWK format**. This is shown once — keep it.
4. On the **Okta API Scopes** tab, **Grant** each of the five default scopes
   above (plus any optional ones you want).
5. On the app's **Admin roles** tab, **assign an admin role** — **Read-only
   Administrator** is sufficient for the required scope set.
6. Copy the app's **Client ID** from the General tab.

!!! danger "Scopes *and* an admin role are both required"
    An API Services app with the scopes granted but **no admin role assigned**
    authenticates fine and then 403s on groups and per-user roles. Granting a
    `.read` scope does not by itself confer directory read access.

!!! danger "Private-key JWT is mandatory"
    Okta's **org authorization server rejects client-secret authentication**
    for `okta.*` scopes — it requires `private_key_jwt`. If you configure the
    app with a client secret, token minting fails with *"Client Credentials
    requests to the Org Authorization Server must use the private_key_jwt
    token_endpoint_auth_method"*. Use **Public key / Private key**.

!!! info "DPoP is handled for you"
    On newly created API Services apps you may find the sender-constrained
    tokens (**DPoP**) toggle switched on and not editable. This is not a
    misconfiguration and needs no credential field: when the token endpoint
    requires DPoP, the collector detects it and switches to DPoP
    automatically.

## Create the credentials secret

**API Services app (recommended)** — paste the private JWK as a nested JSON
object, no string-escaping needed:

```json
{
  "org_url": "https://example.okta.com",
  "client_id": "<app-client-id>",
  "private_key": { "kty": "RSA", "kid": "...", "n": "...", "e": "AQAB", "d": "...", "p": "...", "q": "..." }
}
```

A PEM string is also accepted for `private_key`; in that case add `"key_id"`
with the key's `kid`.

**SSWS token (alternative)**:

```json
{"org_url": "https://example.okta.com", "api_token": "<SSWS-token>"}
```

Either shape also accepts an optional `org_domain` — the org's primary email
domain. It is treated as an internal domain on top of the record's
`internal_domains`, so users outside it are flagged as external collaborators.

!!! note "`org_url` in the secret wins"
    The org URL can be carried on the provider record (`okta_org_url`) or in
    the secret (`org_url`). When both are present the **secret's** value is
    used; the record's is only a fallback.

Store it:

```bash
limacharlie secret set --key okta-credentials \
    --value "$(cat okta-secret.json)" --enabled
```

`secret set` wraps the value into the secret record's `{"secret": "..."}`
envelope for you.

### Requesting extra scopes

By default the collector requests exactly the five scopes listed above. To use
an optional scope, grant it on the app **and** list the full scope set in the
secret:

```json
{
  "org_url": "https://example.okta.com",
  "client_id": "<app-client-id>",
  "private_key": { "...": "..." },
  "scopes": ["okta.users.read", "okta.roles.read", "okta.groups.read",
             "okta.apps.read", "okta.idps.read", "okta.apiTokens.read"]
}
```

!!! warning "`scopes` replaces the default set — and misses fail silently"
    The list is used verbatim; it does not add to the defaults. Always repeat
    the five default scopes alongside the optional ones.

    A scope in the list that is **not granted on the app** does not fail the
    token mint: Okta's org authorization server quietly drops it and issues the
    token without it. The gap only shows up later, as that one surface
    returning 403 during the sweep. Grant every scope you list.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: okta
okta_org_url: "https://example.okta.com"
credentials: hive://secret/okta-credentials
internal_domains: [example.com]
refresh: 6h
```

In the web app: **Add provider → Okta**, then set **Org URL**,
**Credentials**, and **Refresh interval**.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The credential was rejected outright (bad key, wrong client ID, wrong org URL). Nothing else is probed. |
| `users` | ✅ | `okta.users.read` denied — no identity inventory. |
| `groups` | ✅ | `okta.groups.read` denied — no groups or membership edges. |
| `apps` | ✅ | `okta.apps.read` denied — no application inventory or app-access edges. |
| `roles` | ✅ | `okta.roles.read` denied — **no users are inventoried** (role enrichment is fatal to the user collector). |
| `idps` | — | External identity-provider posture unavailable. |
| `api_tokens` | — | Per-user API-token hygiene unavailable. |
| `ai_agents` | — | Source-asserted AI-agent classification unavailable (needs Okta for AI Agents + `okta.aiAgents.read`). |

!!! info "401 vs 403"
    A **401** means the credential itself was rejected — the report
    short-circuits to a single failed `auth` check. A **403** means you
    authenticated but lack that scope or admin permission, so `auth` passes and
    only that surface fails.

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails: *must use the private_key_jwt token_endpoint_auth_method* | App configured with a client secret | Switch the app to **Public key / Private key** and store the private JWK |
| `groups` / `roles` 403 while `auth` passes | No admin role assigned to the app | Assign **Read-only Administrator** on the app's *Admin roles* tab |
| A scope you granted still 403s | The org authorization server **silently drops ungranted scopes** at mint — the token simply lacks it | Re-check the *Okta API Scopes* tab; the 403's `WWW-Authenticate` header names the missing scope |
| A surface 403s after you set `scopes` | The list omitted that scope, or it is listed but not granted on the app — either way the mint succeeds without it | List every scope you need and grant each one on the app |
| `auth` fails: host unreachable | Wrong subdomain (org *name* ≠ org *subdomain*) | Use the exact URL you sign in to |
| SSWS token stops working | SSWS tokens expire after 30 days of inactivity and die with their owner | Move to an API Services app |
