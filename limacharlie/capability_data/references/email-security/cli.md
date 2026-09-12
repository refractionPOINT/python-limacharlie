# Command Line Interface

--8<-- "includes/email-security-beta.md"

The `limacharlie mailsec` command group covers the Email Security API surface:
the coverage screen, the message index and drawer, the audited raw-EML download,
verdict revisions, campaigns and campaign-wide sweeps, bulk remediation over a
selection you name, sender profiles, the action audit trail, the abuse-mailbox
report queue, custom-rule validation and backtest, the connection preflight, the
served onboarding guide, and the tenant purge.

Commands take the global options (`--oid`,
`--output json|yaml|toon|csv|table|jsonl`, `--filter <jmespath>`,
`--fields <names>`), and every command and subgroup answers `--ai-help` with
task-oriented guidance.

```bash
limacharlie mailsec --help
```

Every command requires the org to be subscribed to the extension:

```bash
limacharlie extension subscribe --name ext-email-security --oid $OID
```

Provider connections and policy are Hive records — manage them with the
standard `limacharlie hive` commands (`mailsec_provider`, `mailsec_policy`,
`dr-mail`). This group is the query, triage and remediation surface. See
[Policy Reference](policy.md) for the record contracts and
[API Reference](api-reference.md) for the routes these commands call.

## Permissions

Four, rather than the usual get/set pair, because Email Security asks to be
trusted with four separable things — plus one command that is not any of them:

| Permission | Covers |
|---|---|
| `mailsec.get` | Read the product's own view: queue, drawer, campaigns, senders, audit trail |
| `mailsec.set` | Change triage state — resolving a user report |
| `mailsec.act` | Remediate live mail at the provider |
| `mailsec.get.eml` | Download the original bytes of a message; requires a logged justification |
| `mailsec.act` **and** `billing.ctrl` **and** `user.ctrl` | `tenant purge`, in both its preview and its destructive form. Owner-level authority, the same trio deleting the organization requires — there is no separate "owner" permission |

`mailsec.get.eml` is separate on purpose: opening the drawer shows you the
product's structured view of a message, while downloading the EML takes a
person's actual mail out of your tenant. Gating them identically would mean
typing a justification to look at the queue.

## At a glance

```bash
# Coverage
limacharlie mailsec coverage --window-days 30

# The triage queue
limacharlie mailsec message list --verdict suspicious --verdict malicious
limacharlie mailsec message list --mailbox cfo@corp.example --since 2026-08-01
limacharlie mailsec message list --user-reported            # a human flagged these
limacharlie mailsec message list --link-domain evil.example # IOC pivot
limacharlie mailsec message list --attachment-sha256 <sha>  # IOC pivot
limacharlie mailsec message get <msg_uuid>
limacharlie mailsec message similar <msg_uuid>              # who else got it
limacharlie mailsec message eml <msg_uuid> --justification "INC-4471"

# Re-judging a message, and reading how its verdict moved
limacharlie mailsec message revise <msg_uuid> --verdict malicious --rationale "confirmed credential harvest"
limacharlie mailsec message revisions <msg_uuid>

# Remediation
limacharlie mailsec message action <msg_uuid> --action quarantine_message --reason "confirmed phish"
limacharlie mailsec message action <msg_uuid> --action restore_message

# Bulk remediation over a selection you name: previews without --confirm
limacharlie mailsec message bulk-action --action quarantine_message --input-file uuids.txt
limacharlie mailsec message bulk-action --action quarantine_message --input-file uuids.txt --confirm <token> --reason "INC-4471"
limacharlie mailsec message bulk-status <bulk_id>

# Campaigns: one attack, triaged once
limacharlie mailsec campaign list --min-members 3
limacharlie mailsec campaign get <campaign_id>
limacharlie mailsec campaign action <campaign_id> --action quarantine_message              # preview
limacharlie mailsec campaign action <campaign_id> --action quarantine_message --confirm <token>

# Senders and the audit trail
limacharlie mailsec sender get cfo@corp.example
limacharlie mailsec sender get domain:corp.example
limacharlie mailsec action get <action_id>

# Abuse-mailbox reports
limacharlie mailsec report list --status open --oldest-first
limacharlie mailsec report get <report_id>
limacharlie mailsec report resolve <report_id> --disposition true_positive
limacharlie mailsec report reopen <report_id>

# Custom rules
limacharlie mailsec rule validate --file rule.json --rule-id custom-lookalike
limacharlie mailsec rule backtest --file rule.json --since 2026-08-01

# Analysis and setup
limacharlie mailsec analyze --file suspect.eml --org-domain corp.example
limacharlie mailsec connection test gws-exp
limacharlie mailsec onboarding --provider gworkspace

# Delete everything Email Security holds for this org — previews without --confirm
limacharlie mailsec tenant purge
```

