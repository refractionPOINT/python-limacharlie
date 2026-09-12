# Cloud Security: API, Infrastructure-as-Code, and Case Automation

This page is the operator reference for automating LimaCharlie Cloud Security: the
public REST API surface, the Hive records that ARE the Infrastructure-as-Code
surface (providers, policies, saved queries), and the D&R recipes that close the
loop between cloud findings and Cases.

## The REST API

All Cloud Security routes live under `https://api.limacharlie.io/v1/cloudsec/{oid}/…`
and appear in the public OpenAPI spec at
[`/openapi`](https://api.limacharlie.io/openapi). Reads require the `cloudsec.get`
permission, finding-triage writes require `cloudsec.set`, and every route requires
the organization to be subscribed to the `ext-cloud-security` extension (a `403`
tells you to subscribe).

The read surface includes: `findings` (risk-ranked worklist with keyset pagination
and server-side filters), `findings/facets`, `findings/classes` (the canonical
finding-class enum), `findings/causes` (findings grouped by the object whose single
edit fixes them), `attack-paths` (with the same filter selectors), `chokepoints`
(incl. the principal-exposure metrics), `ciem/public-access`, `ciem/facets`,
`ciem/identities` (the filtered, paginated Access list), `ciem/identity` (the
Identity 360 view of one principal, `?urn=`), `inventory` (+`inventory/facets`),
`data-security/facets` (+`data-security/stores`), `topology` (server-side estate
aggregates), `compliance` (+`compliance/frameworks`,
`compliance/assignments`), `policy/vocabulary` (the
classification-policy vocabulary), `providers/manifest` (what a provider collects),
`caasm/assets`, `caasm/coverage`, `caasm/policy`, `overview` (incl. the per-tenant
`usage` metering block), `risk-trend`, `changes`, `scan-status`, `free-tier` (the
org's free-tier standing and limits — descriptive, not a gate), `query` (the graph
DSL), and `graph/neighbors`. There is also a multi-org (no `{oid}`)
`fleet/overview` route that rolls risk up across every tenant you manage. Three
read-only preview POSTs help you author policy before you commit it —
`simulate/resources` (test a classification/coverage/exclusion matcher against
stored inventory), `simulate/findings` (test a suppression matcher against open
findings), and `policy/suggest` (live matcher-value autocomplete from the tenant
estate). See the [API Reference](../cloud-security/api-reference.md) for the full
route list and response shapes.

### CSV export

Add `?format=csv` to `findings`, `inventory`, `compliance`, or `query` to stream the
result as a CSV attachment instead of JSON. The server walks the full filtered set
itself (your filter query parameters apply; paging parameters are ignored), capped
at 100,000 rows with a trailing `#`-comment row as the truncation notice.

```bash
curl -H "Authorization: Bearer $JWT" \
  "https://api.limacharlie.io/v1/cloudsec/$OID/findings?severity=CRITICAL&severity=HIGH&format=csv" \
  -o findings.csv
```

The compliance CSV carries one row per control including the proving finding ids —
the auditor-facing evidence export.

## Hive is the IaC surface

Cloud Security is configured entirely through Hive records. Anything you can click
in the console you can `limacharlie hive set` — which makes tenant onboarding and
multi-tenant policy management a script, not a UI workflow.

| Hive | Record | Purpose |
|---|---|---|
| `cloudsec_provider` | one per connection | what to collect — one of thirteen connectors spanning cloud infra, identity/IdP, SaaS, AI, and LimaCharlie self-inventory (see [Providers](../cloud-security/providers.md) for the full list) |
| `cloudsec_policy` | many, typed by `policy_type` | `classification` (crown jewels), `coverage` (EDR expectation — accepted but not yet evaluated; see the [Configuration reference](../cloud-security/configuration.md)), `emission` (event feed), `exclusions` (resource escape hatch), `suppression` (finding disposition rules), `compliance` (scoped framework assignment), [`rules`](../cloud-security/custom-rules.md) (your own posture detections, plus overrides of the built-in ones), [`sla`](../cloud-security/remediation-sla.md) (remediation due dates) |
| `cloudsec_query` | one per saved query | org-shared saved graph queries (the Query Console library) |

!!! note "`limacharlie sync` does not cover these hives"
    The `cloudsec_*` hives are outside the set `limacharlie sync` walks, so a
    config pull/push will not round-trip them. Manage them with explicit
    `limacharlie hive set` / `hive get` calls — the loops below are the pattern.

### Onboarding a tenant (recipe)

```bash
# 1. Subscribe the org to the extension (billing/enable gate).
limacharlie extension subscribe --name ext-cloud-security --oid $OID

# 2. Connect a provider.
cat > provider.json <<EOF
{
  "provider_type": "gcp",
  "gcp_scope": "organizations/123456789",
  "credentials": "hive://secret/gcp-collector-sa",
  "internal_domains": ["acme.com"],
  "sync_now": "onboard-1"
}
EOF
limacharlie hive set --hive-name cloudsec_provider --key ${ORG_CODE}-gcp \
  --oid $OID --input-file provider.json --enabled

# 3. Declare the crown jewels (nothing is sensitive without a policy).
cat > classification.json <<EOF
{
  "policy_type": "classification",
  "classification": {
    "data_stores": [
      {"name_contains": ["customer", "pii"], "classes": ["pii"]}
    ]
  }
}
EOF
limacharlie hive set --hive-name cloudsec_policy --key classification \
  --oid $OID --input-file classification.json --enabled
```

### Multi-tenant policy push (recipe)

The same records applied to N organizations is the MSSP fleet-policy story:

```bash
for OID in $(cat tenant-oids.txt); do
  limacharlie hive set --hive-name cloudsec_policy --key classification \
    --oid "$OID" --input-file classification.json --enabled
done
```

### Suppression rules (finding disposition policy)

A `suppression`-typed `cloudsec_policy` record dispositions matching findings
automatically — the "accept this known risk in the sandbox for 90 days" mechanic.
An operator's own disposition always wins, deleting a rule releases exactly its own
findings on the next cycle, and criticals are never auto-suppressed unless a rule's
`max_severity` says `critical` explicitly.

`match` takes four selectors — OR within a selector, AND across them:
`finding_class` (the class enum), `rule` (exact rule ids), `account` (shell globs,
including leading-`!` negation — `"!prod-*"` scopes to every account that is *not*
production), and `urn_prefix` (resource-URN prefixes), with `max_severity` as the
inclusive ceiling.
The record is validated on write and rejected unless every rule has a unique
non-empty `name` (it becomes the disposition actor, `policy:<name>`), at least one
of those four match keys with no empty entries, a well-formed account glob, a
`max_severity` from the severity enum, an `effect.kind` of `accepted` or
`false_positive` — `mitigated` is not a policy's call to make — and a non-empty
`effect.reason`, since an unexplained auto-disposition is unauditable. Rules are
ordered and first match wins.

```json
{
  "policy_type": "suppression",
  "suppression": {
    "rules": [{
      "name": "sandbox-key-age",
      "match": {
        "rule": ["stale-user-managed-sa-key"],
        "account": ["proj-sandbox-*"],
        "max_severity": "high"
      },
      "effect": {
        "kind": "accepted",
        "reason": "sandbox accepted risk (SEC-123)",
        "ttl_days": 90
      }
    }]
  }
}
```

### Saved queries

```json
{
  "version": 1,
  "name": "Exposed VMs reaching sensitive data",
  "query": {"text": "MATCH (t:ComputeInstance {is_sensitive:true})<-[:can_reach]-(s:ComputeInstance) RETURN s, t"},
  "project": "rows",
  "tags": ["weekly"]
}
```

Save it as a `cloudsec_query` record and it appears in every teammate's Query
Console and as a pinnable lens on the Attack Surface page's lens rail.

The `schedule` block is **active**: a record with `schedule.scheduled: true` is
evaluated after each projection cycle — or on an optional cadence, one of
`interval` (a duration of at least `5m`) or `cron` (standard 5-field) — and emits
`cloud_query.match` / `cloud_query.resolved` as anchors enter and leave its
match-set. A scheduled query must be an enabled record, since a disabled one has to
stay inert. Anchors already suppressed by the org's suppression policy do not emit
unless the schedule sets `emit_suppressed`. The `detection` block is still
reserved: it is shape-checked on write, so IaC written today survives the
promote-to-detection phase, but nothing consumes it yet.

## Findings ↔ Cases automation

Cloud findings emit lifecycle events into the organization's own event stream via
the internally-provisioned `cloudsec` webhook adapter: `cloud_finding.created`
(carries the full finding under `finding`), `cloud_finding.closed`
(`{finding_id, fingerprint, finding_class}`), and `cloud_finding.still_open`
(re-asserted at most once per day for open findings with a linked ticket, carrying
that `ticket` in the payload). D&R rules match these like any event; the Cases
extension actions close the loop.
For richer automation the same stream also carries `cloud_finding.updated` (an
open finding materially changed: a severity move in either direction, the
subject becoming internet-reachable, or one of its CVEs entering CISA KEV)
and the disposition verbs `cloud_finding.resolved` / `.dismissed` /
`.reopened` / `.assigned`, plus `cloud_finding.sla_breached` when a finding
passes the due date an [`sla` policy](../cloud-security/remediation-sla.md)
assigned it. The four disposition verbs cover both human triage and a
`suppression` policy acting on its own: read `actor` to tell them apart (a user id
versus `policy:<rule name>`), and branch on the payload's `resolution` rather than
the verb, since an accepted risk and a fixed one both arrive as `.resolved`.

The console installs these three rules with one click (Settings → Cloud Security →
Cases, an opt-in), or write them yourself:

**Auto-case on high/critical findings** (async, grouped, storm-safe — one case per
rule category per window, and first-sync floods are summarized upstream):

```yaml
detect:
  event: cloud_finding.created
  op: in
  path: event/finding/severity
  values: [CRITICAL, HIGH]
respond:
  - action: extension request
    extension name: ext-cases
    extension action: ingest_detection
    extension request:
      detect_id: "{{ .event.finding.fingerprint }}"
      cat: "cloudsec:{{ .event.finding.rule_id }}"
      source: cloudsec
      detect: "{{ .event.finding }}"
```

**Resolve the case when the sweep confirms the fix:**

```yaml
detect:
  event: cloud_finding.closed
  op: exists
  path: event/fingerprint
respond:
  - action: extension request
    extension name: ext-cases
    extension action: update_case
    extension request:
      detect_id: "{{ .event.fingerprint }}"
      status: resolved
      note: "Finding closed: condition no longer detected by sweep"
```

**Reopen a case that was closed while the cloud wasn't actually fixed:**

```yaml
detect:
  event: cloud_finding.still_open
  op: exists
  path: event/fingerprint
respond:
  - action: extension request
    extension name: ext-cases
    extension action: update_case
    extension request:
      detect_id: "{{ .event.fingerprint }}"
      reopen_if_closed: true
      note: "Linked cloud finding is still open — verified by latest sweep"
```

`update_case` resolves the case through the detection index (`detect_id` = the
finding fingerprint), so the rules never need a case number; a finding with no
linked case is a no-op. Cases never close findings — findings are detection truth
and close when the sweep confirms the fix (or via operator/policy disposition).

**Non-Cases shops:** route the same `cloud_finding.*` events to Jira/ServiceNow via
an Output on the `cloudsec` adapter's stream and key your tickets on `fingerprint`
the same way.
