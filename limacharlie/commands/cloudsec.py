"""Cloud Security (CNAPP) commands for LimaCharlie CLI v2.

Commands for the ``/cloudsec`` API surface: the merged, risk-ranked
findings worklist (CSPM misconfigurations + attack paths + CIEM) with
its facet and shared-fix (cause) rollups, the identity access
population, the cloud resource inventory, the Data Security (DSPM)
store list and facets, the pre-aggregated estate topology and
security graph, compliance assessment, the risk overview, CAASM
(third-party asset attack surface), sensor<->cloud-asset resolution,
finding triage, the free-tier standing, and the cloudsec_policy
authoring aids (vocabulary, autocomplete, and the "Simulate" matcher
previews).

Reads require the ``cloudsec.get`` permission and writes require
``cloudsec.set``. Every command requires the org to be subscribed to
the ``ext-cloud-security`` extension:

  limacharlie extension subscribe --name ext-cloud-security

Provider credentials and the cloudsec policies are hive records —
manage them with the hive commands (``limacharlie hive list
--hive-name cloudsec_provider``, same for ``cloudsec_policy`` and
``cloudsec_query``);
the one provider command here is the pre-save credential preflight
(``cloudsec provider test``).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.cloudsec import CloudSec
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# DEFAULT_CODE_SCANNER_IMAGE is the published scanner image `cloudsec code scan` runs.
#
# It is pinned to a TAG rather than floating on `latest`, because a scan's findings depend on
# which engines produced them: a moving tag would silently change what a local scan reports
# between two runs of the same command on the same tree, and the report records the versions
# it used precisely so that question has an answer.
DEFAULT_CODE_SCANNER_IMAGE = "gcr.io/legion-212720/github.com/refractionpoint/lc-code-scanner:v0.4.0"

# Where a LOCAL scan gets its vulnerability data.
#
# The image deliberately ships no defaults for these: inside the hosted sandbox the only
# reachable source is our own mirror, and a default pointing anywhere else would work on a
# developer's machine and then fail inside the sandbox — where the failure reads as "no
# vulnerabilities found". A local scan is the other case, and it is the one these are for:
# the machine has ordinary internet access, and the upstream public databases are what it
# should use. Override with --db-repo / --java-db-repo for an air-gapped or rate-limited
# network, which is exactly when a mirror of your own is worth having.
DEFAULT_TRIVY_DB_REPO = "ghcr.io/aquasecurity/trivy-db:2"
DEFAULT_TRIVY_JAVA_DB_REPO = "ghcr.io/aquasecurity/trivy-java-db:1"


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_OVERVIEW = """\
Composed risk overview for the org in one round-trip: the risk
score, severity distribution, top attack paths, account coverage,
the score trend, and recent finding changes.

Examples:
  limacharlie cloudsec overview
  limacharlie cloudsec overview --trend-days 90
"""

_EXPLAIN_CHANGES = """\
Recent cloud-finding lifecycle changes (created/closed), newest
first.

Examples:
  limacharlie cloudsec changes
  limacharlie cloudsec changes --limit 100
"""

_EXPLAIN_RISK_TREND = """\
The org's risk-score history over time (the Overview sparkline),
oldest first.

Examples:
  limacharlie cloudsec risk-trend --trend-days 90
"""

_EXPLAIN_SCAN_STATUS = """\
Cloud-collection run status for one provider: whether a sweep is in
progress, when it last started/completed, the last diff stats, and
any error.

Examples:
  limacharlie cloudsec scan-status
  limacharlie cloudsec scan-status --provider aws
