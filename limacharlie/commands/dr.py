"""D&R Rule commands for LimaCharlie CLI v2.

Commands for listing, creating, deleting, testing, replaying,
validating, exporting, and importing Detection & Response rules via the
Hive API.  D&R rules are stored in hives named dr-general, dr-managed,
and dr-service.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click
import yaml

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.hive import Hive, HiveRecord
from ..sdk.replay import Replay as ReplaySDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ._time_validation import validate_epoch_seconds


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

_NS_CHOICES = click.Choice(["general", "managed", "service"], case_sensitive=False)


def _hive_name(namespace: str | None) -> str:
    """Map a user-facing namespace to the hive name."""
    return f"dr-{namespace or 'general'}"


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all D&R rules in the organization.  By default, rules from the
'general' namespace are returned.  Use --namespace to select:

  general  - Custom rules created by users (the default namespace).
  managed  - Rules managed by LimaCharlie or extensions.
  service  - Rules created by services/replicants.

Each returned rule contains:
  data:
    detect: { ... }    # detection logic (operators, paths, values)
    respond: [ ... ]   # list of response actions
    tests:             # optional unit tests
      match: [ ... ]
      non_match: [ ... ]
  usr_mtd:
    enabled: true/false
    expiry: 0          # unix epoch, 0 = no expiry
    tags: []
    comment: ""

Examples:
  limacharlie dr list
  limacharlie dr list --namespace managed
  limacharlie dr list --namespace service
"""

_EXPLAIN_GET = """\
Get the full definition of a single D&R rule by key.  Returns the
detection component, response component, enabled status, and metadata.

The returned structure looks like:

  data:
    detect:
      event: NEW_PROCESS
      op: ends with
      path: event/FILE_PATH
      value: .exe
    respond:
      - action: report
        name: my-detection
    tests:             # optional unit tests
      match: [...]
      non_match: [...]
  usr_mtd:
    enabled: true
    expiry: 0
    tags: []
    comment: ""

Rule keys are unique within a namespace.  If the rule is in the
'managed' or 'service' namespace, pass --namespace accordingly.

Examples:
  limacharlie dr get --key my-rule
  limacharlie dr get --key some-managed-rule --namespace managed
"""

_EXPLAIN_SET = """\
Create or update a D&R rule.  Provide rule data via --input-file
(JSON/YAML) or stdin.

The input must contain detect and respond components.  Minimal example:

  detect:
    event: NEW_PROCESS
    op: contains
    path: event/COMMAND_LINE
    value: mimikatz
  respond:
    - action: report
      name: mimikatz-detected

The detect component matches events using operators against event field
paths.  Common operators: is, contains, starts with, ends with, matches
(regex), exists, is greater than, is lower than, string distance.
Boolean operators (and, or) combine sub-rules via the 'rules:' list.
Use 'not: true' on any operator to invert its match.

The 'event:' field filters to a specific event type (NEW_PROCESS,
NETWORK_CONNECTIONS, DNS_REQUEST, CODE_IDENTITY, WEL, etc.).  By
default rules target 'edr' events; use 'target:' to switch to
detection, deployment, artifact, artifact_event, schedule, audit,
or billing targets.

For stateful detection use 'with child:', 'with descendant:', or
'with events:' to correlate across multiple events over time.
Use 'count:' and 'within:' (seconds) for frequency thresholds.

The respond component is a list of actions.  Common actions:
  - action: report           # generate a detection/alert
    name: detection-name
  - action: task             # send a command to the sensor
    command: history_dump
  - action: add tag          # tag the sensor
    tag: suspicious
    ttl: 86400               # optional TTL in seconds
  - action: isolate network  # isolate from network
  - action: output           # forward to a specific output
    name: my-output

Any action supports a 'suppression:' block to limit frequency:
  suppression:
    max_count: 1
    period: 1h
    is_global: false
    keys:
      - '{{ .event.FILE_PATH }}'

You can optionally include unit tests:
  tests:
    match:
      - - event: { ... }       # list of events that should trigger
          routing: { ... }
    non_match:
      - - event: { ... }       # list of events that should NOT trigger
          routing: { ... }

The input can also use the full hive record format with a 'data'
wrapper and 'usr_mtd' for metadata like enabled/expiry/tags:

  data:
    detect: { ... }
    respond: [ ... ]
  usr_mtd:
    enabled: true
    expiry: 0
    tags: []
    comment: "rule description"

Examples:
  limacharlie dr set --key my-rule --input-file rule.yaml
  cat rule.json | limacharlie dr set --key my-rule
  limacharlie dr set --key my-rule --namespace managed --input-file rule.yaml
"""

