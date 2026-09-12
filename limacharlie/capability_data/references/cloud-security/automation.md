# Automation & Infrastructure-as-Code

Everything Cloud Security does is scriptable: configuration is Hive records,
the query/triage surface is the [REST API](api-reference.md) and
[CLI](cli.md), and findings flow through the standard event pipeline. This
page collects the operator recipes.

## Onboarding a tenant

```bash
# 1. Subscribe the org to the extension (billing/enable gate).
limacharlie extension subscribe --name ext-cloud-security --oid $OID

# 2. Store the collector credential as a secret (hive set reads
#    record data from --input-file or piped stdin).
echo '{"secret": "<service-account-key-json>"}' | \
  limacharlie hive set --hive-name secret --key gcp-collector-sa \
    --oid $OID --enabled

# 3. Connect the provider.
cat > provider.json <<EOF
{
  "provider_type": "gcp",
  "gcp_scope": "organizations/123456789",
  "credentials": "hive://secret/gcp-collector-sa",
  "internal_domains": ["acme.com"]
}
EOF
limacharlie hive set --hive-name cloudsec_provider --key acme-gcp \
  --oid $OID --input-file provider.json --enabled

# 4. Declare the crown jewels (nothing is sensitive without a policy).
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

## Multi-tenant policy push

The same records applied to N organizations is the MSSP fleet-policy story:

```bash
for OID in $(cat tenant-oids.txt); do
  limacharlie hive set --hive-name cloudsec_policy --key classification \
    --oid "$OID" --input-file classification.json --enabled
done
```

!!! tip "Fleet-wide roll-up"
    Beyond pushing policy to N orgs, the cross-tenant fleet board rolls risk
    up across every org you manage — `limacharlie cloudsec fleet overview`
    (see the [CLI](cli.md)), the multi-org `fleet/overview` route (see the
    [API Reference](api-reference.md)), and the console's Cloud Security Fleet
    view. It's the MSSP read half of the same fleet story.

## Suppression rules (finding disposition policy)

A `suppression`-typed `cloudsec_policy` record dispositions matching
findings automatically — the "accept this known risk in the sandbox for 90
days" mechanic. An operator's own disposition always wins; deleting a rule
releases exactly its own findings on the next cycle; criticals are never
auto-suppressed unless a rule's `max_severity` says `critical` explicitly.
The `account` matcher takes globs, including leading-`!` negation —
`"account": ["!prod-*"]` scopes a rule to every account **outside** `prod-*`
(see [Glob syntax](configuration.md#glob-syntax)).

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

## Custom posture rules

Your own CSPM detections are a `rules`-typed `cloudsec_policy` record, which
makes them the easiest part of the product to keep in a git repository and push
to a fleet. The full authoring contract — the detection format, the operator
allowlist, `scope`, id stability, and the per-organization bounds — is in
[Custom Posture Rules](custom-rules.md).

```bash
cat > rules.json <<EOF
{
  "policy_type": "rules",
  "rules": {
    "rules": [
      {
        "id": "custom-public-bucket-outside-cdn",
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
        }
      }
    ],
    "overrides": [
      {"rule_id": "bucket-uniform-access-disabled", "disabled": true}
    ]
  }
}
EOF
limacharlie hive set --hive-name cloudsec_policy --key my-rules \
  --oid $OID --input-file rules.json --enabled
```

The write is validated synchronously — every `detect` block is compiled on the
real detection engine — so a bad rule fails your pipeline loudly instead of
saving and silently never matching. That makes `hive set` a usable CI gate: a
non-zero exit is a rule that could not run.

## Remediation SLAs

An `sla`-typed record puts a due date on findings. There is no default one, so
adopting an SLA is a single write — see [Remediation SLAs](remediation-sla.md).

```bash
cat > sla.json <<EOF
{
  "policy_type": "sla",
  "sla": {
    "default_due_days": { "CRITICAL": 7, "HIGH": 30, "MEDIUM": 90, "LOW": 180 }
  }
}
EOF
limacharlie hive set --hive-name cloudsec_policy --key sla \
  --oid $OID --input-file sla.json --enabled
```

### Escalating an SLA breach

The first projection pass that observes a finding past its due date emits
`cloud_finding.sla_breached` — once per breach, never re-fired for the same
deadline. The payload is flat: `finding_id`, `fingerprint`, `finding_class`,
`severity`, `resource_urn`, `owner`, `ticket`, and `actor: "policy:sla"`.

```yaml
detect:
  event: cloud_finding.sla_breached
  op: exists
  path: event/fingerprint
respond:
  - action: extension request
    extension name: ext-cases
    extension action: update_case
    extension request:
      detect_id: "{{ .event.fingerprint }}"
      reopen_if_closed: true
      note: "Remediation SLA breached — this finding is past its due date"
```

Because the event carries `owner` and `severity`, the same hook routes just as
well to a paging Output or a team channel: branch on `severity` for who gets
woken up, and on `owner` for where it lands.

!!! note "Breach webhooks are capped per pass"
    A pass that newly breaches a very large number of findings pushes at most
    **200** breach events, so an SLA adopted over an old backlog cannot flood
    your stream on day one. Every breach is still reflected in the findings API
    — read `sla_state` there when you need the complete set.

## Saved queries

Save a graph query as a `cloudsec_query` record and it appears in every
teammate's query console:

```json
{
  "version": 1,
  "name": "Exposed VMs reaching sensitive data",
  "query": {"text": "..."},
  "tags": ["weekly"]
}
```

See [Configuration](configuration.md#cloudsec_query) for the full record
shape.

## CSV export

Add `?format=csv` to `findings`, `inventory`, `compliance`, or `query` to
stream the result as a CSV attachment instead of JSON. Filter parameters apply;
paging parameters are ignored, because the export owns its own walk:

```bash
curl -H "Authorization: Bearer $JWT" \
  "https://api.limacharlie.io/v1/cloudsec/$OID/findings?severity=CRITICAL&severity=HIGH&format=csv" \
  -o findings.csv