"""

_EXPLAIN_FREE_TIER = """\
Where the org stands on the cloud-security free tier, and the limits
that apply to it: is_free_tier, sensor_quota, and — for a free-tier
org only — max_providers plus enabled_providers ("you are using N of
M provider connections"). A paying org has no provider cap, so those
two fields are absent for one.

This endpoint only DESCRIBES the limits; the collector and the
provider-record validator enforce them, so a limit applies whether or
not you call this. enabled_providers is omitted rather than zeroed
when the count could not be read, so an absent field means "unknown",
never "none configured". There is no trial countdown here — the
authoritative clock lives in the datacenter, and the collector
publishes a gated reason through 'cloudsec scan-status'.

Example:
  limacharlie cloudsec free-tier
"""

_EXPLAIN_FINDING_LIST = """\
List the merged, risk-ranked cloud-security findings (CSPM
misconfigurations + graph toxic-combination attack paths + CIEM
access), ordered by lc_risk.

Repeatable filters are OR within a key and AND across keys:

  --severity CRITICAL --severity HIGH --class toxic_combination

Finding classes: toxic_combination, public_exposure, ciem_risk,
privilege_escalation, vulnerability, misconfig, coverage_gap,
device_posture. The canonical, always current list is served by
'cloudsec finding classes'.

--owner filters by assigned owner (set with 'finding set-owner');
--unassigned selects the untriaged bucket and combines with --owner,
so "mine or nobody's" is --owner me@corp.com --unassigned.

Pagination is keyset-based: pass the previous page's next_cursor
via --cursor.

Examples:
  limacharlie cloudsec finding list --severity CRITICAL
  limacharlie cloudsec finding list --class public_exposure --kev
  limacharlie cloudsec finding list --status open --limit 50
  limacharlie cloudsec finding list --owner alice@corp.com --status open
  limacharlie cloudsec finding list --unassigned --severity CRITICAL
"""

_EXPLAIN_FINDING_FACETS = """\
Cross-filtered facet counts for the findings worklist under the
same filter selectors as 'finding list'. Each facet dimension is
counted against the other active filters.

The 'owner' facet is keyed by owner, with the empty string holding the
unassigned bucket, and is capped at the top 50 owners by count —
'owner_truncated' says whether any were dropped. --owner-pin keeps
named owners in that capped facet even when they would not rank into
it (pass your own identity so your row stays reachable on an estate
with more owners than the cap). It is NOT a filter: it selects no rows
and changes no count.

That guarantee is bounded by the same cap rather than absolute: pins
share the 50 slots with any --owner values (and the unassigned bucket
takes one, outranking every pin), so past ~50 combined a pin can still
be dropped and 'owner_truncated' cannot tell you it was. Render a
pinned-but-absent owner as zero.

Examples:
  limacharlie cloudsec finding facets --severity CRITICAL
  limacharlie cloudsec finding facets --owner-pin me@corp.com
"""

_EXPLAIN_FINDING_CAUSES = """\
Findings grouped by their CAUSE — the mutable object (a firewall
rule, the principal an attack path's grants land on) whose single
edit resolves every finding under it. Lets a worklist be worked by
fix instead of by row: "change this one thing, close N findings".

Only CAUSE-BEARING findings are in scope, and that is a small slice of
an estate: causes are stamped on the attack-path classes, while
vulnerability findings (~90% of a typical estate) deliberately carry
none. So these counts never sum to the worklist total, and
'--class vulnerability' legitimately returns no causes at all — that
means "no shared fix on this class", not "no findings".

Takes the same filters as 'finding list', so a rollup can be scoped
exactly like the list it summarizes. Pass --cause for the count of
one cause (an empty 'causes' means no finding under the filter
carries it); omit it for the top causes by count (--limit, default
20, cap 200). 'distinct' is the total number of matching causes, so
you can tell how much tail the head hides.

A count is a whole-population figure rather than a capped one, but it
is computed on each finding's STORED status, which lags a disposition
that expired on its own: an acceptance past its expiry still counts as
accepted until the backstop rewrites it, while reading that finding
returns it as open. Treat a count as a ranking and scale signal.

'kind' is an open vocabulary that grows server-side; treat an
unrecognized value as "some object" rather than assuming a class.

Examples:
  limacharlie cloudsec finding causes
  limacharlie cloudsec finding causes --severity CRITICAL --limit 5
  limacharlie cloudsec finding causes --cause "lcrn:...:firewalls/allow-all"
"""

_EXPLAIN_FINDING_GET = """\
Get a single finding by its id (e.g. fnd_<fingerprint>).

Example:
  limacharlie cloudsec finding get fnd_0123abcd...
"""

_EXPLAIN_FINDING_CLASSES = """\
The canonical finding_class vocabulary served from the backend enum
(the valid values for the 'finding list --class' filter and for a
suppression-policy finding_class matcher), so you never guess at the
valid set.

Example:
  limacharlie cloudsec finding classes
"""

_EXPLAIN_FINDING_RESOLVE = """\
Disposition a finding: record an operator resolution, or reopen it.

--kind is one of:
  mitigated       the risk was fixed
  accepted        the risk is accepted (optionally until --expires-at)
  false_positive  the finding was wrong
  open            clear the disposition and reopen (owner/ticket kept)

--expires-at is unix seconds and only meaningful with 'accepted'.

Examples:
  limacharlie cloudsec finding resolve fnd_abc... --kind mitigated --reason "SG tightened"
  limacharlie cloudsec finding resolve fnd_abc... --kind accepted --expires-at "$(date -d '+90 days' +%s)"
  limacharlie cloudsec finding resolve fnd_abc... --kind open
"""

_EXPLAIN_FINDING_BULK_RESOLVE = """\
Apply one resolution to many findings in a single call.

--kind is mitigated, accepted, or false_positive. Reopening is a
single-finding operation only (the bulk API does not accept 'open');
use 'finding resolve <id> --kind open' per finding.

Example:
  limacharlie cloudsec finding bulk-resolve --finding-id fnd_a... --finding-id fnd_b... \\
      --kind false_positive --reason "expected configuration"
"""

_EXPLAIN_FINDING_SET_OWNER = """\
Assign the owner of a finding, or clear it with --clear.

Examples:
  limacharlie cloudsec finding set-owner fnd_abc... --owner alice@corp.com
  limacharlie cloudsec finding set-owner fnd_abc... --clear
"""

_EXPLAIN_FINDING_SET_TICKET = """\
Link a ticket id/url to a finding, or clear it with --clear.

Examples:
  limacharlie cloudsec finding set-ticket fnd_abc... --ticket JIRA-123
  limacharlie cloudsec finding set-ticket fnd_abc... --clear
"""

_EXPLAIN_ATTACK_PATH_LIST = """\
The headline toxic-combination attack paths for the org
(internet-exposed workload with a KEV vulnerability that can reach
a sensitive resource). Accepts the severity/account/status/q
selectors to narrow the list.

Examples:
  limacharlie cloudsec attack-path list
  limacharlie cloudsec attack-path list --severity CRITICAL
"""

_EXPLAIN_CIEM_PUBLIC_ACCESS = """\
CIEM: which identities have public or external access to sensitive
resources.

Example:
  limacharlie cloudsec ciem public-access
"""

_EXPLAIN_CIEM_FACETS = """\
CIEM identity facet counts (identity kinds, MFA state, risk bands,
plus the admin/external/public/disabled/dormant/escalation/
sensitive-access rollups and the total), so the identity view can
lead with insight before the row list.

The selectors CROSS-FILTER the rail: each dimension is counted under
the other active selectors but not its own, so a value's count is
exactly how many rows selecting it would list. With no selectors the
response is the whole-population rollup. It takes the SAME selectors
as 'ciem identities', so the counts and that list describe the same
population — with ONE exception: the no-tier bucket that
--unclassified selects is skipped when counting, so it is the only
selection whose count the rail cannot give you.

--mfa unknown is everyone the MFA question does not apply to (no
identity-provider observation, or non-human) — it is NOT 'off'. The
boolean filters are tri-state: omitting one leaves the dimension
unconstrained, which is not the same as pinning it false.

Examples:
  limacharlie cloudsec ciem facets
  limacharlie cloudsec ciem facets --kind service_account --admin
"""

_EXPLAIN_CIEM_IDENTITIES = """\
One page of the Access screen's identity population: the same
per-principal effective-access rollup rows 'ciem public-access'
carries (grant / privileged / sensitive-reach counts, posture facets,
risk score), but server-filtered and pageable instead of a
risk-ranked top-N.

Takes the same selectors as 'ciem facets', so the rail's counts and
this list describe the same population — except for the no-tier bucket
(--unclassified), which the rail skips when counting. Ranked by risk score
descending by default; a walk that spans a projector recompute can
move a row across the cursor, so use it for browsing rather than for
exact exports.

--account / --region are served from the projector's merged view: on a
tenant whose view has not been built yet the call fails loudly rather
than returning a misleading zero.

Examples:
  limacharlie cloudsec ciem identities --limit 50
  limacharlie cloudsec ciem identities --kind service_account --can-escalate
  limacharlie cloudsec ciem identities --external --with-sensitive
  limacharlie cloudsec ciem identities --mfa off --admin
"""

_EXPLAIN_CIEM_IDENTITY = """\
The single-identity effective-access rollup for one identity URN: the
same row shape 'ciem public-access' carries (grant / privileged /
sensitive-reach counts, posture facets, risk score) but for ANY
identity, not just the risk-ranked top-N. Powers the Identity 360
view. Returns a null identity when the URN is not a known identity.

Example:
  limacharlie cloudsec ciem identity "lcrn:gcp:...:serviceAccount/deploy"
"""

_EXPLAIN_INVENTORY_LIST = """\
List the cloud resource inventory (system-of-record rows).

--provider scopes to the producing sweep (e.g. gcp, aws, azure,
okta, google_workspace) — useful when several providers feed the
same org.

Examples:
  limacharlie cloudsec inventory list
  limacharlie cloudsec inventory list --type gcp_bucket --region us-central1
  limacharlie cloudsec inventory list --provider okta
  limacharlie cloudsec inventory list -q prod --limit 50
"""

_EXPLAIN_INVENTORY_FACETS = """\
Inventory facet counts by type/account/region.

Example:
  limacharlie cloudsec inventory facets
"""

_EXPLAIN_TOPOLOGY = """\
The pre-aggregated estate topology powering the Topology view:
per-scope node counts and inter-scope relationship rollups, an
O(#scopes) response that is exact at any estate size (independent of
resource count).

'available' is false when the projector has not yet materialized this
org — fall back to 'inventory list' in that case.

Example:
  limacharlie cloudsec topology
"""

_EXPLAIN_DATA_SECURITY_FACETS = """\
DSPM data-store facet counts: total/sensitive/public/public-sensitive
data stores plus store-kind, sensitivity, and exposure histograms.

The selectors cross-filter the rail (each dimension counted under the
other active selectors but not its own) and are the SAME ones 'stores'
takes, so the counts describe the population that list returns — except
for the no-tier bucket (--unclassified), which the rail skips when
counting and therefore cannot predict.

Examples:
  limacharlie cloudsec data-security facets
  limacharlie cloudsec data-security facets --store-kind bucket
"""

_EXPLAIN_DATA_SECURITY_STORES = """\
One keyset page of the org's data stores, served from the
materialized graph store under the same selectors as
'data-security facets' — so the filtered list stays exact at any
estate size instead of client-filtering a capped walk.

--sensitive / --public are tri-state: omitting one leaves the
dimension unconstrained; --no-sensitive / --no-public pin it to
false. Rows are ordered by a stable stored key, so a full walk with
--cursor is safe.

Examples:
  limacharlie cloudsec data-security stores --limit 50
  limacharlie cloudsec data-security stores --sensitive --public
  limacharlie cloudsec data-security stores --store-kind bucket --data-class pii
"""

_EXPLAIN_RESOURCE_GET = """\
Get the single canonical record for any urn the system-of-record or
security graph knows (including derived nodes like vulnerabilities
and identities that have no inventory row). Returns a null resource
when the urn is unknown.

Example:
  limacharlie cloudsec resource get "lcrn:gcp:...:bucket/prod-data"
"""

_EXPLAIN_GRAPH_NEIGHBORS = """\
Expand a resource's 1-hop neighborhood in the security graph: every
node directly connected to the urn (either direction) plus the
connecting edges. Server-bounded and ranked (sensitive -> public ->
data/identity); 'truncated' is true past the cap.

Examples:
  limacharlie cloudsec graph neighbors "lcrn:gcp:...:instance/web-1"
  limacharlie cloudsec graph neighbors "lcrn:..." --limit 500
"""

_EXPLAIN_QUERY_LIST = """\
List the named graph queries available in the query pack (name,
title, description, and the underlying DSL).

Saved org-defined queries live in the cloudsec_query hive
(limacharlie hive list --hive-name cloudsec_query).

Example:
  limacharlie cloudsec query list
"""

_EXPLAIN_QUERY_RUN = """\
Run a graph query against the org's security graph. Provide exactly
one of --named (a query-pack name), --text (a text query), or
--query-json (a raw DSL object). Returns alias->urn rows.

Examples:
  limacharlie cloudsec query run --named public_data_stores
  limacharlie cloudsec query run --text 'MATCH (d:DataStore {is_sensitive: true})<-[:has_permission_on]-(i:Identity {is_external: true}) RETURN i, d'
  limacharlie cloudsec query run --query-json '{"anchor": ...}' --project graph
"""

_EXPLAIN_COMPLIANCE_REPORT = """\
Per-control pass/fail compliance assessment against the org's open
findings, with evidence and a summary score. Defaults to the
cis-gcp framework; pass --assignment to evaluate a named scoped
assignment instead (--framework is then ignored).

Examples:
  limacharlie cloudsec compliance report
  limacharlie cloudsec compliance report --framework cis-aws
  limacharlie cloudsec compliance report --assignment prod-scope
"""

_EXPLAIN_COMPLIANCE_FRAMEWORKS = """\
List the selectable compliance frameworks (id, name, version,
control count).

Example:
  limacharlie cloudsec compliance frameworks
"""

_EXPLAIN_COMPLIANCE_ASSIGNMENTS = """\
List the org's scoped compliance assignments (name, framework,
scope, and a full scoped summary score per assignment). Empty when
the org has defined none.

Example:
  limacharlie cloudsec compliance assignments
"""

_EXPLAIN_CHOKEPOINT_LIST = """\
Estate-wide chokepoints: the shared attack-path hops ranked by how
many distinct paths each one breaks, plus the total path count — so
"fix this one resource" can be framed as "closes N of M paths".

Example:
  limacharlie cloudsec chokepoint list
"""

_EXPLAIN_CHOKEPOINT_DISMISS = """\
Dismiss an estate-wide choke point (by its resource urn) so it no
longer surfaces on the risk overview. Optionally records a reason.

Example:
  limacharlie cloudsec chokepoint dismiss "lcrn:..." --reason "planned decom"
"""

_EXPLAIN_CHOKEPOINT_RESTORE = """\
Restore (un-dismiss) a previously dismissed choke point so it
surfaces on the risk overview again.

Example:
  limacharlie cloudsec chokepoint restore "lcrn:..."
"""

_EXPLAIN_RESOLVE_SENSORS = """\
Resolve LimaCharlie sensor ids to the cloud asset (URN, with
posture flags) each runs on. Pass any number of SIDs — requests are
chunked automatically to stay within URL limits; unresolved sensors
are returned in 'unresolved'.

Example:
  limacharlie cloudsec resolve sensors <SID1> <SID2>
"""

_EXPLAIN_RESOLVE_ASSETS = """\
Resolve cloud asset URNs to the LimaCharlie sensor ids running on
each. Pass any number of URNs — requests are chunked automatically
to stay within URL limits; unresolved URNs are returned in
'unresolved'.

Example:
  limacharlie cloudsec resolve assets "lcrn:...instance/web-1"
"""

_EXPLAIN_CAASM_ASSETS = """\
The merged third-party asset inventory: every device/identity the
org's connected tools (EDR / IdP / MDM / scanners) report,
entity-resolved to one row per real asset with per-source
provenance in props.

Examples:
  limacharlie cloudsec caasm assets
  limacharlie cloudsec caasm assets -q laptop --limit 50
"""

_EXPLAIN_CAASM_COVERAGE = """\
Coverage-gap findings: assets observed by at least one connected
tool but missing a tool the org's expected-coverage policy requires
(e.g. seen by the IdP, no EDR). Same shape as 'finding list' with
the coverage_gap class stamped server-side.

Examples:
  limacharlie cloudsec caasm coverage
  limacharlie cloudsec caasm coverage --status open --severity HIGH
"""

_EXPLAIN_CAASM_POLICY_GET = """\
Get the stored expected-coverage policy. The response is the
standard resource-list shape: 'resources' holds zero rows (no
policy declared — coverage evaluation is then a no-op) or one row
whose 'props' object is the policy ({expect:[...]}).

Example:
  limacharlie cloudsec caasm policy get
"""

_EXPLAIN_CAASM_POLICY_SET = """\
Set (upsert) the expected-coverage policy: the declarative
expectations the coverage engine evaluates over the merged asset
inventory. Validated server-side; an invalid policy is rejected.

The policy can come from inline JSON, a JSON/YAML file, or stdin.

Examples:
  limacharlie cloudsec caasm policy set \\
      --policy-json '{"expect":[{"label":"edr-on-devices","capability":"edr","kinds":["device"]}]}'
  limacharlie cloudsec caasm policy set --input-file policy.yaml
  cat policy.yaml | limacharlie cloudsec caasm policy set
"""

_EXPLAIN_CAASM_INGEST = """\
Ingest a batch of raw third-party asset records into the merged
asset inventory. --source names the CAASM source the records come
from (today: sentinelone, crowdstrike, defender, okta, entraid,
ms_graph, wiz — the registry grows and is validated server-side);
records are the raw vendor-shaped JSON objects that source ships.
Re-ingesting identical records is a no-op (idempotent). Chunk large
imports — the request body is capped at 1 MiB.

Examples:
  limacharlie cloudsec caasm ingest --source okta --records-file users.json
  limacharlie cloudsec caasm ingest --source crowdstrike --record-json '{...}'
"""

_EXPLAIN_FLEET_OVERVIEW = """\
Multi-org fleet posture board in one call: one posture row per
authorized org (score, severity distribution, trend direction,
coverage/freshness, usage counters) plus, on the first page, the
cross-tenant rollups (widely-recurring rules, fleet risk
distribution, orgs with failing providers).

The org set is every org your credentials can see — narrowed with
--oid (repeatable) and/or an org --group — intersected with the orgs
where you hold cloudsec.get and that are subscribed to the
cloud-security extension. Orgs failing either filter are silently
excluded and counted in 'skipped'. With user-scoped credentials the
CLI mints a temporary multi-org token for the call, so the fleet is
NOT limited to the configured --oid.

Keyset-paginated by org (default 25, cap 100); the resolved org set
is capped at 500 — narrow with --oid or --group past that.

Examples:
  limacharlie cloudsec fleet overview
  limacharlie cloudsec fleet overview --group <GROUP_ID> --trend-days 90
  limacharlie cloudsec fleet overview --oid <OID1> --oid <OID2>
"""

_EXPLAIN_PROVIDER_MANIFEST = """\
Per-provider coverage manifests: for each provider, the collectors
(resource kinds + edge kinds) with their status, the posture checks
that can fire, the activity/CIEM support level, the validation
grade, the known gaps, and the org's own scan coverage/freshness —
the honest picture of what the platform CAN collect merged with what
THIS org's connection actually got.

Pass --type to fetch a single provider's manifest (returned under
'manifest' instead of 'manifests'), including a provider the org has
never swept.

Examples:
  limacharlie cloudsec provider manifest
  limacharlie cloudsec provider manifest --type gcp
"""

_EXPLAIN_EXPORT_FINDINGS = """\
Export the (filtered) findings worklist as CSV. The server walks the
FULL filtered set (no pagination), capped at 100k rows — a trailing
'#' comment row marks a truncated export. Takes the same filters as
'finding list'.

Examples:
  limacharlie cloudsec export findings -o findings.csv
  limacharlie cloudsec export findings --severity CRITICAL --status open
"""

_EXPLAIN_EXPORT_INVENTORY = """\
Export the (filtered) cloud resource inventory as CSV. The server
walks the full filtered set (no pagination), capped at 100k rows.
Takes the same filters as 'inventory list'.

Examples:
  limacharlie cloudsec export inventory -o inventory.csv
  limacharlie cloudsec export inventory --provider okta
"""

_EXPLAIN_EXPORT_COMPLIANCE = """\
Export a compliance assessment as CSV. Takes the same selectors as
'compliance report' (--framework, or --assignment for a scoped
assignment).

Examples:
  limacharlie cloudsec export compliance -o cis-gcp.csv
  limacharlie cloudsec export compliance --framework cis-aws -o cis-aws.csv
"""

_EXPLAIN_EXPORT_QUERY = """\
Run a graph query and export the rows as CSV. Takes the same query
selectors as 'query run' (exactly one of --named / --text /
--query-json).

Examples:
  limacharlie cloudsec export query --named public_data_stores -o rows.csv
  limacharlie cloudsec export query --text 'MATCH (d:DataStore {is_sensitive: true})<-[:has_permission_on]-(i:Identity {is_external: true}) RETURN i, d'
"""

_EXPLAIN_PROVIDER_TEST = """\
Preflight a cloud provider configuration before saving it: connect
to the provider with the given credentials (ephemeral — never
stored) and probe every permission surface collection needs.
report.ok is the overall verdict over the REQUIRED checks; a failed
optional check flags a gracefully-degraded surface, not a failure.

The input is a cloudsec_provider hive record shape; 'credentials'
may be inline plaintext or a hive://secret/<name> reference. Saved
provider configs are managed via the hive:

  limacharlie hive set --hive-name cloudsec_provider --key my-gcp \\
      --input-file provider.json --enabled

The record can come from inline JSON, a JSON/YAML file, or stdin.

Examples:
  limacharlie cloudsec provider test --input-file provider.yaml
  limacharlie cloudsec provider test --provider-json '{"provider_type":"gcp",...}'
"""

_EXPLAIN_POLICY_VOCABULARY = """\
The server-driven vocabulary that the cloudsec_policy rule form
(Data Classification / Coverage / Exclusions) renders against: the
per-surface capability table (which matcher dimensions each policy
surface honors), the closed vocabularies (resource types grouped per
section, providers, criticality tiers, content classes, suggested
classes), and the org's in-use histograms (accounts, regions, label
keys, network tags, resource types) — so you author against real
tokens instead of guessing.

The policies themselves are hive records (limacharlie hive list
--hive-name cloudsec_policy).

Example:
  limacharlie cloudsec policy vocabulary
