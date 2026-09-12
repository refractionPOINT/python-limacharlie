# Messages & Triage

--8<-- "includes/email-security-beta.md"

**Messages** is the queue: every message the product has seen, filtered down to
the ones that need a person. This page covers the queue, the drawer, the actions
and the audit trail they leave.

## The queue

Filtering is **entirely server-side** — every filter below narrows the query in
the backend, so a filtered page is a statement about your whole mail history, not
about the rows a browser happened to have loaded.

| Filter | Notes |
|---|---|
| `verdict` | Repeatable: `malicious`, `suspicious`, `graymail`, `benign`, `unknown` |
| `state` | Repeatable: `delivered`, `quarantined`, `trashed`, `restored`, `bannered`, `spam` |
| `direction` | Repeatable: `inbound`, `outbound`, `internal` |
| `mailbox` | One protected mailbox address |
| `sender_email` | One sender address |
| `sender_root_domain` | One sender registrable domain |
| `campaign_id` | The members of one campaign |
| `link_domain` | Messages linking to this **registrable root** domain (`evil.example`, not `login.evil.example`) |
| `attachment_sha256` | Messages carrying an attachment with this hash |
| `user_reported` | Tri-state — see below |
| `min_score` | Messages scoring at least this much |
| `q` | Free-text over the message's identifying fields |
| `since` / `until` | RFC3339 or unix seconds |

Repeatable filters **OR within a key and AND across keys**: `verdict=suspicious`
plus `verdict=malicious` plus `mailbox=cfo@corp.example` means "suspicious or
malicious, delivered to that mailbox".

```bash
limacharlie mailsec message list --verdict suspicious --verdict malicious \
  --mailbox cfo@corp.example --since "$(date -d '7 days ago' +%s)" --oid $OID
```

!!! warning "Tri-state booleans: absent is not `false`"
    Omitting `user_reported` means the dimension is *unconstrained*. Setting it
    to `false` selects mail **nobody reported**, which is a different and much
    larger set than "all mail".

### The two IOC pivots

`link_domain` and `attachment_sha256` are the incident-response pivots, and they
are the reason the queue is not just a mailbox view. Given one confirmed phish,
they answer **"who else received this"** across every protected mailbox — which
is the question that decides whether you are handling one message or an incident.

```bash
limacharlie mailsec message list --link-domain evil.example --oid $OID
limacharlie mailsec message list --attachment-sha256 <sha256> --oid $OID
```

### Pagination

Pages are keyset-paginated. `next_cursor` is opaque and is passed back verbatim;
an empty one is the last page.

A cursor is **bound to the filter set that minted it**. The backend chooses its
read index from the filters and stamps that choice into the cursor, so changing a
filter mid-walk fails the next page rather than silently resuming at a position
that means something else. Restart the walk instead.

### Retention

