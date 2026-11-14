"""Host Posture commands for LimaCharlie CLI v2.

Wraps the ``ext-host-posture`` extension and its ``host_posture_rule`` hive:

* ``rules`` -- the hive, one record per rule (record name = rule id).
* ``install-defaults`` -- write LimaCharlie's default pack into the hive.
* ``scan`` / ``sweep`` -- check one sensor now, or sweep the fleet now.
* ``results`` -- the per-host results the extension keeps.

Rules are validated by the server when saved, so the CLI does no client-side
validation of a rule.
"""

from __future__ import annotations

import click

from ..cli import pass_context
from ..client import Client
from ..discovery import register_explain
from ..sdk.host_posture import HostPosture, SEVERITIES, STATUSES
from ..sdk.organization import Organization
from ._hive_shortcut import PAGING_HELP, make_hive_group
from ._output_helpers import command_output

group = click.Group(
    "host-posture",
    help="Host Posture: misconfiguration checks on Windows, macOS and Linux hosts.",
)

rules_group = make_hive_group(
    "rules", "host_posture_rule", "Host Posture rule",
    "Host Posture rules", explain_prefix="host-posture.rules",
)
group.add_command(rules_group)


@click.group("results")
def results_group() -> None:
    """Per-host results: summary, hosts, host, rules, rule-hosts, standards."""


group.add_command(results_group)


def _get_hp(ctx: click.Context) -> HostPosture:
    client = Client(
        oid=ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
    )
    return HostPosture(Organization(client))


_PAGE_HELP = (
    "Lists are filtered and paged on the server. --limit is at most 200 (default 50); "
    "pass the next_cursor of a page as --cursor to get the next one."
)


def _page_options(fn):
    fn = click.option("--cursor", default=None, help="next_cursor of the previous page.")(fn)
    fn = click.option("--limit", type=click.IntRange(min=1, max=200), default=None,
                      help="Page size (default 50, at most 200).")(fn)
    return fn


register_explain("host-posture", """\
Host Posture checks Windows, macOS and Linux sensors for misconfigurations.
The checks are rules stored in the organization's 'host_posture_rule' hive,
one record per rule (the record name is the rule id). The extension
('ext-host-posture') ships no rules: install LimaCharlie's default pack with
'install-defaults', then edit, disable or add your own. Every rule is
equally trusted, whoever wrote it.

  rules             The hive: list, get, set, delete, enable, disable, tag.
  install-defaults  Write the default pack into the hive.
  scan              Check one online sensor now.
  sweep             Sweep sensors now (reaches offline sensors later).
  results           Per-host results: summary, hosts, host, rules,
                    rule-hosts, standards.
  status            Extension health: build, pack version, rule counts.

Permissions: host_posture.get reads, host_posture.set writes. Saving,
enabling and disabling a rule ALSO need sensor.task (a rule runs on the
sensors); deleting a rule needs only host_posture.set.

Examples:
  limacharlie host-posture install-defaults
  limacharlie host-posture results summary
  limacharlie host-posture scan --sid <SID>
""")

register_explain("host-posture.rules", """\
Manage Host Posture rules (hive 'host_posture_rule').  One record per rule,
keyed by rule id.  See 'limacharlie host-posture rules set --ai-help' for the
record format.
""")

register_explain("host-posture.rules.list", """\
List the Host Posture rules stored in the organization (the rule documents,
not results; for per-rule pass and fail counts use 'host-posture results rules').
The hive is per-org (OID-partitioned).
""" + "\n" + PAGING_HELP)

register_explain("host-posture.rules.get", """\
Get one Host Posture rule by rule id, with its data and metadata.
""")

register_explain("host-posture.rules.set", """\
Create or update a Host Posture rule.  The record key (--key) is the rule id
and must equal rule.id.

The data payload:

  data:
    rule:                          # one lc-posture/v1 signature document
      apiVersion: lc-posture/v1
      kind: Signature
      id: acme.linux.fs.protected-symlinks
      version: 1
      title: ...
      severity: medium             # critical | high | medium | low | info
      platforms: [linux]           # linux | windows | macos
      probes: {...}
      violation: '...'
      remediation: {text: ...}
      tests: [...]                 # optional; when present they must all pass
    scope:                         # optional
      sensor_tags: [prod]          # run only on sensors with one of these tags
      exclude_sensor_tags: [kiosk] # skip sensors with any of these (wins)

No other top-level key is accepted.  Each tag list holds at most 32 tags of
at most 128 bytes, and the rule document is at most 128 KiB.  The server
validates the whole rule, including its tests, and refuses it with the field
path of every problem.

Permissions: host_posture.set AND sensor.task (checked when saving).

The server stores a new record with no metadata according to the hive's
default; pass --enabled to be sure the rule runs.  Passing --tag or --comment
without --enabled keeps an existing record's enabled state; a record that does
not exist yet is created DISABLED (with a warning).

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie host-posture rules set --key acme.linux.fs.protected-symlinks --input-file rule.yaml --enabled
""")