"""

_EXPLAIN_POLICY_SUGGEST = """\
Live matcher-value autocomplete from the org's own inventory (the
companion to 'policy vocabulary' for the high-cardinality
dimensions).

--dimension is one of:
  name     walk the estate's policy-matchable resources for names
           containing the typed --q
  account  filter the account facet by --q

--target optionally narrows the walked resource family to the rule
set being edited (data_store | compute | identity | any).

Examples:
  limacharlie cloudsec policy suggest --dimension name -q prod
  limacharlie cloudsec policy suggest --dimension account -q 1234 --limit 10
  limacharlie cloudsec policy suggest --dimension name -q data --target data_store
"""

_EXPLAIN_SIMULATE_RESOURCES = """\
"Simulate" preflight: evaluate a set of cloudsec_policy resource
matcher rules (account_contains / account_glob / name_contains /
name_glob / label / label_key_present / tag — rules compose as OR)
against the org's stored inventory BEFORE you save them, so a
glob/label typo is visible as an actionable result instead of a
silent "matches nothing" after the next sweep. Read-only: nothing is
saved.

Returns evaluated / matched / indeterminate counts, a bounded sample
of matching resources, and truncated=true when the walk hit its
size/time bound. 'indeterminate' counts resources whose stored row
cannot evaluate a label constraint (their type does not persist
labels).

--target (data_store | compute | identity | any, default any) scopes
the walked resource family to the rule set being edited. The rules
come from inline JSON, a JSON/YAML file, or stdin (a JSON array of
rule objects).

Examples:
  limacharlie cloudsec simulate resources \\
      --rules-json '[{"name_glob":"prod-*"}]' --target data_store
  limacharlie cloudsec simulate resources --input-file rules.yaml
  cat rules.json | limacharlie cloudsec simulate resources
"""

_EXPLAIN_SIMULATE_FINDINGS = """\
"Simulate" preflight: evaluate a suppression-policy matcher
(finding_class / rule / account globs / urn_prefix / max_severity)
against the org's OPEN findings using the exact matching semantics
the suppression engine applies, so you see what a rule would
disposition before saving it. Read-only: nothing is dispositioned.

An EMPTY match is allowed — it matches everything up to the default
severity ceiling, and showing that blast radius is the point.

The match object comes from inline JSON, a JSON/YAML file, or stdin.

Examples:
  limacharlie cloudsec simulate findings \\
      --match-json '{"finding_class":"misconfig","max_severity":"LOW"}'
  limacharlie cloudsec simulate findings --input-file match.yaml
"""

register_explain("cloudsec.overview", _EXPLAIN_OVERVIEW)
register_explain("cloudsec.changes", _EXPLAIN_CHANGES)
register_explain("cloudsec.risk-trend", _EXPLAIN_RISK_TREND)
register_explain("cloudsec.scan-status", _EXPLAIN_SCAN_STATUS)
register_explain("cloudsec.topology", _EXPLAIN_TOPOLOGY)
register_explain("cloudsec.free-tier", _EXPLAIN_FREE_TIER)
register_explain("cloudsec.finding.list", _EXPLAIN_FINDING_LIST)
register_explain("cloudsec.finding.facets", _EXPLAIN_FINDING_FACETS)
register_explain("cloudsec.finding.causes", _EXPLAIN_FINDING_CAUSES)
register_explain("cloudsec.finding.classes", _EXPLAIN_FINDING_CLASSES)
register_explain("cloudsec.finding.get", _EXPLAIN_FINDING_GET)
register_explain("cloudsec.finding.resolve", _EXPLAIN_FINDING_RESOLVE)
register_explain("cloudsec.finding.bulk-resolve", _EXPLAIN_FINDING_BULK_RESOLVE)
register_explain("cloudsec.finding.set-owner", _EXPLAIN_FINDING_SET_OWNER)
register_explain("cloudsec.finding.set-ticket", _EXPLAIN_FINDING_SET_TICKET)
register_explain("cloudsec.attack-path.list", _EXPLAIN_ATTACK_PATH_LIST)
register_explain("cloudsec.ciem.public-access", _EXPLAIN_CIEM_PUBLIC_ACCESS)
register_explain("cloudsec.ciem.facets", _EXPLAIN_CIEM_FACETS)
register_explain("cloudsec.ciem.identity", _EXPLAIN_CIEM_IDENTITY)
register_explain("cloudsec.ciem.identities", _EXPLAIN_CIEM_IDENTITIES)
register_explain("cloudsec.inventory.list", _EXPLAIN_INVENTORY_LIST)
register_explain("cloudsec.inventory.facets", _EXPLAIN_INVENTORY_FACETS)
register_explain("cloudsec.data-security.facets", _EXPLAIN_DATA_SECURITY_FACETS)
register_explain("cloudsec.data-security.stores", _EXPLAIN_DATA_SECURITY_STORES)
register_explain("cloudsec.resource.get", _EXPLAIN_RESOURCE_GET)
register_explain("cloudsec.graph.neighbors", _EXPLAIN_GRAPH_NEIGHBORS)
register_explain("cloudsec.query.list", _EXPLAIN_QUERY_LIST)
register_explain("cloudsec.query.run", _EXPLAIN_QUERY_RUN)
register_explain("cloudsec.compliance.report", _EXPLAIN_COMPLIANCE_REPORT)
register_explain("cloudsec.compliance.frameworks", _EXPLAIN_COMPLIANCE_FRAMEWORKS)
register_explain("cloudsec.compliance.assignments", _EXPLAIN_COMPLIANCE_ASSIGNMENTS)
register_explain("cloudsec.chokepoint.list", _EXPLAIN_CHOKEPOINT_LIST)
register_explain("cloudsec.chokepoint.dismiss", _EXPLAIN_CHOKEPOINT_DISMISS)
register_explain("cloudsec.chokepoint.restore", _EXPLAIN_CHOKEPOINT_RESTORE)
register_explain("cloudsec.resolve.sensors", _EXPLAIN_RESOLVE_SENSORS)
register_explain("cloudsec.resolve.assets", _EXPLAIN_RESOLVE_ASSETS)
register_explain("cloudsec.caasm.assets", _EXPLAIN_CAASM_ASSETS)
register_explain("cloudsec.caasm.coverage", _EXPLAIN_CAASM_COVERAGE)
register_explain("cloudsec.caasm.policy.get", _EXPLAIN_CAASM_POLICY_GET)
register_explain("cloudsec.caasm.policy.set", _EXPLAIN_CAASM_POLICY_SET)
register_explain("cloudsec.caasm.ingest", _EXPLAIN_CAASM_INGEST)
register_explain("cloudsec.provider.test", _EXPLAIN_PROVIDER_TEST)
register_explain("cloudsec.provider.manifest", _EXPLAIN_PROVIDER_MANIFEST)
register_explain("cloudsec.policy.vocabulary", _EXPLAIN_POLICY_VOCABULARY)
register_explain("cloudsec.policy.suggest", _EXPLAIN_POLICY_SUGGEST)
register_explain("cloudsec.simulate.resources", _EXPLAIN_SIMULATE_RESOURCES)
register_explain("cloudsec.simulate.findings", _EXPLAIN_SIMULATE_FINDINGS)
register_explain("cloudsec.fleet.overview", _EXPLAIN_FLEET_OVERVIEW)
register_explain("cloudsec.export.findings", _EXPLAIN_EXPORT_FINDINGS)
register_explain("cloudsec.export.inventory", _EXPLAIN_EXPORT_INVENTORY)
register_explain("cloudsec.export.compliance", _EXPLAIN_EXPORT_COMPLIANCE)
register_explain("cloudsec.export.query", _EXPLAIN_EXPORT_QUERY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_cloudsec(ctx: click.Context) -> CloudSec:
    client = Client(
        oid=ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
    )
    org = Organization(client)
    return CloudSec(org)


def _parse_json_opt(value: str | None, param_hint: str) -> Any:
    """Parse a JSON CLI option value, raising a clean usage error."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"invalid JSON: {exc}", param_hint=param_hint)


from ._input_helpers import load_file as _load_file, load_stdin as _load_stdin


def _one_of(param_hint: str, **provided: Any) -> None:
    """Require exactly one of the given options to be set, and non-empty.

    ``None`` means absent; an explicit empty string is an error (either as
    the single provided option, or alongside a real one — both are
    ambiguous invocations worth rejecting, not guessing about).
    """
    given = [k for k, v in provided.items() if v is not None]
    if len(given) != 1:
        names = ", ".join(f"--{k.replace('_', '-')}" for k in provided)
        raise click.UsageError(
            f"provide exactly one of {names} for {param_hint}",
        )
    if not provided[given[0]]:
        raise click.BadParameter(
            "must not be empty", param_hint=f"--{given[0].replace('_', '-')}",
        )


def _load_json_object_arg(
    *,
    inline: str | None,
    inline_hint: str,
    input_file: str | None,
    file_hint: str,
    what: str,
    shape_msg: str,
) -> dict[str, Any]:
    """Load a required JSON-object argument from inline JSON, a file, or stdin.

    At most one of the inline/file options may be set; with neither, piped
    stdin is read (YAML or JSON). The result must be an object — a `null`
    or non-object input is rejected here rather than reaching the server.
    """
    if inline is not None and input_file is not None:
        raise click.UsageError(
            f"provide only one of {inline_hint} or {file_hint} for {what}",
        )
    if inline is not None:
        if not inline.strip():
            raise click.BadParameter("must not be empty", param_hint=inline_hint)
        value = _parse_json_opt(inline, inline_hint)
        hint = inline_hint
    elif input_file is not None:
        value = _load_file(input_file, file_hint)
        hint = file_hint
    else:
        value = _load_stdin()
        hint = "stdin"
        if value is None:
            raise click.UsageError(
                f"provide {inline_hint}, {file_hint}, or pipe {what} via stdin",
            )
    if not isinstance(value, dict):
        raise click.BadParameter(shape_msg, param_hint=hint)
    return value


def _load_json_array_arg(
    *,
    inline: str | None,
    inline_hint: str,
    input_file: str | None,
    file_hint: str,
    what: str,
    shape_msg: str,
) -> list[Any]:
    """Load a required JSON-array argument from inline JSON, a file, or stdin.

    The list-shaped sibling of :func:`_load_json_object_arg` (used for the
    simulate rule set). At most one of the inline/file options may be set;
    with neither, piped stdin is read (YAML or JSON). The result must be a
    list — a `null` or non-list input is rejected here rather than reaching
    the server.
    """
    if inline is not None and input_file is not None:
        raise click.UsageError(
            f"provide only one of {inline_hint} or {file_hint} for {what}",
        )
    if inline is not None:
        if not inline.strip():
            raise click.BadParameter("must not be empty", param_hint=inline_hint)
        value = _parse_json_opt(inline, inline_hint)
        hint = inline_hint
    elif input_file is not None:
        value = _load_file(input_file, file_hint)
        hint = file_hint
    else:
        value = _load_stdin()
        hint = "stdin"
        if value is None:
            raise click.UsageError(
                f"provide {inline_hint}, {file_hint}, or pipe {what} via stdin",
            )
    if not isinstance(value, list):
        raise click.BadParameter(shape_msg, param_hint=hint)
    return value


# Resolution kinds are a fixed server contract; 'open' (reopen) is only
# accepted by the single-finding endpoint, not the bulk one.
_KIND_CHOICES = click.Choice(
    ["mitigated", "accepted", "false_positive", "open"], case_sensitive=False,
)
_BULK_KIND_CHOICES = click.Choice(
    ["mitigated", "accepted", "false_positive"], case_sensitive=False,
)
_ORDER_CHOICES = click.Choice(["asc", "desc"], case_sensitive=False)
# The policy-authoring walk-type filter and suggest dimension ARE fixed,
# small, closed server contracts (unlike the growing provider/source
# registries) — a click.Choice gives clean up-front validation and tab
# completion without pinning a moving target.
_SIMULATE_TARGET_CHOICES = click.Choice(
    ["data_store", "compute", "identity", "any"], case_sensitive=False,
)
_SUGGEST_DIMENSION_CHOICES = click.Choice(
    ["name", "account"], case_sensitive=False,
)
# The identity MFA selector is three-state by contract ("unknown" is not
# "off"), and the set is closed server-side — a Choice keeps a typo from
# reading as "no MFA constraint".
_MFA_CHOICES = click.Choice(["on", "off", "unknown"], case_sensitive=False)
# Risk bands partition the whole score space and criticality tiers are a
# fixed assign-side vocabulary, so both are closed sets like --kind is not.
# They get a Choice because the backend fails CLOSED on an unknown value:
# an unrecognized band contributes a FALSE predicate and a misspelled tier
# matches no row, so a typo would exit 0 with an empty result under a
# filter the user can see is applied — the worst of both answers.
_RISK_BAND_CHOICES = click.Choice(
    ["critical", "high", "medium", "low"], case_sensitive=False,
)
_TIER_CHOICES = _RISK_BAND_CHOICES
# Provider and CAASM-source values are deliberately NOT click.Choice lists:
# both are growing server-side registries (new providers/sources ship without
# a CLI release) and the server rejects unknown values with a clean error.


def _paging_options(f):
    f = click.option(
        "--limit", default=None, type=int,
        help="Page size (server clamps to 1000).",
    )(f)
    f = click.option(
        "--cursor", default=None,
        help="Keyset-pagination token (next_cursor from the previous page).",
    )(f)
    return f


