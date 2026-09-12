# Google Workspace

Collects identity posture from Google Workspace — users, groups and
membership, admin roles, user security posture, devices, inbound-SSO profiles,
and Gemini-in-Workspace usage — via the Admin SDK and Cloud Identity APIs.

**Auth model:** a **Google Cloud service account**, in one of two setups:

- **Domain-wide delegation (DWD)** — the service account **impersonates a
  Workspace super admin** to read directory data. This is the recommended
  setup and the rest of this page assumes it.
- **No delegation** — the service account calls the Admin SDK directly, and
  must itself hold a Workspace admin role in the Admin console. See
  [Alternative: no delegation](#alternative-no-delegation).

## Prerequisites

1. A GCP **service account** with a JSON key (a dedicated one, or reuse your
   GCP collector service account).
2. In that service account's GCP project, **enable**:
    - **Admin SDK API** (`admin.googleapis.com`)
    - **Cloud Identity API** (`cloudidentity.googleapis.com`) — needed for
      inbound-SSO and Cloud Identity device surfaces.
3. A real **Workspace Super Admin** account to impersonate
   (e.g. `admin@example.com`) — DWD setup only.

## OAuth scopes

Only the user and group scopes are required. Each remaining scope unlocks one
surface, and leaving it out degrades only that surface.

| Capability | Required | Scope |
|---|:--:|---|
| Directory users (read) | ✅ | `https://www.googleapis.com/auth/admin.directory.user.readonly` |
| Groups & membership | ✅ | `https://www.googleapis.com/auth/admin.directory.group.readonly` |
| Group members | ✅ | `https://www.googleapis.com/auth/admin.directory.group.member.readonly` |
| User security posture | — | `https://www.googleapis.com/auth/admin.directory.user.security` |
| Admin roles | — | `https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly` |
| Inbound SSO profiles | — | `https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly` |
| Mobile devices | — | `https://www.googleapis.com/auth/admin.directory.device.mobile.readonly` |
| ChromeOS devices | — | `https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly` |
| Cloud Identity devices | — | `https://www.googleapis.com/auth/cloud-identity.devices.readonly` |
| Gemini-in-Workspace usage | — | `https://www.googleapis.com/auth/admin.reports.audit.readonly` |

Copy-paste block for the DWD scopes field (one comma-separated line):

```text
https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.group.member.readonly,https://www.googleapis.com/auth/admin.directory.user.security,https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly,https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly,https://www.googleapis.com/auth/admin.directory.device.mobile.readonly,https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly,https://www.googleapis.com/auth/cloud-identity.devices.readonly,https://www.googleapis.com/auth/admin.reports.audit.readonly
```

!!! info "What the Gemini scope collects"
    `admin.reports.audit.readonly` reads the Admin SDK **Reports** audit stream
    to land Gemini-in-Workspace usage as an application with per-user access
    edges — only the set of users seen in the trailing window, never any
    prompt or response content. Skipping it costs only that surface: it degrades
    to unobserved and previously collected rows are kept, never deleted.

## Register domain-wide delegation

In the **Google Admin console** → **Security → Access and data control → API
controls → Manage Domain-Wide Delegation → Add new**:

- **Client ID** = the service account's **numeric OAuth client ID** (from the
  service-account JSON key's `client_id`, or GCP Console → IAM & Admin →
  Service Accounts → the service account → *Unique ID*).
- **OAuth scopes** = the full comma-separated list above.

!!! warning "Register the entire scope list, exactly"
    Two Google behaviors bite here:

    - **All-or-nothing token mint:** when LimaCharlie requests a token, if
      *any* requested scope is not authorized for the client, Google rejects
      the **whole** request. Registering only
      `admin.directory.user.readonly` will still fail because other surfaces
      request additional scopes.
    - **Literal string match:** the broader `…/admin.directory.user` does
      **not** satisfy the narrower `…/admin.directory.user.readonly`. No
      typos or trailing spaces.
    - DWD changes can take ~10 minutes (occasionally up to 24h) to propagate.

## Create the credentials secret

The Workspace provider record has **no field for the impersonation admin** —
it lives **inside the secret**, which is a **wrapper** around the
service-account key:

```json
{
  "service_account_json": { "type": "service_account", "project_id": "...", "private_key": "...", "client_email": "...", "...": "..." },
  "admin_email": "admin@example.com"
}
```

- `service_account_json` — the **entire raw Google service-account key JSON**,
  nested as this key's value.
- `admin_email` — the Super Admin to impersonate. Omit it only for the
  no-delegation setup below.
- `domain` — **optional**, and a filter rather than a label. Most connections
  should leave it out entirely.

