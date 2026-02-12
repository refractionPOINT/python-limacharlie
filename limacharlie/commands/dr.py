"""D&R Rule commands for LimaCharlie CLI v2.

Commands for listing, creating, deleting, testing, replaying,
validating, exporting, and importing Detection & Response rules via the
Hive API.  D&R rules are stored in hives named dr-general, dr-managed,
and dr-service.
"""

import json
import sys

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.hive import Hive, HiveRecord
from ..sdk.replay import Replay as ReplaySDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

_NS_CHOICES = click.Choice(["general", "managed", "service"], case_sensitive=False)


def _hive_name(namespace):
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

The output includes the rule data and metadata from the hive.
"""

_EXPLAIN_GET = """\
Get the full definition of a single D&R rule by key.  Returns the
detection component, response component, enabled status, and metadata.

Rule keys are unique within a namespace.  If the rule is in the
'managed' or 'service' namespace, pass --namespace accordingly.
"""

_EXPLAIN_SET = """\
Create or update a D&R rule.  Provide rule data via --input-file
(JSON/YAML) or stdin.

The input should contain 'detect' and 'respond' keys (optionally
wrapped in a 'data' key for the full hive record format).

Examples:
  limacharlie dr set --key my-rule --input-file rule.yaml
  cat rule.json | limacharlie dr set --key my-rule
"""

_EXPLAIN_DELETE = """\
Delete a D&R rule by key.  This permanently removes the rule and stops
all detections based on it.  The --confirm flag is required to prevent
accidental deletion.

If the rule is in the 'managed' or 'service' namespace, pass --namespace
accordingly.
"""

_EXPLAIN_TEST = """\
Test a D&R rule against sample events.  This evaluates the rule's
detection logic against the provided events without deploying the rule
live.

The --events parameter accepts a path to a JSON file containing a
single event, a list of events, or newline-delimited JSON events.

You can test an existing rule by name, or provide a rule file with
--input-file containing 'detect' and 'respond' keys.

Examples:
  limacharlie dr test --name my-rule --events events.json
  limacharlie dr test --input-file rule.yaml --events events.json
"""

_EXPLAIN_REPLAY = """\
Replay a D&R rule against historical sensor data.  This evaluates
the rule against past events stored in Insight without deploying the
rule live.

The --start and --end times are Unix timestamps in seconds.  Use
--sid to limit replay to a specific sensor, or --selector for a
sensor selector expression.

Use --trace to include detailed evaluation trace output.
Use --dry-run to estimate the evaluation cost without running.

Examples:
  limacharlie dr replay --name my-rule --start 1700000000 --end 1700100000
  limacharlie dr replay --name my-rule --start 1700000000 --end 1700100000 --sid <SID>
"""

_EXPLAIN_VALIDATE = """\
Validate D&R rule components without deploying.  Checks that the
detection and response components compile correctly.

Provide the detection and response components as JSON or YAML files.

Examples:
  limacharlie dr validate --detect detect.yaml --respond respond.yaml
"""

_EXPLAIN_EXPORT = """\
Export all D&R rules as YAML.  Useful for backup, version control,
or migration between organizations.

Use --namespace to export only rules from a specific namespace.

Examples:
  limacharlie dr export
  limacharlie dr export --namespace managed
  limacharlie dr export > rules-backup.yaml
"""

_EXPLAIN_IMPORT = """\
Import D&R rules from a YAML or JSON file.  The file should contain
a mapping of rule names to rule definitions, each with 'detect' and
'respond' keys.

Rules are upserted (existing rules with the same name are overwritten).

Use --dry-run to preview what would be imported without making changes.

Examples:
  limacharlie dr import --input-file rules.yaml
  limacharlie dr import --input-file rules.yaml --dry-run
  limacharlie dr import --input-file rules.yaml --namespace managed
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text):
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx, data):
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx):
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _load_file(path):
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
def group():
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_rules(ctx, namespace):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, key, namespace):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SET),
    help="Show detailed explanation of this command.",
)
@pass_context
def set_cmd(ctx, key, input_file, namespace):
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
        record = HiveRecord(key, raw=raw)
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, key, namespace, confirm):
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

def _load_events(events_path):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_TEST),
    help="Show detailed explanation of this command.",
)
@pass_context
def test(ctx, name, events_path, input_file, trace, namespace):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_REPLAY),
    help="Show detailed explanation of this command.",
)
@pass_context
def replay(ctx, name, start, end, sid, selector, trace, dry_run, namespace):
    """Replay a rule against historical sensor data.

    Examples:
        limacharlie dr replay --name my-rule \\
            --start 1700000000 --end 1700100000

        limacharlie dr replay --name my-rule \\
            --start 1700000000 --end 1700100000 --sid <SID> --trace
    """
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_VALIDATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def validate(ctx, detect_path, respond_path):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_EXPORT),
    help="Show detailed explanation of this command.",
)
@pass_context
def export_rules(ctx, namespace):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_IMPORT),
    help="Show detailed explanation of this command.",
)
@pass_context
def import_rules(ctx, input_file, namespace, dry_run):
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
                record = HiveRecord(rule_name, raw=raw)
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
