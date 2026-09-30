[Documentation](../README.md) > [CLI](README.md) > Email Security

# Email Security

Install or upgrade with `python -m pip install --upgrade limacharlie`. See [installation](../getting-started.md#installation) for setup.

Commands for the LimaCharlie Email Security surface: mailbox coverage, the message triage queue and its drawer, the justified raw-EML download, analyst verdict revision, per-message and bulk remediation at the provider, campaigns, sender profiles, the action audit trail, the abuse-mailbox report queue, standalone EML analysis, custom-rule validation and backtest, the connection preflight, and the tenant purge.

Four permissions rather than the usual get/set pair, because the product asks to be trusted with four different things:

| Permission | Grants |
|---|---|
| `mailsec.get` | Read the product's own view: the queue, the drawer, campaigns, senders, the audit trail |
| `mailsec.set` | Change detection behaviour and triage state |
| `mailsec.act` | Remediate live mail, revise verdicts and test provider connections |
| `mailsec.get.eml` | Download original message bytes; also requires `mailsec.get` and a logged justification |

Connection testing and verdict revision require `mailsec.act`. Connection records
have separate `mailsec_provider.*` permissions: creating a provider and enabling
its record require `mailsec_provider.set` and `mailsec_provider.set.mtd`.
Policy and `dr-mail` writes use `mailsec.set`. Creating and enabling the credential
secret requires `secret.set` and `secret.set.mtd`. Report resolution and reopening
use `mailsec.set`.

`mailsec tenant purge` is the exception: it is Owner-level, and needs `mailsec.act` **and** `billing.ctrl` **and** `user.ctrl` — the same trio `org delete` asks for.

Every command requires the org to be subscribed to the `ext-email-security` extension:

```bash
limacharlie extension subscribe --name ext-email-security
```

Provider connections and policy are hive records — manage them with the hive commands (`limacharlie hive list --hive-name mailsec_provider`, same for `mailsec_policy` and `dr-mail`).

Every command supports `--ai-help` for a detailed description with examples.

## Coverage & onboarding

Start by selecting your organization with the global `--oid` option, or your
configured default. Subscribe to the extension, then fetch the provider's current
setup guide. For Workspace, supplying your Google Cloud project and service account
fills those values into the returned commands; reading the guide creates no resources.

```bash
limacharlie mailsec coverage --window-days 30   # mailboxes protected vs not
limacharlie mailsec coverage --since 2026-09-01T00:00:00Z --until 2026-09-02T00:00:00Z
limacharlie mailsec onboarding --provider gworkspace
limacharlie mailsec onboarding --provider gworkspace --project-id your-project --sa-email mailsec@your-project.iam.gserviceaccount.com
limacharlie mailsec onboarding --provider m365
limacharlie mailsec connection test workspace-mail     # post-save credential preflight
limacharlie mailsec connection test workspace-mail --include-watch
```

`coverage` reports the mailboxes that are NOT protected rather than omitting them, so the number is a coverage statement an admin can act on. `connection test` takes the `mailsec_provider` RECORD NAME, never a credential.

`--topic` and `--subscription` on `onboarding` override the suggested Workspace
Pub/Sub names. Workspace needs domain-wide delegation and a topic and pull
subscription in the service account's own Google Cloud project. Microsoft 365 uses
an Entra application with admin-consented application permissions. Follow the
returned scopes, including optional capabilities, before saving a connection.

For example, after creating the Microsoft application, save a secret file whose
`secret` value is the serialized credential JSON:

```json
{"secret":"{\"tenant_id\":\"YOUR_TENANT_ID\",\"client_id\":\"YOUR_CLIENT_ID\",\"client_secret\":\"YOUR_CLIENT_SECRET\"}"}
```

Save the connection body as `connection.json`:

```json
{
  "provider": "m365",
  "credentials": "hive://secret/m365-mail",
  "scope": {"include_addresses": ["pilot@corp.example"]},
  "ingest": {"mode": "push", "backfill_days": 14}
}
```

```bash
limacharlie secret set --key m365-mail --input-file credential-secret.json --enabled
limacharlie hive set --hive-name mailsec_provider --key m365-mail --input-file connection.json --enabled
limacharlie mailsec connection test m365-mail
limacharlie mailsec coverage
limacharlie mailsec message list --mailbox pilot@corp.example
```

Hive records are disabled by default, so `--enabled` is essential. The example
protects one pilot mailbox; an empty include list covers all discovered mailboxes.
Workspace uses `provider: gworkspace`, a service-account credential with
`admin_email`, explicit `ingest.mode: push`, and `features.pubsub_topic` and
`features.pubsub_subscription` containing full resource names from its setup guide.
The default backfill is 14 days; explicit `backfill_days: 0` disables it. Backfill
judges historical mail without emitting live message events or performing automatic
remediation. New organizations have no automatic remediation configured; add an
automation policy deliberately after validating coverage and verdicts.

An optional capability can be unavailable while the connection still works. Read
each diagnostic check's `required`, `status` and `remediation` fields. `--include-watch`
establishes a real Workspace watch. Coverage confirms ongoing protection after the
credential test; investigate any unprotected or error mailboxes it reports.

Coverage defaults to a cached 24-hour volume window. Explicit windows are
recomputed and rate-limited. Use `--window-days` or `--since`/`--until`, never both;
`volume.truncated` means the requested period exceeds retained message history.

## The triage queue

Repeatable filters are OR within a key and AND across keys. Cursors are opaque and passed back verbatim; changing a filter mid-walk is an error, not a differently-meaning page.

```bash
limacharlie mailsec message list --verdict suspicious --verdict malicious
limacharlie mailsec message list --mailbox cfo@corp.example --since 2026-08-01
limacharlie mailsec message list --user-reported
limacharlie mailsec message list --lane backfill --since 2026-09-01T00:00:00Z
limacharlie mailsec message list --link-domain evil.example         # IOC pivot
limacharlie mailsec message list --attachment-sha256 <SHA256>
limacharlie mailsec message list --search "invoice overdue" --since 2026-08-01
limacharlie mailsec message get <MSG_UUID>                          # the drawer
limacharlie mailsec message similar <MSG_UUID>                      # who else got this
limacharlie mailsec message revisions <MSG_UUID>                    # verdict history
limacharlie mailsec message revisions <MSG_UUID> --limit 1000
```

`--lane live` selects newly arriving mail and `--lane backfill` selects onboarding
history; omitting it includes either. Lane works with time, verdict and IOC queries.
Combining it with `--mailbox`, `--sender-email` or `--campaign-id` returns
`lane_unsupported`. Keep the lane and other filters unchanged when following cursors.

An unknown message id returns a null message rather than an error. The message
index is retained for at most 35 days; the organization's retention policy can
shorten that period. The drawer normally serves the preserved MDM and original
enrichments (`mdm_source: stored`). Its raw-EML fallback (`eml_reparse`) omits
enrichments; expired content returns `mdm: null` and `mdm_unavailable_reason`.

`message similar` returns bounded clustering-key neighbours, not necessarily the
same campaign, and has no pagination. Read each candidate's `matched_keys` and
the response's lookback windows. Use `message list --campaign-id` for a paginated
campaign membership query. Revision history also has no cursor: inspect
`revisions_truncated` before treating it as a complete audit export.

## Raw EML

A different privilege from opening the drawer, because it takes a person's actual mail out of the building. Downloading requires both `mailsec.get` and `mailsec.get.eml`. `--justification` is required and is written to the access audit with your identity.

These are the sender's own bytes, unmodified, so the command **refuses to write them to a terminal**: a hostile message carrying ANSI escape sequences would repaint your screen. Give it `--out-file`, or pipe it. Redirects and pipes are unaffected; `--to-terminal` overrides the refusal if you really want the bytes on screen. The check happens before the download, so a refusal records no access.

```bash
limacharlie mailsec message eml <MSG_UUID> --justification "..." --out-file suspect.eml
limacharlie mailsec message eml <MSG_UUID> --justification "..." | less
```

## Triage & remediation

`message revise` records a human disposition and appends to the verdict history; `message action` remediates at the provider. Watch for `result=alert_only` — the action was DECIDED and deliberately not performed because the org is not in enforce mode. The response then carries `force_required: true` and the command prints a note on stderr. `--force` performs the action even if the organization is in alert-only mode (no automation in enforce mode); the override is recorded in the audit trail. `bulk-action` and `campaign action` take `--force` on the execute (with `--confirm`) only — it is not part of the confirmation token, and a forced bulk execute runs as a new job.

```bash
limacharlie mailsec message revise <MSG_UUID> --verdict malicious --rationale "confirmed credential harvest"
limacharlie mailsec message action <MSG_UUID> --action quarantine_message --reason "confirmed phish"
limacharlie mailsec message action <MSG_UUID> --action quarantine_message --reason "confirmed phish" --force
limacharlie mailsec message action <MSG_UUID> --action restore_message
```

Single-message actions also include `move_to_spam`, `banner_message`,
`unbanner_message`, `submit_to_triage` and `crawl_link`. Banners use the organization's
`banners` policy, with optional provider scopes required by Workspace. Triage
submission records an `EMAIL_ACTION` for a configured AI trigger to consume;
it does not itself start an agent session. Link crawling requests analysis and
can spend the organization's analysis budget. Inspect action results rather
than assuming an accepted request changed message placement.

Bulk remediation is two-step: without `--confirm` it previews, and the preview's `confirm` token is derived from the normalized selection, so it can only execute what you previewed. Up to 500 messages per call — a larger selection is refused, not truncated.

```bash
limacharlie mailsec message bulk-action --action quarantine_message --input-file ids.json
limacharlie mailsec message bulk-action --action quarantine_message --input-file ids.json --confirm <TOKEN> --reason "INC-4471"
limacharlie mailsec message bulk-status <BULK_ID>
```

`--reason` belongs to the execute and is recorded on the job's audit row *and* on every message's. It is deliberately not part of the confirmation token, so rewording it between previewing and executing neither invalidates a token you hold nor starts a second job over the same messages.

## Campaigns, senders & the audit trail

```bash
limacharlie mailsec campaign list --state active --min-members 5
limacharlie mailsec campaign get <CAMPAIGN_ID>
limacharlie mailsec campaign action <CAMPAIGN_ID> --action quarantine_message              # preview
limacharlie mailsec campaign action <CAMPAIGN_ID> --action quarantine_message --confirm <TOKEN> --reason "confirmed credential harvest"
limacharlie mailsec campaign action <CAMPAIGN_ID> --action quarantine_message --confirm <TOKEN> --attempt after-the-outage
limacharlie mailsec sender get sender@corp.example
limacharlie mailsec action get <ACTION_ID>
```

A sweep's `--reason` lands on the sweep's own record and on every member's audit row. Repeating a sweep is idempotent per member, so a double run collapses onto the rows it already wrote; `--attempt` is how you ask for a deliberate second run — a retry after a provider outage recorded *beside* what failed rather than over it. It is an opaque handle, at most 128 characters, refused rather than truncated. Neither field is part of the confirmation token, so adding either one after previewing does not invalidate it.

## Reports, analysis & rules

```bash
limacharlie mailsec report list --status open
limacharlie mailsec report resolve <REPORT_ID> --disposition benign
limacharlie mailsec report reopen <REPORT_ID>
limacharlie mailsec analyze --file suspect.eml --org-domain corp.example   # no ingest
limacharlie mailsec rule validate --file rule.json --rule-id custom-lookalike
limacharlie mailsec rule backtest --file rule.json --since 2026-08-01
```

`rule backtest` reports `precision: null` — not `0` — when nothing it matched has an analyst disposition yet, and counts what it could not examine, so a precision figure whose denominator silently shrank is visible as one.

Validation and backtesting do not save a rule. Save an accepted rule with
`hive set --hive-name dr-mail --key <RULE_ID> --input-file rule.json --enabled`.
An invalid rule returns `valid: false` with its reason; check that field even
when the request succeeds. To disable a vendor rule, set its metadata disabled
instead of deleting it: vendor pack releases can recreate deleted vendor rules.

Additional extension workflows use the generic CLI (requires `ext.request`):

```bash
limacharlie extension request --name ext-email-security --action restore_default_rules
limacharlie extension request --name ext-email-security --action get_dlp_pack
```

`restore_default_rules` creates missing defaults without overwriting existing
records. `get_dlp_pack` only returns the opt-in outbound DLP definitions; it does
not install them. Install the returned lookup records before their `dr-general`
rules and preserve each record's `usr_mtd.enabled` setting, or use the console's
installation flow. Outbound mail is observation only; DLP detections do not stop
delivery or remediate sent messages.

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

Historical email searches use platform LCQL over `EMAIL_MESSAGE` events. Pass selected message UUIDs to `mailsec message bulk-action` for a preview, then repeat it with the selection-bound `--confirm` token; there is no separate MailSec hunt job API.

## Disposition and release

Disposition is an analyst decision independent of the engine verdict. Values are
`malicious`, `spam`, `graymail`, `benign`, and `simulation`. Notes support up to
1024 characters. Use `none` to filter messages awaiting a decision.

```bash
limacharlie mailsec message disposition <MSG_UUID> --disposition spam --note "Reviewed"
limacharlie mailsec message disposition <MSG_UUID> --clear
limacharlie mailsec message list --disposition none
limacharlie mailsec message bulk-disposition --input-file ids.json --disposition simulation
limacharlie mailsec message release <MSG_UUID> --reason "Confirmed safe" --mode analyst
```

Bulk disposition accepts 1–500 unique message IDs and reports individual errors.
A benign disposition repairs sender flagged history; malicious contributes once.
Neither changes the engine verdict nor triggers policy automations.
Release restores placement and records a benign verdict and disposition together.
It requires `mailsec.act`; alert-only organizations must explicitly add `--force`.
Retrying the same successful release does not add another verdict revision.

Report resolution uses the same dispositions and needs `mailsec.set`. Optional
remediation additionally requires `mailsec.act` and uses preview then confirmation:

```bash
limacharlie mailsec report resolve <REPORT_ID> --disposition malicious --scope message --action quarantine_message
limacharlie mailsec report resolve <REPORT_ID> --disposition malicious --scope message --action quarantine_message --confirm <TOKEN> --reason "Confirmed threat"
```

Scope can be `message` or `campaign`. Preview keeps the report open, as do failed,
withheld, or partial remediation attempts. Successful resolution classifies the
linked original without changing its engine verdict. Report detail shows
`resolution_reply_status`; an ambiguous provider send is not automatically retried.
