# Cloudflare

The lightest provider: a **scoped, read-only API token** plus your **account
ID**. No infrastructure to stand up.

## Create the API token

Cloudflare has two kinds of token, created in two different places. Use an
**Account API token** — it is owned by the account rather than by a person, so
it survives that person leaving:

**Cloudflare dashboard → Manage Account → API Tokens → Create Token → Create
Custom Token.**

!!! note "User tokens live elsewhere"
    Tokens created under **My Profile → API Tokens** are *user*-owned. One
    scoped to the account also works for the surfaces below, but it is tied to
    an individual. A user token is only needed to enumerate *user*-owned API
    tokens, and as a fallback for account membership — see
    [account members and user-owned API tokens](#optional-account-members-and-user-owned-api-tokens).

**Minimum permissions** (the required checks — authenticate plus the
zones/DNS inventory):

| Type | Permission | Access |
|---|---|---|
| Account | Account Settings | Read |
| Zone | Zone | Read |
| Zone | DNS | Read |

!!! warning "DNS: Read is not covered by the preflight check"
    The `zones` check reads the zone *list*, which needs only **Zone: Read** — so
    a token without **DNS: Read** passes preflight and then collects zero DNS
    records. Every check that depends on record-level data, such as unproxied
    origin IPs published in public DNS, then silently never fires. Grant both.

**Optional permissions** — each lights up an additional inventory surface
(skip any you do not want):

| Surface | Add (all Account-scope, Read) |
|---|---|
| Zero Trust Access (apps, IdPs, service tokens) | Access: Apps and Policies · Access: Service Tokens · Access: Organizations, Identity Providers, and Groups |
| Security Center findings | Security Center Insights |
| R2 storage inventory | Workers R2 Storage |

Scope the token's resources:

- **Account Resources:** Include → your account.
- **Zone Resources:** Include → All zones.

Copy the token (it is shown once). You can confirm it independently — an
account-owned token introspects under the account:

```bash
curl -s -H "Authorization: Bearer <TOKEN>" \
  https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/tokens/verify
# "status":"active" confirms it is valid
```

!!! note "Each token kind has its own verify endpoint"
    `/accounts/<ACCOUNT_ID>/tokens/verify` introspects **account-owned** tokens
    only; the equivalent for a *user*-owned token is `/user/tokens/verify`. A
    token that verifies under the wrong one returns 401 even though it works
    fine. `provider test` sidesteps this entirely: it authenticates by reading
    the account itself, which works for either kind.

## Get the account ID

The 32-hex string in the dashboard's right-hand sidebar (Overview), or in the
dashboard URL.

## Create the credentials secret

Save the credential JSON as `cf-secret.json`:

```json
{"api_token": "<the-scoped-read-only-token>"}
```

```bash
limacharlie secret set --key cloudflare-credentials \
    --value "$(cat cf-secret.json)" --enabled
```

`secret set` wraps whatever you pass in `--value` into the secret record's
`{"secret": "..."}` shape for you.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: cloudflare
cloudflare_account_id: "<32-hex-account-id>"
credentials: hive://secret/cloudflare-credentials
```

In the web app: **Add provider → Cloudflare**, then set **Account ID**,
**Credentials**, and **Refresh interval**.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The token was rejected (401), or it is valid but missing **Account Settings: Read** (403), or it cannot see the configured account. A failure here stops the run — nothing else is probed. |
| `zones` | ✅ | Zone inventory unavailable. Note this reads the zone list only; see the DNS caveat above. |
| `access` | — | Zero Trust Access apps, identity providers, and service tokens unavailable. Passes with a note when Zero Trust Access is not enabled on the account. |
| `security_center` | — | Security Center findings unavailable. Passes with a note when Security Center is not available on the account's plan. |
| `r2` | — | R2 storage inventory unavailable. Passes with a note when R2 is not enabled on the account. |
| `user_scoped` | — | The configured `user_api_token` could not read account members and/or user-owned API tokens. Passes with a note when no `user_api_token` is configured at all. |

Each optional check passes when the matching token permission is present. It
**also passes, with a note**, when the product itself is not enabled on the
account or plan — there is genuinely nothing to collect, which is a true empty
rather than a coverage gap. An optional check fails only on a real permission
denial or a connectivity problem.

### Optional: account members and user-owned API tokens

Two surfaces may want a *user*-owned token:

- **Account members** — read with the account token first, falling back to the
  user token, so on many accounts the account token alone is enough.
- **API tokens** — account-owned tokens are enumerated with the account token;
  **user**-owned tokens can only be enumerated with a user token.

To cover both regardless, create a second token under **My Profile → API
Tokens** and add it to the same secret:

```json
{"api_token": "<account-scoped-token>", "user_api_token": "<user-owned-token>"}
```

Without it, account members are collected only if the account token can read
them, and user-owned tokens are simply unobserved.