_EXPLAIN_DELETE = """\
Delete a D&R rule by key.  This permanently removes the rule and stops
all detections based on it.  The --confirm flag is required to prevent
accidental deletion.

If the rule is in the 'managed' or 'service' namespace, pass
--namespace accordingly.

Examples:
  limacharlie dr delete --key my-rule --confirm
  limacharlie dr delete --key some-managed-rule --namespace managed --confirm
"""

_EXPLAIN_TEST = """\
Test a D&R rule against sample events without deploying it live.  This
sends the events through the rule engine and returns which ones matched
along with the actions that would fire.

You can test an existing deployed rule by --name, or provide an ad-hoc
rule file via --input-file containing 'detect' and 'respond' keys.

The --events parameter accepts a path to a JSON file containing:
  - A single event object  {"event": {...}, "routing": {...}}
  - A JSON array of events [{"event": {...}}, ...]
  - Newline-delimited JSON (one event per line)

Events should match the structure LimaCharlie uses internally:

  {
    "event": {
      "FILE_PATH": "C:\\temp\\evil.exe",
      "COMMAND_LINE": "evil.exe --payload",
      "PROCESS_ID": 1234
    },
    "routing": {
      "event_type": "NEW_PROCESS",
      "hostname": "workstation-1",
      "sid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    }
  }

Use --trace for a detailed step-by-step evaluation trace showing
which operators matched or failed, useful for debugging rules.

The response includes num_evals, eval_time, num_events, responses
(list of actions that would fire), and errors.

Examples:
  limacharlie dr test --name my-rule --events events.json
  limacharlie dr test --input-file rule.yaml --events events.json
  limacharlie dr test --input-file rule.yaml --events events.json --trace
"""

_EXPLAIN_REPLAY = """\
Replay a D&R rule against historical sensor data.  This evaluates
the rule against past events stored in Insight without deploying the
rule live.  Replay is billed based on data volume processed; use
--dry-run first to estimate cost.

The --start and --end times are Unix timestamps in seconds.  Use
--sid to limit replay to a specific sensor, or --selector for a
sensor selector expression (boolean expression filtering sensors
by tags, platform, hostname, etc.).

Use --trace to include a detailed step-by-step evaluation trace.
Use --dry-run to estimate the evaluation cost without running.

The response includes num_evals, eval_time, num_events, responses
(detections that would have been generated), and errors.

Note: stateful rules are forward-looking only.  Changing a stateful
rule resets its state, so the parent event must be re-seen before
child matches apply.

Examples:
  limacharlie dr replay --name my-rule --start 1700000000 --end 1700100000
  limacharlie dr replay --name my-rule --start 1700000000 --end 1700100000 --sid <SID>
  limacharlie dr replay --name my-rule --start 1700000000 --end 1700100000 --dry-run
  limacharlie dr replay --name my-rule --start 1700000000 --end 1700100000 --trace
"""

_EXPLAIN_VALIDATE = """\
Validate D&R rule components without deploying.  Checks that the
detection and response components compile correctly: verifies
operators are known, paths are well-formed, and response actions
are valid.  Returns success: true if valid.

Provide separate files for the detection and response components:

  detection file (detect.yaml):
    event: NEW_PROCESS
    op: ends with
    path: event/FILE_PATH
    value: .scr

  response file (respond.yaml):
    - action: report
      name: suspicious-screensaver

This is useful for CI/CD validation before pushing rules.

Examples:
  limacharlie dr validate --detect detect.yaml --respond respond.yaml
"""

_EXPLAIN_EXPORT = """\
Export all D&R rules as YAML.  Useful for backup, version control,
or migration between organizations.

The output is a YAML mapping of rule names to their full hive
records (data + usr_mtd).  This format is compatible with
'limacharlie dr import'.

Use --namespace to export only rules from a specific namespace
(general, managed, or service).  Defaults to general.

Examples:
  limacharlie dr export
  limacharlie dr export --namespace managed
  limacharlie dr export > rules-backup.yaml
"""

