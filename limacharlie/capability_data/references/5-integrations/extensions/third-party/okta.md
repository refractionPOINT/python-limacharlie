# Okta

The Okta LimaCharlie Extension exposes the incident-response and investigation surface of an Okta org (the **Okta management API**) to D&R rules and AI agents. It enables automated investigation and containment of an Okta account compromise directly from detections — suspend a user, reset their MFA, kill their sessions **and** OAuth tokens, revoke their app grants, quarantine them into a group, and pull the System Log for triage.

The extension provides two layers:

- **Typed actions** for the common containment, credential, MFA, session, and triage workflows, with friendly parameter names and built-in safety rails.
- A generic **`api_call`** passthrough for any Okta management endpoint not covered by a typed action.

Authentication is either a user-owned **SSWS API token** or an **OAuth 2.0 "API Services" app** (client credentials) — no user interaction, no delegated tokens. Okta's **DPoP** (sender-constrained token) requirement is handled transparently.

## Setup

Pick **one** authentication mode.

### Option A — SSWS API token (simplest)

1. In the Okta Admin Console, go to **Security → API → Tokens → Create Token** and copy the token value (shown only once).
2. Create the token from a **dedicated service admin account**, not a person's account: an SSWS token inherits the creator's privilege level, and it is revoked after 30 days of inactivity or if the creating account is deactivated.

### Option B — OAuth API Services app (recommended)

1. In the Admin Console, go to **Applications → Create App Integration → API Services**.
2. On the app's **General** tab, switch client authentication to **Public key / Private key** and generate (or add) a key. Save the private key — a PEM or the private JWK Okta hands out.
3. On the app's **Okta API Scopes** tab, grant the `okta.*` scopes for the actions you will use (least-privilege set below), then admin-consent them.

> **Okta requires `private_key_jwt` for management scopes.** The org authorization server rejects a plain `client_id` + `client_secret` for `okta.*` scopes — use a private key. (A `client_secret` field is accepted by the extension for completeness but expect Okta to reject it for these scopes.) New API Services apps also have **DPoP** locked on; the extension detects and satisfies this automatically.

Least-privilege scopes:

| Capability | Scope |
| --- | --- |
| Read users / lists | `okta.users.read` |
| User lifecycle / password / factor writes | `okta.users.manage` |
| Clear sessions / revoke tokens | `okta.sessions.manage` |
| Read groups | `okta.groups.read` |
| Group membership changes | `okta.groups.manage` |
| System Log | `okta.logs.read` |

> The org authorization server **silently drops** requested-but-ungranted scopes from the minted token; a missing grant then surfaces as that endpoint returning **403** (`insufficient_scope`), not a mint failure. Grant only what you use — every action degrades independently.

### Subscribe to the extension

Subscribe to `ext-okta` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### Store the secret

In **Secrets Manager**, create a secret (for example `okta-api-token` or `okta-private-key`) and paste the SSWS token or the private key as its value.

### Configure the extension

In **Extensions → ext-okta → Configuration**, fill in `org_url` plus the fields for your chosen auth mode:

| Field | Required | Value |
| --- | --- | --- |
| `org_url` | yes | Okta org URL or host, e.g. `https://acme.okta.com` (admin / `-admin` URLs are normalized). |
| `api_token` | Option A | Reference to the SSWS-token secret, e.g. `hive://secret/okta-api-token`. |
| `client_id` | Option B | The API Services app client ID. |
| `private_key` | Option B | Reference to the private-key secret (PEM or private RSA JWK), e.g. `hive://secret/okta-private-key`. |
| `key_id` | no | `kid` for a PEM private key (JWKs carry their own). |
| `client_secret` | no | App client secret (alternative to `private_key`; rejected by Okta for management scopes). |
| `scopes` | no | OAuth scope override; empty uses an IR-oriented default set. |

Provide `api_token` **or** the OAuth fields, not both.

## Actions

Every action that targets an entity requires an explicit selector (`user_id`, `group_id` + `user_id`, `factor_id`) — the extension refuses to run without one, preventing accidental org-wide containment.