def _selector_with_empty(values, include_empty: bool) -> list[str] | None:
    """Fold a "…or none of them" flag into a repeatable wire selector.

    Several dimensions express "not set" as the EMPTY value rather than
    as a separate parameter: an unowned finding, an unclassified
    criticality tier. That value rides the same repeatable selector, so
    "mine or nobody's" is one filter with two values. No selection at
    all returns None, so the request carries no constraint on the
    dimension (an empty list would narrow it to the not-set bucket).
    """
    out = list(values)
    if include_empty:
        out.append("")
    return out or None


def _finding_filter_options(f):
    """The findings worklist filter selectors (shared by list/facets).

    Click stacks decorators bottom-up, so the option that should show
    first in --help is applied last.
    """
    f = click.option(
        "-q", "--search", "q", default=None,
        help="Substring search over the findings.",
    )(f)
    f = click.option(
        "--unassigned", is_flag=True, default=False,
        help="Include findings with no owner (the untriaged bucket); "
             "combines with --owner.",
    )(f)
    f = click.option(
        "--sla", "sla_states", multiple=True,
        help="Filter by remediation-SLA state; repeatable (OR): breached, "
             "due_soon, on_track, exempt (the finding is not open, so the "
             "clock does not report on it), none (no SLA clause covers it). "
             "There is no built-in default SLA, so every finding reads "
             "'none' until the org writes an 'sla' cloudsec_policy record.",
    )(f)
    f = click.option(
        "--owner", "owners", multiple=True,
        help="Filter by assigned owner; repeatable (OR). Use --unassigned "
             "for findings nobody owns.",
    )(f)
    f = click.option(
        "--kev/--no-kev", "kev", default=None,
        help="Only findings with (without) a KEV vulnerability.",
    )(f)
    f = click.option(
        "--reachable/--no-reachable", "reachable", default=None,
        help="Only findings on (non-)reachable resources.",
    )(f)
    f = click.option(
        "--repo", "repos", multiple=True,
        help="Filter to findings about a source repository, keyed "
             "'<owner>/<name>' as 'cloudsec code repos' returns it; "
             "repeatable (OR). This is the AppSec code lane's selector — "
             "cloud findings have no repository, so any --repo excludes "
             "them, and an unknown repository returns nothing rather than "
             "everything.",
    )(f)
    f = click.option(
        "--account", "accounts", multiple=True,
        help="Filter by cloud account; repeatable (OR).",
    )(f)
    f = click.option(
        "--status", "statuses", multiple=True,
        help="Filter by status (open/resolved/accepted); repeatable (OR). "
             "'accepted' is a live risk acceptance (the risk remains, on purpose); "
             "'resolved' means mitigated or false-positive.",
    )(f)
    f = click.option(
        "--class", "finding_classes", multiple=True,
        help="Filter by finding class (e.g. toxic_combination, misconfig); repeatable (OR).",
    )(f)
    f = click.option(
        "--severity", "severities", multiple=True,
        help="Filter by severity (CRITICAL/HIGH/MEDIUM/LOW/INFO); repeatable (OR).",
    )(f)
    return f


def _inventory_filter_options(f):
    """The inventory filter selectors (shared by list/export)."""
    f = click.option(
        "--all-accounts", "all_accounts", is_flag=True, default=False,
        help="Escape hatch: drop the per-account scoping and span the "
             "whole estate (the account-scoped default holds otherwise).",
    )(f)
    f = click.option(
        "-q", "--search", "q", default=None, help="Substring search.",
    )(f)
    f = click.option(
        "--region", default=None, help="Filter by region.",
    )(f)
    f = click.option(
        "--account", default=None, help="Filter by cloud account.",
    )(f)
    f = click.option(
        "--provider", default=None,
        help="Filter by the producing provider sweep (e.g. gcp, okta, google_workspace).",
    )(f)
    f = click.option(
        "--type", "resource_type", default=None, help="Filter by resource type.",
    )(f)
    return f


def _identity_filter_options(f):
    """The merged-identity cross-filter (shared by ciem facets/identities).

    One decorator for both routes on purpose: a dimension that reaches
    the list and not the rail is how a facet count stops describing the
    list it annotates. The boolean flags are tri-state — omitted leaves
    the dimension unconstrained, which is not the same as pinning it
    false, which is why every one of them defaults to None rather than
    being an is_flag.
    """
    f = click.option(
        "-q", "--search", "q", default=None,
        help="Substring filter over the identity's urn/email/kind.",
    )(f)
    for opt, help_text in [
        ("--with-sensitive/--no-with-sensitive",
         "Holds (or not) at least one non-deny grant on a sensitive resource."),
        ("--dormant-90d/--no-dormant-90d",
         "No observed activity in 90 days (or some)."),
        ("--can-escalate/--no-can-escalate",
         "Can (or cannot) escalate its own privileges."),
        ("--crown-jewel/--no-crown-jewel",
         "Declared sensitive by the org's cloudsec_policy (or not) — the "
         "flag any matching rule sets, independent of whether that rule "
         "also assigned a tier (see --criticality)."),
        ("--disabled/--no-disabled", "Disabled (or enabled) identities."),
        ("--public/--no-public",
         "Public principals (allUsers / allAuthenticatedUsers and "
         "equivalents), or not."),
        ("--external/--no-external",
         "Outside (or inside) the org's own domains."),
        ("--admin/--no-admin", "Holds (or does not hold) an admin role."),
    ]:
        f = click.option(
            opt, default=None, help=f"{help_text} Omit for no constraint.",
        )(f)
    f = click.option(
        "--mfa", default=None, type=_MFA_CHOICES,
        help="MFA state: on | off | unknown. 'unknown' is everyone the "
             "question does not apply to (no IdP observation, or non-human) "
             "— it is NOT 'off'.",
    )(f)
    f = click.option(
        "--risk-band", "risk_bands", multiple=True, type=_RISK_BAND_CHOICES,
        help="Filter by risk band; repeatable (OR). The band token the rail "
             "renders, not a numeric range.",
    )(f)
    f = click.option(
        "--unclassified", "unclassified", is_flag=True, default=False,
        help="Include identities with no TIER assigned; combines with "
             "--criticality. Wider than --no-crown-jewel: a declared crown "
             "jewel whose policy rule sets no tier lands here too. The "
             "criticality facet does not count this bucket, so 'facets' "
             "cannot predict how many rows it returns.",
    )(f)
    f = click.option(
        "--criticality", "criticalities", multiple=True, type=_TIER_CHOICES,
        help="Filter by assigned criticality tier; repeatable (OR). The tier "
             "a cloudsec_policy rule assigned, which is a different column "
             "from the crown-jewel flag --crown-jewel reads. Use "
             "--unclassified for identities with no tier.",
    )(f)
    f = click.option(
        "--kind", "kinds", multiple=True,
        help="Filter by identity kind (user, service_account, group, "
             "ai_agent, ...); repeatable (OR).",
    )(f)
    f = click.option(
        "--region", "regions", multiple=True,
        help="Filter by region; repeatable (OR). Served from the projector's "
             "merged view — fails loudly on a tenant whose view is unbuilt.",
    )(f)
    f = click.option(
        "--account", "accounts", multiple=True,
        help="Filter by account/project; repeatable (OR). Served from the "
             "merged view, like --region.",
    )(f)
    f = click.option(
        "--source", "sources", multiple=True,
        help="Filter by producing sweep (okta, gcp, google_workspace, ...); "
             "repeatable (OR). Same dimension 'inventory list' calls "
             "--provider.",
    )(f)
    return f


def _data_store_filter_options(f):
    """The Data Security cross-filter (shared by data-security facets/stores).

    Shared for the same reason as the identity filter: the facet counts
    must describe the population the store list returns. The one value
    this cannot cover is the empty tier, which the facet pass skips.
    """
    f = click.option(
        "-q", "--search", "q", default=None,
        help="Substring filter over the store's name/urn.",
    )(f)
    f = click.option(
        "--public/--no-public", "exposure", default=None,
        help="The 'exposure' dimension: only publicly-exposed (or only "
             "non-public) stores. Omit for no constraint.",
    )(f)
    f = click.option(
        "--sensitive/--no-sensitive", "sensitivity", default=None,
        help="The 'sensitivity' dimension: only sensitive (or only "
             "non-sensitive) stores. Omit for no constraint.",
    )(f)
    f = click.option(
        "--data-class", "data_classes", multiple=True,
        help="Filter by content class (pii, secrets, ...); repeatable (OR).",
    )(f)
    f = click.option(
        "--unclassified", "unclassified", is_flag=True, default=False,
        help="Include stores with no criticality tier assigned; combines "
             "with --tier. The tier facet does not count this bucket, so "
             "'facets' cannot predict how many rows it returns.",
    )(f)
    f = click.option(
        "--tier", "tiers", multiple=True, type=_TIER_CHOICES,
        help="Filter by criticality tier; repeatable (OR). Use "
             "--unclassified for stores with no tier.",
    )(f)
    f = click.option(
        "--store-kind", "store_kinds", multiple=True,
        help="Filter by store kind (bucket, sql_instance, ...); "
             "repeatable (OR).",
    )(f)
    f = click.option(
        "--region", "regions", multiple=True,
        help="Filter by region; repeatable (OR).",
    )(f)
    f = click.option(
        "--account", "accounts", multiple=True,
        help="Filter by account/project; repeatable (OR).",
    )(f)
    f = click.option(
        "--provider", "providers", multiple=True,
        help="Filter by provider; repeatable (OR).",
    )(f)
    return f


def _sort_options(f):
    f = click.option(
        "--order", default=None, type=_ORDER_CHOICES,
        help="Sort order: desc (default) or asc.",
    )(f)
    f = click.option(
        "--sort", default=None,
        help="Sort key: lc_risk (default), severity, first_seen, or due_at. "
             "due_at is the one key that defaults to ASCENDING (soonest due "
             "first) and puts findings with no due date last, not out.",
    )(f)
    return f


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("cloudsec")
def group() -> None:
    """Cloud Security (CNAPP): findings, inventory, graph, compliance.

    Requires the org to be subscribed to the ext-cloud-security
    extension. Reads need the 'cloudsec.get' permission; triage and
    other writes need 'cloudsec.set'. Provider configs and policies
    are hive records (cloudsec_provider / cloudsec_policy hives).

    \b
    Subgroups / commands:
      overview            Composed risk overview (score, top paths, trend)
      changes             Recent finding created/closed feed
      risk-trend          Risk-score history
      scan-status         Cloud-collection run status per provider
      topology            Pre-aggregated estate topology (exact at scale)
      free-tier           Free-tier standing and the limits that apply
      fleet overview      Multi-org fleet posture board (MSSP)
      finding ...         Findings worklist + triage (resolve, owner, ticket, causes, classes)
      attack-path list    Headline toxic-combination attack paths
      ciem ...            Identity access (public-access, facets, identities, identity)
      inventory ...       Cloud resource inventory
      data-security ...   DSPM data-store facets + store list
      resource get        Canonical record for any urn
      graph neighbors     1-hop graph expansion around a urn
      query ...           Graph queries (list pack, run)
      compliance ...      Framework assessment, frameworks, assignments
      chokepoint ...      Estate-wide chokepoints (list, dismiss, restore)
      resolve ...         Sensor <-> cloud asset resolution
      code ...            AppSec code lane (repos, status, sbom)
      caasm ...           Third-party asset inventory, coverage, ingest
      provider ...        Credential preflight + coverage manifests
      policy ...          cloudsec_policy vocabulary + autocomplete
      simulate ...        Preview a policy matcher (resources, findings)
      export ...          CSV exports (findings, inventory, compliance, query)
    """


# ---------------------------------------------------------------------------
# Top-level reads
# ---------------------------------------------------------------------------

@group.command("overview")
@click.option("--trend-days", default=None, type=int, help="Days of score trend to include (default 30).")
@pass_context
def overview(ctx, trend_days) -> None:
    """Composed risk overview for the org.

    \b
    Example:
      limacharlie cloudsec overview --trend-days 90
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_overview(trend_days=trend_days))


@group.command("changes")
@click.option("--limit", default=None, type=int, help="Max change events (default 50).")
@pass_context
def changes(ctx, limit) -> None:
    """Recent finding lifecycle changes (created/closed), newest first.

    \b
    Example:
      limacharlie cloudsec changes --limit 100
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_changes(limit=limit))


@group.command("risk-trend")
@click.option("--trend-days", default=None, type=int, help="Days of score trend to include (default 30).")
@pass_context
def risk_trend(ctx, trend_days) -> None:
    """The org's risk-score history, oldest first.

    \b
    Example:
      limacharlie cloudsec risk-trend --trend-days 90
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_risk_trend(trend_days=trend_days))


@group.command("scan-status")
@click.option("--provider", default=None,
              help="Cloud provider (e.g. gcp, aws, azure, okta, entra, "
                   "google_workspace, 1password, cloudflare, auth0, github, "
                   "openai, anthropic, limacharlie); validated server-side; "
                   "default gcp.")
@pass_context
def scan_status(ctx, provider) -> None:
    """Cloud-collection run status for a provider.

    \b
    Example:
      limacharlie cloudsec scan-status --provider aws
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_scan_status(provider=provider))