The searchable message index keeps **35 days** by default; flagged messages and
their stored evidence are kept up to **400 days**. Both are *maxima* you can
lower — `message_days` and `flagged_days` in
[`mailsec_policy/retention`](policy.md#retention) — and data past whichever
horizon you set is deleted rather than merely hidden. A miss on an older id is a
normal outcome and returns a null message rather than an error.

## The drawer

Opening a row shows what the engine decided and why:

- **Why this verdict** — the top signals with their weights, from the same
  `top_signals` the API returns.
- **The message itself** — a sanitized rendering plus the parsed model: sender
  and recipients, authentication results, the links table with display/href
  mismatches highlighted, attachments and their explosion tree, and the thread
  segmentation.
- **The sender profile card** — this organization's history with the sender.
- **The action timeline** — every audited action on this message.
- **Remediation controls**, driven by the message's current placement: the
  actions offered are the ones that make sense for where the message actually is.

### Which model you are looking at

The detail response labels its source, because the two are not equivalent:

| `mdm_source` | What it is |
|---|---|
| `stored` | The model the collector actually judged with — the enrichments it resolved at ingest (sender prevalence, lookalike distances, link features, domain age) and the verdict as stamped |
| `eml_reparse` | Today's parser reading the original bytes. The same message, a different parse, and **no enrichments at all** |

`stored` is served when it exists; `eml_reparse` is the fallback for mail
ingested before stored models existed. An analyst deciding whether the engine was
right needs to know which one they are reading, so the field is always present.

Neither requires a justification. The model is the product's own structured view;
the *original bytes* are what is gated.

### Similar messages

`GET /messages/{id}/similar` (`limacharlie mailsec message similar <msg_uuid>`)
returns recent messages sharing at least one
[clustering key](campaigns.md#how-clustering-works) with this one, each row
carrying the `matched_keys` that matched. These are **candidates, not a
cluster** — deciding that two messages are the same attack belongs to the
clustering engine. The response echoes the lookback window, because "no similar
messages" only means something alongside the window it looked at.

## Actions

Six typed actions apply to a single message. Each is idempotent, performed at the
provider, and audited.

| Action | Effect |
|---|---|
| `quarantine_message` | Out of the inbox into a product-owned quarantine location — restorable, invisible to the user |
| `trash_message` | To the provider's recoverable trash |
| `move_to_spam` | To the provider's junk/spam location |
| `restore_message` | Back to where it was before we moved it, falling back to the Inbox when that is unknown |
| `banner_message` | Prepend the organization's warning banner. Its wording comes from the `banners` [policy record](policy.md#banners) and is escaped into a fixed template — no caller supplies HTML |
| `unbanner_message` | Remove it |

The per-provider mechanics differ and are documented in
[Connecting Providers](providers.md#capability-differences-between-providers).

```bash
limacharlie mailsec message action <msg_uuid> \
  --action quarantine_message --reason "confirmed credential phish" --oid $OID
```

Actions require `mailsec.act`.

To act on many messages at once — a filtered page of this queue, or a selection
you built elsewhere — see [Bulk Remediation](remediation.md). It is the same
executor and the same audit trail, with a preview and a confirmation over the set
you named.

### Outcomes are reported honestly

| `result` | Meaning |
|---|---|
| `ok` | The provider was changed |
| `skipped` | The desired state already held, so nothing was written. Recording this as success would make the audit claim a provider write that never happened |
| `alert_only` | The action was **decided and deliberately not performed**, because the organization is not in enforce mode. Not an error |
| `failed` | The provider refused or errored; `error` carries the reason |
| `pending` | In flight |

!!! note "`unbanner_message` does not change placement"
    A message's `state` is a **placement**. Bannering is a modification, so a
    message that was quarantined and then un-bannered is still quarantined —
    writing `delivered` there would move it back in the UI without moving it at
    the provider.

### Idempotency

Repeating an action collapses onto the existing attempt, so a redelivery, a
double-click or a rule firing twice on one event is a no-op rather than two
quarantines. To deliberately act *again* — re-running a quarantine after a
provider outage — pass a new `attempt` token.

### Enforcement

Analyst-initiated actions from the console, CLI or API **always execute**.
`alert_only` withholds *automation*, not people: a human clicking quarantine has
already made the decision the mode exists to withhold from a rule, and refusing
them would make the product unusable during the incident it was bought for.

Automated actions are governed by [policy](policy.md#automations).

## The audit trail

Every action writes an audit row — including failures and skips, because
"quarantined 412 of 418, 6 failed" is only answerable if the six are recorded —
and emits an `EMAIL_ACTION` event.

| Field | Meaning |
|---|---|
| `action_id` | The row's identity and its idempotency key |
| `action`, `ts`, `result`, `error` | What was attempted, when, and what happened |
| `actor` | **Who asked** — stamped by the server from the caller's authenticated claims. A request body cannot supply it |
| `source` | `analyst`, `automation`, `ai`, `api` or `dr` |
| `provider` | Which mail tenant it hit |

The per-message timeline is deliberately narrow and does **not** carry the action's
request payload. Expand one row to read it:

```bash
limacharlie mailsec action get <action_id> --oid $OID --output yaml
```

A `null` request on a timeline row means **"not read"**, never "no parameters
recorded" — an auditor asking whether a justification exists must expand the row
rather than infer absence from the list.

## Downloading the original message

This is a privileged read of a person's mail, and it is gated separately from the
rest of the product. It requires **both** `mailsec.get` and `mailsec.get.eml`,
plus a justification.

```bash
limacharlie mailsec message eml <msg_uuid> \
  --justification "INC-4471, user reported credential harvest" \
  --out-file suspect.eml --oid $OID
```

- The justification is **required**. A blank or whitespace-only reason is
  refused.
- It is recorded against your authenticated identity in the organization's action
  audit and retained for 400 days. **A failed attempt is recorded too.**
- It is stored verbatim. The backend enforces a minimum and a maximum length, and
  refuses an over-long reason rather than truncating — silently clipping the
  record the gate exists to produce would corrupt it.
- Raw copies expire 35 days after delivery (longer for flagged messages), after
  which this returns a typed expiry error while the index row stays readable.

Read a justification back with `mailsec action get <action_id>`.

## Sender profiles

```bash
limacharlie mailsec sender get cfo@corp.example --oid $OID
limacharlie mailsec sender get domain:corp.example --oid $OID
```

A key with no profile means **no history at all**, and the response says so
explicitly rather than returning a zeroed profile that would read as a
known-but-quiet sender. Keys are lowercased, and a bare address or domain is
resolved for you.
