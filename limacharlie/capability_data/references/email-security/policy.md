# Policy Reference

--8<-- "includes/email-security-beta.md"

Email Security is configured through Hive records. Anything the console can
configure, `limacharlie hive set` can configure — so tenant onboarding and
fleet-wide policy are a script, not a UI workflow.

| Hive | Records | Purpose |
|---|---|---|
| `mailsec_provider` | one per mail connection | which tenant to protect, with which credential — see [Connecting Providers](providers.md) |
| `mailsec_policy` | many, discriminated by `policy_type` | managed detections, automations, exclusions, VIPs, thresholds, banners, retention, reporter replies, hunt defaults, clustering |
| `dr-mail` | one per custom rule | your own mail detection rules — see [Custom Rules](custom-rules.md) |

## How `mailsec_policy` records work

Every record carries a `policy_type` discriminator. There may be **many records
of each type**, and they compose into one resolved policy.

### Composition is by record name

Records compose in **record-name order**. The name is not decoration: it is the
only thing that makes composition deterministic when two records set the same
field. An organization that needs a specific precedence names its records
accordingly — `00-baseline`, `50-team-x`, `99-override` — the same convention as
every other ordered configuration surface.

How each type composes:

| Type | Composition |
|---|---|
| `automations` | Concatenated in name order; evaluated as an ordered list |
| `exclusions` | Concatenated — a set of independent suppressions |
| `vips` | Union, deduplicated and sorted |
| `thresholds` | Last writer wins per field, with the ordering invariant re-checked afterwards |
| `managed_rules`, `banners`, `reporter_reply`, `hunt_defaults`, `clustering` | Last writer wins per field |
| `retention` | **Maximum** wins — see [Retention](#retention) |

### Unknown fields are refused

Every record body is decoded strictly. A key the contract does not define is a
**rejected record**, not an ignored field. A policy is a security control, and a
typo'd key that silently does nothing is the worst available failure mode: the
operator believes mail is being quarantined and it is not. A rejected record is
visible; an ignored field is not.

The validator's own wording is what you get back — in the CLI, in the API, and
verbatim in the console's Policy page.

### Editing preserves what you did not touch

The console's **Policy** page edits every record type, and saves are
**patch-preserving**: fields the form does not manage are written back exactly as
they were. Editing a policy record in the UI never silently drops a field you set
through the API or through git-sync.

### Defaults

An organization that has written no policy still has one. Every type below states
its default, and the defaults are deliberately inert: nothing moves mail, nothing
modifies mail, and nothing sends mail until you say so.

---

## `managed_rules`

The switch for the packaged detection pack. It is the first record in this
reference because it is the only one that can turn detection off.

```yaml
policy_type: managed_rules
enabled: false
```

| Field | Default | |
|---|---|---|
| `enabled` | `true` | Whether the managed rule pack is matched at all |

**`enabled` must be stated.** A `managed_rules` record that sets nothing is
refused rather than read as "disable": the failure mode of guessing wrong here is
an organization with no detection that believes it has some.

**Absent is enabled.** An organization that has never written this record has the
pack. "No record" is the product default, not an opt-out, and nothing in the
console or the API renders a missing record as off.

**When it is off**, the managed pack is not matched at all. Your own `dr-mail`
rules still are, and they are still scored the same way — so an organization that
wants to own detection entirely can. A message that then matches nothing is
`unknown`, never `benign`: "nobody was looking" and "we looked and it was fine"
are different facts and are reported differently. See
[Managed detections are optional](pipeline.md#managed-detections-are-optional).

You do not need this switch to *tune* the pack. Disabling one packaged rule, or
changing its weight, is a [`rule_overrides`](#thresholds) entry.

### The three ways to flip it

All three write the same record — same name, same `policy_type`, same field — and
the collector cannot tell which one wrote it.

=== "Console"

    **Email Security → Settings** carries a managed-detection switch, and
    **Overview** leads with a banner while the pack is off — that one fact
    changes how every count below it should be read. Turning the pack **off**
    asks for confirmation; turning it back on restores the product default and
    does not.

    When more than one `managed_rules` record exists, or the canonical one has
    been disabled in the Hive, the switch is **replaced** by a status badge
    showing the resolved value and a link to the **Policy** page. It does not
    offer to write, because a write in that state would either be overridden by
    a later-named record or silently do nothing — and a switch that reports a
    state it did not produce is worse than no switch.

=== "CLI"

    ```bash
    cat > managed-rules.yaml <<'YAML'
    policy_type: managed_rules
    enabled: false
    YAML

    limacharlie hive set --hive-name mailsec_policy --key managed_rules \
      --input-file managed-rules.yaml --enabled --oid $OID
    ```

=== "Extension"

    `ext-email-security` exposes two actions for reading and flipping this
    without hand-writing a record — which is how a D&R rule or an automation
    reaches it:

    | Action | Body | Returns |
    |---|---|---|
    | `set_managed_rules` | `enabled` (**required** boolean), optional `reason` — recorded as the record's comment | `managed_rules_enabled` |
    | `get_managed_rules` | — | `managed_rules_enabled`, and `configured` |

    `configured` is the field that distinguishes **on by default** from **turned
    on deliberately**: it is `false` when no record exists. `set_managed_rules`
    needs `mailsec.set`; `get_managed_rules` needs `mailsec.get`.

!!! note "`managed_rules` is the canonical record name"
    The console and the extension both write the record **named**
    `managed_rules`, and the CLI example above does too. Any record name works —
    composition is last-writer-wins in record-name order over the records the
    Hive has *enabled* — but a second record named later than `managed_rules`
    wins over it, and a `managed_rules` record the Hive has disabled does not
    count at all. Keep it to one record unless you mean to layer them.

    Only the extension stamps the record with the `lc:system` tag. The console
    and the CLI do not add it, and the console **preserves** it when it edits a
    record the extension wrote — so the tag tells you how a record was first
    created, and nothing more. Do not treat its absence as meaningful.

### How fast a change takes effect

| | |
|---|---|
| **Normally** | Seconds. A `mailsec_policy` write is broadcast on the Hive's change feed and the collector drops that organization's cached policy on the spot |
| **If the broadcast is missed** | The next mailbox-lease renewal tick re-reads policy |
| **Worst case** | **Five minutes** — the resolved-policy cache's TTL, which expires whether or not anything was heard |

The broadcast is the fast path and never the guarantee: it is fire-and-forget, so
a collector that was restarting can miss it. The bound you are promised is the
five-minute TTL, and the broadcast is why you almost never wait for it.

---

## `automations`

The ordered list of `{match → actions}` rules that decide what happens to a
message automatically.

```yaml
policy_type: automations
automations:
  - name: malicious-quarantine
    match:
      verdicts: [malicious]
    actions: [quarantine_message]
    mode: alert_only
  - name: reported-mail-quarantine
    match:
      user_reported: true
      min_score: 45
    actions: [quarantine_message]
    mode: alert_only
```

### `match`

| Field | Meaning |
|---|---|
| `verdicts` | Any of `malicious`, `suspicious`, `graymail`, `benign`, `unknown`, `error`. An unrecognized verdict is refused rather than silently never matching |
| `tags` | Verdict tags contributed by the rules that fired |
| `directions` | `inbound`, `outbound`, `internal` |
| `min_score` | 0–100 |
| `user_reported` | Tri-state: omit to ignore, `true` for mail a human flagged, `false` for mail nobody reported |

An **empty match matches everything**. An enforcing rule with an empty match is
refused at save — "quarantine all mail" is never what someone meant to write.

### `actions`

| Action | | Touches the mailbox |
|---|---|:--:|
| `quarantine_message` | Out of the inbox, restorable — a change of **placement** | ✅ |
| `trash_message` | To recoverable trash — a change of placement | ✅ |
| `move_to_spam` | To the junk/spam location — a change of placement | ✅ |
| `banner_message` | Prepend the warning banner. A **modification**, not a placement: a bannered message does not move. Needs `enabled` on the [`banners`](#banners) record | ✅ |
| `submit_to_triage` | Record that this message warrants a look, and say so as telemetry | |
| `crawl_link` | Queue the message's links for [detonation](detections.md#link-detonation) | |

Deliberately **not** automatable: the campaign-wide sweeps (an automation acting
on one message must not fan out to hundreds without a human — that is an explicit
action), `restore_message` (undoing is a human decision), and the disposition
labels (labels are evidence, and a machine writing them would poison the data set
that measures the machine).

### The two asking actions

`submit_to_triage` and `crawl_link` touch no mailbox. They record a question and
hand it off, and neither promotes the message to the 400-day evidence lane —
asking is not an answer. The message gets there when the question produces one.

`submit_to_triage` calls nothing and starts nothing: it writes an audit row and
emits an `EMAIL_ACTION`, which is the event an
[AI triage agent's trigger rule](ai-triage.md) fires on. Deciding *which* mail
warrants a look is this product's half of the job; deciding how an agent runs and
what it costs belongs to the agent.

!!! danger "A trigger on `submit_to_triage` must filter on `result`"
    An `EMAIL_ACTION` is emitted for **every** outcome, including `alert_only` —
    that is what makes the audit complete. So an organization in `alert_only`
    emits `EMAIL_ACTION{action: submit_to_triage, result: alert_only}`, meaning
    "this organization's automations *would* have asked for a look".

    A rule matching the action alone reads that as consent and starts a paid
    session for exactly the organizations that chose not to have things happen on
    their behalf. Always write:

    ```yaml
    op: and
    rules:
      - op: is
        path: routing/event_type
        value: EMAIL_ACTION
      - op: is
        path: event/action
        value: submit_to_triage
      - op: is
        path: event/result
        value: ok
    ```

`crawl_link` returns `ok` meaning **queued**, not fetched. It is subject to the
same enforcement check as everything else, and deliberately so: a detonation
opens a connection to attacker-controlled infrastructure, which confirms to the
sender that the mail landed in a monitored mailbox. An organization in
`alert_only` has said "do not do things on my behalf", and that is such a thing.
An analyst asking always executes. Where detonation is not deployed, the action
records a failed result naming that rather than pretending to have queued it.

### `mode`

| Mode | |
|---|---|
| `alert_only` | **The default.** The rule is evaluated and its intent recorded; the mailbox is not touched. Actions report `alert_only` as their result |
| `enforce` | The action is performed at the provider |

The default is load-bearing. A rule whose mode is missing, misspelled, or written
by an older tool falls back to the harmless behaviour — falling back to `enforce`
would mean a typo silently deletes mail. An unrecognized mode is refused at
save, and anything that ever slipped past decoding still behaves as
`alert_only`.

!!! danger "Enforcement is currently organization-wide at the executor"
    The remediation executor authorizes *automated* action when **any** resolved
    automation rule is in `enforce` mode. Which rule dispatches which action is
    still decided per rule, but the executor's consent check is not per rule — so
    putting one rule into `enforce` enables the organization's automated paths
    generally. Treat the first `enforce` as the decision that this organization
    now moves mail automatically.

    Analyst-initiated actions are unaffected: a human clicking quarantine always
    executes.

**Default:** subscribing seeds a recommended preset entirely in `alert_only` —
malicious → quarantine and graymail → move to spam among them. Nobody is
surprise-quarantined on day one. Review the seeded records before switching any
of them to `enforce`.

!!! note "An automation edit can take up to ten minutes to apply"
    Automations are **compiled** from the resolved policy, and that compile
    happens on a ten-minute tick rather than per message. Everything the
    judgement path reads — [`thresholds`](#thresholds), [`exclusions`](#exclusions),
    the [`managed_rules`](#managed_rules) switch — applies within five minutes and
    usually within seconds. An edit here is the one with the longer bound.

    Plan a change to `enforce` accordingly: the switch is not instantaneous, and
    switching it back is subject to the same tick.

---

## `exclusions`

Suppress signals **before** scoring, so an excluded rule contributes nothing to
the score and never appears in the verdict's reasons. It still appears in
`matched_signals`, so a suppression is auditable rather than invisible.

```yaml
policy_type: exclusions
exclusions:
  - rule_id: ms-sender-first-contact
    sender_domain: newsletters.partner.example
    reason: "Marketing partner onboarded 2026-08; every send is a first contact"
    expires_at: "2026-12-31T00:00:00Z"
```

| Field | |
|---|---|
| `rule_id`, `sender_email`, `sender_domain`, `mailbox` | The scope. **At least one is required** |
| `reason` | **Required.** An exclusion is a permanent hole in detection, and one whose rationale nobody recorded is one nobody can ever safely remove |
| `created_by` | Optional attribution |
| `expires_at` | Optional. After it, the exclusion is inert without anyone deleting it — which is what makes a time-boxed exclusion safe to grant |

Addresses and domains are lowercased on save.

**Default:** none.

---

## `vips`

The protected identities that impersonation detection compares against — the
display names and addresses a `Finance` request is most damaging in the name of.

```yaml
policy_type: vips
vips:
  - name: Ada Lovelace
    email: ada@corp.example
    title: CFO
list_refs:
  - hive://lookup/execs
```

| Field | |
|---|---|
| `vips[]` | Inline entries. Each needs a `name` **or** an `email`; `title` is context for an analyst, not a matching key |
| `list_refs[]` | References to `lookup` Hive records, so the executive list lives in one place — the same lookup your D&R rules and your HR export already feed — instead of being copied into policy where it drifts |

A `list_ref` must be of the form `hive://lookup/<name>`.

### The two accepted lookup shapes

A LimaCharlie lookup record is a map of key → metadata. Both forms are read, and
both are normalized into the same VIP:

```yaml
# (a) the key is the email address, metadata is optional context
"ada@corp.example":
  name: Ada Lovelace
  title: CFO
```

```yaml
# (b) the key is the display name, the address (if known) is in the metadata
"Ada Lovelace":
  email: ada@corp.example
  title: CFO
```

In shape (a) the **key wins** over any `email` in the metadata: in a lookup the
key is the indicator, and that is what every other consumer of the record matches
on. A disagreeing metadata field must not make mail security protect a different
address than the rules do.

An entry with neither a plausible email key nor an email in its metadata — the
bare `"Ada Lovelace": {}` a newline upload produces — becomes a **name-only VIP**.
That is legal and useful: display-name impersonation is the high-yield shape and
needs no address to be detected.

Metadata keys are matched case-insensitively; `name` (alias `display_name`),
`email` and `title` are read and everything else is ignored, so a list maintained
for another purpose can be pointed at without being reshaped.

Both the plain and the pre-indexed (optimized) storage forms of a lookup record
are read, because which one the Hive holds depends only on how the record was
uploaded.

### What is surfaced

- A reference whose record is **absent, disabled, not shaped like a lookup, or
  empty of usable entries** resolves to zero entries and is **reported to the
  organization** — a configured VIP list that contributes nobody is a coverage
  lie, and it is reported repeatedly until fixed rather than once per process.
- A reference that could not be **read** keeps serving its last good entries and
  is reported as stale rather than lost, so one datastore blip does not disarm
  your VIP list.
- Malformed entries and truncation are counted and reported **as counts, never
  with the entry's contents** — a VIP list is a list of named people, and a
  malformed row is exactly as personal as a well-formed one.
- One reference contributes at most **1,000 entries**. The VIP list is scanned
  once per message, so pointing this at a large threat feed would put a huge scan
  in the ingest path of every message. Truncation is surfaced, never silent.

Resolution never fails the policy: inline entries and every other reference stay
in force.

**Default:** none.

---

## `thresholds`

The verdict cutoffs and per-rule overrides.

```yaml
policy_type: thresholds
malicious_min: 80
suspicious_min: 40
rule_overrides:
  ms-link-unranked-domain:
    weight: 15
  ms-graymail-precedence-bulk:
    disabled: true
```

| Field | Default | |
|---|---|---|
| `malicious_min` | 85 | 1–100 |
| `suspicious_min` | 45 | 1–100 |
| `rule_overrides` | — | Keyed by rule id: `disabled` to switch a packaged rule off for your organization, `weight` (0–100) to replace its packaged weight |

`malicious_min` must remain **above** `suspicious_min`. Two records that are each
individually sane can compose into an inversion — one lowers malicious, another
raises suspicious — so the invariant is enforced after composition, not only per
record. An inverted pair would make every suspicious message malicious.

Rule ids are stable and are never renamed, which is the only reason an override
can be persisted at all.

---

## `banners`

The warning banner's text and switch.

```yaml
policy_type: banners
enabled: true
text: "External sender. Verify before clicking links or opening attachments."
```

| Field | Default | |
|---|---|---|
| `enabled` | `false` | Bannering rewrites the customer's mail, and nothing in this product modifies mail by default |
| `text` | A packaged warning | **Plain text only** — no `<` or `>` — and capped at 512 characters |

The HTML template is fixed and sanitized in code; policy contributes only the
text, and it is HTML-escaped when the banner is rendered. Accepting markup here
would turn a configuration field into stored HTML injection against your own
users, so it is refused at the record and escaped again at the render.

**This record is the only source of a banner's wording.** No API call, CLI flag
or D&R rule supplies banner HTML — the `banner` field on the action routes and
the `--banner` flag are deprecated and ignored, and will be removed. If you
change the wording here, every subsequent `banner_message` uses it.

`enabled` is what lets **automation** banner this organization's mail: with it
off, an automation, a D&R rule or the AI triage agent asking for
`banner_message` is decided and audited but the mailbox is not touched
(`alert_only`). It does **not** gate a banner somebody asked for — from the
console, the API or the CLI — because the switch exists to stop the product
rewriting mail on its own, not to stop an operator from acting on a message in
front of them. An organization that has never written this record still has
working `banner_message` from the console; it simply has no automated
bannering, and the wording is the packaged sentence.

Bannering also needs the provider capability: `Mail.ReadWrite` is enough on
Microsoft 365 (edited in place), while Google Workspace additionally needs the
optional `https://mail.google.com/` scope and **replaces** the message.

---

## `retention`

How long Email Security keeps your mail data. Lower it and the data is deleted;
this is the setting that makes "we hold nothing older than N days" true.

```yaml
policy_type: retention
message_days: 14
flagged_days: 180
```

| Field | Default | Range | Governs |
|---|---|---|---|
| `message_days` | 35 | 1–35 | The searchable message index and the stored copy of the raw message |
| `flagged_days` | 400 | 1–400 | Flagged evidence, its stored copy, verdict revisions, and the action, report, campaign and sender-profile history |

Set either, or both. A record that sets neither is rejected — a retention policy
that does nothing is worse than no policy, because you would believe it was in
force.

### Two numbers, because there are two lanes

The **message index** is the recent operational surface: every message, with the
metadata the queue and the hunt read, plus the raw message itself. It is what
`message_days` shortens.

The **evidence lane** is what an investigation reaches for months later: the
flagged messages, their stored copies, every verdict revision, and the record of
what was done to the mail and who did it. It is what `flagged_days` shortens.
There is no separate "evidence" setting — this is it.

"Keep my queue for a week" and "keep my phishing evidence for a week" are
different asks, so they are different fields.

### The defaults are ceilings, not targets

400 and 35 are the store's own hard limits. Policy can only choose a **shorter**
horizon, never a longer one: a setting past the ceiling is rejected rather than
quietly ignored, because it would be a promise the database silently breaks.

The floor is **one day**. Below that a message would not survive long enough for
the queue, the verdict and the analyst who opens it to exist, so a shorter value
is rejected rather than clamped — Email Security tells you it will not do it
instead of doing something else.

### What deletion actually removes

Data past your horizon is removed on a recurring sweep — the rows, the stored
copies of the messages in cloud storage, the parsed projections beside them, and
the link-detonation results derived from that mail. Deletion is permanent and
there is no undo, which is why the horizon is a policy you edit rather than a
button you press.

Two consequences worth knowing:

- Lowering a value takes effect on the next sweep, and a large backlog drains
  over several sweeps rather than all at once.
- The horizons are independent. A flagged message's evidence can outlive its
  index entry (the usual case: 400 against 35), and if you set `flagged_days`
  *below* `message_days` the reverse happens — the index entry remains without a
  downloadable copy of the message, because you asked for the message itself to
  be deleted.

`GET /coverage` reports the horizon actually in force, so a window reaching past
it is labelled rather than shown as though the missing days were empty.

### Composition

Composition takes the **minimum**, not the last writer. If one record says 30
days and another says 200, the answer is 30: a retention record is an instruction
to delete — usually one you have committed to somebody else — so the strictest
one wins, in the direction of holding less of your mail.

Removing an organization's Email Security data outright, rather than waiting for a
window to end, is covered under [Data retention and deletion](#data-retention-and-deletion) below.

---

## Data retention and deletion

Retention and deletion answer different questions. Retention decides *when* data
ages out on a clock and runs on its own. A **tenant purge** decides that the data
is gone *now*: everything Email Security holds for one organization, removed
everywhere, in one operation, on request.

### The three clocks

| Lane | Kept | Holds |
|---|---|---|
| Message index | up to **35 days** | The searchable row for every message, and what the queue and the drawer read from. Tunable with [`retention`](#retention) `message_days` within the 35-day ceiling |
| Evidence | up to **400 days** | Flagged messages and the evidence attached to them. Tunable with [`retention`](#retention) `flagged_days` within the 400-day ceiling |
| Raw messages | follows the message-index lane, and the evidence lane once a message is flagged | The original bytes and the parsed copy behind them |

Nothing on those clocks needs a request. Data leaves each lane when its window
ends, and only that lane's window moves it. See
[Two retention lanes](pipeline.md#two-retention-lanes) for how a message is
placed in a lane and promoted between them.

### What a purge removes

A tenant purge permanently deletes, for one organization:

- the message index and the long-term evidence lane
- campaigns
- sender profiles
- the remediation and action audit trail this product keeps
- user (abuse-mailbox) reports
- stored raw messages and their parsed copies
- link-detonation results
- the organization's Email Security provider connection and policy configuration

It also **stops the mail connections at Microsoft 365 and Google Workspace**, so
the provider stops sending notifications. That matters as much as the deletion
itself: a purge that left the connections running would begin repopulating the
index with the next message to arrive.

!!! danger "A purge cannot be undone"
    There is no restore, no grace period and no partial scope — the unit is the
    whole organization. A purged organization looks to Email Security exactly
    like one that was never connected.

### Authority and audit

Both the preview and the purge itself require **Owner-level authority**:
`mailsec.act`, `billing.ctrl` and `user.ctrl` together. That is the same trio
deleting the organization requires; there is no separate "owner" permission to
grant, and no combination short of all three is accepted.

The purge is written to the organization's audit log with your authenticated
identity and, if you supplied one, a free-text `reason` of up to 1024
characters. As everywhere else in this product, the identity is stamped by the
server from your verified claims rather than taken from the request.

### It also happens without a request

| Event | When the data is deleted | What cancels it |
|---|---|---|
| The organization unsubscribes from Email Security | **30 days** later | Resubscribing at any point inside those 30 days |
| The organization's free trial ends and it stays on the free tier | **30 days** later | Moving the organization off the free tier at any point inside those 30 days |
| The organization itself is deleted | Immediately | Nothing — the organization no longer exists |

None of them needs anyone to ask. The 30-day delay exists so that unsubscribing
by mistake, letting a trial lapse over a holiday, or moving billing around is
recoverable — and undoing the thing that started the clock is all the recovery
takes. The two cancellations are **not interchangeable**: resubscribing does not
cancel a deletion scheduled because a trial ended, and upgrading does not cancel
one scheduled because the organization unsubscribed. Each undoes only what it
contradicts.

### You are told before it happens

A scheduled deletion is never silent. You learn about it three ways:

- **When it is scheduled**, as an error-stream notice naming the exact date, why
  the deletion was scheduled, and what cancels it.
- **Seven days before it fires**, as a second notice marked `FINAL NOTICE`.
- **At any time**, from the `entitlement` block of
  [`GET /coverage`](api-reference.md#reads) — `purge_scheduled_at`,
  `purge_reason`, `purge_days_remaining` and `purge_cancellable`. The block is
  absent from the response only when nothing is scheduled.

Both notices go to the organization's error stream, which is the same place
Email Security reports that ingestion has paused — so there is one place to
watch, and a D&R rule or an output can act on either. Each notice is delivered
exactly once per scheduled deletion; if the deadline moves, the notices are
re-sent for the new date.

## Plans, the free trial, and the mailbox cap

Email Security is available to every organization. What differs between a
**trial** organization and a **paid** one is how long it runs and how many
mailboxes it protects.

An organization is on the trial when it is on the LimaCharlie free tier — the
same line the rest of the platform draws, so an organization evaluating Email
Security and Cloud Security at once gets one answer about what it is paying for.

| | Trial | Paid |
|---|---|---|
| Duration | **14 days** from the day Email Security was enabled | No limit |
| Protected mailboxes | **25** | No limit |
| Everything else — detections, remediation, retention, API, telemetry | Identical | Identical |

### The 14-day clock

The clock starts the day the organization first subscribes to
`ext-email-security` and is recorded durably. **Unsubscribing and resubscribing
does not restart it**: the clock survives an unsubscribe, so a trial is 14 days
once rather than 14 days per subscription. Moving the organization off the free
tier clears the limits immediately.

Read the remaining time from the `entitlement` block of
[`GET /coverage`](api-reference.md#reads): `trial_ends_at` and
`trial_days_remaining`.

### What happens when the trial ends

The same thing that happens when an organization unsubscribes, and for the same
reason — the product stops, nothing is deleted yet:

- **Ingestion pauses.** No new mail is analyzed, and the mail connections are
  not renewed, so the provider's own watches expire on their own schedule.
- **Nothing is deleted, and nothing is changed.** The connections, the policy
  records and every message already analyzed are intact and follow their normal
  [retention](#data-retention-and-deletion).
- **Reading and acting still work.** An analyst can still search the queue, read
  a message and remediate mail that was already ingested.
- **The 30-day deletion clock starts**, with the notices described above.

Moving the organization off the free tier resumes ingestion within about five
minutes, and cancels the scheduled deletion. Mail delivered while ingestion was
paused is not analyzed retroactively.

### The 25-mailbox cap

A trial organization protects up to 25 mailboxes. The cap applies to the whole
organization, across every connected mail tenant, and it works on **activation**
only:

- Discovery still finds every mailbox in the tenant — the ones past the cap are
  reported as `discovered` rather than `protected`, so you can see exactly how
  much of the estate is not covered.
- A mailbox that is already protected is **never** dropped to fit a cap. If the
  cap is reached, further mailboxes stop being protected; the ones already being
  watched keep being watched.
- Use [`exclusions`](#exclusions) and the connection's `scope` to choose *which*
  25 mailboxes matter — the executives and finance addresses attacks aim at are
  the ones worth spending a trial on.

`GET /coverage`'s `entitlement` block reports `mailbox_cap`, `mailboxes_active`,
`mailboxes_over_cap` and `mailbox_cap_reached`, so the shortfall is a number
rather than a discovery.

### Requesting a purge

Two steps, because the confirmation token is minted by a call that shows you the
warning and changes nothing:

```bash
# 1. Preview. Prints the warning and mints a single-use token; deletes nothing.
PREVIEW=$(limacharlie mailsec tenant purge --oid "$OID" --output json)
echo "$PREVIEW" | jq -r .warning

# 2. Purge, within 5 minutes, quoting that token.
limacharlie mailsec tenant purge --oid "$OID" \
  --confirm "$(echo "$PREVIEW" | jq -r .confirmation)" \
  --reason "Tenant offboarded"
```

The token is single-use and expires 5 minutes after it is minted, so a purge
cannot be replayed and a re-run always starts from a fresh preview. See
[the CLI notes](cli.md#the-tenant-purge-is-irreversible) and
[`DELETE /tenant`](api-reference.md#delete-tenant) for the response fields and
for what to do when a purge reports that it did not finish.

---

## `reporter_reply`

The templated acknowledgement sent to someone who reported a message. See
[User Reports](user-reports.md#reporter-replies).

```yaml
policy_type: reporter_reply
enabled: true
templates:
  malicious: "Thanks — you were right. We removed that message from every mailbox it reached."
  benign: "Thanks for checking. That message is legitimate; no action was needed."
```

| Field | Default | |
|---|---|---|
| `enabled` | `false` | It sends mail on your behalf to your own staff; opt-in |
| `templates` | — | Keyed by verdict. A verdict with no template falls back to a generic acknowledgement, so enabling replies can never leave a reporter with silence |

Template keys must be verdicts. Values are plain text (no `<` or `>`), capped at
4096 characters.

---

## `hunt_defaults`

Starting values for retro-hunt requests.

```yaml
policy_type: hunt_defaults
window_days: 7
max_results: 1000
dry_run: true
```

| Field | Default | Range |
|---|---|---|
| `window_days` | 7 | 1–365 |
| `max_results` | 1000 | 1–100000 |
| `dry_run` | `true` | An operation that can bulk-remediate defaults to "show me what this would match" |

!!! warning "Nothing reads this record yet"
    The record type validates and composes like every other one, and it is
    documented here because it is savable and will be refused if you get it
    wrong. But **no surface consumes it today.** The server-side retro-hunt
    (`POST /hunts`, `GET /hunts/{hunt_id}`, `POST /hunts/{hunt_id}/remediate`)
    is registered in the public OpenAPI document and answers a typed
    `not_implemented` — the URLs and their permission gates are frozen ahead of
    the engine that will serve them. The console's **Hunt** screen is a
    different thing entirely: it compiles your criteria to
    [LCQL](automation.md#querying-mail-with-lcql) and runs the ordinary
    historical-event search over `EMAIL_MESSAGE`, with its own window control,
    and it does not read this record.

    Writing `hunt_defaults` now is harmless and changes nothing. Do not treat a
    `dry_run: true` here as a safety control over anything.

---

## `clustering`

How aggressively messages are grouped into a campaign — which is what sets the
blast radius of a campaign-wide action. It is a separate record from
`thresholds` on purpose: `thresholds` is how harshly mail is *judged*, and
folding the reach of a bulk quarantine into a record named for scoring would hide
it.

```yaml
policy_type: clustering
body_similarity: true
body_similarity_distance: 30
```

| Field | Default | Range |
|---|---|---|
| `body_similarity` | `true` | Whether the body fuzzy hash may count as an agreeing cluster key |
| `body_similarity_distance` | 30 | 0–35. Lower is stricter; 0 means byte-identical normalized bodies only |

The default is **on**, because the organization that most needs body similarity —
one being hit by a kit that randomizes subjects and links — is the one least
likely to go looking for a switch to turn on.

The distance default is measured, not chosen: across a 404-message corpus of
ordinary business mail the closest pair of *unrelated* messages is 39 apart,
while two copies of one message differing only in the recipient's name and the
link's tracking parameters are 0 apart. The ceiling of 35 sits below that closest
pair deliberately — a setting above it is one you cannot have measured.

See [Body similarity](campaigns.md#body-similarity) for what the key is and how a
body is normalized before it is hashed.

!!! note "Turning it off does not stop the digest being computed"
    `body_similarity: false` stops the digest counting as *agreement*. It is
    still computed, still stored, still returned on the message and still
    searchable. So turning the switch back on gives you working clustering
    immediately, rather than only for mail that arrives afterwards — and the
    digest an analyst is looking at is never a value the product quietly stopped
    maintaining.

---

## Reading the resolved policy

The resolved automation mode — the effective safety banner — is reported by
coverage, and the console shows it on both **Overview** and **Settings**:

```bash
limacharlie mailsec coverage --oid $OID --output yaml --filter 'overview'
```

It reads `enforce` when any resolved rule can act, and fails closed to
`alert_only` when the policy is absent, unreadable, or carries a mode this build
does not recognize.
