# Security Graph & Queries

Every sweep builds a graph of the estate: resources, identities, and data
stores as nodes; reachability, exposure, permissions, and vulnerability
relationships as edges. The graph is what turns three individually-boring
facts into one critical finding — and it is directly explorable.

## The graph model

Nodes are addressed by URN (the same `lcrn:` identifiers used across the
API — canonically `lcrn:1:<oid>:<provider>:<type>:<rest>`, e.g. a VM's type
segment is `compute_instance`) and carry type-specific properties: exposure
(`is_public`), sensitivity (`is_sensitive`), vulnerability context (`cve`,
`severity`, `in_kev`, `cvss_score`), and identity insight (human/service kind,
external flag, MFA posture, dormancy, escalation potential, least-privilege
suggestions).

Edges carry the relationship semantics:

| Edge | Meaning |
|---|---|
| `exposed_to` | Workload / AI endpoint → the internet (or another external boundary); carries the `via` mechanism |
| `can_reach` | An internet-exposed workload → a **sensitive** workload or data store it can reach on the network. Not a general reachability index: the edge is materialized only from exposed sources to sensitive sinks, collapsed transitively, and carries the `hops` count and `protocol` of the path it stands for |
| `reachable_from` | An internal entry point → the discovered external asset it is reachable from (the outside-in view) |
| `has_vulnerability` | Workload → CVE (with package and fix version) |
| `has_permission_on` | Identity → resource; carries the classified **access level** (the capability the grant confers — `data_admin` › `data_write` › `data_read` › `metadata` › `none`, plus `unknown`), which is the edge verb the UI shows |
| `can_assume` | Identity → identity (role assumption / impersonation) |
| `is_member_of` | Identity → **group** identity (group membership; account containment is not this edge) |
| `has_app_access` | Identity → application assignment (IdP surfaces) |
| `runs_as` | AI service → the identity it runs as (its service-identity pivot) |
| `runs_on` | Sensor — or a merged third-party asset — → the cloud workload it runs on (the runtime ↔ posture join) |
| `owns_device` | Identity → a merged third-party device it owns (see [CAASM](caasm.md)) |
| `member_of_group` | Workload → its workload group (cluster, node pool, scale set) |

## Attack paths

The headline analytic: an internet-exposed workload with a known-exploited
vulnerability that can reach a sensitive resource. Each path is scored and
surfaced both as a `toxic_combination` finding and in the dedicated view:

```bash
limacharlie cloudsec attack-path list --severity CRITICAL
```

That list is the whole `toxic_combination` class, not only the network paths —
it also carries the exposed foothold (an internet-facing workload with an
exploitable vulnerability, even when nothing sensitive is reachable
downstream), the identity path (a weakly-held identity — dormant admin, stale
key, external or third-party principal — that can reach sensitive or
privileged resources), and the CAASM hybrid (a privileged directory identity
whose device fails a posture check; see [CAASM](caasm.md)).

## Exploring the graph

Expand outward from any resource, one hop at a time — the API behind
click-to-expand on the graph canvas of the **Attack Surface** page:

```bash
limacharlie cloudsec graph neighbors "lcrn:...:compute_instance:..." --limit 200
```

The result is an induced subgraph (`nodes` + `edges`), ranked so sensitive
and public neighbors surface first, with `truncated` set when the node has
more neighbors than the cap (hard cap 500).

## Topology

The graph canvas above (on the **Attack Surface** page) is for traversal —
expanding one hop at a time from a starting node. **Topology** is the other
view: an aggregated, explorable diagram of the whole estate, laid out
Provider → Account → Region → Resource. It is the landing view of the
**Inventory** page, alongside **Resources**, **Third-party assets** and
**Sensor coverage**. A node-type declutter filter hides the classes you don't
care about, and the current view (filters, expansion) is captured in a
shareable URL so a colleague opens exactly what you're looking at.

It is backed by **server-side aggregates**, so the counts on every node are
exact at any scale — no capped page, no guessing. The response says whether the
aggregate is available for the organization yet; until it has been built the
console falls back to a bounded client-side walk, which is the one case where
counts reflect only what was walked. Topology is served by `GET /topology` (see
[API Reference](api-reference.md)) and by `limacharlie cloudsec topology` on the
CLI.

## Graph queries

Ask questions of the whole graph. Three input forms, one endpoint:

```bash
# A named query from the built-in query pack:
limacharlie cloudsec query list
limacharlie cloudsec query run --named public_data_stores

# The text form — a compact MATCH ... RETURN pattern:
limacharlie cloudsec query run --text 'MATCH (d:DataStore {is_sensitive: true})<-[:has_permission_on]-(i:Identity {is_external: true}) RETURN i, d'

# The raw query DSL:
limacharlie cloudsec query run --query-json '{...}'
```

