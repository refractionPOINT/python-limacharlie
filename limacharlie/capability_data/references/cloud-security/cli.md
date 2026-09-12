# Command Line Interface

The `limacharlie cloudsec` command group (Python SDK/CLI v2) covers most of
the Cloud Security API surface: the posture and inventory reads, findings
triage, graph queries, policy previews, CSV exports, and the fleet roll-up.
Commands take the global options (`--oid`,
`--output json|yaml|toon|csv|table|jsonl`, `--filter <jmespath>`,
`--fields <names>`), and every command and subgroup answers `--ai-help` with
task-oriented guidance. The `export` subgroup is the one exception: it writes
a server-rendered CSV straight through, so the output, filter, and field
options do not apply to it.

```bash
pip install 'limacharlie>=5.5.3'   # Python 3.10 or newer
limacharlie cloudsec --help
```

Configuration (providers, policies, saved queries) is managed with the
standard `limacharlie hive` commands — see
[Configuration](configuration.md); this group is the query and triage
surface.

For the complete local-scanning, SARIF/CycloneDX ingest, and CI workflow, see
[Code Scanning & Pushed Results](code-scanning.md).

## At a glance

```bash
# Posture
limacharlie cloudsec overview --trend-days 90
limacharlie cloudsec changes --limit 100
limacharlie cloudsec risk-trend
limacharlie cloudsec scan-status --provider gcp
limacharlie cloudsec topology

# Findings worklist + triage
limacharlie cloudsec finding list --severity CRITICAL --class toxic_combination --kev
limacharlie cloudsec finding list --sla breached --sort due_at        # what is late
limacharlie cloudsec finding facets --status open
limacharlie cloudsec finding classes                      # the finding_class enum
limacharlie cloudsec finding get fnd_0a1b...
limacharlie cloudsec finding resolve fnd_0a1b... --kind mitigated --reason "SG tightened"
limacharlie cloudsec finding resolve fnd_0a1b... --kind open          # reopen
limacharlie cloudsec finding bulk-resolve --finding-id fnd_a --finding-id fnd_b --kind accepted
limacharlie cloudsec finding set-owner fnd_0a1b... --owner alice@acme.com
limacharlie cloudsec finding set-ticket fnd_0a1b... --ticket JIRA-1234

# Attack paths, chokepoints
limacharlie cloudsec attack-path list --severity CRITICAL
limacharlie cloudsec chokepoint list
limacharlie cloudsec chokepoint dismiss "lcrn:..." --reason "bastion by design"
limacharlie cloudsec chokepoint restore "lcrn:..."

# Identity & data
limacharlie cloudsec ciem public-access
limacharlie cloudsec ciem facets
limacharlie cloudsec ciem identity "lcrn:..."             # Identity 360
limacharlie cloudsec data-security facets

# Inventory & graph
limacharlie cloudsec inventory list --type <resource-type> --provider gcp -q prod --limit 50
limacharlie cloudsec inventory list --all-accounts --limit 50   # drop per-account scoping
limacharlie cloudsec inventory facets
limacharlie cloudsec resource get "lcrn:..."
limacharlie cloudsec graph neighbors "lcrn:..." --limit 200
limacharlie cloudsec query list
limacharlie cloudsec query run --named public_data_stores
limacharlie cloudsec query run --text 'MATCH (d:DataStore {is_sensitive: true})<-[:has_permission_on]-(i:Identity {is_external: true}) RETURN i, d'

# Compliance
limacharlie cloudsec compliance report --framework cis-gcp
limacharlie cloudsec compliance report --assignment prod-cis
limacharlie cloudsec compliance frameworks
limacharlie cloudsec compliance assignments

# Sensors <-> cloud assets
limacharlie cloudsec resolve sensors $SID1 $SID2
limacharlie cloudsec resolve assets "lcrn:..."

# CAASM
limacharlie cloudsec caasm assets -q laptop
limacharlie cloudsec caasm coverage --status open --sort lc_risk --order desc
limacharlie cloudsec caasm policy get
limacharlie cloudsec caasm policy set --input-file coverage.json
limacharlie cloudsec caasm ingest --source okta --records-file users.json

# Provider preflight + coverage manifest
limacharlie cloudsec provider test --input-file provider.json
limacharlie cloudsec provider manifest --type gcp        # "what you get" for a provider

# Code scanning and pushed results (requires a CLI release newer than 5.6.2)
limacharlie cloudsec code repos --with-findings --all
limacharlie cloudsec code scan . --repo acme/api --ingest
limacharlie cloudsec code ingest --repo acme/api --source sarif --file results.sarif

# Policy authoring aids + read-only matcher previews
limacharlie cloudsec policy vocabulary
limacharlie cloudsec policy suggest --dimension name -q prod --limit 10
limacharlie cloudsec simulate resources --input-file rules.yaml --target data_store
limacharlie cloudsec simulate resources --rules-json '[{"name_glob":"prod-*"}]' --resource-type gcp_bucket
limacharlie cloudsec simulate findings --match-json '{"finding_class":"misconfig","max_severity":"LOW"}'

# Full-set CSV export (server-side walk of the entire filtered set)
limacharlie cloudsec export findings -o findings.csv
limacharlie cloudsec export inventory -o inventory.csv
limacharlie cloudsec export compliance --framework cis-gcp -o compliance.csv
limacharlie cloudsec export query --named public_data_stores -o data-stores.csv

# Fleet — cross-tenant (MSSP) roll-up, no single --oid
limacharlie cloudsec fleet overview --oid $OID1 --oid $OID2 --trend-days 30
limacharlie cloudsec fleet overview --group <GROUP_ID> --limit 100
```

