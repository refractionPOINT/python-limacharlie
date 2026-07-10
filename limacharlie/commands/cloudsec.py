"""Cloud Security (CNAPP) commands for LimaCharlie CLI v2.

Commands for the ``/cloudsec`` API surface: the merged, risk-ranked
findings worklist (CSPM misconfigurations + attack paths + CIEM),
the cloud resource inventory and security graph, compliance
assessment, the risk overview, CAASM (third-party asset attack
surface), sensor<->cloud-asset resolution, and finding triage.

Reads require the ``cloudsec.get`` permission and writes require
``cloudsec.set``. Every command requires the org to be subscribed to
the ``ext-cloud-inventory`` extension:

  limacharlie extension subscribe --name ext-cloud-inventory

Provider credentials and the cloudsec policies are hive records —
manage them with the hive commands (``limacharlie hive list
cloudsec_provider``, ``... cloudsec_policy``, ``... cloudsec_query``);
the one provider command here is the pre-save credential preflight
(``cloudsec provider test``).
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.cloudsec import CloudSec
from ..output import format_output, detect_output_format
from ..discovery import register_explain


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

_EXPLAIN_FINDING_LIST = """\
List the merged, risk-ranked cloud-security findings (CSPM
misconfigurations + graph toxic-combination attack paths + CIEM
access), ordered by lc_risk.

Repeatable filters are OR within a key and AND across keys:

  --severity CRITICAL --severity HIGH --class toxic_combination

Finding classes: toxic_combination, public_exposure, ciem_risk,
privilege_escalation, vulnerability, misconfig, malware, secret,
scan_finding, coverage_gap.

Pagination is keyset-based: pass the previous page's next_cursor
via --cursor.

Examples:
  limacharlie cloudsec finding list --severity CRITICAL
  limacharlie cloudsec finding list --class public_exposure --kev
  limacharlie cloudsec finding list --status open --limit 50
"""

_EXPLAIN_FINDING_FACETS = """\
Cross-filtered facet counts for the findings worklist under the
same filter selectors as 'finding list'. Each facet dimension is
counted against the other active filters.

Example:
  limacharlie cloudsec finding facets --severity CRITICAL
"""

_EXPLAIN_FINDING_GET = """\
Get a single finding by its id (e.g. fnd_<fingerprint>).

Example:
  limacharlie cloudsec finding get fnd_0123abcd...
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
  limacharlie cloudsec finding resolve fnd_abc... --kind accepted --expires-at 1767225600
  limacharlie cloudsec finding resolve fnd_abc... --kind open
"""

_EXPLAIN_FINDING_BULK_RESOLVE = """\
Apply one resolution to many findings in a single call.

--kind is mitigated, accepted, or false_positive. Reopening is a
single-finding operation only (the bulk API does not accept 'open');
use 'finding resolve <id> --kind open' per finding.

Example:
  limacharlie cloudsec finding bulk-resolve --finding-id fnd_a... --finding-id fnd_b... \\
      --kind false_positive --reason "scanner artifact"
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
CIEM identity facet counts (identity kinds, external/public splits).

Example:
  limacharlie cloudsec ciem facets
"""

_EXPLAIN_INVENTORY_LIST = """\
List the cloud resource inventory (system-of-record rows).

Examples:
  limacharlie cloudsec inventory list
  limacharlie cloudsec inventory list --type gcp_bucket --region us-central1
  limacharlie cloudsec inventory list -q prod --limit 50
"""

_EXPLAIN_INVENTORY_FACETS = """\
Inventory facet counts by type/account/region.

Example:
  limacharlie cloudsec inventory facets
"""

_EXPLAIN_DATA_SECURITY_FACETS = """\
DSPM data-store facet counts: total/sensitive/public/public-sensitive
data stores plus store-kind, sensitivity, and exposure histograms.

Example:
  limacharlie cloudsec data-security facets
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
(limacharlie hive list cloudsec_query).

Example:
  limacharlie cloudsec query list
"""

_EXPLAIN_QUERY_RUN = """\
Run a graph query against the org's security graph. Provide exactly
one of --named (a query-pack name), --text (a text query), or
--query-json (a raw DSL object). Returns alias->urn rows.

Examples:
  limacharlie cloudsec query run --named public-buckets
  limacharlie cloudsec query run --text "public bucket with sensitive data"
  limacharlie cloudsec query run --query-json '{"match": ...}' --project a,b
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

_EXPLAIN_PROVIDER_TEST = """\
Preflight a cloud provider configuration before saving it: connect
to the provider with the given credentials (ephemeral — never
stored) and probe every permission surface collection needs.
report.ok is the overall verdict over the REQUIRED checks; a failed
optional check flags a gracefully-degraded surface, not a failure.

The input is a cloudsec_provider hive record shape; 'credentials'
may be inline plaintext or a hive://secret/<name> reference. Saved
provider configs are managed via the hive:

  limacharlie hive set cloudsec_provider --key my-gcp --data provider.json

The record can come from inline JSON, a JSON/YAML file, or stdin.

Examples:
  limacharlie cloudsec provider test --input-file provider.yaml
  limacharlie cloudsec provider test --provider-json '{"provider_type":"gcp",...}'
"""

