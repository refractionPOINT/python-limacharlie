# User Reports

--8<-- "includes/email-security-beta.md"

Your own people are the best detector you have for the mail that got through.
Email Security turns an abuse mailbox into an SLA queue: reports are joined back
to the original message across the whole tenant, robots that mail the abuse
address are kept out of the numbers, and the reporter can be told what happened.

## Setting it up

Designate an abuse mailbox on the connection record:

```yaml
features:
  reports_mailbox: phishing@corp.example
```

Anything delivered to that mailbox is read as a report. Point your existing
report path at it — a "report phishing" button that forwards, a mail rule, or
just an address people know.

!!! warning "The abuse mailbox must not be a mailbox people report *from*"
    A report is a message forwarded **to** the abuse address. One mailbox cannot
    be both the sender and the destination of the same forward, so keep the
    abuse address separate from the mailboxes your users send from.

The reported message arrives as a forward carrying the original as a nested
message. The parser handles the nesting, and the original is located across
**every** protected mailbox by its internet message id — so a campaign that hit
forty people is found from one person's report.

## What happens to a report

1. An `EMAIL_USER_REPORT` event is emitted and a report row is created.
2. The original message is located across the tenant and joined to the report.
3. The original's campaign, if it has one, is attached.
4. The original is stamped `user_reported`. That flag outranks a benign verdict
   in the triage queue — a human flagging something is the strongest free signal
   the product gets.
5. If reporter replies are enabled, the reporter is sent a templated
   acknowledgement.

Reports have three states: `open`, `triaging`, `resolved`.

## The queue

```bash
limacharlie mailsec report list --status open --oldest-first --oid $OID
limacharlie mailsec report get <report_id> --oid $OID
```

`--oldest-first` is what makes this an SLA surface rather than a feed. "The
oldest thing nobody has looked at" is the question a queue exists to answer, and
it is not answerable from a newest-first page.

In the console, **Reports** carries the queue, per-row age and resolution, SLA
tiles computed from exact sources, a drawer timeline (reported → joined →
actioned → reporter replied) and pivots to the message and its campaign.

### `original_found`

Every report says whether its original was located. A report whose original was
never indexed is a **real state**, not a blank field: the mail predates the
connection, or it landed in a mailbox outside the connection's scope. It is shown
as a gap so you can tell "we could not find it" from "we did not look".

## Resolving

```bash
limacharlie mailsec report resolve <report_id> --disposition true_positive --oid $OID
```

| Disposition | Meaning |
|---|---|
| `true_positive` | It was malicious |
| `false_positive` | We flagged it and it was fine |
| `benign` | It was never a threat |

Resolving requires `mailsec.set`, **not** `mailsec.act`: it changes triage state
the product owns, and touches nobody's mailbox. That is the line `mailsec.act`
draws.

Resolving an already-resolved report succeeds and reports `already_resolved`, so
two analysts clicking at once is not an error.

!!! tip "`benign` also repairs the sender's history"
    Resolving a report as `benign` subtracts that message's contribution from the
    sender's flagged-history counter. Without it, one wrong flag would keep
    weighing on every later message from a legitimate correspondent. The repair
    runs once per report even if the resolution is retried.

## Reopening

```bash
limacharlie mailsec report reopen <report_id> --oid $OID
```

A resolved report goes back to `open` and is worked again. The command takes no
options beyond the report id: **who** reopened it is stamped from your
authenticated identity and cannot be supplied by the caller.

The resolution columns are deliberately **kept**. Only the status moves, so the
row still reads "previously resolved `benign` by `system:automated-sender`"
rather than erasing the very thing being disputed — and `reopened_from` names the
state it came out of.

Reopening a report that is already `open` or `triaging` succeeds and reports
`already_open`, so two analysts clicking at once is not an error. An unknown
report id **is** an error rather than a silent success, because this names one
specific row to change.

Reopening needs `mailsec.set` — exactly the permission the resolve it undoes
needs, and deliberately not a wider one. An analyst who can close a report must
be able to reopen one, or a mis-click is permanent.