_EXPLAIN_IMPORT = """\
Import D&R rules from a YAML or JSON file.  The file should contain
a mapping of rule names to rule definitions.  Rules are upserted
(existing rules with the same name are overwritten).

The file format is a mapping of rule-key to rule definition:

  my-rule-1:
    detect:
      event: NEW_PROCESS
      op: contains
      path: event/COMMAND_LINE
      value: evil
    respond:
      - action: report
        name: evil-detected

  my-rule-2:
    detect: { ... }
    respond: [ ... ]

The full hive record format (with 'data' wrapper and 'usr_mtd') is
also accepted:

  my-rule-1:
    data:
      detect: { ... }
      respond: [ ... ]
    usr_mtd:
      enabled: true
      tags: [production]

Use --dry-run to preview what would be imported without making changes.

Examples:
  limacharlie dr import --input-file rules.yaml
  limacharlie dr import --input-file rules.yaml --dry-run
  limacharlie dr import --input-file rules.yaml --namespace managed
"""

_EXPLAIN_CONVERT_RULES = """\
Mass-convert external detection rules to LimaCharlie D&R format using
AI-powered translation.  Reads rules from a local directory or a GitHub
repository, converts each to LC D&R format, and optionally creates
them in the dr-general hive.

The AI backend auto-detects the source format and platform — Sigma,
Splunk SPL, Elastic KQL, CrowdStrike, and many more are supported
without any format hint.

The GitHub crawler intelligently identifies rule files by extension
(.yml, .yaml, .json, .sigma, .spl, .kql, .toml) and filters out
non-rule files (README, LICENSE, CI configs, etc.).

Rules are created disabled by default for safety.  Use --enabled to
create them enabled.  Use --dry-run to preview conversions without
creating hive records.

Examples:
  limacharlie dr convert-rules --github SigmaHQ/sigma \\
      --github-path rules/windows/process_creation
  limacharlie dr convert-rules --input-dir ./splunk-rules --dry-run
  limacharlie dr convert-rules --github elastic/detection-rules \\
      --parallel 10 --tag migrated
"""

