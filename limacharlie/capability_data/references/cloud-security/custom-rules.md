# Custom Posture Rules

The built-in CSPM pack is not the ceiling. A `rules`-typed
[`cloudsec_policy`](configuration.md#cloudsec_policy) record lets an organization
author its **own** posture detections — and retune, re-severity, or switch off the
built-in ones — in exactly the same format the built-in pack uses.

There is no separate rule language to learn: a posture rule is a **real D&R
detection**, in the same `op` / `path` / `value` dictionary vocabulary as the
detection & response rules you already write, evaluated against a cloud resource
presented as a `cloud_resource.<ResourceType>` event whose body is the resource's
normalized properties.

!!! info "Authored as Hive records"
    Unlike classification, coverage, exclusions, and suppression, custom rules
    have **no console editor**. They are written as Hive JSON through
    `limacharlie hive set` (or the Hive API), which also makes them the easiest
    policy to keep in a git repository and push to a fleet — see
    [Automation & IaC](automation.md#custom-posture-rules).

## A first rule

```json
{
  "policy_type": "rules",
  "rules": {
    "rules": [
      {
        "id": "custom-public-bucket-outside-cdn",
        "name": "Public bucket outside the CDN convention",
        "resource_type": "DataStore",
        "finding_class": "public_exposure",
        "severity": "HIGH",
        "title": "Storage bucket is readable by anyone on the internet",
        "detect": {
          "op": "and",
          "rules": [
            {"op": "is", "path": "event/store_kind", "value": "bucket"},
            {"op": "is", "path": "event/is_public", "value": true},
            {"op": "starts with", "path": "event/name", "value": "cdn-", "not": true}
          ]
        },
        "meta": {
          "description": "A bucket granting read access to anyone, outside the cdn- naming convention used for deliberately public assets.",
          "rationale": "Anonymous read on a bucket exposes every object in it, and our public assets are all published under the cdn- prefix.",
          "references": ["https://cloud.google.com/storage/docs/access-control/making-data-public"],
          "false_positives": "A newly created public asset bucket that has not been renamed to the cdn- convention yet."
        }
      }
    ]
  }
}
```

```bash
limacharlie hive set --hive-name cloudsec_policy --key my-rules \
  --oid $OID --input-file rules.json --enabled
```

The record is validated **synchronously**. The Hive compiles every `detect` block
on the real detection engine and checks every vocabulary, so a rule that could
never run is rejected while you are still looking at the error — never accepted
and then silently skipped hours later inside a projection you cannot see.

An organization may hold **many** `rules` records; they compose into one policy in
record-name order.

## The record

`rules` is an object with two independent lists, `rules` (your own detections) and
`overrides` (retunes of rules that already exist). At least one must be non-empty
— a record that adds nothing and overrides nothing is rejected rather than saved
as a no-op.

### Rule fields

| Field | Required | Meaning |
|---|---|---|
| `id` | ✔ | Stable identifier, kebab-case, **must start with `custom-`**, max 64 characters. Never rename it — see [Rule ids are permanent](#rule-ids-are-permanent). |
| `resource_type` | ✔ | Which resources the rule is evaluated against; routes it to `cloud_resource.<type>` events. |
| `finding_class` | ✔ | `misconfig` or `public_exposure` — the whole authorable set (see below). |
| `severity` | ✔ | `CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW` \| `INFO`. |
| `title` | ✔ | What the operator reads on the finding. State the **risk**, not the setting: "Bucket is readable by anyone on the internet", never "uniform bucket-level access is disabled". Max 256 characters. |
| `detect` | ✔ | The detection block (see [Writing the detection](#writing-the-detection)). |
| `name` | | A short internal label, for your own bookkeeping. |
| `subject_path` | | A **top-level property key** — a single lookup, *not* a detection path — used as the finding's subject instead of the resource URN. `email`, never `event/email`. Max 256 characters. |
| `criticality_mult` | | Risk multiplier applied to `lc_risk`, `0` to `1.6`. `0` means unset (1.0). |
| `meta` | | Authoring metadata: `description`, `rationale`, `references`, `no_framework`, `false_positives`. Inert at evaluation time — it exists so the reasoning travels with the rule. |

`resource_type` must be one of:

`Account` · `AIService` · `Application` · `ComputeInstance` · `ConfigStore` ·
`DataStore` · `DNSZone` · `EnrollmentKey` · `HasPermission` · `Identity` ·
`Network` · `TelemetryOutput`

!!! note "Only two finding classes, on purpose"
    A custom rule may emit `misconfig` or `public_exposure` and nothing else. The
    other classes in the [finding-class
    enum](findings.md#the-worklist) are produced by other engines and carry
    lifecycle behavior a single-resource rule cannot honor: `vulnerability`,
    `malware`, `secret`, and `scan_finding` are asserted by scanners;
    `ciem_risk`, `privilege_escalation`, and `toxic_combination` come from grant
    expansion and attack paths; the coverage-gap classes drive their own
    carry-forward semantics. A finding in one of those classes is read by
    consumers that assume an evidence source a posture rule does not have.

    ```text
    rule 0 ("custom-critical-vuln"): finding_class "vulnerability" is invalid
    (want one of misconfig, public_exposure)
    ```

## Rule ids are permanent

**Once a rule has produced findings, its id is never renamed.** The id is
load-bearing in two places:

- **The finding fingerprint.** A finding's dedup key is derived from the rule id
  and the resources it names. Rename the id and every finding the rule ever
  produced closes and a brand-new one opens: a create/close storm through the
  `cloud_finding.*` feed, every operator disposition (accepted / false positive)
  orphaned, and every linked ticket pointing at a dead finding.
- **The compliance join.** Framework catalogs map controls to rules **by id**.

The corollary is worth internalising: **severity is safe to change, detection is
not.** Severity is not a fingerprint input, so retuning it updates findings in
place. Changing what a rule *detects* while keeping its id re-purposes every
historical finding underneath it — if you need different semantics, ship a new id
and retire the old one.

### Why `custom-`

Every customer-authored id must start with `custom-`, enforced at write time and
again when the pack is resolved:

```text
rule 0: id "public-bucket" must start with "custom-" — custom rule ids share the
finding fingerprint space and the compliance join with the built-in rules, so
they are namespaced to keep them from ever colliding
```

Your ids land in the same fingerprint space and the same compliance keyspace as
the built-ins, so the namespace makes a collision impossible by construction —
and it keeps the built-in id space free to grow without ever asking whether some
tenant already took a name.

## Writing the detection

`detect` is the same nested dictionary a D&R rule's `detect` block uses:
`{"op": …, "path": …, "value": …}` leaves, composed with
`{"op": "and" | "or", "rules": [ … ]}`, and negated by adding `"not": true` to
any node.

Paths are rooted at `event/`, and the event body is the resource's normalized
properties. `limacharlie cloudsec resource get "lcrn:..."` prints a real
resource, which is the fastest way to see the exact property names for a type.

!!! note "A few facets are computed at evaluation time"
    Some properties a rule can match on are derived when the rule runs rather
    than stored on the resource, so they do **not** appear in `resource get`:

    - **Network** — `covers_all_ports` (the rule's port range spans the whole
      port space) and `ports_effective` (the explicitly listed ports plus every
      well-known port a listed range contains). Both exist because a declarative
      rule cannot expand a port range itself; the firewall example below uses
      them.
    - **Identity** — `dormant`, `mfa_known` / `mfa_enabled`,
      `credential_recently_used`, and `service_linked` (an AWS service-linked
      role).
    - **HasPermission** — `effective_public_grant`: the grant really does expose
      the target to the internet, after accounting for a `deny` statement and
      for a target whose own public-access block neutralizes it. Match on this
      rather than on `public_principal`, which is only half the question.

    Everything else you can match on is a stored property, visible in
    `resource get`.

### The operator allowlist

A rule may use only these operators, anywhere in its `detect` tree:

`and` · `cidr` · `contains` · `ends with` · `exists` · `is` · `is greater than` ·
`is lower than` · `is older than` · `matches` · `or` · `scope` · `starts with`

This is a **safety boundary, not a curated convenience list**. The detection
engine is shared with the endpoint product, and most of its other operators reach
for things a cloud resource does not have — sensor platform, tags, process trees,
or a service resolved through callbacks the posture evaluator does not supply.
Anything outside the list is rejected at write time:

```text
rule 0 ("custom-tagged-prod"): detect uses operator(s) is tagged, which a posture
rule may not use (allowed: and, cidr, contains, ends with, exists, is, is greater
than, is lower than, is older than, matches, or, scope, starts with)
```

`is tagged` is excluded even though it is harmless, because it reads *sensor*
tags a cloud resource never has: it would install cleanly and never match, which
is worse than being told no.

### Value syntaxes and paths that are rejected

| Rejected | Why |
|---|---|
| `[[name]]` in any `value` | A sensor-variable reference. It resolves through a callback the posture evaluator does not supply — a cloud resource has no sensor variables. Use a literal value or an `event/` path. |
| `{{ … }}` in any `value` | Templates can carry a pattern the regex budgets cannot see. Their only extra capability here is `secret`, which the posture evaluator does not supply either. |
| `*` or `?` in a `path` | A wildcard makes the engine walk the resource's **entire** property tree for every row, so the cost is set by your data rather than by the rule (measured at 187× a literal path). Name the field explicitly. |

Path redirection (`<<event/other_field>>`) is fine — it is a pure extractor over
the same event the rule already addresses.

```text
rule 0 ("custom-any-public"): detect uses the wildcard path(s) event/*/is_public
— a wildcard makes the engine walk the resource's ENTIRE props tree for every
row, so the cost is set by the data rather than by the rule (measured at 187x a
literal path). Name the field explicitly
```

### `scope` — the trap that manufactures false positives

**Whenever two conditions must hold on the *same element* of a list, they must be
inside a `scope`.** This is the single most common way a hand-written posture
rule goes wrong.

Without `scope`, the engine flattens the list and the conditions are free to match
across *different* elements. A firewall allowing `[{udp, 22}, {tcp, 443}]` will
satisfy "protocol is tcp AND port is 22" — one condition from each element — and
report SSH open to the world on a host where it is not.

Inside a `scope`, the sub-rule's paths are **relative to the scoped element**
(`protocol`, not `event/ingress_rule/protocols/protocol`):

```json
{
  "policy_type": "rules",
  "rules": {
    "rules": [
      {
        "id": "custom-postgres-open-to-internet",
        "resource_type": "Network",
        "finding_class": "public_exposure",
        "severity": "CRITICAL",
        "title": "PostgreSQL (5432) is reachable from the entire internet",
        "detect": {
          "op": "and",
          "rules": [
            {"op": "or", "rules": [
              {"op": "is", "path": "event/network_kind", "value": "firewall_rule"},
              {"op": "is", "path": "event/network_kind", "value": "aws_security_group"},
              {"op": "is", "path": "event/network_kind", "value": "azure_nsg"}
            ]},
            {"op": "is", "path": "event/ingress_rule/allow", "value": true},
            {"op": "is", "path": "event/ingress_rule/disabled", "value": true, "not": true},
            {"op": "or", "rules": [
              {"op": "is", "path": "event/ingress_rule/source_cidrs/v", "value": "0.0.0.0/0"},
              {"op": "is", "path": "event/ingress_rule/source_cidrs/v", "value": "::/0"}
            ]},
            {"op": "scope", "path": "event/ingress_rule/protocols", "rule": {
              "op": "and",
              "rules": [
                {"op": "or", "rules": [
                  {"op": "is", "path": "protocol", "value": "tcp"},
                  {"op": "is", "path": "protocol", "value": "all"}
                ]},
                {"op": "or", "rules": [
                  {"op": "exists", "path": "ports", "not": true},
                  {"op": "is", "path": "covers_all_ports", "value": true},
                  {"op": "is", "path": "ports_effective/v", "value": "5432"}
                ]}
              ]
            }}
          ]
        }
      }
    ]
  }
}
```

Two related path rules the example above also demonstrates:

- **Lists of scalars are addressed through `/v`.** The resource→event adapter
  reshapes arrays of plain values into arrays of objects, so a list of CIDRs is
  matched as `event/ingress_rule/source_cidrs/v`.
- **Absence is not a value.** `{"op": "exists", "path": "ports", "not": true}` is
  how you match "no ports listed" — and in the firewall family that absence means
  *all* ports, the worst case, not a benign default.

### Never fire on silence

**A rule must assert on an observed bad state, never on the absence of a fact.**

The collectors use observation-gated properties: a boolean is absent when the
collector could not determine it, and only an explicit value is stamped. A rule
written as "encryption disabled" against a field that is merely *missing* fires
on every resource the collector could not fully inspect — and a partial sweep
then reads as an estate-wide breach. If a rule genuinely means "this setting is
missing", pair it with a positive signal that the resource *was* successfully
inspected.

### Two more write-time checks worth knowing

`subject_path` is a top-level property key resolved by a single lookup, not a
detection path — writing it in `event/…` form is rejected rather than silently
resolving to nothing:

```text
rule 0 ("custom-public-bucket"): subject_path "event/name" looks like a detection
path, but it is a top-level props key (a single map lookup) — it would resolve to
nothing and the finding would silently fall back to the resource urn
```

And an override that changes nothing is rejected, because the failure mode is an
operator walking away believing they turned a rule off:

```text
override 0 ("bucket-uniform-access-disabled") does nothing: set disabled=true or
a severity
```

## Overriding a built-in

An `overrides` entry retunes a rule that already exists — built-in or one of your
own — **for your organization only**:

```json
{
  "policy_type": "rules",
  "rules": {
    "overrides": [
      {"rule_id": "bucket-uniform-access-disabled", "disabled": true},
      {"rule_id": "open-admin-port-to-internet", "severity": "CRITICAL"}
    ]
  }
}
```

An override can set `disabled` and/or `severity`. It deliberately **cannot**
change a rule's detection, resource type, or finding class: those decide what a
finding *means*, and redefining a built-in while keeping its id would corrupt the
compliance join — a control pointing at that id would be evidenced by a detection
the framework never asked for.

To change what a rule detects, author a `custom-` rule and disable the built-in in
the same record:

```json
{
  "policy_type": "rules",
  "rules": {
    "rules": [
      {
        "id": "custom-sa-key-older-than-30d",
        "resource_type": "Identity",
        "finding_class": "misconfig",
        "severity": "HIGH",
        "title": "Service-account credential has not been rotated in 30 days",
        "subject_path": "email",
        "criticality_mult": 1.2,
        "detect": {
          "op": "and",
          "rules": [
            {"op": "or", "rules": [
              {"op": "is", "path": "event/kind", "value": "service_account"},
              {"op": "is", "path": "event/kind", "value": "app_integration"}
            ]},
            {"op": "is greater than", "path": "event/oldest_key_age_days", "value": 30}
          ]
        },
        "meta": {
          "rationale": "Our key-rotation standard is 30 days; the built-in rule only fires at 90."
        }
      }
    ],
    "overrides": [
      {"rule_id": "stale-user-managed-sa-key", "disabled": true}
    ]
  }
}
```

### Precedence, exactly

1. The built-in pack is the base.
2. Valid custom rules are appended. An invalid one is dropped and reported.
3. A duplicate custom id, or one shadowing a built-in, is dropped and reported —
   **first wins**, deterministic because records compose in sorted record-name
   order.
4. Overrides apply **last**, over the union, so they can retune a built-in or a
   custom rule. **Disable wins over severity.**
5. An override naming an id that is not in the pack is dropped and **reported** —
   a typo must never read as a successfully-disabled rule.

## How evaluation works

A saved record reaches the engine at the end of the **next collection sweep**,
and is applied on the projection after it. Change the provider's `sync_now` nonce
to a new value to trigger a sweep immediately instead of waiting for the refresh
cadence.

Once it is there, evaluation is **stateless and per resource**: each rule is
tested against every resource of its `resource_type`, on every projection pass,
using only that resource's own properties. Two consequences matter in practice:

- **A new rule applies to your whole existing estate**, not just to resources
  that change afterwards. Nothing has to be backfilled — the first projection
  after the policy lands re-derives findings across everything already in
  inventory.
- **Findings close by themselves.** When the condition stops being true, the
  finding closes on the next pass, exactly like a built-in one.

Findings from custom rules are ordinary findings. They land in the same
risk-ranked worklist, carry `lc_risk` and its breakdown, and support the full
lifecycle: dispositions, owners, tickets, cases, `suppression` policy,
[remediation SLAs](remediation-sla.md), cause grouping, CSV export, and the
`cloud_finding.*` [event feed](findings.md#findings-are-events-too). There is no
rule-id filter on the worklist, but free-text search matches the finding body, so
`limacharlie cloudsec finding list -q custom-public-bucket-outside-cdn` pulls up
everything one rule produced.

Evidence is rendered from the **affected resource type**, using the same
renderers the built-in rules use, so a custom finding carries a real
offending-configuration detail. Rule-specific evidence wording and the
ready-to-apply remediation snippets are authored per built-in rule, so a custom
rule's findings may carry none — which is the practical reason to write the
`title` as the action an operator must take.

!!! warning "Measure a broad rule before you trust it"
    A rule that matches a quarter of its resource type is a rule that buries the
    rest of your worklist. Before relying on a new rule, count what it actually
    produced — the worklist has no rule-id facet, so search for the id with
    `limacharlie cloudsec finding list -q custom-your-rule-id`. A single
    near-universal condition can produce six-figure finding counts on a large
    estate, and past the per-pass budget below it costs you *every* custom
    finding, not just its own. If the condition is real but the *unit* is wrong
    (an account-level setting reported once per bucket), express it at the level
    it is actually fixed, or ship it at `LOW`/`INFO` so it stays out of the
    default worklist while remaining queryable.

## Compliance interaction

Disabling a rule affects compliance, and it does so **honestly**. A control whose
only evidence comes from rules you disabled is reported **`NOT_ASSESSED`** — never
a pass.

A zero-violation result from a detector that did not run means nothing, so it is
reported as what it is: not assessed. This is the same verdict the platform gives
a control no detector covers at all, and it keeps `NOT_ASSESSED` out of the
compliance score's denominator rather than inflating it into a green check. See
[Compliance](compliance.md).

The reverse direction is worth knowing before you write a broad rule. Your own
rules can never make a control **pass** — a control passes when nothing proves a
violation, and a rule only ever adds findings. They can, however, make one
**fail**: framework catalogs join controls to detections two ways, by rule id
(no catalog names a `custom-` id) and by **finding class**, scoped to the
control's resource types. `public_exposure` is a class several frameworks join
on, so a `public_exposure` rule over a resource type such a control scopes to
attaches to it as evidence and flips it to FAIL. `misconfig` is not a class-join
key in any shipped catalog, so a `misconfig` rule never moves a compliance
verdict.

## Bounds

The projector that evaluates rules is shared infrastructure, so the limits below
are availability bounds, not just per-tenant quotas.

| Bound | Value |
|---|---|
| Rules per organization | 200 |
| Rules on any **one** resource type | 25 |
| Overrides per organization | 1000 |
| Composed policy size (all `rules` records together) | 512 KiB |
| Size of one record | 256 KiB |
| `detect` size per rule | 8 KiB |
| Total `detect` budget across the organization | 64 KiB, with a rule containing a `scope` charged **10×** its size |
| `scope` operators per rule | 2, never nested |
| `detect` nesting depth | 32 |
| Compiled size of one regex (`matches` pattern) | 1000 instructions |
| Compiled regex size, summed per rule and per organization | 5000 instructions |
| Rule id / title length | 64 / 256 characters |
| `criticality_mult` | 0 – 1.6 |
| Custom findings kept in one projection pass | 25,000 per evaluator — the pass runs two, so roughly 50,000 per organization |

The 25-rules-per-resource-type bound is the one that surprises people, and it is
the one that matters most: every rule is evaluated against every row of its type
and resolves its own path independently, so per-row cost is (rules on the type) ×
(elements at the path) — a product neither the rule count nor the byte budget
bounds. Spread rules across resource types the way the built-in pack does.

!!! note "The regex bounds are program size, not pattern length"
    If you use the `matches` operator, the budget is charged against the
    **compiled program size** of the pattern, not how long the pattern is.
    Nothing about a pattern's length bounds its program: a 253-byte alternation
    compiles to 7 instructions, while a 230-byte nested-group pattern compiles to
    over 200,000. A byte limit would accept the expensive one and reject the
    cheap one, so the check counts instructions instead — which is why the number
    in a rejection message will not correspond to anything you can see by looking
    at the pattern. Flatten nested groups and large bounded repeats, or express
    the same set as an `or` of `is` / `starts with` leaves, which is far cheaper.

!!! note "Reject per record, truncate across records"
    **Within one record the Hive rejects**: you are there, you can read the
    error, and a record you cannot save is better than one that saves and
    silently never applies. **Across records the collector truncates**, keeping
    the first entries in record-name order and reporting the rest — by then
    nobody is watching, and one runaway generator must not cost you the rules
    that were fine.

    Because several records compose, an organization can exceed the per-type and
    org-wide bounds across records even though every individual record was legal.
    The excess is dropped, not applied, and reported on each sweep.

!!! info "A bad rule cannot break your posture"
    Rule resolution never fails. Every rejection comes back as data: the built-in
    pack survives intact, and a rule that will not compile — or uses an operator
    outside the allowlist — is dropped rather than left to silently never match.

    The finding budget is deliberately **all-or-nothing**: a pack that blows the
    25,000-findings-per-pass cap has *all* of its custom findings dropped for that
    pass and reported, rather than an arbitrary subset kept. The cap is reached in
    row order, which is not stable between passes, so keeping a partial set would
    churn the finding feed forever.

## What custom rules are not

- **Not cross-resource correlation.** A rule sees exactly one resource. "Public
  workload that can reach a sensitive database" is a relationship, not a
  property — that is what the [security graph](graph.md) and attack paths are
  for, and a [saved query on a schedule](configuration.md#scheduled-queries-any-saved-query-as-a-detection-source)
  turns any graph query into a detection source with no new rule syntax.
- **Not temporal.** There is no "changed in the last hour" or "seen N times":
  evaluation is a stateless function of the resource's current properties.
- **Not a new finding class.** `misconfig` and `public_exposure` are the whole
  authorable set.
- **Not a console feature.** Authoring is Hive JSON through the CLI or API.