@group.command("topology")
@pass_context
def topology(ctx) -> None:
    """Pre-aggregated estate topology (exact at any scale).

    \b
    Example:
      limacharlie cloudsec topology
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_topology())


@group.command("free-tier")
@pass_context
def free_tier(ctx) -> None:
    """Free-tier standing and the limits that apply to the org.

    \b
    Example:
      limacharlie cloudsec free-tier
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_free_tier())


# ---------------------------------------------------------------------------
# code subgroup (AppSec code lane)
# ---------------------------------------------------------------------------

@group.group("code")
def code_group() -> None:
    """AppSec code lane: repositories, scan status, SBOM export.

    The lane scans a connected source-control organization's repositories
    and emits findings into the same worklist the cloud collectors feed,
    so the findings themselves are read with 'cloudsec finding list
    --repo <owner>/<name>'. The commands here are the repository-shaped
    views that worklist cannot give you.
    """


@code_group.command("repos")
@click.option("-q", "--search", "q", default=None,
              help="Substring over the repository key and urn.")
@click.option("--with-findings/--without-findings", "has_findings", default=None,
              help="Only repositories that do (or do not) have at least one "
                   "OPEN finding. Omit for no constraint — note that "
                   "--without-findings is a real selection, not 'no filter'.")
@click.option("--provider", default=None,
              help="Source-control provider (e.g. github). Omit for all.")
@click.option("--all", "walk_all", is_flag=True, default=False,
              help="Follow the cursor and return EVERY matching repository "
                   "instead of one page. Filtered pages can be short without "
                   "being last, so this is the safe way to get a full list.")
@_paging_options
@pass_context
def code_repos(ctx, q, has_findings, provider, walk_all, cursor, limit) -> None:
    """List the org's repositories with their scan state and finding counts.

    Each row carries 'repo' (the '<owner>/<name>' key the other code
    commands take), the connector's view of the repository, the code-scan
    state, and the OPEN finding rollup.

    'scan_status' is scanned, partial or unknown. 'partial' means the scan
    tripped a limit, so the finding set is INCOMPLETE — not a clean bill.
    'unknown' means this view has no scan state for the repository and says
    so rather than guessing; 'cloudsec code status' is the authoritative
    view of the run.

    \b
    Examples:
      limacharlie cloudsec code repos
      limacharlie cloudsec code repos --with-findings --all
      limacharlie cloudsec code repos -q appsec-fixtures
    """
    cs = _get_cloudsec(ctx)
    if walk_all:
        repos = list(cs.iter_code_repos(
            q=q, has_findings=has_findings, provider=provider, limit=limit))
        _output(ctx, {"repos": repos, "next_cursor": ""})
        return
    _output(ctx, cs.list_code_repos(
        q=q, has_findings=has_findings, provider=provider,
        cursor=cursor, limit=limit,
    ))


@code_group.command("status")
@pass_context
def code_status(ctx) -> None:
    """Code-lane run status per source-control connection, plus totals.

    An empty 'code' list means the lane has never run in this org. It does
    NOT mean the lane is off — that is the org's code_scanning
    cloudsec_policy record, not this call.

    \b
    Example:
      limacharlie cloudsec code status
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_code_status())


@code_group.command("sbom")
@click.option("--repo", required=True,
              help="Repository key '<owner>/<name>' as 'code repos' returns it.")
@click.option("--provider", default=None,
              help="Source-control provider the key belongs to (default github).")
@click.option("-o", "--output", "output_path", default=None,
              help="Download the SBOM document to this path (gzipped "
                   "CycloneDX). Omit to print the signed link and its "
                   "metadata instead.")
@pass_context
def code_sbom(ctx, repo, provider, output_path) -> None:
    """Get a repository's SBOM: the signed link, or the document itself.

    A repository with no SBOM yet is not an error — the command reports the
    reason (the first scan has not completed, or the lane is not enabled in
    this datacenter) and exits non-zero only when -o was requested, since
    there is then nothing to write.

    The link is short-lived and leaves the API's auth boundary, so fetch it
    promptly and do not store it.

    \b
    Examples:
      limacharlie cloudsec code sbom --repo refractionPOINT/lc-appsec-fixtures
      limacharlie cloudsec code sbom --repo acme/api -o api-sbom.json.gz
    """
    cs = _get_cloudsec(ctx)
    if not output_path:
        _output(ctx, cs.get_code_sbom(repo, provider=provider))
        return
    body = cs.download_code_sbom(repo, provider=provider)
    if body is None:
        # Report WHY, from the same response the download consulted, rather
        # than writing an empty file that looks like an SBOM of nothing.
        resp = cs.get_code_sbom(repo, provider=provider)
        raise click.ClickException(
            "no SBOM available for %s (%s)"
            % (repo, resp.get("reason") or "unknown reason"))
    with open(output_path, "wb") as f:
        f.write(body)
    _output(ctx, {"repo": repo, "written": output_path, "size_bytes": len(body)})


@code_group.command("ingest")
@click.option("--repo", required=True,
              help="Repository key '<owner>/<name>' as 'code repos' returns it.")
@click.option("--source", required=True,
              type=click.Choice(["sarif", "cyclonedx", "report"]),
              help="Format of the document: a SARIF results file, a CycloneDX "
                   "bill of materials, or the LimaCharlie scanner's own "
                   "report/v1 document.")
@click.option("-f", "--file", "file_path", required=True,
              help="Path to the document. A '.gz' file is sent compressed.")
@click.option("--commit", default=None,
              help="The revision the document describes. Recorded, not verified.")
@click.option("--ref", default=None, help="The branch or tag, for context.")
@click.option("--provider", default=None,
              help="Source-control provider the key belongs to (default github).")
@pass_context
def code_ingest(ctx, repo, source, file_path, commit, ref, provider) -> None:
    """Push scan results your own pipeline produced for one repository.

    Findings are deduplicated against the hosted scan by IDENTITY, so
    pushing something the hosted scanner also found updates it rather than
    duplicating it, and re-pushing an identical document writes nothing.

    Two things in the response are worth reading rather than skimming.
    'notes' lists what the FORMAT could not carry — 'secrets_not_ingestable'
    means credential findings were deliberately dropped, because a pushed
    document cannot carry the keyed digest a secret is identified by and the
    plaintext is never accepted. And 'closed' counts findings THIS source
    previously reported and no longer does; a pushed document can never
    close what the hosted scanner found.

    \b
    Examples:
      limacharlie cloudsec code ingest --repo acme/api --source sarif -f trivy.sarif
      limacharlie cloudsec code ingest --repo acme/api --source report -f report.json.gz \\
          --commit "$GITHUB_SHA"
    """
    with open(file_path, "rb") as f:
        document = f.read()
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.ingest_code_results(
        repo, source, document, commit=commit, ref=ref, provider=provider))


@code_group.command("scan")
@click.argument("path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--repo", default=None,
              help="Repository key '<owner>/<name>' to attribute the results to. "
                   "Required with --ingest; inferred from the checkout's git "
                   "origin when it can be.")
@click.option("--commit", default=None,
              help="The revision scanned. Read from the checkout when omitted.")
@click.option("--ingest/--no-ingest", "do_ingest", default=False,
              help="Push the report to LimaCharlie when the scan finishes.")
@click.option("--image", "image", default=None,
              help="Scanner image to run (default: the published lc-code-scanner).")
@click.option("--binary", "binary", default=None,
              help="Run this scanner-agent binary instead of the container.")
@click.option("-o", "--output", "output_path", default=None,
              help="Write the report here (default: a temporary file).")
@click.option("--scanners", default="sca,iac,licenses",
              help="Comma-separated scanners to run. 'secrets' is OFF by default "
                   "on purpose — see the command help.")
@click.option("--timeout", "timeout_s", default=1800, show_default=True,
              help="Seconds to allow the scan.")
@click.option("--db-repo", "db_repo", default=DEFAULT_TRIVY_DB_REPO, show_default=True,
              help="Vulnerability database to scan against.")
@click.option("--java-db-repo", "java_db_repo", default=DEFAULT_TRIVY_JAVA_DB_REPO,
              show_default=True, help="Java artifact index to resolve jars against.")
@click.option("--checks-repo", "checks_repo", default=None,
              help="Infrastructure-checks bundle. Omit to use the checks compiled into "
                   "the scanner, which is what a local scan normally wants.")
@pass_context
def code_scan(ctx, path, repo, commit, do_ingest, image, binary,
              output_path, scanners, timeout_s, db_repo, java_db_repo,
              checks_repo) -> None:
    """Scan a local checkout with the LimaCharlie code scanner.

    Runs the scanner over PATH (default: the current directory) and writes a
    report/v1 document. With --ingest the report is pushed to this org, where
    it lands on exactly the rows a hosted scan of the same repository would
    write — the report format is loss-free, so the identities match and
    nothing is duplicated.

    The scanner runs in a container by default; --binary runs an already
    installed scanner-agent instead. Nothing about the checkout leaves your
    machine except the report.

    SECRET SCANNING IS OFF BY DEFAULT and turning it on here is usually not
    what you want. A secret's identity in this pipeline is a digest keyed by
    a deployment-side salt this command does not have, so locally-found
    credentials would not dedupe against the hosted scan's, and the ingest
    refuses them for the same reason. Use the hosted lane for secrets.

    \b
    Examples:
      limacharlie cloudsec code scan
      limacharlie cloudsec code scan ~/src/api --repo acme/api --ingest \\
          --commit "$(git -C ~/src/api rev-parse HEAD)"
    """
    root = os.path.abspath(path)
    if commit is None:
        commit = _git_head(root)
    if repo is None:
        repo = _git_repo_key(root)
    if do_ingest and not repo:
        raise click.ClickException(
            "--ingest needs --repo '<owner>/<name>': this checkout's git origin "
            "did not name one, and the repository a finding belongs to is not "
            "something to guess")
    if not do_ingest and not output_path:
        # Checked BEFORE the scan, not after: the report would be written into a
        # temporary directory and deleted with it, so the command would spend
        # minutes of somebody's time and leave nothing behind.
        raise click.ClickException(
            "nothing to do with the report: pass --ingest to push it, or "
            "-o PATH to keep it")

    wanted = [s.strip() for s in scanners.split(",") if s.strip()]
    with tempfile.TemporaryDirectory(prefix="lc-code-scan-") as workdir:
        # The report is always produced inside this private directory and copied out
        # afterwards. Writing it straight to --output would mean mounting whatever
        # directory the caller named into the container, which hands a container running
        # third-party engines write access to a directory it has no business in.
        report_path = os.path.join(workdir, "report.json.gz")
        spec = {
            "job_id": "cli-%s" % uuid.uuid4().hex[:12],
            # Carried for the agent's own logging only; the scan is local and the
            # agent makes no per-tenant decision from it.
            "oid": getattr(ctx.obj, 'oid', None) or "",
            "mode": "repo",
            "source": {"kind": "local", "org": "", "repo": "", "clone_url": "", "ref": "",
                       "default_branch": ""},
            "local_path": root,
            "scanners": {s: (s in wanted) for s in
                         ("sca", "secrets", "secrets_history", "iac", "sast", "licenses", "images")},
        }
        _run_code_scanner(spec, root, report_path, workdir,
                          image=image, binary=binary, timeout_s=timeout_s,
                          db_repo=db_repo, java_db_repo=java_db_repo,
                          checks_repo=checks_repo)
        with open(report_path, "rb") as f:
            document = f.read()

        result = {"bytes": len(document), "repo": repo, "commit": commit}
        if output_path:
            with open(output_path, "wb") as f:
                f.write(document)
            result["written"] = output_path
        if do_ingest:
            cs = _get_cloudsec(ctx)
            result["ingest"] = cs.ingest_code_results(
                repo, "report", document, commit=commit)
        _output(ctx, result)


def _git_head(root: str) -> str | None:
    """The checked-out commit, or None. A checkout that is not a git working
    tree is a perfectly good thing to scan; it just cannot say which revision
    it is, and a fabricated one would mislabel every finding."""
    return _git(root, "rev-parse", "HEAD")


def _git_repo_key(root: str) -> str | None:
    """The '<owner>/<name>' key from the checkout's origin remote, or None.

    Read from the remote rather than from the directory name: the directory
    is whatever the person cloned it as, and the repository a finding belongs
    to is an identity, not a label."""
    url = _git(root, "config", "--get", "remote.origin.url")
    if not url:
        return None
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # Both spellings of a remote: https://host/owner/name and git@host:owner/name
    tail = url.split(":")[-1] if "://" not in url else url.split("://", 1)[1]
    parts = [p for p in tail.split("/") if p]
    if len(parts) < 2:
        return None
    return "%s/%s" % (parts[-2], parts[-1])


def _git(root: str, *args: str) -> str | None:
    try:
        out = subprocess.run(("git", "-C", root) + args, capture_output=True,
                             timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace").strip() or None


def _run_code_scanner(spec: dict, root: str, report_path: str, workdir: str,
                      *, image: str | None, binary: str | None, timeout_s: int,
                      db_repo: str, java_db_repo: str,
                      checks_repo: str | None) -> None:
    """Run the scanner over a local checkout, writing report_path.

    Two backends, one contract: the agent reads a spec and writes a gzipped
    report. The container is the default because it carries the pinned engines
    and their databases; a locally installed binary is offered because a CI
    job that already has one should not pay for a pull.
    """
    spec_path = os.path.join(workdir, "spec.json")
    # The scanner takes its data sources from the environment and refuses to start without
    # them — which is the right behaviour for the sandbox and means a local run has to
    # supply them.
    env = dict(os.environ)
    env["TRIVY_DB_REPOSITORY"] = db_repo
    env["TRIVY_JAVA_DB_REPOSITORY"] = java_db_repo
    extra_args: list[str] = []
    if checks_repo:
        env["TRIVY_CHECKS_BUNDLE_REPOSITORY"] = checks_repo
    else:
        # The checks compiled into the binary. A local scan has no mirror to point at, and
        # the alternative — refusing to scan infrastructure files — would be a silent gap.
        extra_args.append("--embedded-checks")

    if binary:
        with open(spec_path, "w") as f:
            json.dump(spec, f)
        cmd = [binary, "--spec", spec_path, "--out", report_path] + extra_args
        _run(cmd, timeout_s, env=env)
        return

    # In the container the checkout is mounted read-only at a fixed path, so the spec has to
    # name THAT path rather than the host's.
    #
    # The private working directory is mounted as the container's whole scratch volume
    # (/scan), which is what the engines unpack databases and layers into. Mounting only an
    # output directory looked tidier and does not work: the container runs as the invoking
    # user (so the report comes back readable) and that user does not own the image's own
    # /scan.
    container_spec = dict(spec, local_path="/scan/src")
    with open(spec_path, "w") as f:
        json.dump(container_spec, f)
    cmd = [
        "docker", "run", "--rm",
        # As the invoking user, so the report comes back readable. The container's own
        # identity is irrelevant here — there is no sandbox boundary on a laptop — and a
        # root-owned artifact in somebody's temporary directory is a nuisance at best.
        "--user", "%d:%d" % (os.getuid(), os.getgid()),
        "-v", "%s:/scan" % workdir,
        "-v", "%s:/scan/src:ro" % root,
        "-e", "TRIVY_DB_REPOSITORY=%s" % db_repo,
        "-e", "TRIVY_JAVA_DB_REPOSITORY=%s" % java_db_repo,
        "-e", "HOME=/scan",
    ]
    if checks_repo:
        cmd += ["-e", "TRIVY_CHECKS_BUNDLE_REPOSITORY=%s" % checks_repo]
    cmd += [
        image or DEFAULT_CODE_SCANNER_IMAGE,
        "--spec", "/scan/spec.json",
        "--out", "/scan/%s" % os.path.basename(report_path),
    ] + extra_args
    _run(cmd, timeout_s)


def _run(cmd: list[str], timeout_s: int, *, env: dict | None = None) -> None:
    try:
        proc = subprocess.run(cmd, timeout=timeout_s, check=False, env=env)
    except FileNotFoundError:
        raise click.ClickException(
            "%s is not installed or not on PATH" % cmd[0])
    except subprocess.TimeoutExpired:
        raise click.ClickException(
            "the scan did not finish within %d seconds" % timeout_s)
    if proc.returncode != 0:
        # The agent's exit codes are a closed vocabulary and it prints a
        # machine-readable line before a fatal exit, so the caller is pointed at
        # that rather than told a number.
        raise click.ClickException(
            "the scanner exited %d; its last line names the reason "
            "(error_code=...)" % proc.returncode)


# ---------------------------------------------------------------------------
# fleet subgroup (multi-org)
# ---------------------------------------------------------------------------

@group.group("fleet")
def fleet_group() -> None:
    """Multi-org fleet views (MSSP)."""


@fleet_group.command("overview")
@click.option("--oid", "oids", multiple=True,
              help="Explicit org id to include; repeatable. Omit (with no --group) "
                   "to span every org your credentials can see.")
@click.option("--group", "group_id", default=None,
              help="An org-group id: include the group's member orgs "
                   "(you must be a member or owner of the group).")
@click.option("--trend-days", default=None, type=int,
              help="Days of score-trend window per org (default 30).")
@click.option("--limit", default=None, type=int,
              help="Orgs per page (default 25, cap 100).")
@click.option("--cursor", default=None,
              help="Keyset-pagination token (next_cursor from the previous page).")
@pass_context
def fleet_overview(ctx, oids, group_id, trend_days, limit, cursor) -> None:
    """Multi-org fleet posture board: one row per authorized org.

    \b
    Examples:
      limacharlie cloudsec fleet overview
      limacharlie cloudsec fleet overview --group <GROUP_ID> --trend-days 90
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_fleet_overview(
        oids=list(oids) or None,
        group=group_id,
        cursor=cursor,
        limit=limit,
        trend_days=trend_days,
    ))


