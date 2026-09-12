# CAASM — Cyber Asset Attack Surface Management

Your tools already know what you own: the EDR sees devices, the identity
provider sees users and their devices, MDM and scanners see more. CAASM
merges those third-party views into one entity-resolved asset inventory and
evaluates your *expected-coverage* policy over it — surfacing the assets a
required tool does **not** see. The same policy also covers your cloud
workloads, so "which of my VMs has no agent on it" is answered the same way.

## The merged asset inventory

Records from connected sources are normalized and entity-resolved into one
canonical asset per real device or person. Resolution is deterministic — a
union-find over a ladder of match keys, strongest first, with explicit ambiguity
handling instead of fuzzy scoring:

| Match key | Strength |
|---|---|
| `serial` | Strong — always links |
| `mac` | Strong — always links |
| `cloud_id` | Strong — always links |
| `hostname` | Weak — links only under the guards below |
| `email` | Strong for identities; the owner key on devices |
| `source_id` | Last resort — the asset stands alone under the reporting tool's own id |

Hostname is the key that over-merges — two laptops both called
`DESKTOP-1234` — so it links only under guards: a hostname one tool reports for
two distinct assets never links anything, and two records that *conflict* on a
stronger key (different non-empty serials or cloud ids) never merge on hostname
alone. The merged asset's identity derives from its strongest key, so which
source reported first never changes the outcome: same records in, in any order,
same assets out. The same laptop seen by the EDR, the IdP, and MDM collapses to a
single row with per-source provenance retained:

```bash
limacharlie cloudsec caasm assets -q laptop --limit 50
```

The merge is normally served from a **materialized merged view**, kept current
as records arrive; when that view is not ready for an organization the same
resolution runs **on read**, so the answer is the same either way.

Supported sources: `sentinelone`, `crowdstrike`, `defender`, `okta`,
`entraid`, `ms_graph`, `wiz`, plus two **native** sources — `limacharlie`
(your own LimaCharlie endpoint sensors, capability `edr`) and `google_workspace`
(managed devices from the Workspace directory, capability `mdm`). The native
sources feed automatically once the corresponding provider is connected — no
ingest needed. On the LimaCharlie side that means the provider's own sweep of
your sensors, and only real endpoints become assets: USP adapters and the
cloud/SaaS log-ingestion platforms are inventory noise here and are skipped.