!!! tip "This is the escape hatch the auto-resolver depends on"
    A report from an [automated sender](#automated-senders) is born resolved and
    attributed to `system:automated-sender`. That classifier is only defensible
    because it is reversible: without a reopen, one wrong call about an
    organization's mail would close real reports permanently. It serves a wrong
    AI resolution and an analyst's mis-click equally — none of the three is
    special here.

## Automated senders

An abuse mailbox receives a great deal that is not a report: vendor service
notices, ticketing and calendar robots, delivery-status notifications for mail
the mailbox itself sent, and list traffic the address was subscribed to years
ago. Left alone, each one becomes an open queue item with no reported message
behind it, ageing in the SLA numbers next to real reports — and, with reporter
replies on, gets mailed back to an address that cannot receive mail.

So a message whose **sender says it is a machine** produces a report row that is
born **resolved**, attributed to `system:automated-sender`.

Five triggers, each independently sufficient, and every one of them is a
statement the sending system made about itself:

| Reason | What it is |
|---|---|
| `no_reply_local_part` | The address itself says replies go nowhere — `no-reply`, `no_reply`, `No.Reply`, `donotreply`, `do-not-reply`, and vendor variants like `<product>-noreply@…`. Matched on the local part only, tokenized on its separators, so `juno.reply` does not join them |
| `auto_submitted` | RFC 3834: any `Auto-Submitted` keyword other than `no` means the message was generated automatically |
| `precedence_bulk` | The pre-RFC convention: `Precedence: bulk`, `junk` or `auto_reply` |
| `list_id` | RFC 2919: the message came from a mailing list — a distribution mechanism nobody clicks "report phishing" from. Carve-out: if the list-id names your own abuse mailbox (many organizations run the abuse address as a group), it does not count |
| `null_return_path` | RFC 5321's null reverse path, required on every delivery-status notification. The sender is asserting this message must never be bounced |

This is **not a filter**:

- The message is still ingested, still indexed, still judged, and its raw copy is
  still stored.
- An `EMAIL_USER_REPORT` event is still emitted and a report row still exists.
- The reasons are recorded on the report, so "auto-resolved because the sender set
  `Precedence: bulk`" names the thing to argue with, rather than an unactionable
  "auto-resolved".

Two things it deliberately does *not* do:

- **It does not stamp `user_reported` on the original.** No human flagged
  anything. A delivery-status notification really does carry the message it
  bounced, and manufacturing the product's strongest human signal out of a robot
  — in the one place a reader cannot check — would be worse than the noise it
  removes. The join is still recorded on the report; only the claim about who
  made it is withheld.
- **It never overrules a human.** The classifier gets exactly one attempt at a
  report. A report an analyst has touched — reopened, put in `triaging`, or
  resolved themselves — is left alone, which is what makes a reopen stick. That
  is the whole basis on which auto-resolving is defensible.

The `system:` prefix cannot be a real principal, so an analyst reading the
resolved queue can tell at a glance that nobody looked.

## Reporter replies

Off by default: it sends mail on your behalf, to your own staff.

```yaml
policy_type: reporter_reply
enabled: true
templates:
  malicious: "Thanks — you were right. We have removed that message from every mailbox it reached."
  benign: "Thanks for checking. That message is legitimate; no action was needed."
```

- Templates are keyed by verdict, and a verdict with no template falls back to a
  generic acknowledgement — enabling replies can never leave a reporter with
  silence.
- Templates are **plain text** (no `<` or `>`), capped in length. The rendering
  is fixed in code.
- Sending needs the optional provider capability: `Mail.Send` on Microsoft 365,
  `https://mail.google.com/` on Google Workspace. Without it the reply is refused
  **by name** rather than silently skipped.
- Replies are **never** sent to an automated sender. A no-reply address either
  blackholes it or bounces it straight back into the abuse mailbox, producing a
  fresh report and another reply.
- A reply is sent **once per report**, and the acknowledgement carries a marker so
  it cannot be re-read as a new report. The loop guard requires both the marker
  **and** that the sender is the abuse mailbox, because a header alone is
  attacker-controlled — otherwise anyone who had ever received an
  acknowledgement could forge one and keep a phish out of the abuse queue.

## Automating on reports

`EMAIL_USER_REPORT` is ordinary telemetry, so a D&R rule can act the moment
someone reports something — page a channel, open a case, or drive remediation
through the extension. See [Events & Automation](automation.md).