`user_id` accepts either the Okta user id (e.g. `00u1a2b3c4...`) or the user's login (e.g. `alex@acme.com`).

### Pagination

Okta paginates with the HTTP `Link` header (`rel="next"`), not a body cursor. The `list_*` actions return `{data: [...], pagination: {next_link}}`; pass the opaque `next_link` back as the `next_link` parameter to fetch the next page (it is an absolute, self-contained URL — never hand-build it). `limit` is clamped to 200 for users/groups and 1000 for the System Log.

### Generic

#### `api_call`

Generic passthrough to the Okta management API.

| Field | Type | Notes |
| --- | --- | --- |
| `method` | enum | `GET` (default), `POST`, `PUT`, `DELETE`. |
| `path` | string | **Required.** Path relative to the org base (e.g. `api/v1/users/{id}/lifecycle/reactivate`) or a full `Link: rel="next"` URL. |
| `query` | object | Query-string parameters. |
| `headers` | object | Extra request headers. |
| `body` | object | JSON body for `POST`/`PUT`. |

### User investigation

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_users` | `q`, `search`, `filter`, `sort_by`, `sort_order`, `limit`, `after`, `next_link`, `extra_query` | List/search users. Use `q` for a starts-with search on name/email, `search` for an expression (e.g. `status eq "ACTIVE"` or `profile.email eq "a@b.com"`), or `filter` for the older syntax. |
| `get_user` | `user_id` | Get one user. Read the returned `status` before a lifecycle action (see below). |
| `list_user_factors` | `user_id` + pagination | List a user's enrolled MFA factors (`id`, `factorType`, `status`) — spot attacker-registered MFA. |
| `list_user_groups` | `user_id` + pagination | List a user's group memberships (find a privileged group to strip, or confirm quarantine). |
| `list_user_grants` | `user_id` + pagination | List a user's OAuth consent grants (which apps/scopes they authorized). |
| `list_user_roles` | `user_id` + pagination | List a user's admin roles — is the account privileged (e.g. `SUPER_ADMIN`)? |
| `list_groups` | `q`, `search`, `filter`, `limit`, `after`, `next_link`, `extra_query` | List/search groups. Only `OKTA_GROUP`-type groups accept membership changes. |
| `list_system_log` | `since`, `until`, `filter`, `q`, `sort_order`, `limit`, `next_link`, `extra_query` | Query the System Log (`/api/v1/logs`). Scope with `since`/`until` (ISO-8601) and a SCIM `filter`, e.g. `eventType eq "user.session.start"`, `actor.id eq "00u..."`, or `target.id eq "00u..."`. |

Read the user's `status` first: `suspend` needs `ACTIVE`, `unsuspend` needs `SUSPENDED`, `activate` needs `STAGED`/`DEPROVISIONED`, `unlock` needs `LOCKED_OUT`. A `400` on a lifecycle action is a state mismatch; a `403` is a scope/role problem.

### User lifecycle

| Action | Parameters | What it does |
| --- | --- | --- |
| `suspend_user` | `user_id` | Block sign-in while preserving the account and assignments — the recommended **reversible** containment lever. Reverse with `unsuspend_user`. |
| `unsuspend_user` | `user_id` | Return a suspended user to `ACTIVE`. |
| `deactivate_user` | `user_id`, `send_email` (default `false`) | Deactivate/deprovision the user. **Destructive** — removes app access and is not a clean inverse of `activate`; prefer `suspend_user`. May complete asynchronously on large orgs. |
| `activate_user` | `user_id`, `send_email` (default `false`) | Activate a `STAGED`/`DEPROVISIONED` user. With `send_email=false` the response includes an activation URL/token. |
| `unlock_user` | `user_id` | Unlock a `LOCKED_OUT` user, returning them to `ACTIVE`. |

### Credentials

| Action | Parameters | What it does |
| --- | --- | --- |
| `expire_password` | `user_id`, `temp_password` (default `false`) | Force a password change at next sign-in (`PASSWORD_EXPIRED`). With `temp_password=true` the current password is invalidated immediately and a one-time temp password is returned. |
| `reset_password` | `user_id`, `send_email` (default `false`) | Trigger a reset (transitions the user to `RECOVERY`). With `send_email=false` the response carries a one-time `resetPasswordUrl` to deliver out-of-band. |
| `set_user_password` | `user_id`, `password` | Set a specific new password directly — lock an attacker out with a known-only-to-you value. Must satisfy the org password policy. |

### MFA

| Action | Parameters | What it does |
| --- | --- | --- |
| `reset_user_factors` | `user_id`, `remove_recovery_enrollment` (default `false`) | Unenroll **all** of a user's MFA factors, forcing re-enrollment — high-value against attacker-registered MFA. Does not change the password. |
| `reset_user_factor` | `user_id`, `factor_id`, `remove_recovery_enrollment` (default `false`) | Unenroll a **single** factor (from `list_user_factors`). Note: removing a push/signed-nonce factor also removes the user's related Okta Verify factors. |

### Sessions & OAuth tokens

| Action | Parameters | What it does |
| --- | --- | --- |
| `clear_user_sessions` | `user_id`, `oauth_tokens` (default `true`), `forget_devices` (default `false`) | Revoke all of a user's Okta sessions, forcing re-authentication. `oauth_tokens` defaults to **`true`** (the IR-safe choice) so refresh/access tokens are revoked too — Okta's own API default of `false` leaves them valid, the single most common containment mistake. `forget_devices` also clears remembered-device / factor-trust. |
| `revoke_user_grants` | `user_id` | Revoke **all** of a user's OAuth consent grants across all clients — cut off OAuth-based persistence. Inspect first with `list_user_grants`. |

> Clearing Okta sessions does **not** terminate sessions already established inside downstream apps (M365, Salesforce, …); those need the app's own session revocation.

### Group containment

| Action | Parameters | What it does |
| --- | --- | --- |
| `add_user_to_group` | `group_id`, `user_id` | Add a user to an `OKTA_GROUP` — e.g. drop a compromised user into a quarantine / high-friction sign-on-policy group. Find the group id with `list_groups`. |
| `remove_user_from_group` | `group_id`, `user_id` | Remove a user from a group — e.g. strip a compromised user out of a privileged/admin group. |

### Containment sequencing

For a confirmed account takeover, the effective combination is: `reset_user_factors` (drop attacker MFA) → `expire_password` with `temp_password=true` **or** `set_user_password` (invalidate the credential) → `clear_user_sessions` (kill live sessions **and** OAuth tokens) → `revoke_user_grants` (cut OAuth persistence). Revoke sessions/tokens **last** so the attacker's live session can't outlive the other steps. Use `suspend_user` as the single reversible lever to stop everything first.

## Detection & Response

Example response action that suspends the Okta user named in a detection:

```yaml
- action: extension request
  extension action: suspend_user
  extension name: ext-okta
  extension request:
    user_id: '{{ .event/user_id }}'
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context. Workflows that chain (find the user, reset factors, clear sessions, revoke grants) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold state between calls.

## Notes

- **Two auth modes.** SSWS is the fastest to set up but is tied to an admin account's privilege and dies after 30 days of inactivity. The OAuth API Services app (private_key_jwt) is decoupled from any person, uses short-lived scoped tokens, and is the direction Okta officially steers integrations.
- **DPoP** (sender-constrained tokens) is forced on for new API Services apps; the extension mints a plain token first and, if Okta answers `invalid_dpop_proof`, transparently flips to DPoP for the token request and every API call.
- A single `401` on a call using an OAuth token is treated as a token-expiry race: the cached token is dropped and the request retried once with a fresh token. Rotating the secret in Secrets Manager recovers the same way — the next auth failure evicts the cached client and re-reads the secret.
- Token-endpoint `429`/`5xx` are backed off and retried; a data-endpoint `429` honors Okta's `Retry-After` for a bounded number of retries.
- Error messages are formatted `okta api <status> on <method> <path>: <errorCode>: <errorSummary>`, with query strings redacted.
- Unsubscribing from the extension preserves its saved configuration; re-subscribing restores it without reconfiguration.