register_explain("host-posture.rules.delete", """\
Delete a Host Posture rule by rule id.  Requires --confirm.  Needs
host_posture.set (not sensor.task).  The findings it raised close as retired;
in Cloud Security the rule's finding closes as 'rule removed'.
""")

register_explain("host-posture.rules.enable", """\
Enable a rule.  Needs host_posture.set AND sensor.task.
""")

register_explain("host-posture.rules.disable", """\
Disable a rule so it stops running on sensors.  Needs host_posture.set AND
sensor.task.  In Cloud Security the rule's finding closes as 'rule removed',
never as resolved.
""")

register_explain("host-posture.install-defaults", """\
Write LimaCharlie's default pack of rules into this org's 'host_posture_rule'
hive, with YOUR permissions (host_posture.set and sensor.task).  After that a
default rule is an ordinary record you can edit, disable or delete.

Nothing is overwritten silently:
  - A rule that is not in the hive is created, enabled (--disabled creates
    them disabled).  Creation is conditional, so a record that appears in
    the meantime is not replaced.
  - A rule that exists is skipped and listed, with its installed and pack
    versions.
  - --update replaces a rule only when the pack's version is newer AND the
    record is one a previous install wrote that nobody has edited since
    (its data still matches the digest tag the install stored).  The write
    is conditional on the etag that was read.  Enabled state, expiry, other
    tags and your own comment are kept.
  - A rule the org edited, one not installed from the pack, or one that is as
    new as the pack's is replaced only with --force (which implies --update).
  - --dry-run reports what would happen and writes nothing.

Result: pack_version, created, updated, skipped (each with a reason) and
failed.  Exits 1 when something failed.

Examples:
  limacharlie host-posture install-defaults
  limacharlie host-posture install-defaults --dry-run
  limacharlie host-posture install-defaults --update
  limacharlie host-posture install-defaults --id lc.windows.network.smb1-server --disabled
""")

register_explain("host-posture.scan", """\
Scan one ONLINE sensor now with every enabled rule that applies to it.
Returns {job_id, sid, platform, tasks_issued}.  Results appear as the sensor
replies ('host-posture results host --sid ...').  To reach sensors that may
be offline use 'sweep'.
""")

register_explain("host-posture.sweep", """\
Sweep sensors now with reliable tasking, which also reaches sensors that are
offline now.  Without --tag every supported sensor is swept (subject to the
extension's scope_tags); with --tag only sensors carrying at least one of the
tags.  Returns {job_id, sensors_tasked}.

Examples:
  limacharlie host-posture sweep
  limacharlie host-posture sweep --tag prod --tag web
""")

register_explain("host-posture.status", """\
Extension health: build identity, pack version and rule counts, and any rule
record that failed to parse.
""")

register_explain("host-posture.results", """\
Per-host results kept by the extension.  Statuses: pass, fail, error,
not_applicable, unsupported.  Severities: critical, high, medium, low, info.
""" + _PAGE_HELP)

register_explain("host-posture.results.summary", """\
Org-wide counts: hosts assessed and failing, results by status, failing hosts by
severity, enabled rules, the last sweep and cloud_security
(published | not_subscribed | error).
""")

register_explain("host-posture.results.hosts", """\
List hosts with their failing and error counts and worst severity (server-side
filters).  """ + _PAGE_HELP)

register_explain("host-posture.results.host", """\
Every rule result of one host with its evidence and first and last seen times.
""")

register_explain("host-posture.results.rules", """\
List rules with the number of hosts assessed, failing, in error and not
applicable (server-side filters).  """ + _PAGE_HELP)

register_explain("host-posture.results.rule-hosts", """\
List the hosts that have a given status for one rule.  """ + _PAGE_HELP)