The text form is a compact graph-pattern grammar, not natural language:
nodes are `(alias:Label {prop: value, ...})`, edges are `<-[:edge_name]-`
(inbound to the previous node) or `-[:edge_name]->` (outbound), edge names
use underscores, and the query ends with `RETURN alias, alias...`. Inline
predicates are AND-ed equalities.

Any of the three forms can also be asked to return the result as something
drawable: `project: "graph"` on the API call (see
[API Reference](api-reference.md)) adds an induced subgraph — `nodes` + `edges`
over the matched URNs — next to the rows. That is what the **Query console** tab
of the **Attack Surface** page renders. `graph` is the only projection there is;
the rows are always complete, and only the drawing is capped.

!!! note "Edge names: underscores in the text form, hyphens in the DSL"
    The text form uses the underscore spelling shown in the edge table above
    (`has_permission_on`). The raw JSON DSL uses the hyphen spelling
    (`has-permission-on`) — `{"in": "has_permission_on"}` is rejected as an
    unknown edge. Node type names (`DataStore`, `ComputeInstance`, …) are
    identical in both.

The first node is the **anchor**, and every query must anchor on a
*selective* set and traverse inward. Bounded node types anchor as-is; dense
types must be narrowed by a selective predicate. A query that fans out from the
dense fabric is rejected by design: restructure it to start from the selective
end (the sensitive store, the known-exploited vulnerability, the specific
identity) and walk toward the dense side.

| | Node types | Anchoring |
|---|---|---|
| **Bounded** | `DataStore`, `Vulnerability`, `PublicEndpoint`, `Application`, `ExternalAsset`, `AIService`, `Account`, `ComputeGroup` | Anchor as-is |
| **Dense** | `ComputeInstance`, `Identity`, `Endpoint`, `ThirdPartyAsset` | Need a selective predicate: `is_sensitive: true`, `is_public: true`, `is_external: true`, `in_kev: true`, or an exact `email` / `sid`. The booleans only count when `true` — `{is_sensitive: false}` matches nearly everything and is refused |

Predicates draw from a per-type allow-list that is narrower than the properties
a node *displays*: `ComputeInstance` admits `name` / `is_public` /
`is_sensitive`; `Identity` admits `kind`, `is_human`, `is_public`,
`is_external`, `email`, `mfa_enabled`, `status`; `DataStore` adds `store_kind`;
`Vulnerability` admits `cve` / `severity` / `in_kev` — but *not* `cvss_score`,
which is shown on the node and is not filterable. `ThirdPartyAsset` admits only
`name` / `asset_kind`, neither of which is selective, so a merged third-party
asset is reachable by traversal but can never be the anchor. An off-list field
fails validation with a clear message rather than returning odd results. Edge
predicates work the same way: `has_permission_on` filters on `effect`, `role`,
`granted_via`, `privileged`; `can_reach` on `protocol`; `has_vulnerability` on
`severity`; `runs_on` on `confidence`; `owns_device`, `member_of_group`,
`is_member_of` and `runs_as` carry no filterable properties.

Results are bounded: 1000 rows by default and 10000 at most, raised with the
DSL's `limit` field — the text grammar has no limit clause, so it always takes
the default. Rows are alias → URN
bindings; use `limacharlie cloudsec resource get <urn>` to hydrate any URN into
its full canonical record (this also works for derived nodes —
vulnerabilities, identities — that have no inventory row).

### Shortest-path queries

Instead of a fixed chain of edges, the JSON DSL can ask a variable-length
question — "is there a *short* path from this principal to a crown jewel?" —
with a `path` block in place of `match`: a direction, the edge labels each hop
may use, a hop bound (`max`, up to 12), and the target node. The answer is
ordered paths rather than alias rows, and the graph projection draws the whole
kill chain. `shortest_access_path_external_to_sensitive_data` in the built-in
pack is the worked example: the shortest chain of grants and assume-role hops by
which an identity outside the organization reaches a sensitive data store. This
form is DSL-only — the text grammar expresses fixed chains.