The `export` subgroup streams the **entire** filtered set as a CSV
(server-side keyset walk, capped at 100,000 rows) — use it for offline
analysis. It is distinct from the per-page `--output csv`, which serializes
only the current page of a normal list command. `export findings`,
`export inventory`, and `export compliance` take the same filters as their
`finding list` / `inventory list` / `compliance report` counterparts;
`export query` takes the same `--named` / `--text` / `--query-json`
selectors as `query run`.

`fleet overview` is the multi-org board for MSSPs: pass `--oid` repeatedly,
or `--group <GROUP_ID>` — the opaque id of an org group you own or belong to,
not its display name — to roll risk posture up across tenants. Given neither,
it spans every organization your credentials can see. It carries
`--trend-days`, `--limit`, and `--cursor` for paging the tenant list, and is
the one command that does not resolve a single `--oid`.

!!! note "What lives outside this command group"
    Three read routes have no `cloudsec` command of their own: the shared-fix
    cause rollup (`GET /findings/causes`), the filtered identity list behind
    the Access page (`GET /ciem/identities`), and the paginated data-store
    list (`GET /data-security/stores`). Call them over the REST API, or with
    the generic `limacharlie api <path>` escape hatch — see the
    [API Reference](api-reference.md).

    Some things that look like missing commands are really something else.
    **Scheduled queries** are not a separate feature: a scheduled query is a
    `cloudsec_query` Hive record carrying a `schedule` block, authored with
    `limacharlie hive set --hive-name cloudsec_query` (see
    [Configuration](configuration.md#cloudsec_query)). **Custom posture rules**
    and **remediation SLAs** are likewise `cloudsec_policy` Hive records
    (`policy_type` `rules` and `sla`) written with
    `limacharlie hive set --hive-name cloudsec_policy` — see
    [Custom Posture Rules](custom-rules.md) and
    [Remediation SLAs](remediation-sla.md). **Workload groups**
    are not a view of their own either: they arrive on findings as
    `source_scope` / `target_scope` in `finding list`, and as the
    `ComputeGroup` node type in graph queries.

## Filtering and pagination

`finding list` carries the full vocabulary — repeatable filters (OR within a
key, AND across keys), free-text search, sorting, and keyset pagination:

```bash
limacharlie cloudsec finding list \
  --severity CRITICAL --severity HIGH \
  --status open -q payment \
  --sort lc_risk --order desc \
  --limit 50
# ...then pass the returned next_cursor back:
limacharlie cloudsec finding list --cursor "<next_cursor>" --limit 50
```

Boolean tri-state flags (`--kev/--no-kev`, `--reachable/--no-reachable`)
send the filter only when given, so the server default applies otherwise.

`--sla` selects on the derived [remediation-SLA
state](remediation-sla.md#stored-vs-derived) — `breached`, `due_soon`,
`on_track`, `exempt`, `none` — and is repeatable like the other filters. It
applies to `finding list`, `finding facets`, `finding causes`, and
`export findings`. `--sort due_at` is the matching sort key, and the one key
that defaults to **ascending** (soonest deadline first), keeping findings with
no due date last rather than dropping them.

!!! note "`--sla` needs a CLI newer than 5.6.1"
    The SLA selector and the `due_at` sort key ship in the first `limacharlie`
    release after 5.6.1. On an older CLI, use the `sla=` and `sort=due_at`
    parameters on the [REST route](api-reference.md#reads) — the server-side
    feature is live either way.

The other lists carry a subset, so check `--help` before assuming a flag is
there. `caasm coverage` behaves like `finding list` (repeatable filters,
`--sort`/`--order`, paging). `inventory list` and `caasm assets` page but do
not sort, and inventory's `--type` / `--provider` / `--account` / `--region`
each take a single value rather than repeating. `attack-path list` returns
the headline set in one shot: repeatable filters and `-q`, but no sorting and
no paging.

## Records, files, and stdin

The commands that take a record — `provider test`, `caasm policy set`, and
both `simulate` commands — accept it three ways: `--input-file` (JSON *or*
YAML), an inline-JSON flag (`--provider-json`, `--policy-json`,
`--rules-json`, `--match-json`), or piped on stdin:

```bash
cat provider.yaml | limacharlie cloudsec provider test
limacharlie cloudsec caasm policy set --policy-json '{"expect":[...]}'
```

`caasm ingest` has its own pair: `--records-file` for a JSON or YAML array of
vendor records, `--record-json` for a single inline record.

Both `simulate` commands take `--sample-limit` (default 25, cap 100) to size
the returned sample, and `simulate resources` takes a repeatable
`--resource-type` to narrow the walked types the way an exclusions rule does.
`policy suggest` takes `--limit` (default 20, cap 50).

## Scripting

The SDK class behind the CLI is available directly:

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.cloudsec import CloudSec

cs = CloudSec(Organization(Client(oid="...")))
page = cs.list_findings(severity=["CRITICAL"], kev=True, limit=100)
for f in page["findings"]:
    print(f["lc_risk"], f["title"], f["resource_urn"])
```

Each method mirrors one API route and returns the raw response dict; see the
[API Reference](api-reference.md) for response shapes.