`--window-days` accepts 1-35 (the platform's maximum message retention) and cannot be combined with an explicit `--since`/`--until`. Out-of-range values for `--limit`, `--min-score` and `--min-members` are refused with an error naming the flag rather than silently clamped or ignored.

## Things worth knowing before you script this

### Campaign actions preview by default

`campaign action` reports what it *would* do and changes nothing unless you pass
`--confirm`. That is deliberate for an operation whose blast radius is every
mailbox that received an attack.

The preview returns the members, the distinct mailboxes it would touch, and a
`confirm` **token derived from that exact member set**. Pass the token back —
**not** the campaign id, which is refused — so a campaign that absorbed new
members while you were reading the preview fails the confirmation rather than
sweeping a set nobody approved.

```bash
PREVIEW=$(limacharlie mailsec campaign action "$CAMPAIGN" \
  --action quarantine_message --output json)
echo "$PREVIEW" | jq '{member_count, mailbox_count}'

TOKEN=$(echo "$PREVIEW" | jq -r .confirm)
limacharlie mailsec campaign action "$CAMPAIGN" \
  --action quarantine_message --confirm "$TOKEN"
```

Sweeps are capped at 500 members: above that the answer is a person deciding,
not a bigger dialog. See [Campaigns](campaigns.md#sweeping-a-campaign).

`--reason` is recorded on every member's audit row **and** on the sweep's own
row, which comes back as `action_id` and reads through
`limacharlie mailsec action get`. It is bounded at 1024 characters and refused
rather than truncated, and it is not part of the confirmation token — rewording
it after the preview does not invalidate the token.

`--attempt` asks for a **deliberate second run**. Re-running a sweep is
idempotent per member — the per-member audit key is the campaign itself, so a
double click, or a retry of a request whose response you never saw, collapses
onto the row each member already has instead of claiming a move that happened
once as two. A new `--attempt` composes with the campaign, minting a new action
id per member and a new sweep record, so a re-run after a provider outage is
recorded *beside* the run that failed rather than over it; the same value twice
collapses again. It is an opaque handle you mint, not prose: at most 128
characters, refused rather than truncated, because a clipped idempotency token
is a *different* token, and it is checked on the preview leg too.

Like `--reason`, it is **not** part of a campaign sweep's confirmation — unlike a
*bulk* action's `--attempt` [below](#bulk-remediation-previews-by-default-too),
which is. The two tokens answer different questions: a bulk token derives the
job's own identity, so the attempt is part of what it names, while a sweep's
token authorizes a member set and nothing else. Repeat a bulk `--attempt` on the
execute; add or change a sweep's freely.

`--attempt` on a campaign sweep needs a recent `limacharlie` release; an older
one refuses the flag as unknown, and the field can be sent directly to the API
in the meantime (see
[Campaigns](campaigns.md#repeating-a-sweep-and-asking-for-a-second-one-on-purpose)).

```bash
limacharlie mailsec campaign action "$CAMPAIGN" \
  --action quarantine_message --confirm "$TOKEN" \
  --reason "re-running after the provider outage" \
  --attempt after-the-outage
```

### `alert_only` is a success, not a failure

An action's `result` can come back as `alert_only`, meaning the action was
**decided and deliberately not performed** because your organization is not in
enforce mode. Do not treat it as an error — it is the product doing what you
configured, reported honestly rather than dressed up as `ok`.

### Filters are tri-state

Leaving a boolean filter unset means the dimension is *unconstrained*, which is
not the same as `false`:

```bash
limacharlie mailsec message list                      # every message
limacharlie mailsec message list --user-reported      # only reported mail
limacharlie mailsec message list --no-user-reported   # only unreported mail
```

### The EML download is audited

`message eml` requires `--justification`, and it is written to the access audit
with your identity. There is no way to fetch raw mail without leaving a record
of why.

```bash
limacharlie mailsec message eml <msg_uuid> \
  --justification "INC-4471, user reported credential harvest" \
  --out-file suspect.eml
```

### Reports have an SLA ordering

`--oldest-first` is what makes the report queue an SLA surface rather than a
feed. "The oldest thing nobody has looked at" is the question a queue exists to
answer, and it is not answerable from a newest-first page.

Each report also carries `original_found`. A report whose original was never
indexed is a real state — the mail predates the connection, or landed in a
mailbox outside your scope — and it is shown as a gap rather than as a blank
field.

### Backtest tells you what it could not see

`rule backtest` reports `skipped_no_raw`, `skipped_unparse` and `truncated`
alongside the match count, because a precision figure whose denominator quietly
shrank is a number that looks like a measurement and is not one. Its
`coverage_note` states the window it actually examined.

`precision` comes back as **null**, not `0`, when nothing it matched has an
analyst disposition yet. Zero would read as "everything it matched was wrong"
and would have you discard a good rule.

```bash
limacharlie mailsec rule backtest --file rule.json --output yaml
```

### Bulk remediation previews by default too

`message bulk-action` is the campaign sweep's discipline over a selection you
name: omit `--confirm` and it previews, pass the token back and it executes. The
selection can come from `--msg-uuids`, `--input-file`, or standard input — which
is what lets the queue pipe into it:

```bash
limacharlie mailsec message list --verdict malicious --output json \
  | jq -r '.messages[].msg_uuid' \
  | limacharlie mailsec message bulk-action --action quarantine_message --input-file -
```

The execute must repeat the **identical** `--action`, `--msg-uuids` and
`--attempt` the preview was minted with — the token is derived from those three,
not issued as a nonce. `--reason` is not one of them, and **is** supported: it is
recorded on the job's audit row and on every message's.

The job runs in the background, `--wait` is the default, and **the exit code
carries the outcome** — `0` only when the job completed and something was acted
on. The full contract, including every `state`, `result` and count, is in
[Bulk Remediation](remediation.md#from-the-cli).

### Revising a verdict is `mailsec.act`, not `mailsec.set`

`message revise` records a human disposition over the scorer's, appending to the
message's history rather than overwriting it. `--rationale` is required and
audited — at least one, at most ten, each 280 characters or fewer.

```bash
limacharlie mailsec message revise <msg_uuid> \
  --verdict benign --rationale "internal test send" --rationale "sender verified"
limacharlie mailsec message revisions <msg_uuid> --output yaml
```

The CLI always revises as `analyst`, because the operator of a CLI is a person.
An autonomous agent revises with its **own** key and `mode: ai` through the API,
so the audit can always say whether a person or a model decided.

`applied: false` is an honest outcome and not an error: the message already
carried that verdict and nothing changed. See
[Detections & Verdicts](detections.md#revising-a-verdict).

### The tenant purge is irreversible

`tenant purge` permanently deletes everything Email Security holds for the
organization — the message index and the long-term evidence lane, campaigns,
sender profiles, the action audit trail, user reports, stored raw messages and
their parsed copies, and link-detonation results — and removes the provider
connection and policy records, which stops the provider sending any further
notifications. There is no undo and no smaller scope than the whole tenant.

So it is two calls. With **no** `--confirm` the command previews: it prints the
warning and mints a confirmation token, and destroys nothing.

```bash
# 1. Preview. Prints the warning and a single-use token; changes nothing.
PREVIEW=$(limacharlie mailsec tenant purge --oid "$OID" --output json)
echo "$PREVIEW" | jq -r .warning

# 2. Purge, within 5 minutes, quoting that token.
TOKEN=$(echo "$PREVIEW" | jq -r .confirmation)
limacharlie mailsec tenant purge --oid "$OID" \
  --confirm "$TOKEN" \
  --reason "Tenant offboarded"
```

The token is **single-use and expires 5 minutes after it is minted**, so a purge
cannot be replayed and cannot be scripted without someone having been shown the
warning. A purge that comes back with `complete: false` did not finish and is
safe to repeat — but repeating it means starting again at step 1, because step 2
spent the token.

`--reason` is optional, capped at 1024 characters, and written to the
organization's audit log with your identity. Requires Owner-level authority. See
[Data retention and deletion](policy.md#data-retention-and-deletion) for exactly
what a purge removes, and for the deletion that happens on its own 30 days after
an organization unsubscribes.

## Filtering and pagination

Repeatable filters OR within a key and AND across keys:

```bash
# suspicious OR malicious, AND delivered to that mailbox
limacharlie mailsec message list \
  --verdict suspicious --verdict malicious \
  --mailbox cfo@corp.example
```

Cursors are opaque and are passed back verbatim. They encode which index the
walk is pinned to and are bound to the filter set that minted them — changing a
filter mid-walk is an error rather than a page that silently means something
else.

```bash
PAGE=$(limacharlie mailsec message list --limit 100 --output json)
NEXT=$(echo "$PAGE" | jq -r .next_cursor)
[ -n "$NEXT" ] && limacharlie mailsec message list --limit 100 --cursor "$NEXT"
```

An empty `next_cursor` means the last page.

## Scripting

```bash
# Every suspicious message that reached a VIP mailbox in the last day
limacharlie mailsec message list \
  --verdict suspicious \
  --mailbox ceo@corp.example \
  --since "$(date -d '1 day ago' +%s)" \
  --output json --filter 'messages[].{id: msg_uuid, subject: subject}'

# Quarantine every member of a campaign, after reading the preview
PREVIEW=$(limacharlie mailsec campaign action "$CAMPAIGN" --action quarantine_message --output json)
limacharlie mailsec campaign action "$CAMPAIGN" --action quarantine_message \
  --confirm "$(echo "$PREVIEW" | jq -r .confirm)"

# Resolve the oldest open report
REPORT=$(limacharlie mailsec report list --status open --oldest-first --limit 1 \
  --output json | jq -r '.reports[0].report_id')
limacharlie mailsec report resolve "$REPORT" --disposition true_positive
```

Because the CLI is the whole surface, it is also how an
[AI triage agent](ai-triage.md) reaches Email Security — there is no separate
integration for agents to learn.
