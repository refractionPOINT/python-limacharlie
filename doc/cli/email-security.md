[Documentation](../README.md) > [CLI](README.md) > Email Security

# Email Security

Commands for the LimaCharlie Email Security surface: mailbox coverage, the message triage queue and its drawer, the justified raw-EML download, analyst verdict revision, per-message and bulk remediation at the provider, campaigns, sender profiles, the action audit trail, the abuse-mailbox report queue, standalone EML analysis, retro-hunts, custom-rule validation and backtest, the connection preflight, and the tenant purge.

Four permissions rather than the usual get/set pair, because the product asks to be trusted with four different things:

| Permission | Grants |
|---|---|
| `mailsec.get` | Read the product's own view: the queue, the drawer, campaigns, senders, the audit trail |
| `mailsec.set` | Change detection behaviour and triage state |
| `mailsec.act` | Remediate live mail at the provider |
| `mailsec.get.eml` | Take the original bytes of somebody's mail out of the building; requires a logged justification |

`mailsec tenant purge` is the exception: it is Owner-level, and needs `mailsec.act` **and** `billing.ctrl` **and** `user.ctrl` — the same trio `org delete` asks for.

Every command requires the org to be subscribed to the `ext-email-security` extension:

```bash
limacharlie extension subscribe --name ext-email-security
```

Provider connections and policy are hive records — manage them with the hive commands (`limacharlie hive list --hive-name mailsec_provider`, same for `mailsec_policy` and `dr-mail`).

Every command supports `--ai-help` for a detailed description with examples.

## Coverage & onboarding

```bash
limacharlie mailsec coverage --window-days 30   # mailboxes protected vs not
limacharlie mailsec onboarding --provider gworkspace
limacharlie mailsec onboarding --provider m365
limacharlie mailsec connection test gws-exp     # post-save credential preflight
limacharlie mailsec connection test gws-exp --include-watch
```

`coverage` reports the mailboxes that are NOT protected rather than omitting them, so the number is a coverage statement an admin can act on. `connection test` takes the `mailsec_provider` RECORD NAME, never a credential.

## The triage queue

Repeatable filters are OR within a key and AND across keys. Cursors are opaque and passed back verbatim; changing a filter mid-walk is an error, not a differently-meaning page.

```bash
limacharlie mailsec message list --verdict suspicious --verdict malicious
limacharlie mailsec message list --mailbox cfo@corp.example --since 2026-08-01
limacharlie mailsec message list --user-reported
limacharlie mailsec message list --link-domain evil.example         # IOC pivot
limacharlie mailsec message list --attachment-sha256 <SHA256>
limacharlie mailsec message get <MSG_UUID>                          # the drawer
limacharlie mailsec message similar <MSG_UUID>                      # who else got this
limacharlie mailsec message revisions <MSG_UUID>                    # verdict history
```

An unknown message id returns a null message rather than an error: the index has a 35-day TTL, so a miss is normal.

## Raw EML

A different privilege from opening the drawer, because it takes a person's actual mail out of the building. `--justification` is required and is written to the access audit with your identity.

```bash
limacharlie mailsec message eml <MSG_UUID> --justification "INC-4471 credential harvest"
limacharlie mailsec message eml <MSG_UUID> --justification "..." --out-file suspect.eml
```

## Triage & remediation

`message revise` records a human disposition and appends to the verdict history; `message action` remediates at the provider. Watch for `result=alert_only` — the action was DECIDED and deliberately not performed because the org is not in enforce mode.

```bash
limacharlie mailsec message revise <MSG_UUID> --verdict malicious --rationale "confirmed credential harvest"
limacharlie mailsec message action <MSG_UUID> --action quarantine_message --reason "confirmed phish"
limacharlie mailsec message action <MSG_UUID> --action restore_message
```

Bulk remediation is two-step: without `--confirm` it previews, and the preview's `confirm` token is derived from the normalized selection, so it can only execute what you previewed. Up to 500 messages per call — a larger selection is refused, not truncated.

```bash
limacharlie mailsec message bulk-action --action quarantine_message --input-file ids.json
limacharlie mailsec message bulk-action --action quarantine_message --input-file ids.json --confirm <TOKEN>
limacharlie mailsec message bulk-status <BULK_ID>
```

## Campaigns, senders & the audit trail

```bash
limacharlie mailsec campaign list --state active --min-members 5
limacharlie mailsec campaign get <CAMPAIGN_ID>
limacharlie mailsec campaign action <CAMPAIGN_ID> --action quarantine_message              # preview
limacharlie mailsec campaign action <CAMPAIGN_ID> --action quarantine_message --confirm <TOKEN>
limacharlie mailsec sender get sender@corp.example
limacharlie mailsec action get <ACTION_ID>
```

## Reports, analysis, hunts & rules

```bash
limacharlie mailsec report list --status open
limacharlie mailsec report resolve <REPORT_ID> --disposition benign
limacharlie mailsec report reopen <REPORT_ID>
limacharlie mailsec analyze --file suspect.eml --org-domain corp.example   # no ingest
limacharlie mailsec hunt create --lcql "..." --dry-run
limacharlie mailsec hunt remediate <HUNT_ID> --action quarantine_message --confirm <HUNT_ID>
limacharlie mailsec rule validate --file rule.json --rule-id custom-lookalike
limacharlie mailsec rule backtest --file rule.json --since 2026-08-01
```

`rule backtest` reports `precision: null` — not `0` — when nothing it matched has an analyst disposition yet, and counts what it could not examine, so a precision figure whose denominator silently shrank is visible as one.

## Tenant purge

Permanently deletes everything Email Security holds for the org: the message index and the long-term evidence lane, campaigns, sender profiles, the remediation audit trail, user reports, the stored raw messages and their parsed copies, the link-detonation results, and the org's Email Security connection and policy configuration. It also stops the mail connections at Microsoft or Google, so the provider stops sending notifications.

**This is irreversible.** Two steps, like `org delete`: without `--confirm` the command prints the warning and mints a token and deletes nothing; with `--confirm` it goes through with it. The token is single-use and expires after 5 minutes, so mint it immediately before executing.

```bash
# Step 1 — preview. Prints the warning and the token; nothing is deleted.
limacharlie mailsec tenant purge

# Step 2 — execute, with the token from step 1.
limacharlie mailsec tenant purge --confirm <TOKEN> --reason "customer offboarded"
```

`--reason` is optional, at most 1024 characters, and is recorded in the org audit log next to your identity.

The purge is re-runnable. A partial one returns `complete: false` and counts what did not land (`objects_failed`, `subscriptions_failed`, `connections_unreachable`, `rows_remained`) beside what did; the command exits non-zero in that case so a script cannot mistake a half-purged tenant for a finished one. Re-run it with a fresh token and it picks up what remains.

You may not need it at all: the same data is deleted automatically 30 days after the org unsubscribes from Email Security — resubscribing inside that window cancels the deletion — and immediately if the org itself is deleted.

## See Also

- [CLI Overview](README.md)
- [Platform Administration](platform-admin.md) — `org delete`, audit, users
- [Hive & Data Stores](hive-data.md) — the `mailsec_provider`, `mailsec_policy` and `dr-mail` hives