Queries worth keeping become `cloudsec_query` Hive records — shared,
versioned, and IaC-manageable (see
[Configuration](configuration.md#cloudsec_query)).

## Identity: CIEM views

The console calls this area **Identity & Access**. Three dedicated identity
reads sit on top of the graph:

```bash
# Public / external access to sensitive resources — the headline CIEM view.
limacharlie cloudsec ciem public-access

# Identity facet counts (kinds, external/public splits).
limacharlie cloudsec ciem facets

# Everything one principal can reach — the Identity 360 rollup (below).
limacharlie cloudsec ciem identity "lcrn:...:identity:..."
```

Access is scored by the **capability** a grant confers, not the mere existence
of a grant: the effective action set is classified to an access level —
`data_admin` › `data_write` › `data_read` › `metadata` › `none`. "Reaches
sensitive data" gates on `data_read`-or-higher; `metadata`/`none` grants are a
lower-severity reconnaissance signal rather than a top data-access risk. That
level is stamped on the `has_permission_on` edge and is the verb the UI shows.

There is a sixth level, `unknown`: the grant's effective action set could not be
verified (a role that could not be expanded, so only its verbatim name is
known). It counts as *potential* data access — it passes the sensitive-data gate
rather than being silently dropped, and what it produces is flagged as
unverified so an unexpanded owner-class grant is never mistaken for a clean
result. It deliberately satisfies no "at least this level" comparison, so it can
never be ranked as if it were confirmed.

Identity findings (dormant privileged identities, escalation edges, unused
privileges) surface in the main worklist under the `ciem_risk` and
`privilege_escalation` classes. External-vs-internal classification is driven by
the provider record's `internal_domains`, unioned with the primary domain the
provider discovers on its own (a single primary is not enough — the
organization's own users on secondary or verified domains would be classified
external), so declare every additional domain you own.

### Identity 360

For a single identity, **Identity 360** is the one-screen view of everything
it can reach — direct grants, group-inherited permissions, identities it can
assume, and application assignments — plus a **devices** lane listing the merged
third-party devices the identity owns (the `owns_device` edge from
[CAASM](caasm.md), not the sensors reporting into the organization). Each reach
edge carries its classified access level, so the whole effective blast radius is
visible in one place. It is the console's Identity & Access → *(an identity)*
drill-down, served by
`GET /cloudsec/{oid}/ciem/identity?urn=<identity-urn>` (see
[API Reference](api-reference.md)) and by
`limacharlie cloudsec ciem identity "<identity-urn>"` on the CLI.

## Data security: DSPM facets

```bash
limacharlie cloudsec data-security facets
```

Returns the data-store posture rollup: total stores, sensitive, public, and
public-*and*-sensitive counts, plus seven facet dimensions — `store_kind`,
`sensitivity`, `exposure`, `criticality` (the crown-jewel tier),
`provider`, `account`, and `data_class` (the classifier labels a store
carries). The facets are cross-filtered: each dimension is counted under every
*other* selector but not its own, so a value's number tells you how many stores
you would see if you added it. Sensitivity is your declaration:
`classification`-policy rules matching on account, name, resource type, label,
or tag decide what counts as sensitive (the retired `auto_classify` boolean is
gone, and the `content_class` dimension is accepted but content detection is
not live in the current release) — see
[Configuration](configuration.md#classification-crown-jewels).

## Inventory

The system-of-record behind the graph is queryable directly, filtered by
`--type`, `--provider`, `--account`, `--region`, and free-text `-q`:

```bash
limacharlie cloudsec inventory list \
  --type <resource-type> --provider gcp --region us-central1 -q prod
limacharlie cloudsec inventory facets
```

This is the whole system-of-record, cloud resources and third-party assets
alike. Two of the types are served *merged* rather than raw, because their
underlying rows are per-observing-source:

- `--type ThirdPartyAsset` returns the entity-resolved CAASM assets — one row
  per real device or identity, with per-source provenance retained. The
  provider / account / region filters don't apply to a cross-source merged
  asset; the type is the scope selector. The console shows these in the
  **Third-party assets** view of the **Inventory** page, which appears once the
  organization has any.
- `--type Identity` likewise returns one entity per human rather than one row
  per observing sweep, stamped with the providers that saw it. Here the scope
  filters keep their meaning and match any producing observation.

See [CAASM](caasm.md) for the merge itself and the dedicated third-party
asset reads.

## Sensors ↔ cloud assets

The fusion mapping resolves both directions between runtime (sensors) and
posture (cloud assets), in bulk:

```bash
# Which cloud asset does each sensor run on?
limacharlie cloudsec resolve sensors $SID1 $SID2

# Which sensors run on this asset?
limacharlie cloudsec resolve assets "lcrn:...:compute_instance:..."
```

Each response splits `resolved` and `unresolved`, so a pivot from a cloud
finding to live endpoint telemetry (or the reverse) is one call. It also carries
`resolver_ready`. When that is `false` the resolver is not available for the
organization and *everything* comes back unresolved regardless of what you
asked — which is a different answer from "the resolver ran and matched
nothing". Check it before concluding that a sensor has no cloud asset.
