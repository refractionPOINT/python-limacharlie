# Events & Automation

--8<-- "includes/email-security-beta.md"

Email Security is not a side-car product with its own event bus. Everything it
sees becomes ordinary LimaCharlie telemetry, in the same lake as your endpoint,
cloud and identity data — which is what makes "a phish was delivered, and then
that user's endpoint ran a new binary" one rule instead of two products and a
spreadsheet.

## The sensor

Each mail connection appears as **one cloud sensor** on platform `email`. The
mailbox is a field on the event, not an identity: a ten-thousand-mailbox tenant
is one sensor, not ten thousand.

## The events

| Event | Emitted when |
|---|---|
| `EMAIL_MESSAGE` | Once per message, at ingest. Carries the whole parsed model — headers, sender, recipients, body, links, attachments, authentication, hops — plus the enrichments and the verdict. It is the record that this mail arrived |
| `EMAIL_VERDICT` | On **every** verdict decision: the rule pack's own, at ingest right after the `EMAIL_MESSAGE` (`revision/seq: 0`, `revision/mode: auto`), and then once per override afterwards (`seq: 1…`, mode `analyst`, `ai` or `detonation`) |
| `EMAIL_ACTION` | On every remediation outcome, including failures and skips, **and on every raw-message download** (`action: get_eml`), served or refused. Who asked, what was attempted, what happened |
| `EMAIL_USER_REPORT` | When a message reaches the abuse mailbox and becomes a report |
| `EMAIL_INGEST_ERROR` | When a message could not be fetched or processed. Coverage honesty: failures are visible, never silent |

`EMAIL_MESSAGE` is emitted once and is immutable. When a verdict changes, the
original event is never rewritten — a new `EMAIL_VERDICT` is emitted instead, so
the verdict history is the sequence of those events and a replay can reconstruct
what was known at any point in time.

### `EMAIL_VERDICT`

The body carries the message's identity plus one `revision` block, and it is the
same shape whichever decision it reports — which is the point: one rule reads all
of them.

| Path | |
|---|---|
| `event/msg_uuid` | The durable handle every typed action takes. A provider message id is folder-scoped and stops resolving the moment the message is quarantined; this does not |
| `event/mailbox/address`, `event/provider` | Whose mail, from where |
| `event/internet_message_id` | The cross-mailbox join key: one message sent to forty people is forty `msg_uuid`s and one of these |
| `event/sender_email`, `event/sender_root_domain`, `event/subject` | Enough to match on without a lookup |
| `event/ts` | The message's delivery time. The **event's own** timestamp is when the decision was made, so a hunt can window on either |
| `event/campaign_id` | The campaign, if the message clustered into one |
| `event/revision/seq` | `0` for the rule pack's verdict, `1…` for each override |
| `event/revision/mode` | `auto`, `analyst`, `ai` or `detonation` |
| `event/revision/verdict`, `event/revision/score` | The decision |
| `event/revision/rationale` | The reasons, strongest first. For an override these are what the analyst or agent wrote; for `seq 0` they are the names of the signals that fired — so it is **absent** on a benign message that matched nothing, which is the common case |
| `event/revision/top_signals`, `event/revision/engine_version` | `seq 0` only — the rule ids that fired and the pack version that decided. An override has neither: nothing *matched*, somebody decided |
| `event/revision/actor` | Who decided. Empty on `seq 0`: the rule pack is not a person, and `engine_version` is what identifies it |
| `event/revision/prior` | What the override displaced — verdict, score, mode and engine version. On `seq 0` it is present but empty (`verdict: ""`, `score: 0`), because the engine's first call displaced nothing — so match on `revision/seq` or `revision/mode` to tell the two apart, not on `prior` |

The MDM is deliberately *not* repeated here: it is already in the immutable
`EMAIL_MESSAGE`, and copying it into every verdict change would multiply a year
of telemetry by how often people change their minds.

!!! warning "It roughly doubles your mail event volume"
    `EMAIL_VERDICT` at `seq 0` is emitted for **every** ingested message, not only
    for flagged ones, so a protected mailbox now produces about two events per
    message instead of one. These are ordinary telemetry: they are evaluated by
    your D&R rules and they land in your retention like any other event. The
    bodies are small — identity plus a verdict, never the parsed message — so the
    byte volume moves far less than the count.

!!! info "Everything the rule needs is in the event"
    The verdict, the top signals and the enrichments the pipeline resolved are
    all *in* `EMAIL_MESSAGE`. A rule never has to call back for enrichment, and a
    replay of the event sees exactly what the pipeline saw.

Events arrive on the **default D&R target**, so a rule matching them needs no
`target:` line.

## Acting on mail from a D&R rule