register_explain("dr.list", _EXPLAIN_LIST)
register_explain("dr.get", _EXPLAIN_GET)
register_explain("dr.set", _EXPLAIN_SET)
register_explain("dr.delete", _EXPLAIN_DELETE)
register_explain("dr.test", _EXPLAIN_TEST)
register_explain("dr.replay", _EXPLAIN_REPLAY)
register_explain("dr.validate", _EXPLAIN_VALIDATE)
register_explain("dr.export", _EXPLAIN_EXPORT)
register_explain("dr.import", _EXPLAIN_IMPORT)
register_explain("dr.convert-rules", _EXPLAIN_CONVERT_RULES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
    return Organization(client)


def _load_file(path: str) -> Any:
    """Load a JSON or YAML file and return parsed content."""
    with open(path, "r") as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("dr")
def group() -> None:
    """Manage Detection & Response rules.

    D&R rules are the core detection mechanism in LimaCharlie.  Each
    rule has a detection component (what to look for in sensor telemetry)
    and a response component (what actions to take when a match occurs).
    Rules are stored in hives (dr-general, dr-managed, dr-service).
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Namespace (default: general).",
)
@pass_context
def list_rules(ctx, namespace) -> None:
    """List D&R rules.

    Examples:
        limacharlie dr list
        limacharlie dr list --namespace managed
    """
    org = _get_org(ctx)
    hive = Hive(org, _hive_name(namespace))
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--key", required=True, help="Rule key name.")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Namespace (default: general).",
)
@pass_context
def get(ctx, key, namespace) -> None:
    """Get the full definition of a D&R rule.

    Example:
        limacharlie dr get --key my-detection-rule
    """
    org = _get_org(ctx)
    hive = Hive(org, _hive_name(namespace))
    record = hive.get(key)
    _output(ctx, record.to_dict())


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------

@group.command("set")
@click.option("--key", required=True, help="Rule key name.")
@click.option(
    "--input-file", type=click.Path(exists=True), default=None,
    help="JSON or YAML file with rule data.",
)
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Namespace (default: general).",
)
@pass_context
def set_cmd(ctx, key, input_file, namespace) -> None:
    """Create or update a D&R rule.

    Examples:
        limacharlie dr set --key my-rule --input-file rule.yaml
        cat rule.json | limacharlie dr set --key my-rule
    """
    if input_file:
        with open(input_file, "r") as f:
            content = f.read()
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        raise click.UsageError("Provide data via --input-file or pipe to stdin.")

    try:
        data = yaml.safe_load(content)
    except Exception:
        data = json.loads(content)

    # Support the full hive record format (with "data" wrapper) or
    # a bare rule dict with detect/respond at the top level.
    if isinstance(data, dict) and "data" in data:
        raw = {
            "data": data["data"],
            "usr_mtd": data.get("usr_mtd", {}),
            "sys_mtd": {},
        }
        if data.get("etag"):
            raw["sys_mtd"]["etag"] = data["etag"]
        record = HiveRecord.from_raw(key, raw)
    else:
        record = HiveRecord(key, data=data)

    org = _get_org(ctx)
    hive = Hive(org, _hive_name(namespace))
    result = hive.set(record)
    _output(ctx, result)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--key", required=True, help="Rule key name to delete.")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Namespace (default: general).",
)
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, key, namespace, confirm) -> None:
    """Delete a D&R rule.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie dr delete --key my-rule --confirm
    """
    if not confirm:
        raise click.UsageError("Destructive operation requires --confirm flag.")

    org = _get_org(ctx)
    hive = Hive(org, _hive_name(namespace))
    result = hive.delete(key)
    _output(ctx, result)


# ---------------------------------------------------------------------------
# Helpers for loading events
# ---------------------------------------------------------------------------

def _load_events(events_path: str) -> list[dict[str, Any]]:
    """Load events from a JSON file.

    Supports:
    - A JSON list of events
    - A single JSON event (dict)
    - Newline-delimited JSON (one event per line)
    """
    with open(events_path, "r") as f:
        content = f.read()

    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    # Try newline-delimited JSON
    events = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

@group.command("test")
@click.option("--name", default=None, help="Existing rule name to test.")
@click.option("--events", "events_path", required=True, type=click.Path(exists=True), help="Path to JSON file with events.")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to rule file (JSON or YAML with 'detect' and 'respond' keys).")
@click.option("--trace", is_flag=True, default=False, help="Include detailed evaluation trace in output.")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Rule namespace (when using --name).",
)
@pass_context
def test(ctx, name, events_path, input_file, trace, namespace) -> None:
    """Test a rule against sample events.

    Provide --name for an existing rule, or --input-file for a rule
    definition with 'detect' and 'respond' keys.

    Examples:
        limacharlie dr test --name my-rule --events events.json
        limacharlie dr test --input-file rule.yaml --events events.json
    """
    rule_content = None

    if name is None:
        if input_file is None:
            click.echo(
                "Error: Provide --name for an existing rule, or --input-file with rule definition.",
                err=True,
            )
            ctx.exit(4)
            return
        rule_content = _load_file(input_file)
        if not isinstance(rule_content, dict) or "detect" not in rule_content:
            click.echo("Error: --input-file must contain 'detect' and 'respond' keys.", err=True)
            ctx.exit(4)
            return

    events = _load_events(events_path)

    org = _get_org(ctx)
    replay = ReplaySDK(org)
    data = replay.scan_events(
        events,
        rule_name=name,
        namespace=namespace,
        rule_content=rule_content,
        trace=trace,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name to replay.")
@click.option("--start", required=True, type=int, help="Start time (Unix seconds).")
@click.option("--end", required=True, type=int, help="End time (Unix seconds).")
@click.option("--sid", default=None, help="Specific sensor ID to replay against.")
@click.option("--selector", default=None, help="Sensor selector expression (bexpr).")
@click.option("--trace", is_flag=True, default=False, help="Include detailed evaluation trace in output.")
@click.option("--dry-run", is_flag=True, default=False, help="Estimate cost without running.")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Rule namespace.",
)
@pass_context
def replay(ctx, name, start, end, sid, selector, trace, dry_run, namespace) -> None:
    """Replay a rule against historical sensor data.

    Examples:
        limacharlie dr replay --name my-rule \\
            --start 1700000000 --end 1700100000

        limacharlie dr replay --name my-rule \\
            --start 1700000000 --end 1700100000 --sid <SID> --trace
    """
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    replay_sdk = ReplaySDK(org)
    data = replay_sdk.run(
        rule_name=name,
        start=start,
        end=end,
        sid=sid,
        selector=selector,
        trace=trace,
        dry_run=dry_run,
    )
    _output(ctx, data)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@group.command()
@click.option("--detect", "detect_path", required=True, type=click.Path(exists=True), help="Path to detection component (JSON or YAML file).")
@click.option("--respond", "respond_path", required=True, type=click.Path(exists=True), help="Path to response component (JSON or YAML file).")
@pass_context
def validate(ctx, detect_path, respond_path) -> None:
    """Validate D&R rule components without deploying.

    Examples:
        limacharlie dr validate --detect detect.yaml --respond respond.yaml
    """
    detection = _load_file(detect_path)
    response = _load_file(respond_path)

    rule_content = {
        "detect": detection,
        "respond": response,
    }

    org = _get_org(ctx)
    replay_sdk = ReplaySDK(org)
    data = replay_sdk.validate_rule(rule_content)

    if not ctx.obj.quiet:
        click.echo("Rule validated successfully.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@group.command("export")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Export rules from this namespace only (default: general).",
)
@pass_context
def export_rules(ctx, namespace) -> None:
    """Export all D&R rules as YAML.

    Examples:
        limacharlie dr export
        limacharlie dr export --namespace managed
        limacharlie dr export > rules-backup.yaml
    """
    org = _get_org(ctx)
    hive = Hive(org, _hive_name(namespace))
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    click.echo(yaml.dump(data, default_flow_style=False, sort_keys=True))


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@group.command("import")
@click.option("--input-file", required=True, type=click.Path(exists=True), help="Path to YAML or JSON file with rules to import.")
@click.option(
    "--namespace", default=None, type=_NS_CHOICES,
    help="Import rules into this namespace (default: general).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Preview changes without importing.")
@pass_context
def import_rules(ctx, input_file, namespace, dry_run) -> None:
    """Import D&R rules from a YAML or JSON file.

    The file should contain a mapping of rule names to rule definitions,
    each with 'detect' and 'respond' keys.

    Examples:
        limacharlie dr import --input-file rules.yaml
        limacharlie dr import --input-file rules.yaml --dry-run
        limacharlie dr import --input-file rules.yaml --namespace managed
    """
    rules_data = _load_file(input_file)

    if not isinstance(rules_data, dict):
        click.echo("Error: Input file must contain a YAML/JSON object mapping rule names to definitions.", err=True)
        ctx.exit(4)
        return

    if dry_run:
        if not ctx.obj.quiet:
            click.echo("Dry run - the following rules would be imported:")
            for rule_name in sorted(rules_data.keys()):
                click.echo(f"  {rule_name}")
            click.echo(f"\nTotal: {len(rules_data)} rules.")
        return

    org = _get_org(ctx)
    hive = Hive(org, _hive_name(namespace))
    imported = 0
    errors = []

    for rule_name, rule_def in rules_data.items():
        if not isinstance(rule_def, dict):
            errors.append(f"  {rule_name}: not a valid rule definition (expected dict)")
            continue

        try:
            # Support both bare detect/respond dicts and full hive record format
            if "data" in rule_def:
                record_data = rule_def["data"]
                raw = {
                    "data": record_data,
                    "usr_mtd": rule_def.get("usr_mtd", {}),
                    "sys_mtd": {},
                }
                record = HiveRecord.from_raw(rule_name, raw)
            else:
                record = HiveRecord(rule_name, data=rule_def)
            hive.set(record)
            imported += 1
        except Exception as e:
            errors.append(f"  {rule_name}: {e}")

    if not ctx.obj.quiet:
        click.echo(f"Imported {imported}/{len(rules_data)} rules.")
        if errors:
            click.echo("Errors:", err=True)
            for err in errors:
                click.echo(err, err=True)
    if errors:
        ctx.exit(min(len(errors), 125))


# ---------------------------------------------------------------------------
# convert-rules
# ---------------------------------------------------------------------------

@group.command("convert-rules")
@click.option(
    "--input-dir", type=click.Path(exists=True, file_okay=False), default=None,
    help="Local directory containing detection rule files.",
)
@click.option(
    "--github", "github_repo", default=None,
    help="GitHub repo to crawl (owner/repo or full URL).",
)
@click.option(
    "--github-path", default=None,
    help="Subdirectory within the GitHub repo to search.",
)
@click.option(
    "--github-ref", default=None,
    help="Branch or tag to use (default: repo default branch).",
)
@click.option(
    "--github-token", default=None, envvar="GH_TOKEN",
    help="GitHub token for private repos (or set GH_TOKEN env var).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Convert without creating hive records.")
@click.option(
    "--output-dir", type=click.Path(file_okay=False), default=None,
    help="Save converted rules as YAML files to this directory.",
)
@click.option(
    "--parallel", type=click.IntRange(1, 20), default=10,
    help="Number of parallel conversion workers (default: 10).",
)
@click.option("--prefix", default="", help="Prefix for rule key names in dr-general.")
@click.option("--tag", "tags", multiple=True, help="Tags to add to all converted rules (repeatable).")
@click.option("--enabled/--disabled", default=False, help="Whether rules start enabled (default: disabled).")
@pass_context
def convert_rules(ctx, input_dir, github_repo, github_path, github_ref,
                  github_token, dry_run, output_dir, parallel, prefix,
                  tags, enabled) -> None:
    """Mass-convert external detection rules to LC D&R format.

    Converts rules from local files or a GitHub repository using
    AI-powered translation, then creates them in dr-general.

    The AI auto-detects the source format (Sigma, Splunk, Elastic, etc.).

    Examples:
        limacharlie dr convert-rules --github SigmaHQ/sigma \\
            --github-path rules/windows/process_creation

        limacharlie dr convert-rules --input-dir ./my-rules --dry-run

        limacharlie dr convert-rules --github elastic/detection-rules \\
            --parallel 10 --tag migrated --disabled
    """
    from ._dr_convert import (
        GitHubCrawler, LocalCrawler, ConversionPipeline, ProgressDisplay,
    )

    # -- Validate inputs ---------------------------------------------------
    if not input_dir and not github_repo:
        raise click.UsageError("Provide --input-dir or --github.")
    if input_dir and github_repo:
        raise click.UsageError("Provide --input-dir or --github, not both.")

    quiet = ctx.obj.quiet

    def echo(msg: str) -> None:
        if not quiet:
            click.echo(msg)

    # -- Collect rule files ------------------------------------------------
    if github_repo:
        crawler = GitHubCrawler(github_repo, path=github_path, ref=github_ref, token=github_token)
        echo(f"Crawling GitHub repo: {crawler.display_name}...")
        rule_files = crawler.crawl(progress_echo=echo)
    else:
        echo(f"Scanning directory: {input_dir}")
        rule_files = LocalCrawler(input_dir).crawl()

    if not rule_files:
        click.echo("No rule files found.", err=True)
        ctx.exit(1)
        return

    echo(f"Found {len(rule_files)} rule file(s).\n")

    # -- Run conversion pipeline -------------------------------------------
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, is_retry_quota_errors=True)
    org = Organization(client)

    pipeline = ConversionPipeline(org, parallel=parallel, prefix=prefix)
    progress = ProgressDisplay(len(rule_files), quiet=quiet)
    results = pipeline.convert_all(rule_files, progress_callback=progress.update)

    # -- Create in hive (unless dry-run) -----------------------------------
    if not dry_run:
        hive = Hive(org, "dr-general")
        for r in results:
            if not r.success:
                continue
            try:
                record = HiveRecord(
                    name=r.rule_key,
                    data={"detect": r.detect, "respond": r.respond},
                    enabled=enabled,
                    tags=list(tags) if tags else None,
                    comment=f"Converted from: {r.source_path}",
                )
                hive.set(record)
                r.created_in_hive = True
            except Exception as exc:
                # Don't mark conversion as failed — it succeeded, only the
                # hive write failed.  Track the error separately.
                r.error = f"Hive write failed: {exc}"

    # -- Save to files (optional) ------------------------------------------
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        for r in results:
            if r.success:
                out_path = os.path.join(output_dir, f"{r.rule_key}.yaml")
                with open(out_path, "w") as f:
                    yaml.dump(
                        {"detect": r.detect, "respond": r.respond},
                        f, default_flow_style=False, sort_keys=False,
                    )

    # -- Summary -----------------------------------------------------------
    progress.finish(results)

    # -- Structured output -------------------------------------------------
    output_data = {
        "total": len(results),
        "converted": sum(1 for r in results if r.success),
        "failed": sum(1 for r in results if not r.success),
        "created_in_hive": sum(1 for r in results if r.created_in_hive),
        "rules": [
            {
                "source": r.source_path,
                "key": r.rule_key,
                "success": r.success,
                "error": r.error,
                "created_in_hive": r.created_in_hive,
            }
            for r in results
        ],
    }
    _output(ctx, output_data)

    # -- Exit code ---------------------------------------------------------
    if results and all(not r.success for r in results):
        ctx.exit(1)
