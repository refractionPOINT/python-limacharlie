# 1Password

Collects the 1Password account directory — users and groups with membership —
into the identity graph, unified by email with your cloud and IdP identities.
Optionally, a **1Password Connect** server adds vault (secret-store) inventory.

**Auth model:** the account's **SCIM bridge** and its **bearer token**. This is
the same provisioning endpoint your identity provider uses; the collector reads
it read-only.

## Prerequisites

- **1Password Business**, with **automated provisioning** set up (hosted
  provisioning or a self-hosted SCIM bridge).
- The **SCIM base URL** and its **bearer token**.
- The SCIM URL must be **`https://`** and its hostname must resolve on the
  public internet. Plain `http://`, a private or loopback address literal, and
  URLs with credentials embedded in them are rejected outright. The same applies
  to a Connect URL. A self-hosted bridge behind a VPN or a private-only DNS name
  cannot be collected.
- *(Optional)* a running **1Password Connect** server plus a Connect token, if
  you want vault inventory.

## Get the SCIM URL and bearer token

1. Sign in to your 1Password account on the web as an owner/administrator.
2. Open **Integrations** (the provisioning setup page).
3. Copy the **SCIM URL** and the **bearer token** shown there.

| Deployment | SCIM base URL |
|---|---|
| Hosted provisioning | `https://provisioning.1password.com/scim/v2` |
| Self-hosted SCIM bridge | Your bridge's own URL, e.g. `https://scim.example.com` |

Use exactly the URL your identity provider is configured with — the collector
appends `/Users` and `/Groups` to it, so a wrong base path shows up immediately
as a failed `scim_users` check. A trailing slash is harmless (it is stripped),
but the path before it must be right.

!!! info "Why the two forms differ"
    Hosted provisioning serves SCIM under a `/scim/v2` path, while a
    self-hosted bridge serves it at the **root** of its own domain (the address
    you open in a browser to reach the bridge's status page). Both are correct
    for their deployment — copy whichever your Integrations page shows.

!!! info "This is the provisioning credential, not a new one"
    The bearer token and the `scimsession` file are cryptographically linked.
    If you ever regenerate credentials from the Integrations page, update both
    your identity provider **and** this secret.

!!! tip "Read-only by construction"
    The collector only issues `GET /Users` and `GET /Groups`. The SCIM token is
    account-scoped and all-or-nothing — 1Password does not offer a narrower
    read-only variant.

## Optional: 1Password Connect for vault inventory

[1Password Connect](https://developer.1password.com/docs/connect/) is a
self-hosted server you deploy alongside your account. Follow 1Password's Connect
documentation to deploy the server and issue an access token, then include
`connect_url` and `connect_token` in the secret. The collector reads only
`GET /v1/vaults` — vault names and metadata, never item contents. Without
Connect configured, vault inventory is simply unobserved.

## Create the credentials secret

Save the credential JSON as `op-secret.json`:

```json
{
  "scim_url": "https://provisioning.1password.com/scim/v2",
  "scim_token": "<bearer-token>",
  "connect_url": "https://connect.example.com",
  "connect_token": "<connect-token>",
  "org_domain": "example.com"
}
```

| Field | Required | Meaning |
|---|:--:|---|
| `scim_url` | ✅ | The SCIM base URL |
| `scim_token` | ✅ | The SCIM bearer token |
| `connect_url` / `connect_token` | — | 1Password Connect, for vault inventory. Omit **both** if you are not running Connect. |
| `org_domain` | — | The account's primary email domain. It is merged with the provider record's `internal_domains`, so directory members outside that set are classified as external collaborators. |

```bash
limacharlie secret set --key onepassword-scim \
    --value "$(cat op-secret.json)" --enabled
```

`secret set` wraps whatever you pass in `--value` into the secret record's
`{"secret": "..."}` shape for you.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: 1password
onepassword_scim_url: "https://provisioning.1password.com/scim/v2"
credentials: hive://secret/onepassword-scim
internal_domains: [example.com]
refresh: 6h
```

In the web app: **Add provider → 1Password**, then set **SCIM URL**,
**Credentials**, and **Refresh interval**.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `scim_users` | ✅ | The bearer token was rejected or the SCIM URL is wrong — this both authenticates and reads the user directory. Nothing else is probed on failure. |
| `scim_groups` | ✅ | Group and membership inventory unavailable. |
| `connect_vaults` | — | Vault (secret-store) inventory unavailable. Passes with a note when Connect is simply not configured. |

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `scim_users` fails with 404 | The base URL is missing (or wrongly carrying) the `/scim/v2` path | Copy the SCIM URL verbatim from the Integrations page |
| `scim_users` fails with 401 | The bearer token is wrong, or credentials were regenerated | Copy the current token from the Integrations page |
| `scim_users` fails to connect | The SCIM bridge is not reachable from the public internet, or is behind an allowlist | Self-hosted bridges must be reachable; confirm DNS and TLS |
| The URL is rejected before any check runs | The URL is not `https://`, points at a private/loopback address, or embeds credentials | Use a public `https://` hostname (see [Prerequisites](#prerequisites)) |
| `connect_vaults` fails | Connect URL/token wrong, or the Connect token has no vault access | Verify the Connect server is running and the token grants read on the vaults you want inventoried |

## Known limitations

- **No activity signal.** Neither SCIM nor Connect exposes last-used data, so
  1Password identities carry no dormancy or used-vs-granted analysis. Absence of
  activity is treated as unknown, never as "unused".
- **Connect sees only its own vaults.** The Connect API returns the vaults its
  token has been granted, so vault inventory is a partial view of the estate by
  design — grant the token read access on every vault you want inventoried.
- **No vault ACLs.** Connect does not expose who can open a vault, so
  vault-access edges are not built from this provider.