# ---------------------------------------------------------------------------
# finding subgroup
# ---------------------------------------------------------------------------

@group.group("finding")
def finding_group() -> None:
    """Findings worklist: list, facets, get, and triage writes."""


@finding_group.command("list")
@_finding_filter_options
@_sort_options
@_paging_options
@pass_context
def finding_list(ctx, severities, finding_classes, statuses, accounts, repos,
                 owners, unassigned, sla_states, reachable, kev, q, sort,
                 order, cursor, limit) -> None:
    """List the merged, risk-ranked cloud-security findings.

    \b
    Examples:
      limacharlie cloudsec finding list --severity CRITICAL --severity HIGH
      limacharlie cloudsec finding list --class public_exposure --kev
      limacharlie cloudsec finding list --owner alice@corp.com
      limacharlie cloudsec finding list --unassigned
      limacharlie cloudsec finding list --sla breached --sort due_at
      limacharlie cloudsec finding list --repo refractionPOINT/lc-appsec-fixtures
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_findings(
        severity=list(severities) or None,
        finding_class=list(finding_classes) or None,
        status=list(statuses) or None,
        account=list(accounts) or None,
        repo=list(repos) or None,
        owner=_selector_with_empty(owners, unassigned),
        sla=list(sla_states) or None,
        reachable=reachable,
        kev=kev,
        q=q,
        sort=sort,
        order=order,
        cursor=cursor,
        limit=limit,
    ))


@finding_group.command("facets")
@_finding_filter_options
@click.option("--owner-pin", "owner_pins", multiple=True,
              help="Keep these owners in the capped 'owner' facet even when "
                   "they would not rank into it (pass your own identity); "
                   "repeatable. NOT a filter — selects no rows, changes no "
                   "count. Bounded by the cap: pins share the facet's 50 "
                   "slots with any --owner values, so past ~50 combined a "
                   "pin can still be dropped.")
@pass_context
def finding_facets(ctx, severities, finding_classes, statuses, accounts, repos,
                   owners, unassigned, sla_states, reachable, kev, q,
                   owner_pins) -> None:
    """Cross-filtered facet counts for the findings worklist.

    \b
    Examples:
      limacharlie cloudsec finding facets --severity CRITICAL
      limacharlie cloudsec finding facets --owner-pin me@corp.com
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_finding_facets(
        severity=list(severities) or None,
        finding_class=list(finding_classes) or None,
        status=list(statuses) or None,
        account=list(accounts) or None,
        repo=list(repos) or None,
        owner=_selector_with_empty(owners, unassigned),
        owner_pin=list(owner_pins) or None,
        sla=list(sla_states) or None,
        reachable=reachable,
        kev=kev,
        q=q,
    ))


@finding_group.command("causes")
@_finding_filter_options
@click.option("--cause", default=None,
              help="One cause key: return the count for that cause alone "
                   "instead of the ranked rollup (empty when no finding "
                   "under the filter carries it).")
@click.option("--limit", default=None, type=int,
              help="Rollup size (default 20, cap 200). Not a page size — the "
                   "rollup is not paginated; 'distinct' reports the tail.")
@pass_context
def finding_causes(ctx, severities, finding_classes, statuses, accounts, repos,
                   owners, unassigned, sla_states, reachable, kev, q, cause,
                   limit) -> None:
    """Findings grouped by CAUSE: one edit that closes N findings.

    \b
    Examples:
      limacharlie cloudsec finding causes --severity CRITICAL --limit 5
      limacharlie cloudsec finding causes --cause "lcrn:...:firewalls/allow-all"
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_finding_causes(
        cause=cause,
        severity=list(severities) or None,
        finding_class=list(finding_classes) or None,
        status=list(statuses) or None,
        account=list(accounts) or None,
        repo=list(repos) or None,
        owner=_selector_with_empty(owners, unassigned),
        sla=list(sla_states) or None,
        reachable=reachable,
        kev=kev,
        q=q,
        limit=limit,
    ))


@finding_group.command("classes")
@pass_context
def finding_classes(ctx) -> None:
    """List the canonical finding_class vocabulary (backend enum).

    \b
    Example:
      limacharlie cloudsec finding classes
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_finding_classes())


@finding_group.command("get")
@click.argument("finding_id")
@pass_context
def finding_get(ctx, finding_id) -> None:
    """Get a single finding by FINDING_ID.

    \b
    Example:
      limacharlie cloudsec finding get fnd_0123abcd
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_finding(finding_id))


@finding_group.command("resolve")
@click.argument("finding_id")
@click.option("--kind", required=True, type=_KIND_CHOICES,
              help="Resolution kind; 'open' reopens the finding.")
@click.option("--reason", default=None, help="Optional operator note.")
@click.option("--expires-at", default=None, type=int,
              help="Unix seconds; only meaningful with --kind accepted. Omit for a "
                   "permanent acceptance — an expiry is optional, not required.")
@pass_context
def finding_resolve(ctx, finding_id, kind, reason, expires_at) -> None:
    """Disposition (or reopen, with --kind open) FINDING_ID.

    \b
    Examples:
      limacharlie cloudsec finding resolve fnd_abc --kind mitigated
      limacharlie cloudsec finding resolve fnd_abc --kind open
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.set_finding_status(
        finding_id, kind, reason=reason, expires_at=expires_at,
    ))


@finding_group.command("bulk-resolve")
@click.option("--finding-id", "finding_ids", multiple=True, required=True,
              help="Finding id; repeat for each finding.")
@click.option("--kind", required=True, type=_BULK_KIND_CHOICES,
              help="Resolution kind (reopen is single-finding only: use 'finding resolve --kind open').")
@click.option("--reason", default=None, help="Optional operator note.")
@click.option("--expires-at", default=None, type=int,
              help="Unix seconds; only meaningful with --kind accepted. Omit for a "
                   "permanent acceptance — an expiry is optional, not required.")
@pass_context
def finding_bulk_resolve(ctx, finding_ids, kind, reason, expires_at) -> None:
    """Apply one resolution to many findings.

    \b
    Example:
      limacharlie cloudsec finding bulk-resolve --finding-id fnd_a --finding-id fnd_b --kind mitigated
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.bulk_set_finding_status(
        list(finding_ids), kind, reason=reason, expires_at=expires_at,
    ))


@finding_group.command("set-owner")
@click.argument("finding_id")
@click.option("--owner", default=None, help="The owner to assign.")
@click.option("--clear", is_flag=True, default=False, help="Clear the owner.")
@pass_context
def finding_set_owner(ctx, finding_id, owner, clear) -> None:
    """Assign (or clear, with --clear) the owner of FINDING_ID.

    \b
    Example:
      limacharlie cloudsec finding set-owner fnd_abc --owner alice@corp.com
    """
    if clear == (owner is not None):
        raise click.UsageError("provide exactly one of --owner or --clear")
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.set_finding_owner(finding_id, "" if clear else owner))


@finding_group.command("set-ticket")
@click.argument("finding_id")
@click.option("--ticket", default=None, help="The ticket id/url to link.")
@click.option("--clear", is_flag=True, default=False, help="Clear the ticket.")
@pass_context
def finding_set_ticket(ctx, finding_id, ticket, clear) -> None:
    """Link (or clear, with --clear) a ticket to FINDING_ID.

    \b
    Example:
      limacharlie cloudsec finding set-ticket fnd_abc --ticket JIRA-123
    """
    if clear == (ticket is not None):
        raise click.UsageError("provide exactly one of --ticket or --clear")
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.set_finding_ticket(finding_id, "" if clear else ticket))


# ---------------------------------------------------------------------------
# attack-path subgroup
# ---------------------------------------------------------------------------

@group.group("attack-path")
def attack_path_group() -> None:
    """Headline toxic-combination attack paths."""


@attack_path_group.command("list")
@click.option("--severity", "severities", multiple=True, help="Filter by severity; repeatable (OR).")
@click.option("--account", "accounts", multiple=True, help="Filter by cloud account; repeatable (OR).")
@click.option("--status", "statuses", multiple=True, help="Filter by status; repeatable (OR).")
@click.option("-q", "--search", "q", default=None, help="Substring search.")
@pass_context
def attack_path_list(ctx, severities, accounts, statuses, q) -> None:
    """List the headline toxic-combination attack paths.

    \b
    Example:
      limacharlie cloudsec attack-path list --severity CRITICAL
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_attack_paths(
        severity=list(severities) or None,
        account=list(accounts) or None,
        status=list(statuses) or None,
        q=q,
    ))


# ---------------------------------------------------------------------------
# ciem subgroup
# ---------------------------------------------------------------------------