Telemetry the organization pulls through USP adapters does **not** flow into
CAASM on its own. To feed a source that has no first-class collector, push its
records in — either as a batch, or continuously with a D&R feeder rule. Both are
in [Pushing records in](#pushing-records-in) below, and both are a deliberate
choice: nothing is auto-provisioned.

### Managed devices and device posture

Because assets are resolved per real device, CAASM can reason about **managed
device posture**. When a source positively asserts a non-compliant state on an
asset, CAASM raises a `device_posture` finding:

| Asserted state | Severity |
|---|---|
| `compromised` | High |
| `encryption` off | Medium |
| `screen_lock` off | Low |
| `developer_mode` on | Low |
| Past its auto-update expiration (no longer receives OS updates) | Medium |

Posture checks fire only on a positive assertion — an asset that simply never
reported a field is not flagged.

When a failing device's owner is a **privileged** identity — one holding admin
roles in any connected directory — that raises an *additional* HIGH
`toxic_combination` finding, anchored on the identity rather than the device, and
carrying both the admin roles and the failing checks as evidence. The
device-posture finding still stands on its own; the join adds the "compromise of
this laptop is a direct path to privileged directory access" reading rather than
swallowing either half.

The `owns_device` edge (identity → device) is what joins owners to their devices
in the [security graph](graph.md), so "who owns this at-risk laptop" is one hop
away. It is emitted only when the device's owner email resolves to an identity
already in the inventory — an owner outside your directory (a contractor's
personal account, a typo'd device annotation) never invents an identity node.

## Declare expected coverage

Coverage evaluation is a no-op until you declare expectations — a labeled
list of "assets of these kinds must be seen by a tool with this capability":

```bash
cat > coverage.json <<EOF
{
  "expect": [
    {
      "label": "edr-on-devices",
      "capability": "edr",
      "kinds": ["device"],
      "severity": "HIGH",
      "max_age_days": 30,
      "source_max_age_days": 7
    }
  ]
}
EOF

limacharlie cloudsec caasm policy set --input-file coverage.json
limacharlie cloudsec caasm policy get
```

The policy shape is `{expect: [ ... ]}`, and each expectation rule takes:

- `label` **(required)** — names the expectation; it anchors the resulting
  finding.
- `kinds` — what the rule applies to; defaults to `["device"]`. See
  [the three kinds](#the-three-kinds) below.
- `capability` **or** `sources` **(one required)** — either a required
  capability (`edr`, `idp`, `mdm`, `vuln_scanner`, or `cloud_scanner`) or an
  explicit list of source names that must see the asset.
- `severity` — severity of the gap finding; defaults to `MEDIUM`.
- `max_age_days` — an **exemption** window, not a coverage gate. An asset whose
  own last-seen is older than this (or absent) is skipped entirely: no finding
  either way. Use it to stop retired kit from sitting in the worklist forever.
- `source_max_age_days` — the actual **staleness gate on coverage**. A source
  only satisfies the expectation if *that source's* sighting of the asset falls
  inside the window, so an EDR that last saw the laptop a quarter ago is a gap,
  not coverage — even though its name is still on the asset. A sighting with no
  timestamp can never prove freshness.

With no policy set, there are **no gap findings** — coverage expectations are
entirely user-declared. The policy is validated on write; an invalid policy is
rejected loudly rather than silently ignored.

!!! warning "`vuln_scanner` has no supplying source yet"
    Of the five capabilities, `vuln_scanner` is accepted by validation but no
    connected source currently attests it. An expectation gating on it therefore
    flags every asset in scope, permanently. Declare `edr`, `idp`, `mdm`,
    `cloud_scanner`, or an explicit `sources` list instead.

### The three kinds

The three kinds span two very different populations, which is why what can
satisfy an expectation differs by kind:

| Kind | Population | Satisfied by |
|---|---|---|
| `device` | Merged third-party devices | An observation from a source with the required capability (or in `sources`) |
| `identity` | Merged third-party identities | Same |
| `cloud_instance` | Cloud compute workloads from your provider sweeps | The live sensor ↔ instance runtime join — *not* third-party observations |

`cloud_instance` is the "unprotected workload" expectation: a VM that your cloud
inventory holds but that no live sensor resolves onto. Because its only evidence
is that runtime join, the expectation must be declared with the `edr` capability
or the `limacharlie` source explicitly — anything else is rejected on write
rather than silently flagging every workload forever. Two exemptions are built
in: a workload whose provider reports it stopped, terminated, deallocated or
suspended is never flagged, and nothing is evaluated at all while the resolver is
unavailable (an outage must not read as "no agents"). The gaps land as
`workload_coverage_gap` findings, distinct from the `coverage_gap` class the
merged kinds produce.

!!! note "Related policy surfaces"
    Expected coverage is set through the CAASM policy shown above, for all three
    kinds. There is also a `coverage`-typed `cloudsec_policy` record —
    see [Configuration](configuration.md#coverage-workload-coverage-expectations)
    for its current status. The two are separate records and are not synced;
    the CAASM policy is the one the commands on this page read and write.

## Coverage gaps

Assets observed by at least one source but missing a required capability
become `coverage_gap` findings — same shape and triage verbs as every other
finding, pre-filtered here:

```bash
limacharlie cloudsec caasm coverage --status open --severity HIGH
```

"Seen by Okta, no EDR" is the canonical example: the asset exists, a human
uses it, and your endpoint tooling is blind to it.

This view is pinned to the `coverage_gap` class, so it covers the `device` and
`identity` kinds. Unprotected cloud workloads carry the separate
`workload_coverage_gap` class — filter for it in the main worklist
(`limacharlie cloudsec finding list --class workload_coverage_gap`).

## Pushing records in

For sources without a live adapter, push raw vendor-shaped records directly.
Ingestion is idempotent — re-sending identical records is a no-op:

```bash
# A batch from a file (chunk large imports; the request body caps at 1 MiB).
limacharlie cloudsec caasm ingest --source okta --records-file users.json

# A single record inline (the shape D&R-driven feeders use).
limacharlie cloudsec caasm ingest --source crowdstrike --record-json '{...}'
```

The two native sources are **not** push-ingestable: their own collector is their
single writer, so a raw push under their name is rejected rather than
mis-normalized into a phantom asset.

The response carries the reconcile counters — `received`, `normalized`,
`skipped`, `assets`, `created`, `updated`, `deleted`, plus `policy_set` (true
when the same call also rewrote the coverage policy) — so a feeder can observe
exactly what its batch changed.

### A continuous feeder

To keep a source current instead of importing it once, forward its events to the
same ingest action from a D&R rule — the way anything else in the platform is
automated (see [Automation](automation.md)):

```yaml
detect:
  event: <the adapter event that carries a user or device sighting>
  op: exists
  path: event/actor/id
respond:
  - action: extension request
    extension name: ext-cloud-security
    extension action: caasm_ingest
    extension request:
      source: okta
      record: "{{ .event }}"
    suppression:
      keys:
        - caasm-okta
        - '{{ .event.actor.id }}'
      max_count: 1
      period: 24h
```

The action takes `source` plus either one `record` or a `records` batch, and the
record is the raw vendor event — the same shape the CLI sends, which is why the
detect side just forwards `.event` untouched. Substitute the field the source
identifies its records by: for `okta` that is `actor.id` (or `id` on the users
inventory shape), for `crowdstrike` the agent id, for `ms_graph` the device id.

Ingestion is idempotent, so a re-sent record is harmless; the suppression block
is about volume, not correctness. One forward per asset per day keeps freshness
comfortably inside any sane `source_max_age_days`.

!!! info "Permissions"
    Reading assets and coverage requires `cloudsec.get`; setting the policy
    and ingesting records require `cloudsec.set`.