!!! warning "`domain` narrows what is collected"
    Setting `domain` enumerates that **one** domain instead of the whole
    customer. On a tenant with secondary or additional domains, every user and
    group outside it is silently absent from the inventory — the sweep succeeds
    and the connection looks healthy. Leave `domain` out unless you
    deliberately want a single-domain inventory.

    To declare which domains count as internal (for external-collaborator
    detection), use the provider record's `internal_domains` instead. That is a
    classification list and does not restrict collection.

!!! danger "Do not flatten the wrapper"
    `admin_email` and `domain` are siblings of `service_account_json`, **not**
    fields inside it and **not** extra keys alongside `type` / `private_key` /
    `client_email` at the top level.

    A secret whose top level looks like a service-account key is read as the
    **no-delegation** form. `admin_email` is then ignored *wherever it sits* —
    no error, no warning — the token is minted with no subject, and every call
    goes to Google as the service account itself. The domain-wide delegation
    you registered is never used.

    The symptom is **not** a validation error. Tokens mint normally, and every
    Google surface answers with an authorization denial instead:

    ```text
    core   HTTP 403: Not Authorized to access this resource/api
    groups HTTP 403: Not Authorized to access this resource/api
    ```

    That reads exactly like a missing scope, which sends people back to
    re-audit a delegation setup that is already correct.

!!! tip "Check which form your secret is in"
    Before storing it, look at the **top-level** keys:

    ```bash
    jq 'keys' gw-secret.json
    # want:  ["admin_email", "service_account_json"]   (+ "domain" if you set it)
    # wrong: [..., "client_email", ..., "private_key", ..., "type", ...]
    ```

    If `type`, `private_key` or `client_email` appear at the **top** level, the
    secret is the no-delegation form no matter what else is in it.

    Reusing the same *service account* as the GCP provider is fine. Reusing the
    same *secret* is not — the GCP provider takes the raw key verbatim, so
    pointing the Workspace record at it lands in exactly this case. Give
    Workspace its own secret.

Store it:

```bash
limacharlie secret set --key gw-credentials \
    --value "$(cat gw-secret.json)" --enabled
```

`secret set` wraps the value into the secret record's `{"secret": "..."}`
envelope for you.

Or in the web app: **Organization Settings → Secrets Manager → Add**, name it
`gw-credentials`, and paste the JSON.

### Alternative: no delegation