@group.group("ciem")
def ciem_group() -> None:
    """CIEM identity access views."""


@ciem_group.command("public-access")
@pass_context
def ciem_public_access(ctx) -> None:
    """Public/external access to sensitive resources.

    \b
    Example:
      limacharlie cloudsec ciem public-access
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_public_access())


@ciem_group.command("facets")
@_identity_filter_options
@pass_context
def ciem_facets(ctx, sources, accounts, regions, kinds, criticalities,
                unclassified, risk_bands, mfa, admin, external, public,
                disabled, crown_jewel, can_escalate, dormant_90d,
                with_sensitive, q) -> None:
    """CIEM identity facet counts (cross-filtered by the same selectors).

    \b
    Examples:
      limacharlie cloudsec ciem facets
      limacharlie cloudsec ciem facets --kind service_account --admin
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_identity_facets(
        source=list(sources) or None,
        account=list(accounts) or None,
        region=list(regions) or None,
        kind=list(kinds) or None,
        criticality=_selector_with_empty(criticalities, unclassified),
        risk_band=list(risk_bands) or None,
        mfa=mfa,
        admin=admin,
        external=external,
        public=public,
        disabled=disabled,
        crown_jewel=crown_jewel,
        can_escalate=can_escalate,
        dormant_90d=dormant_90d,
        with_sensitive=with_sensitive,
        q=q,
    ))


@ciem_group.command("identities")
@_identity_filter_options
@_paging_options
@pass_context
def ciem_identities(ctx, sources, accounts, regions, kinds, criticalities,
                    unclassified, risk_bands, mfa, admin, external, public,
                    disabled, crown_jewel, can_escalate, dormant_90d,
                    with_sensitive, q, cursor, limit) -> None:
    """One risk-ranked page of the identity access population.

    \b
    Examples:
      limacharlie cloudsec ciem identities --limit 50
      limacharlie cloudsec ciem identities --external --with-sensitive
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_identity_access(
        source=list(sources) or None,
        account=list(accounts) or None,
        region=list(regions) or None,
        kind=list(kinds) or None,
        criticality=_selector_with_empty(criticalities, unclassified),
        risk_band=list(risk_bands) or None,
        mfa=mfa,
        admin=admin,
        external=external,
        public=public,
        disabled=disabled,
        crown_jewel=crown_jewel,
        can_escalate=can_escalate,
        dormant_90d=dormant_90d,
        with_sensitive=with_sensitive,
        q=q,
        cursor=cursor,
        limit=limit,
    ))


@ciem_group.command("identity")
@click.argument("urn")
@pass_context
def ciem_identity(ctx, urn) -> None:
    """Single-identity effective-access rollup for URN (null when unknown).

    \b
    Example:
      limacharlie cloudsec ciem identity "lcrn:gcp:...:serviceAccount/deploy"
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_identity(urn))


# ---------------------------------------------------------------------------
# inventory subgroup
# ---------------------------------------------------------------------------

@group.group("inventory")
def inventory_group() -> None:
    """Cloud resource inventory."""


@inventory_group.command("list")
@_inventory_filter_options
@_paging_options
@pass_context
def inventory_list(ctx, resource_type, provider, account, region, q,
                   all_accounts, cursor, limit) -> None:
    """List the cloud resource inventory.

    \b
    Examples:
      limacharlie cloudsec inventory list --type gcp_bucket
      limacharlie cloudsec inventory list --provider okta
      limacharlie cloudsec inventory list -q prod --limit 50
      limacharlie cloudsec inventory list --all-accounts
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_inventory(
        resource_type=resource_type, provider=provider, account=account,
        region=region, q=q, account_unscoped=all_accounts or None,
        cursor=cursor, limit=limit,
    ))


@inventory_group.command("facets")
@pass_context
def inventory_facets(ctx) -> None:
    """Inventory facet counts by type/account/region.

    \b
    Example:
      limacharlie cloudsec inventory facets
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_inventory_facets())


# ---------------------------------------------------------------------------
# data-security subgroup
# ---------------------------------------------------------------------------

@group.group("data-security")
def data_security_group() -> None:
    """DSPM data-store views."""


@data_security_group.command("facets")
@_data_store_filter_options
@pass_context
def data_security_facets(ctx, providers, accounts, regions, store_kinds,
                         tiers, unclassified, data_classes, sensitivity,
                         exposure, q) -> None:
    """DSPM data-store facet counts (cross-filtered by the same selectors).

    \b
    Examples:
      limacharlie cloudsec data-security facets
      limacharlie cloudsec data-security facets --store-kind bucket
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_data_security_facets(
        provider=list(providers) or None,
        account=list(accounts) or None,
        region=list(regions) or None,
        store_kind=list(store_kinds) or None,
        tier=_selector_with_empty(tiers, unclassified),
        data_class=list(data_classes) or None,
        sensitivity=sensitivity,
        exposure=exposure,
        q=q,
    ))


@data_security_group.command("stores")
@_data_store_filter_options
@_paging_options
@pass_context
def data_security_stores(ctx, providers, accounts, regions, store_kinds,
                         tiers, unclassified, data_classes, sensitivity,
                         exposure, q, cursor, limit) -> None:
    """One keyset page of the org's data stores.

    \b
    Examples:
      limacharlie cloudsec data-security stores --limit 50
      limacharlie cloudsec data-security stores --sensitive --public
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_data_stores(
        provider=list(providers) or None,
        account=list(accounts) or None,
        region=list(regions) or None,
        store_kind=list(store_kinds) or None,
        tier=_selector_with_empty(tiers, unclassified),
        data_class=list(data_classes) or None,
        sensitivity=sensitivity,
        exposure=exposure,
        q=q,
        cursor=cursor,
        limit=limit,
    ))


# ---------------------------------------------------------------------------
# resource subgroup
# ---------------------------------------------------------------------------

@group.group("resource")
def resource_group() -> None:
    """Point lookups for canonical resource records."""


@resource_group.command("get")
@click.argument("urn")
@pass_context
def resource_get(ctx, urn) -> None:
    """Get the canonical record for URN (null when unknown).

    \b
    Example:
      limacharlie cloudsec resource get "lcrn:gcp:...:bucket/prod-data"
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_resource(urn))


# ---------------------------------------------------------------------------
# graph subgroup
# ---------------------------------------------------------------------------

@group.group("graph")
def graph_group() -> None:
    """Security graph expansion."""


@graph_group.command("neighbors")
@click.argument("urn")
@click.option("--limit", default=None, type=int, help="Max neighbors (default 200, cap 500).")
@pass_context
def graph_neighbors(ctx, urn, limit) -> None:
    """Expand URN's 1-hop neighborhood in the security graph.

    \b
    Example:
      limacharlie cloudsec graph neighbors "lcrn:...instance/web-1" --limit 500
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_graph_neighbors(urn, limit=limit))


# ---------------------------------------------------------------------------
# query subgroup
# ---------------------------------------------------------------------------

@group.group("query")
def query_group() -> None:
    """Graph queries: list the query pack, run a query."""


@query_group.command("list")
@pass_context
def query_list(ctx) -> None:
    """List the named graph queries in the query pack.

    \b
    Example:
      limacharlie cloudsec query list
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_queries())


@query_group.command("run")
@click.option("--named", default=None, help="A query-pack name (see 'query list').")
@click.option("--text", default=None, help="A text query.")
@click.option("--query-json", default=None, help="A raw query DSL object as JSON.")
@click.option("--project", type=click.Choice(["graph"]), default=None,
              help="Also return a drawable projection: 'graph' adds an induced subgraph over the matched URNs.")
@pass_context
def query_run(ctx, named, text, query_json, project) -> None:
    """Run a graph query (one of --named / --text / --query-json).

    \b
    Examples:
      limacharlie cloudsec query run --named public_data_stores
      limacharlie cloudsec query run --text 'MATCH (d:DataStore {is_sensitive: true})<-[:has_permission_on]-(i:Identity {is_external: true}) RETURN i, d'
    """
    _one_of("the query", named=named, text=text, query_json=query_json)
    query = None
    if query_json:
        query = _parse_json_opt(query_json, "--query-json")
        # Unconditional: a JSON `null` must not slip through as "no query".
        if not isinstance(query, dict):
            raise click.BadParameter("must decode to a JSON object", param_hint="--query-json")
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.run_query(
        named=named, text=text, query=query, project=project,
    ))


# ---------------------------------------------------------------------------
# compliance subgroup
# ---------------------------------------------------------------------------

@group.group("compliance")
def compliance_group() -> None:
    """Compliance assessment: report, frameworks, assignments."""


@compliance_group.command("report")
@click.option("--framework", default=None,
              help="Framework id (default cis-gcp); ignored when --assignment is set.")
@click.option("--assignment", default=None,
              help="Named scoped assignment to evaluate instead of the whole estate.")
@pass_context
def compliance_report(ctx, framework, assignment) -> None:
    """Per-control pass/fail compliance assessment.

    \b
    Examples:
      limacharlie cloudsec compliance report --framework cis-aws
      limacharlie cloudsec compliance report --assignment prod-scope
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_compliance(framework=framework, assignment=assignment))


@compliance_group.command("frameworks")
@pass_context
def compliance_frameworks(ctx) -> None:
    """List the selectable compliance frameworks.

    \b
    Example:
      limacharlie cloudsec compliance frameworks
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_compliance_frameworks())


@compliance_group.command("assignments")
@pass_context
def compliance_assignments(ctx) -> None:
    """List the org's scoped compliance assignments.

    \b
    Example:
      limacharlie cloudsec compliance assignments
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_compliance_assignments())


# ---------------------------------------------------------------------------
# chokepoint subgroup
# ---------------------------------------------------------------------------

@group.group("chokepoint")
def chokepoint_group() -> None:
    """Estate-wide chokepoints: list, dismiss, restore."""


@chokepoint_group.command("list")
@pass_context
def chokepoint_list(ctx) -> None:
    """Estate-wide chokepoints ranked by attack paths broken.

    \b
    Example:
      limacharlie cloudsec chokepoint list
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_chokepoints())


@chokepoint_group.command("dismiss")
@click.argument("urn")
@click.option("--reason", default=None, help="Optional reason recorded with the dismissal.")
@pass_context
def chokepoint_dismiss(ctx, urn, reason) -> None:
    """Dismiss the choke point at URN from the risk overview.

    \b
    Example:
      limacharlie cloudsec chokepoint dismiss "lcrn:..." --reason "planned decom"
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.dismiss_chokepoint(urn, reason=reason))


@chokepoint_group.command("restore")
@click.argument("urn")
@pass_context
def chokepoint_restore(ctx, urn) -> None:
    """Restore (un-dismiss) the choke point at URN.

    \b
    Example:
      limacharlie cloudsec chokepoint restore "lcrn:..."
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.restore_chokepoint(urn))


# ---------------------------------------------------------------------------
# resolve subgroup
# ---------------------------------------------------------------------------

@group.group("resolve")
def resolve_group() -> None:
    """Sensor <-> cloud asset resolution (fusion mapping)."""


@resolve_group.command("sensors")
@click.argument("sids", nargs=-1, required=True)
@pass_context
def resolve_sensors(ctx, sids) -> None:
    """Resolve SIDS to the cloud asset each sensor runs on.

    Any number of SIDs — requests are chunked automatically.

    \b
    Example:
      limacharlie cloudsec resolve sensors <SID1> <SID2>
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.resolve_sensors(list(sids)))


@resolve_group.command("assets")
@click.argument("urns", nargs=-1, required=True)
@pass_context
def resolve_assets(ctx, urns) -> None:
    """Resolve asset URNS to the sensors running on each.

    Any number of URNs — requests are chunked automatically.

    \b
    Example:
      limacharlie cloudsec resolve assets "lcrn:...instance/web-1"
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.resolve_assets(list(urns)))


# ---------------------------------------------------------------------------
# caasm subgroup
# ---------------------------------------------------------------------------

@group.group("caasm")
def caasm_group() -> None:
    """CAASM: third-party asset inventory, coverage gaps, policy, ingest."""


@caasm_group.command("assets")
@click.option("-q", "--search", "q", default=None, help="Substring filter over asset urn/name.")
@_paging_options
@pass_context
def caasm_assets(ctx, q, cursor, limit) -> None:
    """The merged third-party asset inventory.

    \b
    Example:
      limacharlie cloudsec caasm assets -q laptop --limit 50
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_caasm_assets(q=q, cursor=cursor, limit=limit))


@caasm_group.command("coverage")
@click.option("--status", "statuses", multiple=True, help="Filter by finding status; repeatable (OR).")
@click.option("--severity", "severities", multiple=True, help="Filter by severity; repeatable (OR).")
@click.option("-q", "--search", "q", default=None, help="Substring search.")
@_sort_options
@_paging_options
@pass_context
def caasm_coverage(ctx, statuses, severities, q, sort, order, cursor, limit) -> None:
    """Coverage-gap findings (assets missing a required tool).

    \b
    Example:
      limacharlie cloudsec caasm coverage --status open --severity HIGH
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_caasm_coverage(
        status=list(statuses) or None,
        severity=list(severities) or None,
        q=q, sort=sort, order=order, cursor=cursor, limit=limit,
    ))


@caasm_group.group("policy")
def caasm_policy_group() -> None:
    """The expected-coverage policy."""


@caasm_policy_group.command("get")
@pass_context
def caasm_policy_get(ctx) -> None:
    """Get the stored expected-coverage policy.

    \b
    Example:
      limacharlie cloudsec caasm policy get
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_caasm_policy())


