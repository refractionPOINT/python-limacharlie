# Google Workspace

--8<-- "includes/email-security-beta.md"

A Google Workspace connection reads and remediates Gmail through the Gmail API,
using a **service account with domain-wide delegation**. There is no mail
routing change and no content compliance rule: the product is not in the
delivery path.

Workspace needs setup that Microsoft 365 does not, and the reason is worth
stating once: **Gmail will only publish change notifications to a Pub/Sub topic
in the service account's own Google Cloud project.** That topic and its
subscription are therefore yours, in your project, and the same service account
that reads mail is the one that reads the subscription — so a Workspace
connection still needs exactly one credential.

**Auth model:** a Google Cloud **service account** whose numeric OAuth2 client ID
is authorized in your Workspace admin console for a specific list of scopes,
impersonating a Workspace admin.

## Prerequisites

- A Google Cloud project you control (it can be a new, empty one).
- **Super Admin** access to the Workspace admin console, to authorize
  domain-wide delegation.
- A Workspace administrator address for the service account to impersonate.

## Scopes

| Scope | Required | What it buys | Without it |
|---|:--:|---|---|
| `https://www.googleapis.com/auth/admin.directory.user.readonly` | ✅ | Read the list of users in your domain, so we know which mailboxes to protect | No mailbox can be discovered, so nothing is protected at all |
| `https://www.googleapis.com/auth/gmail.modify` | ✅ | Read messages, change their labels, and move them to trash. It does **not** permit permanent deletion | No mail can be analyzed, quarantined or restored |
| `https://mail.google.com/` | — | Insert and delete messages, which is the only way to place a warning banner on delivered mail — Gmail has no API to edit a message in place. Also enables reporter auto-replies | Everything works except banners and reporter replies. Quarantine, trash, restore and move-to-spam are unaffected. Grant it only if you want those; it is broader access than the rest |

!!! info "Mail *configuration* is a different product"
    Scopes such as `gmail.settings.basic` are not part of this connection.
    Diffable mail configuration — forwarding rules, delegation, transport rules,
    DKIM/SPF/DMARC posture — belongs to
    [Cloud Security](../../cloud-security/provider-setup/google-workspace.md),
    which collects it as posture findings. Email Security owns the *messages*.

## Setup steps

!!! tip "Let the console render these with your values"
    The wizard serves the same steps with your project id and service-account
    address already substituted, and every command in order as a single paste.
    `limacharlie mailsec onboarding --provider gworkspace --oid $OID` returns
    the same thing headless. The steps below are the narrative.

### 1. Create a service account and download its JSON key

In any Google Cloud project you control. It needs **no IAM roles on the
project** — its mail access comes entirely from domain-wide delegation. Note its
**numeric OAuth2 client ID**; the Workspace console needs the number, not the
email address.

### 2. Enable the APIs

In the same project as the service account.

```bash
gcloud services enable gmail.googleapis.com admin.googleapis.com \
  pubsub.googleapis.com --project=<YOUR_PROJECT_ID>
```

### 3. Authorize the service account in the Workspace admin console

**Security → Access and data control → API controls → Domain-wide delegation →
Add new.** Paste the numeric client ID and the scopes as one comma-separated
line. Include `https://mail.google.com/` only if you want banners and reporter
replies.

*Verified by the `directory` check in the connection test.*

### 4. Create the notification topic

It **must** be in the same project as the service account — Gmail refuses a
topic in any other project.

```bash
gcloud pubsub topics create mailsec-gmail-push --project=<YOUR_PROJECT_ID>
```

### 5. Let Gmail publish to the topic

```bash
gcloud pubsub topics add-iam-policy-binding mailsec-gmail-push \
  --project=<YOUR_PROJECT_ID> \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

`gmail-api-push@system.gserviceaccount.com` is a Google-owned account, so the
console will warn that it is outside your organization. That is expected — it is
how Gmail delivers notifications.

*Verified by the `pubsub_watch` check.*

### 6. Create the subscription we read from

A **pull** subscription on that topic.

```bash
gcloud pubsub subscriptions create mailsec-gmail-push-sub \
  --topic=mailsec-gmail-push --project=<YOUR_PROJECT_ID> --ack-deadline=60
```

### 7. Let us read the subscription

Granted to the **same** service account you already created.

```bash
gcloud pubsub subscriptions add-iam-policy-binding mailsec-gmail-push-sub \
  --project=<YOUR_PROJECT_ID> \
  --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
  --role="roles/pubsub.subscriber"
