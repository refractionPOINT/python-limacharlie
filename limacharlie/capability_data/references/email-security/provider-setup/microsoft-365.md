# Microsoft 365

--8<-- "includes/email-security-beta.md"

A Microsoft 365 connection reads and remediates Exchange Online mail over
Microsoft Graph, using an **application-only** credential. There is no mail
routing change, no connector, and no transport rule: the product is not in the
delivery path.

**Auth model:** an **Entra ID app registration** (service principal) with a
**client secret** and Microsoft Graph **application** permissions, admin-consented
tenant-wide.

## Prerequisites

- Permission to create an app registration (**Application Developer** or higher).
- Permission to **grant tenant-wide admin consent** (**Privileged Role
  Administrator** or **Global Administrator**).
- Your **tenant ID** (Entra ID → Overview).
- Mailboxes on Exchange Online. A user without an Exchange Online mailbox is not
  discovered, because there is no mail to protect.

## Required permissions

Both are **Application** permissions on Microsoft Graph, and both need admin
consent.

| Grant | Why | Connection-test check |
|---|---|---|
| **Mail.ReadWrite** | Read raw message bytes, and perform every remediation: quarantine, trash, move to spam, restore, apply and remove a banner | `mail_write` |
| **User.Read.All** | Enumerate the tenant's users to discover which mailboxes to protect | `mailbox_read` |

## Optional permissions

| Grant | Unlocks | Without it |
|---|---|---|
| **Mail.Send** | Reporter auto-replies — the templated acknowledgement sent to a person who reported a message | Reporter replies are **refused by name**, reported as an explicitly unavailable capability rather than silently skipped. Everything else is unaffected. Check `mail_send` reports `skipped`. |

!!! info "Why the consented set is readable at all"
    Microsoft Graph authorizes at call time, so the only read-only view of what
    was actually consented is the `roles` claim on the app's own access token.
    That is what the connection test reads — which means `mail_send` can be
    checked without sending a message to find out.

!!! danger "Application permissions, not delegated"
    Graph permissions must be added under **Application permissions**. Delegated
    permissions require a signed-in user and leave the connection failing after
    consent looks granted.

## Create the app registration

In the portal: **Microsoft Entra ID → App registrations → New registration**
(single tenant) → **Certificates & secrets → New client secret** (copy the
*Value*, not the *Secret ID*) → **API permissions → Add a permission →
Microsoft Graph → Application permissions** → add `Mail.ReadWrite` and
`User.Read.All` (and `Mail.Send` if you want reporter replies) → **Grant admin
consent**.

With the Azure CLI:

```bash
TENANT_ID=$(az account show --query tenantId -o tsv)

APP_ID=$(az ad app create --display-name lc-email-security --query appId -o tsv)
az ad sp create --id "$APP_ID"

az ad app credential reset --id "$APP_ID" --years 2 --append \
  --display-name lc-email-security --query password -o tsv   # capture this once

GRAPH=00000003-0000-0000-c000-000000000000

# Resolve each app-role id from Graph itself rather than pasting a GUID.
for PERM in Mail.ReadWrite User.Read.All Mail.Send; do   # Mail.Send is optional
  ROLE_ID=$(az ad sp show --id "$GRAPH" \
    --query "appRoles[?value=='$PERM'].id | [0]" -o tsv)
  az ad app permission add --id "$APP_ID" --api "$GRAPH" \
    --api-permissions "$ROLE_ID=Role"
done

az ad app permission admin-consent --id "$APP_ID"
```

!!! danger "`credential reset` clears existing secrets"
    Without `--append`, `az ad app credential reset` **removes every existing
    password and certificate** on the app before adding the new one.

!!! tip "Restricting which mailboxes the app can reach"
    Exchange Online can limit an application's mailbox access at the tenant side
    (application access policies / RBAC for Applications). That is complementary
    to the connection record's own `scope`: the record decides which mailboxes
    the product *asks for*, and the tenant policy decides which ones Exchange
    *permits*. Mailboxes the tenant refuses are tolerated rather than fatal, so
    set the record's `scope` to match the tenant policy — then the coverage
    numbers reflect a decision you made rather than a refusal you have to
    reverse-engineer.

