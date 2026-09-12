# LimaCharlie

Inventories your **own LimaCharlie tenancy** as an estate, like any other SaaS
platform: org members as identities (with MFA state), API keys as machine
identities, sensors as assets, installation keys, telemetry outputs, extension
subscriptions, and configuration stores. Posture findings cover sign-in
requirements, unrestricted privileged API keys, insecure telemetry-output
transports, stale enrollment keys, config stores holding records that fail to
apply, and non-expiring secrets.

**Auth model:** a LimaCharlie **API key** — either an **org** key (one
organization) or a **user** key (every organization that user can reach, which
is the MSSP fleet case).

## Choose a key mode

| Mode | Record field | Enumerates | Use when |
|---|---|---|---|
| **Org key** | `limacharlie_oid` | That one organization | You want a single tenant inventoried |
| **User key** | `limacharlie_uid` | Every organization the user can reach, one account each | You run a fleet and want them all in one connection |

!!! note "What the MFA/SSO posture actually describes"
    The sign-in posture on the Account node (required MFA, SSO-only sign-in) is
    the policy attached to the **email domain of the user whose key is in
    use** — the requirements that apply to everyone signing in with an address
    in that domain. It is not a per-organization setting, so a user key reaching
    several orgs reports the same posture on each of them.

    It is therefore observable **only in user-key mode**: an org key has no user
    identity behind it, so the posture is reported as unobserved rather than as
    "not enforced".

## Required permissions

Set these on the API key. Each maps to a preflight check of the same name.

| Permission | Gives | Preflight check |
|---|---|---|
| `org.get` | The Account node and org info | `org` |
| `sensor.list` | Sensors as assets, and enrollment-key usage | `sensors` |
| `user.ctrl` | Org members as identities, with MFA state | `users` |
| `apikey.ctrl` | API keys as machine identities | `api_keys` |
| `ikey.list` | Installation/enrollment key posture | `ikeys` |
| `output.list` | Telemetry-output posture | `outputs` |

!!! warning "`user.ctrl` and `apikey.ctrl` are broader than read-only"
    LimaCharlie has no read-only permission for users or API keys, so these two
    are the narrowest permissions that expose the data. The collector uses them
    strictly for listing. If that is not acceptable, omit them and accept that
    org members and API keys are not inventoried — but note both checks are
    marked **required**, so `provider test` will report the connection as not
    OK.

## Optional permissions

| Permission | Unlocks | Preflight check |
|---|---|---|
| `ext.conf.get` | Extension subscriptions as applications | `extensions` |
| `replicant.get` | Extension configuration detail | `replicant` |
| `billing.ctrl` | Sign-in requirement posture on the Account node *(user-key mode only)* | `billing` |

!!! info "Several permissions satisfy the extension read"
    The extension-subscription read accepts **any** of `ext.conf.get`,
    `ext.conf.get.mtd`, `ext.conf.set`, `ext.conf.set.mtd`, `ext.conf.del`,
    `ext.request` or `billing.ctrl`, and the `extensions` check passes on any
    one of them. `ext.conf.get` is simply the narrowest of the set.

### Configuration stores

Each configuration store is inventoried separately and needs its own
metadata-read permission. Grant only the stores you want inventoried — a store
whose permission is missing is left out, with no effect on the rest of the
sweep.

| Store | Permission | Preflight check |
|---|---|---|
| Secrets | `secret.get.mtd` | `secret_mtd` |
| Lookups | `lookup.get.mtd` | `lookup_mtd` |
| YARA | `yara.get.mtd` | `yara_mtd` |
| Queries | `query.get.mtd` | `query_mtd` |
| Playbooks | `playbook.get.mtd` | `playbook_mtd` |
| D&R rules (general) | `dr.list` | — |
| D&R rules (managed) | `dr.list.managed` | — |
| False-positive rules | `fp.ctrl` | — |
| Cloud sensors | `cloudsensor.get.mtd` | — |
| External adapters | `externaladapter.get.mtd` | — |
| AI agents | `ai_agent.get.mtd` | — |
| Extension configuration | `ext.conf.get.mtd` (or `ext.conf.get` above) | — |