```

*Verified by the `pubsub_pull` check.*

## Store the credential

The secret is the service-account JSON key **plus** the Workspace administrator
address to impersonate:

```json
{
  "admin_email": "admin@corp.example",
  "type": "service_account",
  "project_id": "<YOUR_PROJECT_ID>",
  "private_key_id": "<key-id>",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "<SERVICE_ACCOUNT_EMAIL>",
  "client_id": "<numeric-oauth2-client-id>",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

```bash
limacharlie secret set --key gws-mail \
  --value "$(cat gws-credential.json)" --enabled --oid $OID
```

## Create the connection

```yaml
# gws.yaml
provider: gworkspace
credentials: hive://secret/gws-mail
ingest:
  mode: push
  backfill_days: 14
features:
  outbound_observation: true
  reports_mailbox: phishing@corp.example
  pubsub_topic: projects/<YOUR_PROJECT_ID>/topics/mailsec-gmail-push
  pubsub_subscription: projects/<YOUR_PROJECT_ID>/subscriptions/mailsec-gmail-push-sub
```

```bash
limacharlie hive set --hive-name mailsec_provider --key gws-prod \
  --input-file gws.yaml --enabled --oid $OID
```

`ingest.mode: push` requires **both** `pubsub_topic` and `pubsub_subscription`;
a record that asks for push and names nowhere to receive is refused at save. Use
`auto` to let the collector decide.

## Verify

```bash
limacharlie mailsec connection test gws-prod --oid $OID --output yaml
limacharlie mailsec connection test gws-prod --include-watch --oid $OID --output yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `credential` | ✅ | The service-account key is malformed, or `admin_email` is missing |
| `directory` | ✅ | `admin.directory.user.readonly` is not delegated |
| `mail_modify` | ✅ | `gmail.modify` is not delegated — no analysis or remediation |
| `mail_full` | — | `https://mail.google.com/` not delegated; banners and reporter replies are unavailable. Reported as `skipped`, and `ok` stays true |
| `mailbox_read` | ✅ | Delegation is in place but the directory returned nothing, or the impersonated admin cannot list users |
| `pubsub_pull` | ✅ (when push is configured) | The service account lacks `roles/pubsub.subscriber` on the subscription, or the subscription name is wrong |
| `pubsub_watch` | ✅ (when push is configured) | Gmail cannot publish to the topic — usually the missing publisher binding, or a topic outside the service account's project |

`--include-watch` establishes a real Gmail watch and requires a real Pub/Sub pull
before lifecycle can pass. It is idempotent and the watch expires on its own.

## How ingestion works

- **Discovery** lists users per domain through the Admin SDK.
- **Push mode**: a `users.watch` per mailbox publishes to your topic; the
  collector pulls your subscription with the same service-account credential and
  reads the change history from the last known point. Watches are renewed on a
  daily schedule — Gmail expires them within seven days.
- **Poll mode** walks each mailbox's change history on an interval. It is a
  small-tenant and failure fallback, not a scale plan: it spends quota in your
  project continuously whether or not any mail arrived.
- Sent mail is ingested as `direction: outbound`, observation-only.

!!! warning "Gmail cannot enumerate active watches"
    There is no Gmail API that lists the watches currently established for a
    domain, so reconciliation compares against **our** stored state rather than
    the provider's own view. That is a genuinely lower assurance than the
    Microsoft 365 side, and it is surfaced on every Workspace connection row
    rather than hidden. `--include-watch` is how you positively prove delivery.

## Remediation semantics

| Action | What happens in Gmail |
|---|---|
| `quarantine_message` | `INBOX` removed, an `LC Quarantine` label added — restorable, and out of the user's inbox |
| `trash_message` | `TRASH` added. The product's own quarantine label is removed afterwards, so the message's placement reads as trashed rather than still quarantined |
| `move_to_spam` | `SPAM` added, resolved through Gmail's own identifiers |
| `restore_message` | The labels are inverted |
| `banner_message` / `unbanner_message` | Gmail cannot edit a stored message, so the message is **replaced**: the banner-carrying copy is inserted before the original is deleted (so an interruption leaves a repairable duplicate rather than data loss), preserving thread, internal date and labels. **The provider message id changes**, and the new one is persisted. Requires `https://mail.google.com/`; without it the action is refused by name |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `credential` fails | Key JSON malformed, or `admin_email` missing from the secret | Re-store the secret with `admin_email` included |
| `directory` fails | Delegation authorized against the service-account **email** instead of its **numeric client ID**, or a scope typo | Re-add the delegation with the numeric client ID and the exact scope strings |
| `mail_full` fails and banners are refused | `https://mail.google.com/` is not in the delegated scope list | Add it to the same delegation entry, or accept that banners and reporter replies are unavailable |
| `pubsub_watch` fails | Missing publisher binding for `gmail-api-push@system.gserviceaccount.com`, or the topic is in a different project | Add the binding; move the topic into the service account's project |
| `pubsub_pull` fails or times out | Missing `roles/pubsub.subscriber`, wrong subscription name, or the subscription is push rather than pull | Grant the role; recreate as a pull subscription |
| Banner "worked" but a later action fails | Something cached the pre-banner provider message id | Re-read `provider_message_id`; a Workspace banner mints a new one |