register_explain("cloudsec.overview", _EXPLAIN_OVERVIEW)
register_explain("cloudsec.changes", _EXPLAIN_CHANGES)
register_explain("cloudsec.risk-trend", _EXPLAIN_RISK_TREND)
register_explain("cloudsec.scan-status", _EXPLAIN_SCAN_STATUS)
register_explain("cloudsec.finding.list", _EXPLAIN_FINDING_LIST)
register_explain("cloudsec.finding.facets", _EXPLAIN_FINDING_FACETS)
register_explain("cloudsec.finding.get", _EXPLAIN_FINDING_GET)
register_explain("cloudsec.finding.resolve", _EXPLAIN_FINDING_RESOLVE)
register_explain("cloudsec.finding.bulk-resolve", _EXPLAIN_FINDING_BULK_RESOLVE)
register_explain("cloudsec.finding.set-owner", _EXPLAIN_FINDING_SET_OWNER)
register_explain("cloudsec.finding.set-ticket", _EXPLAIN_FINDING_SET_TICKET)
register_explain("cloudsec.attack-path.list", _EXPLAIN_ATTACK_PATH_LIST)
register_explain("cloudsec.ciem.public-access", _EXPLAIN_CIEM_PUBLIC_ACCESS)
register_explain("cloudsec.ciem.facets", _EXPLAIN_CIEM_FACETS)
register_explain("cloudsec.inventory.list", _EXPLAIN_INVENTORY_LIST)
register_explain("cloudsec.inventory.facets", _EXPLAIN_INVENTORY_FACETS)
register_explain("cloudsec.data-security.facets", _EXPLAIN_DATA_SECURITY_FACETS)
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


def _load_file(path: str, param_hint: str) -> Any:
    """Read + parse a JSON or YAML file, raising a clean usage error.

    Same YAML-first-then-JSON idiom as the other command modules' file
    inputs (hive, ioc, output, ...), so .yaml configs work everywhere.
    """
    try:
        with open(path, "r") as f:
            content = f.read()
    except OSError as exc:
        raise click.BadParameter(f"cannot read file: {exc}", param_hint=param_hint)
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"file is neither valid YAML nor JSON: {exc}", param_hint=param_hint,
        )


def _load_stdin() -> Any:
    """Parse piped stdin as YAML-or-JSON; None when stdin is a TTY."""
    if sys.stdin.isatty():
        return None
    content = sys.stdin.read()
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


def _one_of(param_hint: str, **provided: Any) -> None:
    """Require exactly one of the given options to be set (non-empty)."""
    given = [k for k, v in provided.items() if v]
    if len(given) != 1:
        names = ", ".join(f"--{k.replace('_', '-')}" for k in provided)
        raise click.UsageError(
            f"provide exactly one of {names} for {param_hint}",
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

    Exactly one of the inline/file options may be set; with neither, piped
    stdin is read (YAML or JSON). The result must be an object — a `null`
    or non-object input is rejected here rather than reaching the server.
    """
    if inline and input_file:
        raise click.UsageError(
            f"provide only one of {inline_hint} or {file_hint} for {what}",
        )
    if inline:
        value = _parse_json_opt(inline, inline_hint)
        hint = inline_hint
    elif input_file:
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


# Resolution kinds are a fixed server contract; 'open' (reopen) is only
# accepted by the single-finding endpoint, not the bulk one.
_KIND_CHOICES = click.Choice(
    ["mitigated", "accepted", "false_positive", "open"], case_sensitive=False,
)
_BULK_KIND_CHOICES = click.Choice(
    ["mitigated", "accepted", "false_positive"], case_sensitive=False,
)
_ORDER_CHOICES = click.Choice(["asc", "desc"], case_sensitive=False)
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
        "--kev/--no-kev", "kev", default=None,
        help="Only findings with (without) a KEV vulnerability.",
    )(f)
    f = click.option(
        "--reachable/--no-reachable", "reachable", default=None,
        help="Only findings on (non-)reachable resources.",
    )(f)
    f = click.option(
        "--account", "accounts", multiple=True,
        help="Filter by cloud account; repeatable (OR).",
    )(f)
    f = click.option(
        "--status", "statuses", multiple=True,
        help="Filter by status (open/resolved); repeatable (OR).",
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


def _sort_options(f):
    f = click.option(
        "--order", default=None, type=_ORDER_CHOICES,
        help="Sort order: asc or desc.",
    )(f)
    f = click.option(
        "--sort", default=None,
        help="Field to sort by (server-side).",
    )(f)
    return f


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("cloudsec")
def group() -> None:
    """Cloud Security (CNAPP): findings, inventory, graph, compliance.

    Requires the org to be subscribed to the ext-cloud-inventory
    extension. Reads need the 'cloudsec.get' permission; triage and
    other writes need 'cloudsec.set'. Provider configs and policies
    are hive records (cloudsec_provider / cloudsec_policy hives).

    \b
    Subgroups / commands:
      overview            Composed risk overview (score, top paths, trend)
      changes             Recent finding created/closed feed
      risk-trend          Risk-score history
      scan-status         Cloud-collection run status per provider
      finding ...         Findings worklist + triage (resolve, owner, ticket)
      attack-path list    Headline toxic-combination attack paths
      ciem ...            Identity access views (public-access, facets)
      inventory ...       Cloud resource inventory
      data-security ...   DSPM data-store facets
      resource get        Canonical record for any urn
      graph neighbors     1-hop graph expansion around a urn
      query ...           Graph queries (list pack, run)
      compliance ...      Framework assessment, frameworks, assignments
      chokepoint ...      Estate-wide chokepoints (list, dismiss, restore)
      resolve ...         Sensor <-> cloud asset resolution
      caasm ...           Third-party asset inventory, coverage, ingest
      provider test       Preflight provider credentials before saving
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
              help="Cloud provider (e.g. gcp, aws, azure, okta, 1password, "
                   "google_workspace, cloudflare); validated server-side; default gcp.")