@caasm_policy_group.command("set")
@click.option("--policy-json", default=None, help="The policy as inline JSON ({expect:[...]}).")
@click.option("--input-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Read the policy from a JSON or YAML file.")
@pass_context
def caasm_policy_set(ctx, policy_json, input_file) -> None:
    """Set (upsert) the expected-coverage policy.

    The policy can also be piped via stdin (JSON or YAML).

    \b
    Example:
      limacharlie cloudsec caasm policy set --input-file policy.yaml
    """
    policy = _load_json_object_arg(
        inline=policy_json, inline_hint="--policy-json",
        input_file=input_file, file_hint="--input-file",
        what="the policy",
        shape_msg="must decode to a JSON object ({expect:[...]})",
    )
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.set_caasm_policy(policy))


@caasm_group.command("ingest")
@click.option("--source", required=True,
              help="The CAASM source the records come from (e.g. sentinelone, "
                   "crowdstrike, defender, okta, entraid, ms_graph, wiz); "
                   "validated server-side.")
@click.option("--records-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="JSON or YAML file holding an array of raw vendor-shaped records.")
@click.option("--record-json", default=None, help="A single raw record as inline JSON.")
@click.option("--policy-json", default=None, help="Optional inline coverage policy override (JSON).")
@pass_context
def caasm_ingest(ctx, source, records_file, record_json, policy_json) -> None:
    """Ingest raw third-party asset records into the merged inventory.

    \b
    Examples:
      limacharlie cloudsec caasm ingest --source okta --records-file users.json
      limacharlie cloudsec caasm ingest --source crowdstrike --record-json '{...}'
    """
    _one_of("the records", records_file=records_file, record_json=record_json)
    records = None
    record = None
    if records_file:
        records = _load_file(records_file, "--records-file")
        # Unconditional: a file whose content is `null` (or any non-array)
        # must not slip through as a silent records-less ingest.
        if not isinstance(records, list):
            raise click.BadParameter(
                "must decode to a JSON array of records", param_hint="--records-file",
            )
    else:
        record = _parse_json_opt(record_json, "--record-json")
        if not isinstance(record, dict):
            raise click.BadParameter("must decode to a JSON object", param_hint="--record-json")
    policy = None
    if policy_json:
        policy = _parse_json_opt(policy_json, "--policy-json")
        if not isinstance(policy, dict):
            raise click.BadParameter("must decode to a JSON object", param_hint="--policy-json")
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.caasm_ingest(
        source, records=records, record=record, policy=policy,
    ))


# ---------------------------------------------------------------------------
# provider subgroup
# ---------------------------------------------------------------------------

@group.group("provider")
def provider_group() -> None:
    """Provider preflight + coverage manifests (configs live in the cloudsec_provider hive)."""


@provider_group.command("manifest")
@click.option("--type", "provider_type", default=None,
              help="Fetch a single provider's manifest (e.g. gcp, aws, azure, okta); "
                   "omit to list every provider the org has a manifest or a sweep for.")
@pass_context
def provider_manifest(ctx, provider_type) -> None:
    """Per-provider coverage manifests (what CAN be collected vs what was).

    \b
    Examples:
      limacharlie cloudsec provider manifest
      limacharlie cloudsec provider manifest --type gcp
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_provider_manifests(provider_type=provider_type))


@provider_group.command("test")
@click.option("--provider-json", default=None,
              help="The provider record (cloudsec_provider hive shape) as inline JSON.")
@click.option("--input-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Read the provider record from a JSON or YAML file.")
@pass_context
def provider_test(ctx, provider_json, input_file) -> None:
    """Preflight a provider configuration (credentials are never stored).

    The record can also be piped via stdin (JSON or YAML).

    \b
    Example:
      limacharlie cloudsec provider test --input-file provider.yaml
    """
    provider = _load_json_object_arg(
        inline=provider_json, inline_hint="--provider-json",
        input_file=input_file, file_hint="--input-file",
        what="the provider record",
        shape_msg="must decode to a JSON object (cloudsec_provider record shape)",
    )
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.test_provider(provider))


# ---------------------------------------------------------------------------
# policy subgroup (cloudsec_policy authoring aids)
# ---------------------------------------------------------------------------

@group.group("policy")
def policy_group() -> None:
    """cloudsec_policy authoring aids: vocabulary + live autocomplete.

    The policies themselves are hive records (limacharlie hive list
    cloudsec_policy); these are the read-only helpers the rule form
    uses. See also the 'simulate' subgroup to preview a matcher.
    """


@policy_group.command("vocabulary")
@pass_context
def policy_vocabulary(ctx) -> None:
    """The server-driven cloudsec_policy authoring vocabulary.

    \b
    Example:
      limacharlie cloudsec policy vocabulary
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_policy_vocabulary())


@policy_group.command("suggest")
@click.option("--dimension", required=True, type=_SUGGEST_DIMENSION_CHOICES,
              help="Which matcher dimension to suggest values for (name/account).")
@click.option("-q", "--search", "q", required=True,
              help="The typed fragment to match (case-insensitive substring).")
@click.option("--target", default=None, type=_SIMULATE_TARGET_CHOICES,
              help="Narrow the walked resource family to the rule set being edited.")
@click.option("--limit", default=None, type=int,
              help="Max suggestions (default 20, cap 50).")
@pass_context
def policy_suggest(ctx, dimension, q, target, limit) -> None:
    """Live matcher-value autocomplete from the org's own inventory.

    \b
    Examples:
      limacharlie cloudsec policy suggest --dimension name -q prod
      limacharlie cloudsec policy suggest --dimension account -q 1234 --limit 10
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.suggest_policy_values(
        dimension, q, target=target, limit=limit,
    ))


# ---------------------------------------------------------------------------
# simulate subgroup ("Simulate" policy preflights)
# ---------------------------------------------------------------------------

@group.group("simulate")
def simulate_group() -> None:
    """Preview a cloudsec_policy matcher against the estate (read-only).

    Both previews evaluate an IN-EDIT matcher against the org's current
    data with the exact semantics the engine applies, so a typo is
    visible before you save the policy. Nothing is persisted.
    """


@simulate_group.command("resources")
@click.option("--rules-json", default=None,
              help="The matcher rules as inline JSON (an array of rule objects).")
@click.option("--input-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Read the rules (JSON array) from a JSON or YAML file.")
@click.option("--target", default=None, type=_SIMULATE_TARGET_CHOICES,
              help="Which rule set is simulated (default any); scopes the walked family.")
@click.option("--resource-type", "resource_types", multiple=True,
              help="Explicit resource_type narrowing (exclusions rules); repeatable.")
@click.option("--sample-limit", default=None, type=int,
              help="Sample size to return (default 25, cap 100).")
@pass_context
def simulate_resources(ctx, rules_json, input_file, target, resource_types,
                       sample_limit) -> None:
    """Preview a resource-matcher rule set against the stored inventory.

    The rules can also be piped via stdin (JSON or YAML array).

    \b
    Examples:
      limacharlie cloudsec simulate resources \\
          --rules-json '[{"name_glob":"prod-*"}]' --target data_store
      limacharlie cloudsec simulate resources --input-file rules.yaml
    """
    rules = _load_json_array_arg(
        inline=rules_json, inline_hint="--rules-json",
        input_file=input_file, file_hint="--input-file",
        what="the rules",
        shape_msg="must decode to a JSON array of rule objects",
    )
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.simulate_resource_match(
        rules, target=target,
        resource_types=list(resource_types) or None,
        sample_limit=sample_limit,
    ))


@simulate_group.command("findings")
@click.option("--match-json", default=None,
              help="The suppression matcher as inline JSON (an object; {} allowed).")
@click.option("--input-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Read the match object from a JSON or YAML file.")
@click.option("--sample-limit", default=None, type=int,
              help="Sample size to return (default 25, cap 100).")
@pass_context
def simulate_findings(ctx, match_json, input_file, sample_limit) -> None:
    """Preview a suppression matcher against the org's OPEN findings.

    The match object can also be piped via stdin (JSON or YAML). An empty
    match ({}) is valid: it matches everything up to the default severity
    ceiling.

    \b
    Examples:
      limacharlie cloudsec simulate findings \\
          --match-json '{"finding_class":"misconfig","max_severity":"LOW"}'
      limacharlie cloudsec simulate findings --input-file match.yaml
    """
    match = _load_json_object_arg(
        inline=match_json, inline_hint="--match-json",
        input_file=input_file, file_hint="--input-file",
        what="the match",
        shape_msg="must decode to a JSON object (a suppression matcher; {} allowed)",
    )
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.simulate_finding_match(match, sample_limit=sample_limit))


# ---------------------------------------------------------------------------
# export subgroup (CSV)
# ---------------------------------------------------------------------------

def _emit_csv(ctx: click.Context, csv_text: str, output_path: str | None) -> None:
    """Write a CSV export to a file (-o) or stdout.

    The CSV is raw data, not a structured object — it bypasses the
    --output format machinery on purpose.
    """
    if output_path:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        if not ctx.obj.quiet:
            click.echo(f"wrote {output_path}", err=True)
    else:
        click.echo(csv_text, nl=False)


def _export_output_option(f):
    return click.option(
        "-o", "--output-file", "output_path", default=None,
        type=click.Path(dir_okay=False, writable=True),
        help="Write the CSV to this file instead of stdout.",
    )(f)


@group.group("export")
def export_group() -> None:
    """CSV exports of the read surface.

    The server walks the FULL filtered set (no pagination), capped at
    100k rows; a trailing '#' comment row marks a truncated export.
    """


@export_group.command("findings")
@_finding_filter_options
@_sort_options
@_export_output_option
@pass_context
def export_findings(ctx, severities, finding_classes, statuses, accounts, repos,
                    owners, unassigned, sla_states, reachable, kev, q, sort,
                    order, output_path) -> None:
    """Export the (filtered) findings worklist as CSV.

    \b
    Examples:
      limacharlie cloudsec export findings -o findings.csv
      limacharlie cloudsec export findings --severity CRITICAL --status open
      limacharlie cloudsec export findings --owner alice@corp.com
    """
    cs = _get_cloudsec(ctx)
    _emit_csv(ctx, cs.export_findings_csv(
        severity=list(severities) or None,
        finding_class=list(finding_classes) or None,
        status=list(statuses) or None,
        account=list(accounts) or None,
        repo=list(repos) or None,
        owner=_selector_with_empty(owners, unassigned),
        sla=list(sla_states) or None,
        reachable=reachable,
        kev=kev,
        q=q,
        sort=sort,
        order=order,
    ), output_path)


@export_group.command("inventory")
@_inventory_filter_options
@_export_output_option
@pass_context
def export_inventory(ctx, resource_type, provider, account, region, q,
                     all_accounts, output_path) -> None:
    """Export the (filtered) cloud resource inventory as CSV.

    \b
    Examples:
      limacharlie cloudsec export inventory -o inventory.csv
      limacharlie cloudsec export inventory --provider okta
    """
    cs = _get_cloudsec(ctx)
    _emit_csv(ctx, cs.export_inventory_csv(
        resource_type=resource_type, provider=provider, account=account,
        region=region, q=q, account_unscoped=all_accounts or None,
    ), output_path)


@export_group.command("compliance")
@click.option("--framework", default=None,
              help="Framework id (default cis-gcp); ignored when --assignment is set.")
@click.option("--assignment", default=None,
              help="Named scoped assignment to evaluate instead of the whole estate.")
@_export_output_option
@pass_context
def export_compliance(ctx, framework, assignment, output_path) -> None:
    """Export a compliance assessment as CSV.

    \b
    Examples:
      limacharlie cloudsec export compliance -o cis-gcp.csv
      limacharlie cloudsec export compliance --framework cis-aws -o cis-aws.csv
    """
    cs = _get_cloudsec(ctx)
    _emit_csv(ctx, cs.export_compliance_csv(
        framework=framework, assignment=assignment,
    ), output_path)


@export_group.command("query")
@click.option("--named", default=None, help="A query-pack name (see 'query list').")
@click.option("--text", default=None, help="A text query.")
@click.option("--query-json", default=None, help="A raw query DSL object as JSON.")
@click.option("--project", type=click.Choice(["graph"]), default=None,
              help="Also return a drawable projection: 'graph' adds an induced subgraph over the matched URNs.")
@_export_output_option
@pass_context
def export_query(ctx, named, text, query_json, project, output_path) -> None:
    """Run a graph query and export the rows as CSV.

    \b
    Examples:
      limacharlie cloudsec export query --named public_data_stores -o rows.csv
    """
    _one_of("the query", named=named, text=text, query_json=query_json)
    query = None
    if query_json:
        query = _parse_json_opt(query_json, "--query-json")
        if not isinstance(query, dict):
            raise click.BadParameter("must decode to a JSON object", param_hint="--query-json")
    cs = _get_cloudsec(ctx)
    _emit_csv(ctx, cs.export_query_csv(
        named=named, text=text, query=query, project=project,
    ), output_path)