```

**`findings` and `inventory`** are multi-page sets, so the server pages through
the whole filtered set for you, capped at 100,000 rows with a trailing
`#`-comment row as the truncation notice. **`compliance` and `query`** are
single-shot: one evaluation or one query execution produces the whole result, so
there is nothing to walk and the CSV is exactly that result in row form.

The compliance CSV carries one row per control including the proving finding
ids — the auditor-facing evidence export, with a higher per-control evidence cap
than the JSON report (see [Compliance](compliance.md#auditor-export)).

!!! note "CLI `--output csv` is per-page"
    The CLI's global `--output csv` formats the rows the command returned —
    one page. For a full-estate export use the `?format=csv` server-side
    walk above, or the `limacharlie cloudsec export` subgroup
    (`export findings|inventory|compliance|query [-o file]`), which drives the
    same server-side full-set walk and writes the CSV to a file.

## Findings ↔ Cases automation

Cloud findings emit lifecycle events into the organization's own event
stream (see the [`emission` policy](configuration.md#emission-the-event-feed)):
`cloud_finding.created` (carries the full finding under `finding`),
`cloud_finding.closed` (`{finding_id, fingerprint, finding_class}`), and
`cloud_finding.still_open` (re-asserted at most once per day for open
findings with a linked ticket). D&R rules match these like any event; the
Cases extension actions close the loop.

!!! tip "You do not have to paste these by hand"
    All three rules below ship as an installable recipe: the Cases toggle in
    Cloud Security's settings writes them into your general D&R rule set for
    you, byte-for-byte identical to what follows. Use the toggle for the
    standard loop, and the YAML here when you want to review what it installs or
    fork it into something org-specific.

**Auto-case on high/critical findings** (async, grouped, storm-safe — one
case per rule category per window, and first-sync floods are summarized
upstream):

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

`update_case` resolves the case through the detection index (`detect_id` =
the finding fingerprint), so the rules never need a case number; a finding
with no linked case is a no-op. Cases never close findings — findings are
detection truth and close when the sweep confirms the fix (or via
operator/policy disposition).

!!! info "More lifecycle events for richer automation"
    The `created` / `closed` / `still_open` verbs above are the Cases loop,
    but D&R rules can key off more of the finding lifecycle:

    - `cloud_finding.updated` — an **open** finding changed materially, on a
      deliberately short list so it does not re-fire every sweep: the severity
      moved (either direction), the finding became reachable, or one of its CVEs
      entered KEV. Payload carries `changed[]` (the fields that moved),
      `old_severity`, `new_severity`, and the full `finding` — the hook for
      reacting to escalation (e.g. re-notify only when a finding crosses into
      CRITICAL).
    - `cloud_finding.resolved` / `.dismissed` / `.reopened` / `.assigned` —
      the disposition verbs, flat payload carrying `actor`, `status`, and
      `resolution`, for auditing triage decisions. Note that **`mitigated` and
      `accepted` both arrive as `.resolved`** — branch on `resolution`, not on
      the verb, to tell "fixed" from "accepted". These are not only human
      actions: a `suppression` policy emits the same verbs with `actor` set to
      `policy:<rule-name>`.
    - `cloud_finding.sla_breached` — an open finding passed the `due_at` its
      [`sla` policy](remediation-sla.md) assigned, emitted exactly once per
      breach. See [Escalating an SLA breach](#escalating-an-sla-breach).
    - `cloudsec.sync_completed` — the first-sync summary
      (`{total, by_class, by_severity}`) emitted once instead of a
      per-finding `created` flood, so onboarding a large estate is one event,
      not thousands.
    - `cloud_resource.created` / `.updated` / `.deleted` — inventory-level
      change events, gated by the [`emission`
      policy](configuration.md#emission-the-event-feed)'s `resource_events`
      flag (**off by default**).
    - `cloud_query.match` / `.resolved` / `.overbudget` — the
      [scheduled-query](configuration.md#scheduled-queries-any-saved-query-as-a-detection-source)
      feed: a saved graph query becomes a detection source, emitting per anchor
      entering and leaving its match set (and one `.overbudget` instead of a
      flood when the match set blows its cap).
    - `cloudsec.sweep_failed` — the operational event for alerting on
      collection health, gated by the `emission` policy's `ops_events` flag
      (**off by default**).

!!! warning "Drive automation from events, read state from the API"
    Event emission is best-effort and at-most-once: events queue in a bounded
    buffer and the oldest batch is dropped under sustained pressure rather than
    stalling the sweep. That is the right trade for triggering work, but it means
    the feed is not a replayable ledger. Whenever correctness matters — a
    reconciliation job, a nightly audit, "is this really still open?" — read the
    findings API rather than replaying events.

**Non-Cases shops:** route the same `cloud_finding.*` events to
Jira/ServiceNow via an Output and key your tickets on `fingerprint` the same
way.
