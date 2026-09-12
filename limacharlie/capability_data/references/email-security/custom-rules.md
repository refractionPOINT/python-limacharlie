# Custom Rules

--8<-- "includes/email-security-beta.md"

Your own mail rules live in the `dr-mail` Hive. They are ordinary D&R detect
blocks evaluated against the [Message Data Model](detections.md#what-the-rules-can-read),
and they compound with the managed pack in the same scoring pass — so a custom
rule is evidence in the same verdict, not a parallel opinion.

## A rule

```yaml
# hive: dr-mail, record name: custom-vendor-bank-change
name: Payment-detail change from a first-contact sender
phase: pre_verdict
class: signal
weight: 70
confidence: 75
tags: [bec, finance]
attack_types: [bec]
fp_notes: >
  Fires on genuine new vendors during onboarding. Intended to compound with
  auth failures rather than to stand alone.
detect:
  op: and
  rules:
    - op: is
      path: enrichments/sender_profile/prevalence
      value: none
    - op: matches
      path: body/current_thread/text
      re: "(?i)(bank details|remittance|update our account)"
```

```bash
limacharlie hive set --hive-name dr-mail --key custom-vendor-bank-change \
  --input-file rule.yaml --enabled --oid $OID
```

### Fields

| Field | Required | Meaning |
|---|:--:|---|
| *(record name)* | ✅ | **The record name is the rule id.** It must start with `custom-`, which is what keeps your rules from ever colliding with a packaged one. It is also what an exclusion or a rule override names, which is why the id is the name rather than a field inside the body — a body field could be duplicated across two records |
| `phase` | ✅ | `pre_verdict` or `post_verdict` — see below |
| `detect` | ✅ | A standard D&R detect block over the MDM |
| `class` | — | `signal` (default), `detection` or `graymail` |
| `weight` | ✅ for `signal` and `detection` | 0–100. Must be **0** for `graymail`, because the graymail lane bypasses the score entirely and a weight there would never be read |
| `confidence` | — | 0–100, **default 100**. An author who does not express a confidence means "when this fires, it is right" |
| `respond` | — | `post_verdict` only |
| `name`, `tags`, `attack_types`, `fp_notes` | — | Documentation and grouping. `fp_notes` is not required of your own rules — that discipline is ours, for the pack we ship |

### The two phases

| Phase | Sees | May do |
|---|---|---|
| `pre_verdict` | The message and its enrichments, before the verdict exists | Contribute weighted evidence to the verdict. **No `respond` block** — there is no verdict yet to respond to, and a rule with one is refused |
| `post_verdict` | The whole message *and* its verdict | `respond` — dispatch a mail action, or raise a detection |

### What a `post_verdict` rule may respond with

| Action | |
|---|---|
| `extension request` naming `ext-email-security` | The way a rule reaches remediation. The typed action goes to the same executor every other action uses, which is where `alert_only` / `enforce` is decided |
| `report` | Raise a detection into the platform's detection stream |

```yaml
phase: post_verdict
class: signal
weight: 1
detect:
  op: and
  rules:
    - op: is
      path: verdict/verdict
      value: malicious
    - op: is
      path: mailbox/address
      value: cfo@corp.example
respond:
  - action: extension request
    extension name: ext-email-security
    extension action: quarantine_message
    extension request:
      msg_uuid: "{{ .msg_uuid }}"
```

Everything sensor-shaped — task, tag, isolate, seal, re-enroll, set variable —
**fails loudly** in a mail rule with a message saying so. There is no sensor
behind a message, and remediation goes through `extension request`.

!!! note "This is the same machinery your automations compile to"
    A `mailsec_policy/automations` rule is compiled into exactly this shape: a
    `post_verdict` rule whose respond block is an `extension request` naming the
    action, bound to the message that matched. Policy is the easy path; a
    `dr-mail` rule is the escape hatch when your condition does not fit the
    match fields.

## Matching one link, not any two links

A mail rule reads the message as JSON, and the paths it writes are the emitted
event's own field names. Two constructs walk a list, and confusing them is the
most common way a mail rule quietly matches the wrong thing.

### `?` walks a list and compares values

`?` is a **path segment**. It stands for "every element", and the condition
matches if **any** element satisfies it.

```yaml
# Any link whose registrable domain is evil.example
op: is
path: links/?/href_url/domain/root
value: evil.example
```

Cheap, and right most of the time. But two conditions using `?` can be satisfied
by **two different elements**:

```yaml
# WRONG if you meant "one link that is both"
op: and
rules:
  - op: is
    path: links/?/href_url/domain/root
    value: evil.example
  - op: is
    path: links/?/mismatched
    value: true
```

That fires on a message with a perfectly ordinary link to `evil.example` *and* a
separate, unrelated link whose visible text disagrees with its destination.
Nothing in it says "the same link" — and a phishing message that carries a
tracking pixel and a footer link will satisfy pairs like this by accident.

### `scope` re-roots a whole sub-rule onto one element

`scope` is an **operator**. It takes a `path` and a `rule`, and evaluates that
whole sub-rule against **each element in turn**, with the element as the root —
so every condition inside is about the *same* one.

```yaml
# ONE link that both points at evil.example and lies about where it goes
op: scope
path: links
rule:
  op: and
  rules:
    - op: is
      path: href_url/domain/root
      value: evil.example
    - op: is
      path: mismatched
      value: true
```

Paths inside a `scope` are **relative to the element** — `href_url/domain/root`
and `mismatched`, not `links/?/href_url/domain/root`. That is the other half of
the trap: a rule that keeps the full path inside a `scope` block looks correct
and matches nothing.

| | `?` | `scope` |
|---|---|---|
| What it is | A segment in a `path` | An operator with `path` and `rule` |
| Correlates fields of one element | **No** | **Yes** |
| Paths inside | Full, from the message root | Relative to the element |
| Cost | One extraction | The sub-rule, once per element |

### `scope` is capped, and nesting is refused

Use `?` unless you actually need the correlation, because `scope` is the one
allowed operator whose cost the rule's own size does not describe: the element
counts — links, attachments, headers, hops — come from **the message**, not from
your rule.

- At most **two** `scope` operators per rule.
- A `scope` inside another `scope` is **refused at save**, not merely
  discouraged. Nesting multiplies: elements to the power of the depth.

Both refusals name the reason rather than reporting a generic validation error.

## Validation

A `dr-mail` record is validated at **write time** by compiling it on the real
engine, so a record that exists has already been proven to compile. Validate a
candidate before you save it — the check calls the *same* function the Hive runs
on save, so "valid here" means "savable there":

```bash
limacharlie mailsec rule validate --file rule.json --rule-id custom-vendor-bank-change --oid $OID
```

An invalid rule is a **200 carrying `valid: false` and the reason**, not an error
response: you asked whether the rule is valid and found out that it is not. The
reason is the validator's own wording, because an author acts on the message and
not on a status code.

Omitting `--rule-id` validates against a placeholder in the `custom-` namespace,
so a rule you have not named yet does not fail on its name.

`limacharlie hive validate --hive-name dr-mail --key <name> --input-file rule.yaml`
performs the same check through the generic Hive path.

### Rules fail loudly, never quietly

A `dr-mail` record that cannot be decoded or converted **fails the whole rule
load** for that organization rather than being skipped. That is the opposite of
how a bad *policy* record is handled, and deliberately so: a dropped policy record
costs one setting, while a dropped rule is a detection the organization believes
exists and does not — silently reduced protection, which no report after the fact
undoes.

Records are loaded in record-name order so the rule set is assembled identically
on every pass, and a **disabled** record is honoured as your own off switch.

## Backtesting

Before you enable a rule, find out what it would have matched.

```bash
limacharlie mailsec rule backtest --file rule.json --since "$(date -d '14 days ago' +%s)" \
  --oid $OID --output yaml
```

The response is deliberately honest about its own limits:

| Field | Meaning |
|---|---|
| `coverage_note` | What was actually examined |
| `skipped_no_raw` | Messages whose raw copy had expired |
| `skipped_unparse` | Messages that could not be re-parsed |
| `truncated` | The run hit its bound |
| `precision` | **`null`, not `0`**, when nothing it matched has an analyst disposition yet |

A precision figure whose denominator quietly shrank is a number that looks like a
measurement and is not one — hence the skip counts. And `0` would read as
"everything it matched was wrong" and would have you discard a good rule, so the
absence of labels is reported as absence.

Backtests are bounded to the window this product retains rather than the full
message history. Both `rule validate` and `rule backtest` are gated on
`mailsec.get`: they reveal only messages you can already read, and a rule author
should be able to check their work with the grant that lets them see what the
rule would be matching.

### Two kinds of rule cannot be backtested

Both are **refused by name**, and in neither case is the rule itself the problem:
the backtest is what cannot be run, not the rule.

**A rule using `lookup`.** The `lookup` operator resolves one of your
organization's own `lookup` Hive records, and the service that answers a backtest
cannot reach them. The refusal names the resource it could not resolve, and says
what to do instead: the rule is otherwise valid, so save it and it evaluates
normally in the pipeline, where the lookup **is** resolved.

That is a real limitation, not a transient error to retry. The alternative would
have been to report "0 messages matched" for a rule that in fact matches plenty,
which is a claim about your mail that nothing looked at.

To size an IOC rule before enabling it, either backtest the same rule with the
`lookup` clause removed — which tells you how much the rest of the logic narrows
— or save it and watch it live, which is safe because a `dr-mail` rule
contributes to a verdict and your automations are in `alert_only` until you say
otherwise. See [IOC & Reputation Feeds](ioc-feeds.md).

**A `post_verdict` rule.** It runs against the verdict a pass would compute, and
a backtest replays a message rather than re-scoring it. Backtest the
`pre_verdict` rules that produce the verdict instead.

### Rules for `lookup` in a mail rule

| | |
|---|---|
| Form | The resource must be `hive://lookup/<name>` — nothing else is accepted |
| Count | At most **four** `lookup` operators per rule. Each resolves a whole lookup record for your organization |
| Existence | Checked **on save**, not by `rule validate` — see below |

!!! warning "`rule validate` does not check that the lookup exists"
    A `lookup` rule naming a record your organization does not have **passes
    `rule validate` and then fails the save.** That is the one place where "valid
    here means savable there" does not hold: the existence check needs to read
    your `lookup` records, and the validate call cannot.

    The check itself is worth having, and the Hive does run it: a dangling
    `hive://lookup/` reference is the most common authoring mistake, it would
    otherwise save cleanly and match nothing forever, and that reads as coverage.
    The refusal names the record and tells you to create it first.

    So: write the lookup before you write the rule that names it, and treat a
    save failure after a clean validate as this, not as a mystery.

## Tuning the managed pack

You do not need a custom rule to change a packaged one. Disable it, or replace
its weight, for your organization:

```yaml
policy_type: thresholds
rule_overrides:
  ms-link-unranked-domain:
    weight: 15
  ms-sender-first-contact:
    disabled: true
```

And to suppress a rule for a specific sender, domain or mailbox rather than
everywhere, use an [exclusion](policy.md#exclusions) — which carries a reason and
an optional expiry, so the hole in detection is reviewable.

## Rules that act on emitted events

A `dr-mail` rule is one of two seats. The other is an ordinary D&R rule in
`dr-general` matching the `EMAIL_*` events, which gets the platform's full
response arsenal and can correlate mail with the rest of your telemetry. See
[Events & Automation](automation.md).

### Acting on a verdict

`EMAIL_VERDICT` carries every verdict decision — the rule pack's own at
`seq: 0`, and each later override — so a rule that should fire whenever a message
is judged malicious is written once, against one path:

```yaml
# Detect
op: and
rules:
  - op: is
    path: routing/event_type
    value: EMAIL_VERDICT
  - op: is
    path: event/revision/verdict
    value: malicious
```

```yaml
# Respond
- action: report
  name: email-verdict-malicious
- action: extension request
  extension name: ext-email-security
  extension action: quarantine_message
  extension request:
    msg_uuid: '{{ .event.msg_uuid }}'
```

That fires when the pack decides a message is malicious **and** when an analyst,
the AI triage agent or a link detonation later decides so. Narrow it with the
fields that distinguish them:

| To match | Add |
|---|---|
| Only the rule pack's own decision | `path: event/revision/seq`, `value: 0` |
| Only overrides | `op: is greater than`, `path: event/revision/seq`, `value: 0` |
| Only what a human decided | `path: event/revision/mode`, `value: analyst` |
| Only a *change* to malicious | `path: event/revision/prior/verdict`, `op: is not`, `value: malicious` |
| A specific rule that fired | `op: is`, `path: event/revision/top_signals/?/rule_id`, `value: ms-link-credentials-in-url` — the `?` matches any element of the list (`seq 0` only; an override carries no signals) |

!!! warning "Overrides go both ways"
    An override can also clear a verdict. A rule that quarantines on
    `verdict: malicious` will see the escalation, and a later `benign` revision
    does **not** undo the action it took — write the compensating rule if you
    want one.