register_explain("host-posture.results.standards", """\
How hosts do against each standard control (CIS, STIG, NIST, ...), optionally
for one framework.
""")


@group.command("install-defaults")
@click.option("--id", "ids", multiple=True, help="Install only this rule id of the pack (repeatable).")
@click.option("--update", is_flag=True, default=False,
              help="Also replace older versions of rules the pack installed and nobody edited.")
@click.option("--force", is_flag=True, default=False,
              help="Replace existing rules that differ from the pack even if edited (implies --update).")
@click.option("--disabled", is_flag=True, default=False, help="Create new rules disabled.")
@click.option("--dry-run", is_flag=True, default=False, help="Report what would happen and write nothing.")
@pass_context
def install_defaults(ctx, ids, update, force, disabled, dry_run) -> None:
    """Write LimaCharlie's default pack into the org's rule hive (never overwrites silently)."""
    result = _get_hp(ctx).install_default_pack(
        list(ids) or None, update=update, force=force, enabled=not disabled, dry_run=dry_run,
    )
    command_output(ctx, result)
    if result["failed"]:
        ctx.exit(1)


@group.command("scan")
@click.option("--sid", required=True, help="Sensor ID to scan (must be online).")
@pass_context
def scan(ctx, sid) -> None:
    """Scan one online sensor now."""
    command_output(ctx, _get_hp(ctx).scan(sid))


@group.command("sweep")
@click.option("--tag", "tags", multiple=True, help="Only sensors with this tag (repeatable, any-of).")
@pass_context
def sweep(ctx, tags) -> None:
    """Sweep sensors now, including offline ones when they return."""
    command_output(ctx, _get_hp(ctx).sweep(list(tags) or None))


@group.command("status")
@pass_context
def status(ctx) -> None:
    """Extension health: build, pack version, rule counts."""
    command_output(ctx, _get_hp(ctx).status())


@results_group.command("summary")
@pass_context
def results_summary(ctx) -> None:
    """Org-wide counts of hosts, results and failing severities."""
    command_output(ctx, _get_hp(ctx).query_summary())


@results_group.command("hosts")
@click.option("--platform", default=None, help="Filter by platform (windows, linux, macos).")
@click.option("--severity", type=click.Choice(SEVERITIES), default=None, help="Filter by worst severity.")
@click.option("--status", "status_", type=click.Choice(STATUSES), default=None, help="Filter by result status.")
@click.option("--search", default=None, help="Search hostnames.")
@_page_options
@pass_context
def results_hosts(ctx, platform, severity, status_, search, cursor, limit) -> None:
    """List hosts with their failing counts."""
    command_output(ctx, _get_hp(ctx).query_hosts(
        platform=platform, severity=severity, status=status_, search=search, cursor=cursor, limit=limit,
    ))


@results_group.command("host")
@click.option("--sid", required=True, help="Sensor ID.")
@pass_context
def results_host(ctx, sid) -> None:
    """Every rule result of one host."""
    command_output(ctx, _get_hp(ctx).query_host(sid))


@results_group.command("rules")
@click.option("--severity", type=click.Choice(SEVERITIES), default=None, help="Filter by severity.")
@click.option("--platform", default=None, help="Filter by platform.")
@click.option("--search", default=None, help="Search rule ids and titles.")
@_page_options
@pass_context
def results_rules(ctx, severity, platform, search, cursor, limit) -> None:
    """List rules with assessed, failing and error host counts."""
    command_output(ctx, _get_hp(ctx).query_rules(
        severity=severity, platform=platform, search=search, cursor=cursor, limit=limit,
    ))


@results_group.command("rule-hosts")
@click.option("--rule-id", required=True, help="Rule id.")
@click.option("--status", "status_", type=click.Choice(["fail", "error", "pass", "not_applicable"]),
              default="fail", show_default=True, help="Result status to list.")
@_page_options
@pass_context
def results_rule_hosts(ctx, rule_id, status_, cursor, limit) -> None:
    """List the hosts with a given status for one rule."""
    command_output(ctx, _get_hp(ctx).query_rule_hosts(rule_id, status_, cursor=cursor, limit=limit))


@results_group.command("standards")
@click.option("--framework", default=None, help="Only this framework (cis, stig, nist, pcidss, cce).")
@pass_context
def results_standards(ctx, framework) -> None:
    """How hosts do against each standard control."""
    command_output(ctx, _get_hp(ctx).query_standards(framework))
