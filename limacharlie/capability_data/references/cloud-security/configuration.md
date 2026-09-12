# Configuration Reference

Cloud Security is configured entirely through three Hive types. Anything the
console can configure, `limacharlie hive set` can configure — which makes
tenant onboarding and fleet-wide policy a script, not a UI workflow (see
[Automation & IaC](automation.md) for recipes).

| Hive | Records | Purpose |
|---|---|---|
| `cloudsec_provider` | one per cloud / IdP / SaaS / AI connection | what to collect and with which credential |
| `cloudsec_policy` | many, discriminated by `policy_type` | classification, coverage, emission, exclusions, suppression, compliance assignments, custom posture rules, remediation SLAs |
| `cloudsec_query` | one per saved query | shared saved graph queries |

!!! info "Permissions"
    `cloudsec_provider` records are gated by the dedicated
    `cloudsec_provider.get/set/del` permissions; `cloudsec_policy` and
    `cloudsec_query` follow `cloudsec.get`/`cloudsec.set`.

## cloudsec_provider

One record per provider connection. `provider_type` discriminates; each type
reads its own scope fields. The full per-provider walkthrough — including the
credential shape for each — is in [Connecting Providers](providers.md); this is
the field reference.

Common fields (all provider types):

| Field | Meaning |
|---|---|
| `provider_type` | `gcp` \| `aws` \| `azure` \| `okta` \| `entra` \| `google_workspace` \| `1password` \| `auth0` \| `cloudflare` \| `github` \| `openai` \| `anthropic` \| `limacharlie` |
| `credentials` | A `hive://secret/<name>` reference. The credential itself lives in the secret Hive — it is **not** stored inline. |
| `compliance_credentials` | Optional second `hive://secret/<name>` reference for providers with a second credential plane (today: Anthropic's compliance/analytics key). |
| `internal_domains` | Your own email domains (bare domains, no `@`) beyond the discoverable primary — human identities outside this set are classified external. |
| `sync_now` | Opaque nonce; change its value to trigger an on-demand sweep. |
| `refresh` | Periodic re-enumeration cadence as a duration string (e.g. `"6h"`); empty uses the service default of **6h**. |
| `feed_subscription` | Optional fully-qualified Pub/Sub subscription carrying a cloud change feed, for event-driven freshness between full sweeps. |

Per-provider scope fields:

| `provider_type` | Fields |
|---|---|
| `gcp` | `gcp_scope`: `projects/{id}`, `folders/{id}`, or `organizations/{id}` (optional `gcp_project`) |
| `aws` | `aws_role_arn` (the read-only role to assume), `aws_external_id`, optional `aws_regions`, optional `aws_member_role_name` — the role *name* assumed in each member account of an AWS Organization (defaults to the name in `aws_role_arn`) |
| `azure` | `azure_tenant_id`, `azure_client_id`, `azure_subscription_id` (service-principal auth) |
| `okta` | `okta_org_url` — the org base URL; the credential is an SSWS API token or an API Services app (client credentials) |
| `entra` | `entra_tenant_id`, `entra_client_id` — a standalone Entra directory connection (no Azure subscription); service-principal auth |
| `google_workspace` | `workspace_customer_id` — `my_customer` or an explicit customer id; the credential is a service-account key with domain-wide delegation plus the admin subject to impersonate |
| `1password` | `onepassword_scim_url` — the SCIM bridge URL; the credential is the SCIM bearer token |
| `auth0` | `auth0_domain` — the canonical tenant domain (`*.auth0.com`); the credential is an M2M app authorized for the Management API |
| `cloudflare` | `cloudflare_account_id` — the 32-hex account id |
| `github` | `github_org`, `github_app_id`, `github_installation_id` — a GitHub App installed on the org; the App private key is the credential |
| `openai` | optional `openai_org_id` (`org-...`); the credential is an Admin API key with `api.management.read` |
| `anthropic` | optional `anthropic_org_uuid` (required when only the compliance plane is connected); Console Admin key in `credentials`, optional compliance key in `compliance_credentials` |
| `limacharlie` | exactly one of `limacharlie_oid` (org key) or `limacharlie_uid` (user key — the MSSP fleet case) |

Use `limacharlie cloudsec provider test` to preflight a record before saving it
— see [Getting Started](getting-started.md#test-the-credential-before-saving).

## cloudsec_policy

Each record declares exactly one `policy_type` and fills the matching
sub-object.

### Rule matchers — read this first

Several policy types scope over resources with **rules**, and every rule shares
the same matcher grammar:

| Matcher | Matches |
|---|---|
| `account_contains` / `account_glob` | the resource's account (substring / glob) |
| `name_contains` / `name_glob` | the resource's name (substring / glob) |
| `resource_type` | the normalized resource type (e.g. `bucket`, `compute_instance`, `service_account`) |
| `provider` | the producing provider (`gcp`, `aws`, `okta`, …) |
| `region` | the region (globs) |
| `label` | a set of `key: value` label pairs — **all** must be present |
| `label_key_present` | a set of label keys — **all** must be present |
| `tag` | a set of tags (compute only) — **all** must be present |
| `public` | tri-state exposure (`true` / `false`) |
| `content_class` | detected sensitive-content classes on a data store (`pii`, `pci`, `phi`, `financial`) — accepted and validated, but see the caveat below |

!!! warning "Matchers within a rule are ANDed"
    A rule matches a resource only when **every populated dimension matches**.
    Within a single-valued dimension the listed patterns are OR alternatives
    (`account_glob: ["a-*", "b-*"]` matches either); set-valued dimensions
    (`label`, `tag`) require **all** entries. A **rule with no matcher matches
    nothing**, and a populated dimension that cannot be evaluated for a given
    resource **fails** the rule rather than being ignored. Separate rules in a
    list compose with OR.

    (This is a change from earlier behavior, where dimensions within a rule were
    ORed. The `store_kind` matcher has been folded into `resource_type`.)

!!! warning "`content_class` rules do not match anything yet"
    The `content_class` dimension is accepted and validated wherever it appears,
    but the content-detection pipeline that populates detected content classes on
    resources is **not live in the current release**. Until it ships, a rule
    matching on `content_class` saves cleanly and matches zero resources. Express
    sensitivity you need enforced today with the other dimensions (`name_glob`,
    `label`, `tag`, `account_glob`, …).

#### Glob syntax

Every glob dimension (`account_glob`, `name_glob`, `region`, and suppression
`account` matchers) shares one dialect:

| Pattern | Matches |
|---|---|
| `*` | any run of characters (not `/`) |
| `?` | one character (not `/`) |
| `[abc]`, `[a-z]` | a character class; `[^…]` or `[!…]` negates the class |
| `{a,b}` | alternation — `proj-{prod,staging}-*` |
| `**` | any run **including** `/` (only differs from `*` on values containing `/`) |
| `\c` | the literal character `c` |

A pattern whose **first character is `!` is a negation**: within one list the
positive patterns OR together as before, and any matching negation **vetoes**
the whole list. A list containing only negations matches everything it doesn't
exclude — `account_glob: ["!sandbox-*"]` means "every account **without** the
`sandbox-` prefix". `\!` matches a literal leading `!`. Case-insensitive
dimensions stay case-insensitive under negation.

```yaml
account_glob: ["*-prod", "!sandbox-*"]  # every -prod account except sandbox ones
region: ["!eu-*"]                        # everywhere outside the EU
```

Not every dimension is honored on every surface, and a dimension a surface does
not accept is **rejected when you save** rather than silently ignored:

| Dimension | Where it is honored |
|---|---|
| `tag` | compute resources only. Within `classification` that means the `compute` section; the dimension is also accepted on `coverage` and `exclusions`. |
| `public` | data stores **and** compute. |
| `content_class` | data stores only — and not yet populated, see the caveat above. |
| `label` / `label_key_present` | resources carrying cloud labels. Not honored on `classification.identities`. |
| `services` / `resource_types` | collection exclusions only. |
| account / name / provider matchers | every surface, including the `exclusions` emission list — which honors *only* these. |

The console's policy editors enforce this per surface and offer live value
**autocomplete** from your actual estate, plus a **Simulate** preview that shows
which resources a rule matches before you save (see
[Previewing policies](#previewing-policies)).

Assign-side fields (not matchers): `name` carries provenance and is accepted
anywhere, but the two that assign meaning are surface-bound and rejected at save
elsewhere — `classes` (the classes a rule assigns) is accepted on
`classification` **data-store** rules only, and `tier`
(`critical`/`high`/`medium`/`low`) on `classification` rules only.

### `classification` — crown jewels

Declares which resources are sensitive (nothing is sensitive by default). Rules
match resources and assign classes and/or a criticality tier, in three sections
— `data_stores`, `compute`, `identities`:

```json
{
  "policy_type": "classification",
  "classification": {
    "data_stores": [
      {"name_contains": ["customer", "pii"], "classes": ["pii"]},
      {"content_class": ["pci"], "classes": ["pci"]}
    ],
    "compute": [
      {"label": {"tier": "crown-jewel"}, "tier": "critical"}
    ]
  }
}
```

Content-based sensitivity is expressed with `content_class` rules: detected
content classes (`pii`, `pci`, `phi`, `financial`) become facts on a data store,
and a `content_class` rule is what turns such a detection into a sensitivity
claim. Your explicit policy always remains authoritative.

!!! warning "Content detection is not live yet"
    `content_class` rules are accepted and validated today, but the pipeline
    that populates detected content classes on resources has **not shipped in
    the current release** — so the second rule in the example above currently
    matches nothing. Classify by name, label, or tag for sensitivity you need
    enforced now, and treat `content_class` rules as forward-looking.

!!! note "auto_classify has been removed"
    Earlier versions accepted an `auto_classify: true` boolean. It is gone, and
    a record that still carries it is now **rejected at save** with an unknown-
    field error rather than being ignored. Remove `auto_classify` from any
    existing record before updating it. Explicit `content_class` rules are the
    replacement: the same intent, but visible in the policy and testable with
    Simulate.

### `coverage` — workload coverage expectations

Declares which **cloud workloads** are expected to run a LimaCharlie sensor,
with `required` and `exempt` resource-rule lists — the "EDR on production VMs"
expectation. An empty `required` means every compute resource is expected to be
covered; `exempt` wins.

!!! warning "Accepted and validated, but not currently evaluated"
    A `coverage`-typed record saves and validates, but **nothing evaluates it in
    the current release** — it produces no findings. Use the **CAASM coverage
    policy** instead, which is the live expected-coverage surface:

    ```bash
    limacharlie cloudsec caasm policy set --input-file coverage.json
    ```

    It has a different shape (`{expect: [{label, capability, kinds}]}`) and is
    evaluated over the merged asset inventory, where a `cloud_instance` kind
    covers cloud workloads as well as third-party assets — so the "EDR expected
    on production VMs" expectation belongs there today. See
    [CAASM](caasm.md#declare-expected-coverage). This `coverage` policy type is
    documented for records that already exist and for the shape it will take
    when evaluation lands; it is not synced with the CAASM policy.

### `emission` — the event feed

Controls which Cloud Security events reach the organization's event stream:

| Field | Meaning | Default |
|---|---|---|
| `resource_events` | `cloud_resource.*` inventory change events | off |
| `finding_events` | `cloud_finding.*` lifecycle events | on |
| `ops_events` | operational events — `cloudsec.sweep_failed` | off |
| `severity_floor` | drop finding events below this severity (`CRITICAL` … `INFO`); the first-sync summary still counts the whole estate | none |
| `suppress_first_sync` | emit one summary instead of a per-finding flood on the first / rebuild sweep | on |

See [Findings are events too](findings.md#findings-are-events-too) for the full
event taxonomy.

### `exclusions` — the escape hatch

The per-org escape hatch for whales and noise: the account with hundreds of
thousands of buckets, the account whose events should never reach your stream.
It has **independent rule lists**, one per surface, and a rule on one surface
has no effect on the others. At least one list must be non-empty:

| List | Effect |
|---|---|
| `collection` | Matching scopes are skipped by the collection sweep. Only this list may add the `services` and `resource_types` narrowers on top of the shared resource matchers — an account-only rule excludes the whole account, while adding `services`/`resource_types` narrows the exclusion to those collector services or resource types inside the matched scope. |
| `emission` | Matching events are dropped before delivery to the event stream. Only account/name/provider matchers are honored here — an emission rule constrained on labels or tags can never be satisfied by a lean event and so never drops one. |

!!! warning "A collection exclusion deletes the inventory it excludes"
    Collection exclusion is not just "stop collecting from here". On the next
    sweep the excluded scope is reported as *covered with zero rows*, so the
    authoritative diff **deletes the scope's existing inventory rows** (the
    resulting delete storm is kept out of the event feed). This is deliberate —
    an excluded scope disappears instead of lingering as stale rows — but it
    means excluding a scope you still want recorded loses that inventory until
    you remove the exclusion and let a sweep repopulate it.

Exclusions are captured when a sweep starts, so an edit lands on the *next*
sweep. Change the provider's `sync_now` nonce to apply it immediately instead of
waiting for the refresh cadence.

### `suppression` — finding disposition policy

Auto-dispositions matching findings — see
[Automation & IaC](automation.md#suppression-rules-finding-disposition-policy)
for semantics and a worked example. Ordered `rules`; each rule's `match` accepts
`finding_class`, `rule`, `account`, `urn_prefix`, `max_severity`; the `effect`
is `kind` (`accepted`/`false_positive`), `reason` (required), `ttl_days`.

### `compliance` — scoped assignments

A named framework assignment over a scoped subset of the estate — see
[Compliance](compliance.md#scoped-assignments). Fields: `framework_id`
(required, lowercase slug), `description`, `scope` (the account/name matchers).

### `rules` — your own posture rules

Your own CSPM detections, plus retunes of the built-in ones — see
[Custom Posture Rules](custom-rules.md) for the full contract. Two independent
lists, at least one non-empty:

| List | Entries |
|---|---|
| `rules` | Your own rules. Required per rule: `id` (must start with `custom-`), `resource_type`, `finding_class` (`misconfig` or `public_exposure`), `severity`, `title`, `detect` (a D&R detection block). Optional: `name`, `subject_path`, `criticality_mult`, `meta`. |
| `overrides` | `{rule_id, disabled?, severity?}` — retunes a built-in or custom rule for this organization only. An override that sets neither field is rejected. |

Every `detect` block is compiled on the real detection engine when you save, so a
rule that could never run is rejected while you can still read the error. Rules
use a [closed operator
allowlist](custom-rules.md#the-operator-allowlist), and per-organization bounds
apply (200 rules, 25 per resource type, 1000 overrides, 512 KiB composed).

### `sla` — remediation due dates

The organization's remediation clock: how long a finding may stay open before it
is late. See [Remediation SLAs](remediation-sla.md).

| Field | Meaning |
|---|---|
| `default_due_days` | Per-severity fallback (`CRITICAL` … `INFO`), applied when no rule matched. |
| `rules` | Ordered `{name, match, due_days}` clauses, **first match wins**. `match` accepts `severity`, `finding_class`, `rule`, `account`, `owner`; an empty `match` is a deliberate catch-all. `due_days: 0` is an **exemption** (no due date, scan stops), not "due immediately". |

There is **no default SLA**: with no `sla` record every finding reads `none` and
nothing is ever breached.

## cloudsec_query

A saved graph query, shared org-wide:

```json
{
  "version": 1,
  "name": "Exposed VMs reaching sensitive data",
  "description": "Weekly review lens",
  "query": {"text": "..."},
  "project": "rows",
  "tags": ["weekly"]
}
```

`query` takes **exactly one** of `named` (a query-pack reference), `text`, or
`ast` (the raw DSL) — setting none or more than one is rejected. The other
fields draw on closed sets: `version` accepts `0` (unset) or `1`, both meaning
the shape documented here; `project` is `rows` (table) or `graph` (canvas),
defaulting to `rows`; the optional `ui` hint takes `view` (`table` or `graph`)
and `columns`. The query appears in the
[Query console and as a pinnable lens on the Attack Surface page](graph.md#graph-queries).

### Scheduled queries — any saved query as a detection source

The `schedule` block turns a saved query into a live detection source, with no
new rule syntax:

```json
{
  "version": 1,
  "name": "Exposed VMs reaching sensitive data",
  "query": {"text": "..."},
  "schedule": {"scheduled": true, "interval": "1h"}
}
```

| Field | Meaning |
|---|---|
| `scheduled` | Activates evaluation. The record must also be **enabled** — a disabled record is never a live detection source. |
| `interval` | Cadence as a Go duration (`"1h"`, `"24h"`); minimum **5m**. |
| `cron` | A 5-field cron expression, with optional `timezone` (IANA name). |
| `emit_suppressed` | Emit matches for anchors your `suppression` policy suppressed. Default `false` (suppressed anchors stay silent). Only meaningful with `scheduled: true`. |

Set **at most one** of `interval` or `cron`. With neither, the query is evaluated
after each projection cycle — the default and usually the right choice, since it
fires as soon as the estate actually changes.

Evaluation follows the same lifecycle symmetry as findings: `cloud_query.match`
is emitted once per **new** anchor entering the match set, `cloud_query.resolved`
once per anchor leaving it — so a re-evaluation that changed nothing emits
nothing. These events flow through the same `emission` policy gate as every
other Cloud Security event.

!!! note "Two budgets protect the loop"
    An org runs at most **25** scheduled queries per pass (excess is skipped in
    deterministic query-name order, not silently dropped). A single query whose
    match set exceeds **1,000** anchors is *over budget*: it emits one
    `cloud_query.overbudget` instead of a match flood, and per-anchor tracking
    pauses until it comes back under the cap. Scope a scheduled query so its
    result set is a worklist, not a table dump.

The `detection` block is still **reserved**: it is validated for shape so
infrastructure-as-code written today keeps working, but nothing consumes it yet.

## Previewing policies

Two read-only, `cloudsec.get`-gated aids make policy authoring safe — both are
in the console policy editors, on the API, and on the CLI
(`limacharlie cloudsec simulate` / `limacharlie cloudsec policy`):

- **Simulate** evaluates an in-progress matcher against your real data before you
  save. A resource matcher (classification / coverage / exclusions) is previewed
  against stored inventory; a suppression matcher is previewed against open
  findings. The result is a match count plus a bounded sample.
- **Vocabulary & autocomplete** feed the editors the closed vocabularies
  (resource types, providers, tiers, content classes) and live value suggestions
  drawn from your estate's actual accounts and names.

See the [API Reference](api-reference.md#policy-authoring-simulate-vocabulary)
for the underlying routes.
