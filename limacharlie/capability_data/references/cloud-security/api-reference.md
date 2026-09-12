# API Reference

All Cloud Security routes live under
`https://api.limacharlie.io/v1/cloudsec/{oid}/…` and appear in the public
OpenAPI spec at [`/openapi`](https://api.limacharlie.io/openapi).
Authentication is the standard `Authorization: Bearer <JWT>` header.

!!! info "Permissions & enable gate"
    Reads — and the read-only preview `POST`s (`query`, `simulate/resources`,
    `simulate/findings`, `policy/suggest`) — require `cloudsec.get`; every
    other write requires `cloudsec.set`. Every route requires the
    organization to be subscribed to `ext-cloud-security` — a `403` on any
    route means subscribe first. The `oid` is always taken from the
    authorized path. Provider *records* are not `/cloudsec` routes: their
    CRUD goes through Hive (`cloudsec_provider` hive, gated by
    `cloudsec_provider.get/set/del`).

Shared behaviors:

- **Repeatable filters** (`severity`, `finding_class`, `status`, `account`, and
  the identity / Data Security / CAASM selectors listed per route below) are
  passed as repeated query keys: `?severity=CRITICAL&severity=HIGH`. OR within a
  key, AND across keys. A read filter takes at most 100 values per key and
  quietly drops the rest; a *write* body over its own cap is rejected outright
  rather than truncated, so a partial write is never silently reported as a
  whole one. The `sid` and `urn` keys on the `/resolve/*` routes are not filters
  but bulk lookup keys, with their own 500-per-request cap.
- **Boolean selectors are tri-state**: an absent parameter means "not
  filtered", which is *not* the same as passing `false`. Omit it for no
  constraint; pass `false` to pin the negative case.
- **Keyset pagination**: pages carry `next_cursor`; pass it back as
  `?cursor=`. `limit` is clamped to 1000.
- **CSV export**: exactly four routes accept `?format=csv` to stream the
  full filtered set as a CSV attachment — `findings`, `inventory`, and
  `compliance` (`GET`), and `query` (`POST`). The stream is a server-side
  keyset walk, capped at 100,000 rows, with an in-band `#`-comment truncation
  notice when the cap is hit.

## Reads

| Route | Returns |
|---|---|
| `GET /findings` | `{findings, next_cursor}` — the risk-ranked worklist. Filters: `severity[]`, `finding_class[]`, `status[]`, `account[]`, `owner[]`, `sla[]`, `reachable`, `kev`, `q`, `sort`, `order`, `cursor`, `limit`. `sort` is `lc_risk` (default), `severity`, `first_seen`, or `due_at`; `due_at` is the one key that defaults to **ascending** and sorts findings with no due date last. |
| `GET /findings/facets` | `{facets}` — cross-filtered facet counts under the same selectors, including an `sla` dimension counting each state. |
| `GET /findings/classes` | `{classes}` — the canonical `finding_class` enum (the 11 values), for building selectors. |
| `GET /findings/causes` | `{causes, distinct}` — findings grouped by their **cause**, the mutable object (a firewall rule, a role binding) whose single edit resolves all of them. Takes the full findings selectors, plus `cause` for the exact count of one cause and `limit` (default 20, max 200) for the top causes; `distinct` is the total number of causes matching the filter. |
| `GET /findings/{finding_id}` | `{finding}` — one finding in full. |
| `GET /attack-paths` | `{paths}` — marquee toxic-combination paths. Filters: `severity[]`, `account[]`, `status[]`, `q`. |
| `GET /chokepoints` | `{chokepoints, total_paths}` — shared attack-path hops ranked by paths broken, including the principal-exposure metrics. |
| `GET /ciem/public-access` | `{access, identity_kpis, principals}` — public/external access to sensitive resources, the identity-posture headline counts, and the risk-ranked per-principal effective-access rollup (top 500). The two extra blocks are best-effort: a read failure omits the key rather than failing the call. |
| `GET /ciem/facets` | `{facets}` — identity facet counts. |
| `GET /ciem/identities` | `{principals, next_cursor}` — the same per-principal effective-access rows `public-access` carries, but server-filtered and keyset-paginated instead of a top-N. Takes the same selectors as `/ciem/facets`, so the rail's counts always describe the population in the list. Ranked by risk score by default, so a walk that spans a projector rebuild can move a row across the cursor — use it for browsing, and `/inventory` with `type=Identity` and the default `urn` sort for an exact export. |
| `GET /ciem/identity?urn=` | `{identity}` — the Identity 360 single-identity rollup for one principal URN: its grants, reachable sensitive resources, access levels, and escalation paths. |
| `GET /inventory` | `{resources, next_cursor}`. Filters: `type`, `provider`, `account`, `region`, `q`, `account_unscoped` (drop the account scoping and walk the whole estate), `sort` (`urn`, the default and the safe order for a full walk or export; `risk` with `type=Identity`; `last_seen` with `type=ThirdPartyAsset`), paging. With `type=Identity`, `provider`/`source`, `account`, and `region` become repeatable and the identity cross-filter applies: `kind`, `criticality`, `risk_band`, `mfa` (`on`/`off`/`unknown`), and the tri-state `admin`, `external`, `public`, `disabled`, `crown_jewel`, `can_escalate`, `dormant_90d`, `with_sensitive`. Pages served from the materialized view also carry `served_from` and `data_as_of` (the snapshot's build time) so a client can render "as of" instead of implying live. |
| `GET /inventory/facets` | Inventory facet counts by type/account/region. |
| `GET /data-security/facets` | `{facets}` — DSPM data-store rollup. |
| `GET /data-security/stores` | `{stores, next_cursor}` — the filtered, paginated data-store list, under the same selectors as `data-security/facets`: `provider`, `account`, `region`, `store_kind`, `tier`, and the tri-state `sensitivity` / `exposure`. Served from the materialized graph, so the list stays exact at any estate size. |
| `GET /resource?urn=` | `{resource}` — the canonical record for any URN (null when unknown). |
| `GET /graph/neighbors?urn=` | `{graph: {nodes, edges}}` — 1-hop expansion; `limit` default 200, cap 500; `truncated` flag. |
| `GET /topology` | `{scopes, edges, available, generated_at}` — the server-side estate aggregate behind the Topology diagram (scope nodes + the edges between them), with the unix time the aggregate was built. `available` is `false` only when the aggregate has not been materialized for this organization yet (the client should fall back to its own walk); a genuinely empty estate answers `available: true` with empty `scopes` and `edges`. |
| `GET /policy/vocabulary` | The classification-policy vocabulary, as a flat object: `surfaces` (the per-surface matcher-capability table), `resource_types` (`data_stores`, `compute`, `identities`), `content_classes`, `providers`, `tiers`, `suggested_classes`, and `in_use` — the org's in-use value histograms. |
| `GET /providers/manifest?type=` | `{manifest}` — the per-provider coverage manifest ("what you get"): the resource kinds, edges, and checks a given `provider_type` produces. Omit `type` to get `{manifests}`, the manifest for every supported provider. |
| `GET /queries` | `{queries}` — the named query pack (name, title, description, query). |
| `POST /query` | `{rows}` — run a graph query. Body: exactly one of `named` / `text` / `query` (DSL object), optional `project`. With `project: "graph"` the response also carries `graph: {nodes, edges}`, the subgraph induced over the matched URNs — or `truncated: true` in its place when the result spans more than 500 nodes (the rows are complete either way; only the drawing is capped). A shortest-path query answers `{paths: [{anchor, target, hops, path}]}` instead of `rows`, and its `project: "graph"` draws the whole kill chain, adding `graph_partial` when only some paths are drawn and `graph_unavailable` when none can be. |
| `GET /compliance` | `{report}` — per-control assessment. Params: `framework` (default `cis-gcp`) or `assignment` (overrides `framework`). |
| `GET /compliance/frameworks` | `{frameworks}` — id, name, version, control counts. |
| `GET /compliance/assignments` | `{assignments}` — scoped assignments with per-assignment scores. |
| `GET /overview` | Composed risk overview in one round-trip: `score`, `severity_counts`, `open_count`, `reachable_open`, `reachable_criticals`, `top_paths`, `coverage`, `trend`, `recent_changes`, the per-tenant `usage` metering block, and `top_issue` when there is one. Also carries `estate_shape` (`cloud` \| `identity` \| `hybrid`) and, for an identity or hybrid estate, an `identity_summary` posture headline — both best-effort and omitted on a read failure. Param: `trend_days` (default 30). |
| `GET /changes` | `{changes}` — created/closed feed, newest first. Param: `limit` (default 50, clamped to 1000). |
| `GET /risk-trend` | `{trend}` — score history, oldest first. Param: `trend_days`. |
| `GET /scan-status` | Collection run state. With `provider` set: `{status}` for that provider — ids are lowercase and the lookup is case-sensitive, so an unknown or miscased id reads as never-scanned. With `provider` omitted: `{coverage, workload, status}` — per-provider run state for every connected cloud provider, `status` as the first cloud provider's state for backward compatibility, and a reserved `workload` section. There is no default provider. |
| `GET /resolve/sensors?sid=…` | `{resolved, unresolved}` — sensor → cloud asset, bulk via repeated `sid` (server cap 500/request; keep URLs under ~8KB — the CLI/SDK chunks automatically). |
| `GET /resolve/assets?urn=…` | `{resolved, unresolved}` — cloud asset → sensors, bulk via repeated `urn` (same caps and chunking). |
| `GET /caasm/assets` | `{resources, next_cursor}` — the merged third-party asset inventory. Params: `q`, `kind[]`, `source[]` (which observing tool reported the asset), the four repeatable device-posture filters `posture_encryption`, `posture_screen_lock`, `posture_compromised`, `posture_managed`, `sort` (`urn` default, or `last_seen`), paging. Pass an **empty** value to a posture filter to select the assets no source reported that fact for — unreported is not the same as compliant. Also carries `served_from` / `data_as_of` when the page came from the materialized merged view. |
| `GET /caasm/coverage` | `{findings, next_cursor}` — coverage-gap findings. Params: `status[]`, `severity[]`, `q`, `sort`, `order`, paging. |
| `GET /caasm/policy` | Resource-list shape: zero rows (no policy) or one row whose `props` is the policy. |
| `GET /free-tier` | `{is_free_tier, sensor_quota, max_providers, enabled_providers}` — the org's free-tier standing and the limits that apply, for surfacing an upgrade prompt before a limit is hit. Descriptive only: it is not a gate, the collector enforces the limits, and reads keep working after a trial expires. |

!!! note "`ciem/*` and `providers/*` families"
    `ciem/*` has four members — `public-access`, `facets`, `identities`, and
    `identity` (singular: one principal). `providers/*` has two — `test`
    (`POST`, below) and `manifest` (`GET`, above). Creating, editing, and
    deleting provider *records* is not a `/cloudsec` route: it goes through the
    `cloudsec_provider` Hive.

## Fleet (multi-org)

One route sits outside the `{oid}` path — the MSSP cross-tenant board:

| Route | Returns |
|---|---|
| `GET /cloudsec/fleet/overview` | `{orgs, rollups, total_orgs, skipped, next_cursor}` — risk posture rolled up across many organizations. `skipped` splits the tenants that could not be included into `not_enabled` (no `ext-cloud-security` subscription) and `lookup_failed` (a transient check failure, so one bad tenant never fails the whole call). Params: `oids[]` (repeat to select tenants), `group` (a saved fleet group), `trend_days`, `cursor`, `limit` (default 25, cap 100). Requires `cloudsec.get` on each tenant in scope — organizations you lack it on are simply left out, not reported as skipped. A single call may resolve to at most 500 organizations (past that, narrow with explicit `oids` or a smaller group), and the route carries its own quota of 120 calls per hour. |

## Writes

All writes are `POST` with a JSON body and require `cloudsec.set`.

| Route | Body | Returns |
|---|---|---|
| `/findings/{finding_id}/status` | `{resolution: {kind, reason, expires_at}}` — `kind` is `mitigated` \| `accepted` \| `false_positive`, or `open` to clear the disposition and reopen. `expires_at` is unix seconds (meaningful with `accepted`). | `{ok}` |
| `/findings/bulk/status` | `{finding_ids: [...], resolution: {...}}` — one resolution applied to many findings. Unlike the single-finding route, `kind` must be `mitigated` \| `accepted` \| `false_positive` — the bulk route does **not** accept `open` (reopen findings one at a time). At most 500 ids per call: an over-cap batch is **rejected**, not truncated, so split larger sets yourself rather than have a prefix dispositioned silently. | `{ok, updated}` |
| `/findings/{finding_id}/owner` | `{owner}` — empty string clears. | `{ok}` |
| `/findings/{finding_id}/ticket` | `{ticket}` — empty string clears. | `{ok}` |
| `/chokepoints/dismiss` | `{urn, reason?}` | `{ok}` |
| `/chokepoints/restore` | `{urn}` | `{ok}` |
| `/caasm/policy` | `{policy: {expect: [{label, capability, kinds}]}}` — validated before storing. | `{ok}` |
| `/caasm/ingest` | `{source, records?: [...], record?: {...}, policy?: {...}}` — `source` required; a single `record` is treated as a one-element batch. Body capped at 1 MiB; ingestion is idempotent. | `{result: {received, normalized, skipped, assets, created, updated, deleted, policy_set}}` |
| `/providers/test` | `{provider: <cloudsec_provider record>}` — credential inline (ephemeral, never stored) or a `hive://secret/<name>` reference. | `{supported, report: {provider, ok, checks: [{id, name, required, ok, detail}]}}`. A provider type with no preflight implemented answers `{supported: false, report: null}` rather than an error — treat it as "cannot verify", not "credential bad". |

Example — disposition a finding:

```bash
curl -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  "https://api.limacharlie.io/v1/cloudsec/$OID/findings/fnd_0a1b.../status" \
  -d '{"resolution": {"kind": "accepted", "reason": "SEC-123", "expires_at": 1767225600}}'
```

## Policy authoring: Simulate & vocabulary

These `POST` routes back the console's policy-authoring aids (matcher
preview and value autocomplete). They never mutate state, so they require
only `cloudsec.get`. On the CLI they are `limacharlie cloudsec simulate
resources` / `simulate findings`, `limacharlie cloudsec policy suggest`,
and `limacharlie cloudsec policy vocabulary`.

| Route | Body | Returns |
|---|---|---|
| `POST /simulate/resources` | `{rules, target, resource_types?, sample_limit?}` — `rules` is a list of matcher rules, `target` scopes the walked surface (`data_store`, `compute`, `identity`, or `any` — the default). `sample_limit` defaults to 25, cap 100. | `{evaluated, matched, indeterminate, truncated, sample, indeterminate_sample}` — preview a classification / coverage / exclusion matcher against stored inventory, with a bounded sample per bucket. |
| `POST /simulate/findings` | `{match, sample_limit?}` — a suppression matcher. An empty `match` is allowed: it matches everything up to the default severity ceiling, and showing that blast radius is the point of the preview. | `{evaluated, matched, partial, indeterminate, truncated, sample, partial_sample, indeterminate_sample}` — preview it against currently-open findings. `partial` counts vulnerability rollups the rule would *shrink* (some affected resources accepted, the finding stays open); `indeterminate` counts rollups whose bounded target sample cannot decide. |
| `POST /policy/suggest` | `{dimension, q, target, limit?}` — `dimension` is `name` or `account`; `q` is required and at most 256 bytes (longer is a `400`); `target` takes the same surface enum as `simulate/resources`; `limit` defaults to 20, cap 50. | `{values: [{value, count}], truncated, evaluated}` — live matcher-value autocomplete drawn from the tenant estate. |

Both simulations are bounded walks: they stop at 50,000 rows or 15 seconds and
report `truncated: true` with the counts so far, so a preview on a large estate
never turns into an unbounded scan.

Pair these with `GET /policy/vocabulary` (the closed vocabularies and
per-surface capability table) and `GET /findings/classes` (the
`finding_class` enum) when building a classification or suppression policy.

## Finding shape

The finding object (list, get, and the `cloud_finding.created` event all
carry the same shape) — key fields:

| Field | Meaning |
|---|---|
| `finding_id`, `fingerprint` | Stable identity of the condition (`fnd_` + fingerprint prefix). |
| `rule_id`, `finding_class`, `classification` | What detected it and its class. The canonical enum is `toxic_combination`, `public_exposure`, `ciem_risk`, `privilege_escalation`, `vulnerability`, `misconfig`, `malware`, `secret`, `scan_finding`, `coverage_gap`, `device_posture` (`malware`, `secret`, and `scan_finding` are reserved for capabilities not yet enabled). `workload_coverage_gap`, the cloud-workload flavor of a coverage gap, can additionally appear on a finding even though it is not one of the 11 picker values. |
| `severity`, `lc_risk`, `risk_breakdown` | `CRITICAL`–`INFO`, the 0–1000 composite, and its explanation. |
| `title`, `resource_urn`, `resource_name`, `resource_type`, `account`, `region` | The affected resource. |
| `related_urns`, `path`, `path_kind` | Related resources; the hop list for path findings and the kind of path it represents. |
| `source_scope`, `target_scope` | For attack-path / toxic findings, the durable workload group at each end (GKE/EKS/AKS node pool, MIG, ASG, VMSS) — `group_urn`, `group_kind`, `group_name` (the human label), `member_count` (the group's full size), `affected_count` (the members actually on paths), and `members`, a sample of those affected members bounded at 20 — so the finding headlines the shared-fix group, not a churny ephemeral node. |
| `cause` | The mutable object that actually gets edited to fix the finding — `kind`, `urn`, `name`. The shared-fix grouping key behind `GET /findings/causes`. |
| `reachable`, `in_kev`, `vulns`, `epss`, `epss_percentile` | Exposure and exploit intelligence; `vulns` entries carry `cve`, `package`, `package_version`, `fix_version`, `cvss_score`. |
| `pivot_targets`, `target_count` | For rollup findings, a bounded sample (20) of the affected targets and the true total, so a rollup states its own blast radius without carrying every row. |
| `evidence`, `remediation` | The offending configuration and the fix. |
| `ciem_access` | For identity findings: role, identity kind, public/external/privileged flags, grant path, and the classified data-plane **access level** / capability (`data_admin` > `data_write` > `data_read` > `metadata` > `none`) the grant confers. A sixth value, `unknown`, is the unverified escape hatch: it ranks below `none` and deliberately fails every "at least" threshold, so handle it explicitly rather than by ordinal comparison. It still counts as potential data access for the "reaches sensitive data" gate, flagged `unverified` instead of silently dropped. |
| `ciem_escalation` | For privilege-escalation findings, the escalation detail: `from_urn`, `admin_urn`, and the ordered identity `path`. |
| `business_criticality`, `environment`, `tags` | Business context carried from the resource, for routing and prioritization. |
| `runtime_sids` | Sensors resolved onto the affected asset. |
| `status`, `resolution`, `resolved_by`, `resolution_expires_at`, `owner`, `ticket` | The triage overlay. |
| `first_seen`, `last_seen` | Lifecycle timestamps. |
| `due_at`, `sla_source`, `sla_state` | The remediation clock. `due_at` (the deadline) and `sla_source` (the policy clause that set it, or `default`) are stored, and are **absent** until the organization writes an [`sla` policy](remediation-sla.md) that covers the finding — there is no default SLA. `sla_state` is always present: it is **derived on every read** from `due_at`, `first_seen`, and `status` (because it changes with the clock and nothing writes when a deadline passes) and reads `none` for any finding no clause covers. Values: `breached` \| `due_soon` \| `on_track` \| `exempt` \| `none`. |

## Events

The platform emits lifecycle events into the organization's event stream. With
no [`emission` policy](configuration.md#emission-the-event-feed) record, finding
events are **on** and resource + operational events are **off** — an org gets
the finding feed without configuring anything, and opts in to the noisier
families. The policy also takes a `severity_floor` that drops finding events
below a given severity (the created/updated/closed feed only — the first-sync
summary still counts the whole estate).

**Detection-truth lifecycle** (from the projector):

- `cloud_finding.created` — the full finding (including `runtime_sids`)
  under `event/finding`.
- `cloud_finding.updated` — an open finding materially changed (severity
  flip, vuln set). Payload `{finding_id, fingerprint, finding_class,
  changed, old_severity, new_severity, finding}`.
- `cloud_finding.closed` — `{finding_id, fingerprint, finding_class}`.
- `cloud_finding.still_open` — re-asserted at most once a day for open
  findings with a linked ticket (the case-sync verb); the payload carries the
  `ticket` alongside the identity fields.
- `cloud_finding.sla_breached` — emitted once, on the first projection pass
  that observes an open finding past its `due_at`. The breach is latched, so
  the event never re-fires for the same breach of the same deadline. Requires
  an [`sla` policy](remediation-sla.md); granularity is the reprojection
  cadence, not the second.

**Disposition** — flat payload
`{finding_id, fingerprint, finding_class, actor, note?}`, plus the finding's
post-disposition `status` and `resolution` on the operator-written ones:

- `cloud_finding.resolved`, `cloud_finding.dismissed`,
  `cloud_finding.reopened`, `cloud_finding.assigned`.

Two things emit these verbs, and `actor` is what tells them apart: an operator
triage write carries the user, while a
[`suppression` policy](configuration.md#suppression-finding-disposition-policy)
applying automatically carries `policy:<rule name>` (and plain `policy` when a
rule stops matching and releases its findings). A broad first application is
capped per pass, so a very large policy rollout summarizes rather than emitting
one event per finding.

The verb alone is deliberately coarse: **both** a `mitigated` and an `accepted`
disposition emit `cloud_finding.resolved`, because minting a new verb would
break consumers filtering on a known set. Branch on `resolution` — not on
`event_type` — to tell a risk somebody signed off on carrying from one that was
actually fixed.

**Summary & inventory:**

- `cloudsec.sync_completed` — emitted once on the first-ever (or rebuilt)
  projection in place of a per-finding `created` flood; payload
  `{total, by_class, by_severity}`.
- `cloud_resource.created`, `cloud_resource.updated`,
  `cloud_resource.deleted` — inventory change events (off by default).

**Scheduled queries:** a `cloudsec_query` record with `schedule.scheduled` set
emits `cloud_query.match` once per new anchor entering its result set and
`cloud_query.resolved` once per anchor leaving — the same lifecycle symmetry as
findings — plus `cloud_query.overbudget` once on each transition into the
over-budget state (rather than a match flood).

**Operational:** `cloudsec.sweep_failed` reports a collection pass that
failed. Off by default; opt in with the emission policy's `ops_events`.

Every payload also carries `event_type` and `oid`.

See [Automation & IaC](automation.md#findings-cases-automation) for D&R
rules that consume them.