## Store the credential

```json
{"tenant_id": "<tenant-id>", "client_id": "<application-client-id>", "client_secret": "<the-secret-value>"}
```

```bash
limacharlie secret set --key m365-mail \
  --value "$(cat m365-credential.json)" --enabled --oid $OID
```

## Create the connection

In the console: **Email Security → Settings → add a connection → Microsoft 365**.
The wizard renders the setup guide with your own values, stores the credential
as a secret if you paste one, and runs **Test Connection** before you finish.

As code:

```yaml
# m365.yaml
provider: m365
credentials: hive://secret/m365-mail
ingest:
  mode: auto
  backfill_days: 14
features:
  outbound_observation: true
  reports_mailbox: phishing@corp.example
```

```bash
limacharlie hive set --hive-name mailsec_provider --key m365-prod \
  --input-file m365.yaml --enabled --oid $OID
```

The full field reference is in [Connecting Providers](../providers.md#the-connection-record).

## Verify

```bash
limacharlie mailsec connection test m365-prod --oid $OID --output yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `credential` | ✅ | The tenant/client/secret triple was rejected, or the client secret expired |
| `mailbox_read` | ✅ | `User.Read.All` not consented — no mailbox can be discovered. Also fails when the directory genuinely returns no mailboxes |
| `mail_write` | ✅ | `Mail.ReadWrite` not consented — nothing can be read or remediated |
| `mail_send` | — | `Mail.Send` not consented; reporter replies unavailable. Reported as `skipped`, and `ok` stays true |

## How ingestion works

- **Discovery** enumerates users with mailboxes and reconciles the mailbox
  inventory, re-syncing periodically.
- **Change notifications**: one Microsoft Graph subscription per mailbox on
  `/users/{id}/messages`, delivered to a dedicated public receiver that validates
  and enqueues **routing identifiers only** — no subject, sender or body ever
  passes through it. Lifecycle notifications arrive on a separate endpoint and
  drive reauthorization, recreation and gap backfill.
- **Fetch**: on notification, the raw MIME is fetched, parsed, enriched, judged,
  persisted and emitted. Only folders that mean "delivered" are analyzed as
  inbound; Sent is processed as `direction: outbound`, observation-only.
- Subscriptions are renewed well before expiry, and the renewal sweep reconciles
  the provider's subscription set against ours.

## Remediation semantics

| Action | What happens in Exchange Online |
|---|---|
| `quarantine_message` | Moved to a **hidden** `LC Quarantine` folder we create in the mailbox — invisible to the user, fully restorable |
| `trash_message` | Moved to **Recoverable Items**. Invisible to the user and recoverable by an admin; this is deliberately *not* Deleted Items |
| `move_to_spam` | Moved to the Junk Email folder |
| `restore_message` | Moved back to the folder it came from, which we recorded at quarantine time. If that is unknown it goes to the Inbox — a message the customer asked to have back belongs somewhere they will find it |
| `banner_message` / `unbanner_message` | The body is edited **in place** with a fixed, sanitized banner block carrying an idempotency marker, so it is never applied twice and can be removed cleanly. The message keeps its provider id |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `credential` fails with `invalid_client` | Stored the secret **ID** instead of its **Value**, or the secret expired | Re-mint the secret and update the secret record |
| `mail_write` fails after consent | Permissions added as *Delegated*, or admin consent not actually granted | Re-add under *Application permissions* and grant tenant-wide admin consent |
| `mailbox_read` reports no mailboxes | Wrong tenant, or the users have no Exchange Online mailbox | Confirm the tenant, confirm licensing |
| Some mailboxes never become `protected` | An Exchange application access policy denies the app for those mailboxes | Widen the policy, or exclude those mailboxes in the record's `scope` so coverage reflects a decision rather than a refusal |
| Attachment analysis looks incomplete | Defender **Safe Attachments in Dynamic Delivery mode** detaches the attachment from the delivered message | Use Block mode if you want attachments analyzed post-delivery |
| Everything fails at `credential` after months of working | Client secrets expire | Re-mint before expiry and update the secret record; nothing else changes |