!!! warning "Only the first five stores are preflighted"
    `provider test` probes the secret, lookup, YARA, query and playbook stores
    only. The stores below them have no check of their own: with the permission
    missing, the test still reports the connection OK and those stores are
    simply absent from the inventory. If you expected a store and do not see
    it, compare the key's permissions against this table.

    Note also that `fp.ctrl` is broader than read-only — LimaCharlie has no
    read-only false-positive-rule permission, the same trade-off as `user.ctrl`
    and `apikey.ctrl` above. It is used strictly for listing.

All `*.get.mtd` and `*.list` permissions read **metadata only** — record names
and attributes, never secret values or rule bodies. That metadata includes each
store's count of records whose last apply failed, which is what raises the
broken-records finding, and (for the secret store) which stored credentials
carry no expiry.

## Create the API key

See [API Keys](../../7-administration/access/api-keys.md) for the full
reference; both key types are managed from the organization view of the web
interface.

### Org key

1. Open the organization's **REST API** section.
2. Create a new API key, name it (e.g. `cloudsec-collector`), and select the
   permissions above.
3. Copy the key value.
4. Note the **organization ID** (a lowercase UUID) — `limacharlie org list`
   maps org names to IDs.

### User key

1. Retrieve your **user API key** from the web interface.
2. Note your **user ID**, also shown in the web interface. It is a free-form,
   **case-sensitive** identifier, not a UUID — copy it verbatim.

!!! warning "User keys are powerful"
    A user API key carries the same access as the user across **every**
    organization they can reach. Prefer an org key unless you specifically want
    fleet-wide inventory.

## Create the credentials secret

```json
{"api_key": "<the-api-key>"}
```

A bare key string is also accepted and wrapped automatically, so the key can go
in directly:

```bash
limacharlie secret set --key limacharlie-collector \
    --value '<the-api-key>' --enabled
```

`secret set` wraps the value into the secret record's `{"secret": "..."}`
envelope for you. To store the JSON object form instead, pass
`--value "$(cat lc-secret.json)"`.

## Create the provider record

Org-key mode:

```yaml
provider_type: limacharlie
limacharlie_oid: "00000000-0000-0000-0000-000000000000"
credentials: hive://secret/limacharlie-collector
internal_domains: [example.com]
refresh: 6h
```

User-key mode:

```yaml
provider_type: limacharlie
limacharlie_uid: "<your-user-id>"
credentials: hive://secret/limacharlie-collector
internal_domains: [example.com]
refresh: 6h
```

!!! danger "Exactly one of the two"
    Set `limacharlie_oid` **or** `limacharlie_uid`, never both and never
    neither — the pair selects the key's mode as well as the scope, so the
    record is rejected otherwise.

In the web app: **Add provider → LimaCharlie**, then choose the scope mode, set
**Credentials**, and set the **Refresh interval**.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The API key was rejected. Nothing else is probed. |
| `scope` | ✅ | The key's identity does not match the configured org/user, or cannot reach it. |
| `org`, `sensors`, `users`, `api_keys`, `ikeys`, `outputs` | ✅ | That permission is not granted — see the table above for what each one covers. |
| `extensions`, `replicant`, `billing`, `secret_mtd`, `lookup_mtd`, `yara_mtd`, `query_mtd`, `playbook_mtd` | — | That surface is unobserved; everything else still collects. |

Each permission check reports the concrete consequence in its `detail`, whether
it passes or fails.

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails | Key revoked, mistyped, or an org key used in user mode (or vice versa) | Re-copy the key; confirm the mode matches the field you set |
| `scope` fails | `limacharlie_oid` is not the org the key belongs to, or the user ID is wrong | Confirm the org UUID / user ID; the user ID is case-sensitive |
| A permission check fails after granting it | Permission changes need the key's effective permissions to refresh | Re-run the test; re-issue the key if it persists |
| `billing` fails in org-key mode | Expected — the sign-in posture is keyed on a user identity, so an org key cannot observe it | Use user-key mode if you want that posture |
| `billing` reports the permission as missing, yet the sign-in posture is collected | The check looks for `billing.ctrl` on the key, while the underlying read is gated on the user identity rather than that permission | Grant `billing.ctrl` if you want the check to pass cleanly |
| A configuration store is missing from the inventory | Its metadata-read permission is not on the key, and most stores have no preflight check | Grant the store's permission from the [Configuration stores](#configuration-stores) table |
| Only some orgs appear in user-key mode | The user does not have the required permissions in the missing orgs | Grant the same permission set in each org you want inventoried |