```yaml
# Detect
op: and
rules:
  - op: is
    path: routing/event_type
    value: EMAIL_MESSAGE
  - op: is
    path: event/verdict/verdict
    value: malicious
  - op: is
    path: event/direction
    value: inbound
```

```yaml
# Respond
- action: report
  name: email-malicious-delivered
- action: extension request
  extension name: ext-email-security
  extension action: quarantine_message
  extension request:
    msg_uuid: '{{ .event.msg_uuid }}'
```

The typed actions available to `extension request` are the same six the console
and the CLI use: `quarantine_message`, `trash_message`, `move_to_spam`,
`restore_message`, `banner_message`, `unbanner_message`. They route to the same
executor, so the organization's `alert_only` / `enforce` mode, the audit row and
idempotency all apply unchanged — there is exactly one remediation path in this
product.

A rule does not supply banner HTML: `banner_message` uses the organization's own
banner from its [`banners` policy record](policy.md#banners), rendered
server-side into a fixed escaped template. Automated bannering also requires
`enabled` on the [`banners` record](policy.md#banners); without it a rule's
`banner_message` is decided and audited but the mailbox is not touched
(`alert_only`). Bannering asked for by a person — console, API, CLI — is not
gated by that switch.

Actions dispatched this way are attributed with `source: dr` in the audit trail.

!!! tip "Which seat should this rule sit in?"
    A rule that should **change the verdict** belongs in `dr-mail` as a
    `pre_verdict` signal — see [Custom Rules](custom-rules.md). A rule that
    should **do something once the verdict exists** can sit in either seat: in
    `dr-mail` as `post_verdict` if it only needs mail actions, or here as an
    ordinary D&R rule if it needs the platform's full response arsenal, Outputs,
    Cases, or correlation with non-mail telemetry.

## Reacting to a user report

```yaml
# Detect
op: is
path: routing/event_type
value: EMAIL_USER_REPORT
```

```yaml
# Respond
- action: report
  name: user-reported-phish
  priority: 3
```

From there the detection flows into Cases, Outputs and everything else that
consumes detections. A report is the highest-signal thing your users will ever
hand you, so treating it as a first-class detection is usually right.

## Watching your own coverage

`EMAIL_INGEST_ERROR` is the event to alert on. A mail security product that
quietly stops seeing a mailbox is worse than one that is visibly down, so
failures are emitted rather than swallowed:

```yaml
op: is
path: routing/event_type
value: EMAIL_INGEST_ERROR
```

Pair it with the `coverage` call, which reports mailboxes in `error`, the
parse-degradation rate and the emission backlog. See
[Getting Started](getting-started.md#6-watch-coverage-fill-in).

## Querying mail with LCQL

`EMAIL_*` events are queryable like any other telemetry in the Query Console and
through `limacharlie search`, over the platform's normal retention rather than
the 35-day product index. That makes it the right tool for questions that reach
further back than the queue does.

Use `limacharlie ai generate-query` to build the query and
`limacharlie search validate` before running it — LCQL is validated against
org-specific schemas and hand-written queries fail or mislead. See
[Data & Queries](../4-data-queries/index.md).

For the everyday "who else got this" question, the
[message index pivots](messages.md#the-two-ioc-pivots) are faster and are
purpose-built.

## Outputs

Because the events are ordinary telemetry, every
[Output](../5-integrations/outputs/index.md) works without any mail-specific
configuration: stream `EMAIL_MESSAGE` to a data lake, forward detections to a
SIEM, or push `EMAIL_ACTION` into an audit pipeline.

## Configuration as code

Every piece of Email Security configuration is a Hive record, so a tenant's whole
mail posture is a directory of YAML:

| Hive | Holds |
|---|---|
| `secret` | The provider credential |
| `mailsec_provider` | The connection |
| `mailsec_policy` | Automations, exclusions, VIPs, thresholds, banners, retention, reporter replies |
| `dr-mail` | Custom mail rules |
| `lookup` | VIP lists referenced by `vips.list_refs` |
| `dr-general` | The D&R rules on `EMAIL_*` events |

```bash
limacharlie hive set --hive-name mailsec_policy --key 50-finance-vips \
  --input-file policy/50-finance-vips.yaml --enabled --oid $OID

limacharlie hive list --hive-name mailsec_policy --oid $OID --output yaml
limacharlie hive get  --hive-name mailsec_policy --key 50-finance-vips --oid $OID
```

Two conventions make this pleasant to keep in git:

- **Records compose in name order**, so number your records (`00-baseline`,
  `50-team-x`, `99-override`) when precedence matters.
- **Unknown fields are refused**, so a typo fails the write rather than silently
  disabling a control. Validate a rule with `limacharlie hive validate` or
  `limacharlie mailsec rule validate` before committing it.

Onboarding a new tenant is then: subscribe the extension, write the secret, write
the provider record, apply the policy directory, run the connection test.
