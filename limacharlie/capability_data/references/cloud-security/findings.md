# Findings & Triage

Everything Cloud Security detects lands in one place: a merged, risk-ranked
findings worklist. CSPM misconfigurations, graph-derived attack paths, and
identity (CIEM) risks are all findings with the same shape, the same triage
verbs, and the same automation events.

!!! info "In the console it's called **Risks**"
    The worklist is the **Risks** page. Lens tabs slice it without losing the
    unified ranking: *All risks*, *Public exposure & misconfig*, *Identity*,
    *Vulnerabilities*, and *Data*. Everything below is the same
    data through the CLI/API.

## The worklist

Findings are ordered by `lc_risk` — a 0–1000 composite built from the severity
of the condition and the exploit intelligence around it, amplified by how much
the affected resource matters:

- a **severity** base term, plus an **EPSS** term (the exploit-probability of
  the finding's CVEs) and a **KEV** term (a bonus when a CVE is on CISA's Known
  Exploited Vulnerabilities list);
- multiplied by the **criticality** of the affected resource — the tier your
  [`classification` policy](configuration.md#classification-crown-jewels)
  assigned it (nothing is critical by default);
- multiplied by a **blast-radius** factor taken from the graph: how many
  sensitive nodes are reachable from the affected resource.

Every finding carries a `risk_breakdown` that decomposes its score into those
terms, so a position in the worklist is always explainable rather than an
opaque number.

!!! note "Runtime state never moves the score"
    `lc_risk` is a property of the condition and of the resource's importance.
    Whether a LimaCharlie sensor happens to be running on the affected asset is
    context (`runtime_sids`) and can drive its own coverage findings, but it
    never raises or lowers `lc_risk`.

Each finding carries:

- `finding_id` (stable, prefixed `fnd_`) and `fingerprint` — the identity of
  the *condition*; the same misconfiguration on the same resource keeps the
  same fingerprint across sweeps.
- `finding_class` — one of `toxic_combination`, `public_exposure`,
  `ciem_risk`, `privilege_escalation`, `vulnerability`, `misconfig`,
  `malware`, `secret`, `scan_finding`, `coverage_gap`, `device_posture`,
  plus `license_risk`, `eol_runtime` and `code_weakness` (`scan_finding` is
  reserved for a capability not yet enabled). Cloud-workload coverage findings
  additionally carry `workload_coverage_gap`, which is not part of the class
  list offered by the suppression rule picker.

    `secret`, `malware`, `license_risk`, `eol_runtime` and `code_weakness`, and
    the `misconfig` findings whose rule id is an infrastructure-as-code check,
    come from [Code Scanning](code-scanning.md). Those carry a `repo` key and a
    `code` block with the file, the line range, the package and the fixed
    version where one applies — and the **Repository** filter narrows the
    worklist to one repository.
- `severity` (`CRITICAL` … `INFO`), `lc_risk`, and the `risk_breakdown`
  above.
- The affected resource (`resource_urn`, `resource_name`, `resource_type`,
  `account`, `region`), related resources, and — for path findings — the
  full `path` of hops.
- `evidence` (the offending configuration) and `remediation` (what to
  change).
- Vulnerability context where applicable: `vulns` (CVEs with fix versions),
  `epss`, `in_kev`.
- Runtime context: `runtime_sids` — the LimaCharlie sensors running on the
  affected asset, when the fusion mapping resolves any.
- Remediation clock: `due_at`, `sla_source`, and the derived `sla_state` —
  present once the organization has written an
  [`sla` policy](remediation-sla.md); absent (and `sla_state: none`) until then.

!!! tip "Your own rules land here too"
    Detections you author yourself with a
    [`rules` policy](custom-rules.md) produce ordinary findings: same worklist,
    same ranking, same triage verbs, same events. Nothing about the rest of this
    page treats them differently.

Attack-path and `toxic_combination` findings headline the durable **workload
group** rather than a single ephemeral node: a GKE/EKS/AKS node pool, a GCE
managed instance group, an AWS Auto Scaling group, or an Azure VM scale set.
The group is carried on `source_scope` / `target_scope`, so remediation reads
as one shared fix for the whole pool instead of one finding per short-lived VM.

For identity (CIEM) findings, access is scored by the **capability** a grant
confers — `data_admin` › `data_write` › `data_read` › `metadata` › `none` —
not by the mere existence of the grant. "Reaches sensitive data" gates on
`data_read`-or-higher; `metadata`/`none` grants surface as a lower-severity
reconnaissance signal, not a top data-access risk.

A grant whose effective capability cannot be resolved is `unknown`. It is not
assumed harmless: it counts as *potentially* data-capable and surfaces as
unverified access to review, but it is never treated as proven `data_read`.

List, filter, and paginate server-side:

```bash
limacharlie cloudsec finding list \
  --severity CRITICAL --severity HIGH \
  --class toxic_combination --status open \
  --kev --limit 50
```

Repeatable filters are OR within a key and AND across keys. Free-text search
is `-q`; pagination is keyset-based (`next_cursor` from one page becomes
`--cursor` for the next). `finding facets` returns the cross-filtered facet
counts that drive the console's filter rail, and `finding get <id>` returns
one finding in full.

## Dispositions

A finding is `open` until the sweep observes the condition gone (automatic
close) or an operator dispositions it:

| Kind | Meaning |
|---|---|
| `mitigated` | The risk was fixed operator-side; treated as closed. |
| `accepted` | Known and accepted, optionally until an expiry (`expires_at`, unix seconds) — after which it reopens. |
| `false_positive` | The finding was wrong. |
| `open` | Clears a previous disposition and reopens the finding (owner and ticket are kept). |

```bash
# Accept a known risk for 90 days.
limacharlie cloudsec finding resolve fnd_0a1b... --kind accepted \
  --reason "sandbox accepted risk (SEC-123)" \
  --expires-at "$(date -d '+90 days' +%s)"

# Reopen it.
limacharlie cloudsec finding resolve fnd_0a1b... --kind open

# Disposition a batch at once.
limacharlie cloudsec finding bulk-resolve \
  --finding-id fnd_0a1b... --finding-id fnd_2c3d... \
  --kind false_positive --reason "scanner artifact"
```

The `bulk-resolve` route applies one disposition to many findings at once, but
it does **not** accept `open` — reopen findings one at a time with
`finding resolve <id> --kind open`. A single call takes at most **500** finding
ids; a larger batch is rejected outright rather than silently truncated, so
split long lists into chunks of 500 yourself.

In the console, the same dispositions are one-click buttons on a finding, plus
the workflow actions built on top of them:

| Button | What it does |
|---|---|
| **Mark fixed** | disposition `mitigated` |
| **Accept risk** | disposition `accepted`, with an optional re-surface expiry |
| **Mute** | disposition `false_positive` |
| **Reopen** | clears the disposition |
| **Assign owner** | sets/clears `owner` |
| **Link ticket** | sets/clears `ticket` |
| **Create case** | one-click, idempotent — opens (or updates) the linked case |
| **Create suppression rule** | opens a prefilled `suppression` policy rule |
| **Create D&R rule** | opens a prefilled detection & response rule |

Ownership and ticket linkage are separate, lighter-weight fields:

```bash
limacharlie cloudsec finding set-owner fnd_0a1b... --owner alice@acme.com
limacharlie cloudsec finding set-ticket fnd_0a1b... --ticket JIRA-1234
```

Dispositions can also be applied *as policy* — a `suppression`-typed
`cloudsec_policy` record auto-dispositions matching findings (see
[Automation & IaC](automation.md#suppression-rules-finding-disposition-policy)).
An operator's explicit disposition always wins over policy.

!!! info "Permissions"
    Reading findings requires `cloudsec.get`; every disposition, owner,
    ticket, and chokepoint write requires `cloudsec.set`.

## Due dates

With an [`sla` policy](remediation-sla.md) written, every covered finding carries
a `due_at` and a derived state — `breached`, `due_soon`, `on_track`, `exempt`, or
`none` — so the worklist can be worked by deadline as well as by risk:

```bash
limacharlie cloudsec finding list --sla breached --sort due_at
```

In the console the **Risks** table gains a sortable **Due** column and the filter
rail an **SLA** facet. There is no default SLA: with no policy record every
finding reads `none`.

## Chokepoints — fix one thing

Attack paths tend to share hops. The chokepoint view ranks resources by how
many distinct attack paths each one sits on, so remediation can be framed as
"fixing this one security group closes 41 of 63 paths":

```bash
limacharlie cloudsec chokepoint list
```

A chokepoint that is understood and tolerated (e.g. a bastion by design) can
be dismissed from the risk overview — and restored later:

```bash
limacharlie cloudsec chokepoint dismiss "lcrn:..." --reason "bastion by design"
limacharlie cloudsec chokepoint restore "lcrn:..."
```

## Overview, changes, and trend

Three read endpoints power the at-a-glance layer:

```bash
# Score, severity distribution, top paths, coverage, trend — one call.
limacharlie cloudsec overview --trend-days 90

# The created/closed feed, newest first.
limacharlie cloudsec changes --limit 100

# The risk-score history on its own.
limacharlie cloudsec risk-trend --trend-days 90
```

## Findings are events too

Every lifecycle transition emits an event into the organization's event
stream, so D&R rules, Outputs, and the Cases loop consume findings like any
other telemetry. Two families:

**Detection-truth lifecycle** (emitted by the projector as the sweep observes
the world):

- `cloud_finding.created` — a new finding; the full finding object rides under
  `event/finding` (including `runtime_sids`).
- `cloud_finding.updated` — the content of an already-open finding materially
  changed. "Material" is a deliberately short list, so the event does not
  re-fire on every sweep: the **severity** moved (in either direction), the
  finding became **reachable** (not reachable → reachable), or one of its CVEs
  entered **KEV** (not in KEV → in KEV). The payload names the `changed`
  fields, `old_severity`/`new_severity`, and carries the current `finding`.
- `cloud_finding.closed` — the condition is gone; `{finding_id, fingerprint,
  finding_class}`.
- `cloud_finding.still_open` — re-asserted at most once per day for open
  findings that carry a linked ticket, the heartbeat that keeps a Case honest
  when the cloud was never actually fixed.
- `cloud_finding.sla_breached` — emitted once, on the first projection pass that
  observes an open finding past the `due_at` its
  [`sla` policy](remediation-sla.md) assigned. Never re-fired for the same
  breach of the same deadline.

**Operator-disposition verbs** (flat payload
`{finding_id, fingerprint, finding_class, actor, status, resolution, note?}`):
`cloud_finding.resolved`, `cloud_finding.dismissed`, `cloud_finding.reopened`,
`cloud_finding.assigned`. `status` is the finding's new status and `resolution`
the disposition kind that produced it — note that **both `mitigated` and
`accepted` emit `cloud_finding.resolved`**, and `resolution` is what tells them
apart. Key on `resolution` (not on the verb) if "fixed" and "accepted" should
drive different automation.

These verbs are not exclusively human: when a `suppression` policy
auto-dispositions a finding it emits the same events, with `actor` set to
`policy:<rule-name>` — and plain `policy` on the `reopened` event when a rule
is removed or stops matching and releases its findings. Policy and human
triage are therefore auditable through one stream, and the `actor` field is
how you separate them.

**Summary:** on the first-ever projection (or a rebuild) the platform emits a
single `cloudsec.sync_completed` (`{total, by_class, by_severity}`) instead of
a per-finding `created` flood — first-sync suppression.

!!! warning "The event feed is best-effort"
    Emission is at-most-once: events queue in a bounded buffer and the oldest
    batch is dropped under sustained pressure rather than stalling the sweep.
    Use the feed to *drive* automation, but treat the read API
    (`finding list` / `finding get`) as the authoritative state of a finding —
    it is not a replayable ledger of every transition.

See [Automation & IaC](automation.md#findings-cases-automation) for the
ready-made Cases loop that keys on `fingerprint`, and the
[`emission` policy](configuration.md#emission-the-event-feed) for the feed
controls (severity floor, which families are on).
