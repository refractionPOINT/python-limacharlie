# Remediation SLAs

A remediation SLA puts a **due date** on findings, so the worklist can answer
*"what is late?"* rather than only *"what is bad?"*. You declare how long a
finding of a given severity, class, detecting rule, account, or owner may stay
open; every
covered finding then carries a `due_at`, and being breached is a plain
comparison against the clock rather than a stored judgement somebody has to
maintain.

It is one `sla`-typed [`cloudsec_policy`](configuration.md#cloudsec_policy)
record.

## There is no default SLA

An organization with no `sla` policy record has **no due dates and nothing
breached**. Every finding reads `none`. That is deliberate, and it is not an
oversight waiting to be fixed:

- An SLA is a commitment **you** make about your own remediation capacity. The
  platform inventing one on your behalf is the same category of mistake as
  declaring your data sensitive without being told — which is why the
  [`classification` policy](configuration.md#classification-crown-jewels) works
  the same way.
- A built-in default would mean that every existing estate instantly acquires a
  five- or six-figure `breached` count for work nobody ever promised to do. A
  manufactured number is worse than a missing one.

So adoption is a single Hive write, and the starter policy below is what to
write.

!!! note "It takes one sweep to land"
    Like every other `cloudsec_policy` record, an `sla` policy reaches the engine
    at the end of the **next collection sweep**, and the due dates are stamped on
    the projection after it. Writing the record and immediately reading
    `sla_state: none` across the estate does not mean it was rejected — change
    the provider's `sync_now` nonce to trigger a sweep straight away instead of
    waiting for the refresh cadence.

## The starter policy

The four-tier shape below is the common industry default and a reasonable place
to begin. It is a **recommendation, not a default** — nothing applies it until you
write it:

```json
{
  "policy_type": "sla",
  "sla": {
    "default_due_days": { "CRITICAL": 7, "HIGH": 30, "MEDIUM": 90, "LOW": 180 }
  }
}
```

```bash
limacharlie hive set --hive-name cloudsec_policy --key sla \
  --oid $OID --input-file sla.json --enabled
```

Start there, watch the breach count for a cycle, then add rules to **tighten** the
part of the estate you actually care about — internet-exposed resources,
production accounts, crown-jewel data stores — rather than loosening the defaults
to make the number look better.

## The record

| Field | Meaning |
|---|---|
| `default_due_days` | Per-severity fallback, keyed by `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `INFO` (case-insensitive). Applied only when **no** rule matched. A severity absent from the map gets no due date. |
| `rules` | An **ordered** list of `{name, match, due_days}` clauses. First match wins. |

```json
{
  "policy_type": "sla",
  "sla": {
    "default_due_days": { "CRITICAL": 7, "HIGH": 30, "MEDIUM": 90, "LOW": 180 },
    "rules": [
      {
        "name": "sandbox-is-exempt",
        "match": { "account": ["sandbox-*", "*-scratch"] },
        "due_days": 0
      },
      {
        "name": "production-criticals",
        "match": { "severity": ["CRITICAL"], "account": ["prod-*"] },
        "due_days": 3
      },
      {
        "name": "known-exploited-vulns",
        "match": { "finding_class": ["vulnerability"], "severity": ["CRITICAL", "HIGH"] },
        "due_days": 14
      },
      {
        "name": "platform-team",
        "match": { "owner": ["*@platform.example.com"] },
        "due_days": 14
      },
      {
        "name": "everything-else",
        "match": {},
        "due_days": 90
      }
    ]
  }
}
```

Many `sla` records compose: rule lists concatenate in **record-name** order — so
first-match-wins is deterministic across records too — and the per-severity
defaults merge first-record-wins.

### Matching

- **Rules are ordered and the first match wins** — the same convention the
  [`suppression`](automation.md#suppression-rules-finding-disposition-policy) and
  [`exclusions`](configuration.md#exclusions-the-escape-hatch) policies use. Put
  the narrow clauses first.
- Within a rule, keys **AND** together and lists **OR** within a key. An empty key
  is unconstrained, and an **entirely empty `match` is a deliberate catch-all** —
  that is how you say "everything else in 90 days" as the last rule.
- Each rule's `name` is required and must be unique within the record. It is
  recorded on every finding the clause dates (as `sla_source`), so an operator
  can always see *which* clause put the date there.

| `match` key | Matches |
|---|---|
| `severity` | The finding's severity, exact, case-insensitive. |
| `finding_class` | The finding's class (`misconfig`, `vulnerability`, `toxic_combination`, …), exact, case-insensitive. |
| `rule` | The **detecting** rule's id, matched exactly — e.g. `public-data-store`. A misspelled id silently matches nothing, so copy it from a real finding (`limacharlie cloudsec finding get <id>`) rather than typing it. |
| `account` | The finding's account, with the shared [glob dialect](configuration.md#glob-syntax) including leading-`!` negation. |
| `owner` | The **assigned** owner, same glob dialect. |

!!! note "An owner rule never claims the untriaged backlog"
    An unassigned finding has an empty owner, and no glob matches an empty
    value — so an `owner`-scoped rule silently skips everything nobody has picked
    up. If untriaged findings should also have a clock, write a separate
    catch-all rule for them.

### `due_days: 0` is an exemption, not "due immediately"

A matched rule with `due_days: 0` assigns **no** due date and **stops** the scan.
It does not fall through to the next rule or to `default_due_days`.

That is what lets you write "never put a clock on the sandbox" as an early rule
ahead of a broad catch-all, instead of having to express the complement as a
glob.

`due_days` is a whole number of **calendar** days, 0 to 3650. Calendar rather than
business days: business days need a per-organization holiday and region calendar
that nothing in the platform models, and half-modelling one would be worse than
the honest simple thing.

## Stored vs derived

**Stored on the finding:** `due_at` (= `first_seen` + the matched window) and
`sla_source` (the rule name that matched, or `default`). Both are recomputed on
every projection pass from the finding's current attributes, so a deadline moves
when the inputs a clause matches on move — most visibly, **assigning or
reassigning an owner** re-runs the scan and can hand the finding to a different
`owner`-scoped clause, with no policy edit involved. A severity change does the
same.

**Derived at read time, never stored:** the `sla_state`. It is always present —
a finding no clause covers reads `none`.

| State | Meaning |
|---|---|
| `breached` | Past `due_at`. |
| `due_soon` | Inside the tail of its own window (see below). |
| `on_track` | Has a due date, comfortably ahead of it. |
| `exempt` | The finding is not `open`, so the clock does not report on it. |
| `none` | No policy clause covers it, so it has no clock. |

The state is a function of the current clock, so materializing it would be wrong
the moment after it was written — nothing wakes up when a due date passes. It is
computed on every read from `due_at`, `first_seen`, and `status`.

!!! info "`due_soon` is a fraction of the window, not a fixed lead time"
    A finding reads `due_soon` in the final **quarter** of its own window, clamped
    to at least a day and at most a week.

    A flat warning window is wrong at both ends of a normal policy: under a flat
    7-day warning a 3-day `CRITICAL` would read "due soon" from the instant it was
    created and never once read as on track, while a 180-day `LOW` would get four
    days' notice on a six-month commitment.

### Due dates anchor to first-seen

The window runs from `first_seen` — when the platform first detected the
condition — not from when you wrote the policy or last looked at the worklist.
Adopting an SLA therefore tells you the truth about your existing backlog
immediately, including findings that are already past due on day one.

## Exempt, not paused

A finding that is not `open` — an accepted risk, a mitigation, a policy
suppression — is `exempt`. It **keeps** its `due_at`; the state simply does not
report on it, and it is never counted as breached.

When it returns to `open` (an acceptance expires, a suppression rule is deleted)
the **original** due date applies again, which may mean it is immediately
breached. That is deliberate: the risk was live for the whole acceptance window —
that is precisely what "accepted" means, a live risk carried on purpose — so its
age is real, and resetting the clock would launder it.

A finding that genuinely went away and came back gets a fresh clock for free:
closing removes it, so the recurrence is a new finding with a new `first_seen`.

## Breach events

When a projection pass first observes a finding past its due date it emits
`cloud_finding.sla_breached` into the organization's event stream (subject to the
[`emission` policy](configuration.md#emission-the-event-feed)) and latches the
breach, so the event fires **once per breached deadline** rather than on every
pass. A D&R rule can route it to a ticket, a page, or an escalation — see
[Automation & IaC](automation.md#escalating-an-sla-breach).

The latch is held against the *specific* `due_at` it fired for. If the deadline
later moves — a policy edit, or an owner change that hands the finding to a
different clause — the old commitment no longer exists, the finding is re-armed,
and a breach of the **new** deadline fires again. That is the intended reading:
each distinct commitment gets its own alert.

!!! warning "Granularity is the reprojection cadence, not the second"
    A breach is noticed on the next projection pass that touches your
    organization — a change-driven reprojection, or the periodic full backstop at
    worst. Do not build anything that assumes minute-accurate breach timing.

## Working the clock

In the console, the **Risks** worklist carries a sortable **Due** column showing
the relative deadline (`in 6d`, `12d ago`, `today`), toned by state, with the
exact date and the clause that set it on hover. The filter rail carries an
**SLA** facet with a count per state.

On the CLI and API, `sla` is a repeatable selector on the findings surfaces, and
`due_at` is a sort key:

```bash
# Everything past due, soonest deadline first.
limacharlie cloudsec finding list --sla breached --sort due_at

# What is about to go late in production.
limacharlie cloudsec finding list --sla due_soon --account prod-app --sort due_at

# The breach/on-track split for the whole estate.
limacharlie cloudsec finding facets --status open
```

`--sla` is repeatable (OR within the key, AND with the other filters) and takes
`breached`, `due_soon`, `on_track`, `exempt`, or `none`. It reaches
`finding list`, `finding facets`, `finding causes`, and `export findings`; the
exported CSV rows carry `due_at`, `sla_state`, and `sla_source` alongside the
usual worklist fields.

!!! note "`--sort due_at` is the one ascending sort"
    Every other sort key defaults to descending. `due_at` defaults to
    **ascending** — soonest deadline first, which is the only useful reading of a
    deadline column — and it places findings with **no** due date last rather than
    dropping them from the page.

    `--sla` and `--sort due_at` require a `limacharlie` CLI newer than 5.6.1. On
    an older CLI, pass `sla=` and `sort=due_at` on the
    [REST route](api-reference.md#reads) directly.

## Bounds

| Bound | Value |
|---|---|
| Rules per composed policy | 200 |
| `due_days` | 0 – 3650 |
| Rule name length | 128 characters |

Matching is a linear scan per finding on the projection hot path, over a set that
reaches tens of thousands of rows, so the rule count is a per-row cost multiplier.
Ten years is not an SLA; the `due_days` ceiling keeps a fat-fingered value from
producing an "on track until 4021" row that reads like a bug.

The rule count is checked twice, and the two behave differently on purpose. A
single record over the limit is **rejected** when you save it — you are there and
can read the error. Records that compose past it are **truncated** in record-name
order, keeping the rules that fit, because refusing the whole composed policy
would silently leave the previous one applied forever.