@pass_context
def scan_status(ctx, provider) -> None:
    """Cloud-collection run status for a provider.

    \b
    Example:
      limacharlie cloudsec scan-status --provider aws
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_scan_status(provider=provider))


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
def finding_list(ctx, severities, finding_classes, statuses, accounts,
                 reachable, kev, q, sort, order, cursor, limit) -> None:
    """List the merged, risk-ranked cloud-security findings.

    \b
    Examples:
      limacharlie cloudsec finding list --severity CRITICAL --severity HIGH
      limacharlie cloudsec finding list --class public_exposure --kev
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_findings(
        severity=list(severities) or None,
        finding_class=list(finding_classes) or None,
        status=list(statuses) or None,
        account=list(accounts) or None,
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
@pass_context
def finding_facets(ctx, severities, finding_classes, statuses, accounts,
                   reachable, kev, q) -> None:
    """Cross-filtered facet counts for the findings worklist.

    \b
    Example:
      limacharlie cloudsec finding facets --severity CRITICAL
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_finding_facets(
        severity=list(severities) or None,
        finding_class=list(finding_classes) or None,
        status=list(statuses) or None,
        account=list(accounts) or None,
        reachable=reachable,
        kev=kev,
        q=q,
    ))


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
              help="Unix seconds; only meaningful with --kind accepted.")
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
              help="Unix seconds; only meaningful with --kind accepted.")
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
@pass_context
def ciem_facets(ctx) -> None:
    """CIEM identity facet counts.

    \b
    Example:
      limacharlie cloudsec ciem facets
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_identity_facets())


# ---------------------------------------------------------------------------
# inventory subgroup
# ---------------------------------------------------------------------------

@group.group("inventory")
def inventory_group() -> None:
    """Cloud resource inventory."""


@inventory_group.command("list")
@click.option("--type", "resource_type", default=None, help="Filter by resource type.")
@click.option("--account", default=None, help="Filter by cloud account.")
@click.option("--region", default=None, help="Filter by region.")
@click.option("-q", "--search", "q", default=None, help="Substring search.")
@_paging_options
@pass_context
def inventory_list(ctx, resource_type, account, region, q, cursor, limit) -> None:
    """List the cloud resource inventory.

    \b
    Examples:
      limacharlie cloudsec inventory list --type gcp_bucket
      limacharlie cloudsec inventory list -q prod --limit 50
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.list_inventory(
        resource_type=resource_type, account=account, region=region,
        q=q, cursor=cursor, limit=limit,
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
@pass_context
def data_security_facets(ctx) -> None:
    """DSPM data-store facet counts.

    \b
    Example:
      limacharlie cloudsec data-security facets
    """
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.get_data_security_facets())


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
@click.option("--project", default=None,
              help="Comma-separated aliases to project into the rows.")
@pass_context
def query_run(ctx, named, text, query_json, project) -> None:
    """Run a graph query (one of --named / --text / --query-json).

    \b
    Examples:
      limacharlie cloudsec query run --named public-buckets
      limacharlie cloudsec query run --text "public bucket with sensitive data"
    """
    _one_of("the query", named=named, text=text, query_json=query_json)
    query = None
    if query_json:
        query = _parse_json_opt(query_json, "--query-json")
        # Unconditional: a JSON `null` must not slip through as "no query".
        if not isinstance(query, dict):
            raise click.BadParameter("must decode to a JSON object", param_hint="--query-json")
    project_list = [p.strip() for p in project.split(",") if p.strip()] if project else None
    cs = _get_cloudsec(ctx)
    _output(ctx, cs.run_query(
        named=named, text=text, query=query, project=project_list,
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
    """Resolve SIDS to the cloud asset each sensor runs on (bulk, max 500).

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
    """Resolve asset URNS to the sensors running on each (bulk, max 500).

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
    """Provider credential preflight (configs live in the cloudsec_provider hive)."""


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