!!! warning "Only if you chose this deliberately"
    This form is accepted, but it is not the recommended setup and it is the
    one operators land in **by accident** — it is what a raw service-account
    key, pasted verbatim, is read as. If `core` is failing with
    `HTTP 403: Not Authorized to access this resource/api` and you did not set
    this up on purpose, you are in this form by accident: go back to the
    [wrapper envelope](#create-the-credentials-secret).

If you would rather not register domain-wide delegation, the **raw
service-account key JSON** is accepted as the secret on its own — the file GCP
hands you, stored verbatim with no wrapper and no `admin_email`:

```bash
limacharlie secret set --key gw-credentials \
    --value "$(cat sa-key.json)" --enabled
```

In this form the service account calls the Admin SDK as itself instead of
impersonating an admin, so it must **hold a Workspace admin role** granted in
the Google Admin console — assign the service account a read-only or custom
admin role covering the directory surfaces you want. No DWD registration is
needed, and there is no way to set `domain`: the whole customer is enumerated.

Everything else on this page is unchanged; `provider test` reports the same
checks, and a surface the role does not cover fails exactly as an unregistered
scope would.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: google_workspace
workspace_customer_id: my_customer          # or an explicit customer ID
credentials: hive://secret/gw-credentials
internal_domains: [example.com]
```

In the web app: **Add provider → Google Workspace**, then set **Customer ID**
(`my_customer`), **Credentials** (`gw-credentials`), and **Refresh interval**.

!!! tip "Use `my_customer` unless you have a reason not to"
    `my_customer` is an alias Google resolves to the customer the impersonated
    admin (or the service account) belongs to, so it is correct for every tenant
    and there is nothing to look up or mistype. Set an explicit ID only when a
    reseller-style account has to be pinned to a specific customer.

    **Customer ID is not your organization's name.** It is an opaque ID Google
    issues, like `C01ab2cd3`. Find it in the **Google Admin console** →
    **Account** → **Account settings** → **Profile**, next to **Customer ID**.

    Any other value is rejected — but Google rejects it in a way that reads like
    a permission problem, not a typo: the Admin SDK answers an unrecognized
    customer with a bare `HTTP 400: Bad Request` that never names the field or
    echoes the value. Every required surface fails at once, so the connection
    shows **Failed** and `provider test`'s first check — *Authenticate + read
    directory users* — fails, even though the credential and the delegation are
    fine. If `provider test` reports a 400 on that check, it re-runs the same
    read against `my_customer` and tells you outright when the customer ID is
    the culprit.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `core` | ✅ | Authentication plus the directory user read. A failure here means the delegation (or, in the no-delegation setup, the service account's admin role) is wrong — nothing else can be probed meaningfully. |
| `groups` | ✅ | Groups and membership unavailable — the group edges that complete the GCP IAM picture are missing. |
| `security` | — | Per-user security posture (2SV enrolment/enforcement) unavailable. |
| `roles` | — | Admin-role assignments unavailable. |
| `sso` | — | Inbound-SSO profile posture unavailable. |
| `devices_mobile` | — | Mobile device inventory unavailable. |
| `devices_chromeos` | — | ChromeOS device inventory unavailable. |
| `devices_ci` | — | Cloud Identity device inventory unavailable. |
| `reports` | — | Gemini-in-Workspace usage unavailable (no AI-application rows or per-user access edges). |

!!! warning "An ungranted optional scope still shows the connection as Failed"
    The optional surfaces above degrade safely — the surface goes unobserved,
    its previously collected rows are kept rather than deleted, and
    `provider test` still reports **OK** overall, because only the required
    checks decide that verdict.

    The **Last Sync** badge on the providers page works differently. It reports
    *partial coverage*: any collector left uncovered marks the sync **Failed**,
    even when every required surface succeeded. So a connection that is working
    as intended, minus one optional scope you chose not to grant, sits on a
    permanent **Failed** badge.

    Hover the badge for the error detail — it names the collectors that were
    left uncovered and why. If the reason is a scope you deliberately skipped,
    the connection is healthy and the badge can be ignored; grant the scope to
    clear it.

## Troubleshooting

| `provider test` error | Cause | Fix |
|---|---|---|
| `HTTP 400: Bad Request` on the user check, with every other check failing too | `workspace_customer_id` is not a customer ID Google recognizes — most often the organization's **name** rather than the ID. Google returns this same opaque 400 for every customer-aimed call, which reads as a permission problem and sends people back to re-audit delegation and scopes that are already correct | Set `workspace_customer_id` to `my_customer`, or to the ID from **Admin console → Account → Account settings → Profile**. `provider test` names this explicitly when it can confirm it: the same read is retried against `my_customer`, and if that succeeds the check reports the real customer ID to use |
| Users or groups from a secondary domain are missing | `domain` is set in the secret, narrowing collection to that one domain | Remove `domain` from the secret; declare internal domains with `internal_domains` on the record |
| `token mint failed (HTTP 401): scope not granted to the delegated admin` | DWD missing scopes (all-or-nothing mint), a non-`.readonly` variant, or not yet propagated | Register the **full** scope list exactly; wait for propagation; confirm the service account's client ID matches |
| `core` fails: `HTTP 403: Not Authorized to access this resource/api` | A token **was** minted (so the scopes are registered) but the caller has no Workspace admin authority. Almost always the secret is a **raw service-account key with no `admin_email`** — typically the GCP provider's secret reused verbatim, or the wrapper flattened — so nothing is impersonated and the delegation you configured is never used. It is silently accepted as the no-delegation form. Otherwise, `admin_email` names a user who is not a Super Admin | Give Workspace its **own** secret in the wrapper envelope with `admin_email`; leave the GCP provider's secret untouched. Reusing the same *service account* is fine — reusing the same *secret* is not. Confirm the form with the `jq 'keys'` check [above](#create-the-credentials-secret) |
| `HTTP 403: … API has not been used in project …` | Admin SDK / Cloud Identity API not enabled | Enable the named API in the service account's project |
| `reports` fails: `HTTP 401: Access denied. You are not authorized to read activity records.` | The token minted (so the DWD registration itself is fine) but the impersonated admin cannot read the Reports audit stream — either `admin.reports.audit.readonly` is missing from the DWD scope list, or `admin_email` names an admin without the *Reports* privilege | Add the scope to the delegation and impersonate a Super Admin. Optional surface: leaving it as-is drops only Gemini-in-Workspace usage — but it does leave the connection's **Last Sync** badge on Failed, per the note above |

!!! tip "A changed error means you fixed something"
    These failures **mask each other**, and the **Last Sync** badge says only
    *Failed* either way — so a real fix can look like no fix at all.

    Google validates the customer ID *before* it checks authorization, so a
    wrong `workspace_customer_id` answers `400` on every surface and hides
    whatever the credential would have said. Correct the customer ID and the
    same connection starts answering `403` instead. That is not a new problem
    and not a regression: it is the next one, previously unreachable.

    Read the *error text*, not the badge, and re-diagnose against the table
    above after each change. `provider test` is the fastest way to see it —
    it reports one check per surface rather than a single verdict.

    Both misconfigurations can be present at once, so budget for two rounds:
    an unrecognized customer ID and a flattened secret are independent, and
    fixing either one alone still leaves the connection Failed.
