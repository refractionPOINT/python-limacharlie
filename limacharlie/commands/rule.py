"""D&R Rule commands for LimaCharlie CLI v2.

Commands for listing, creating, updating, and deleting Detection &
Response rules.  D&R rules are the core detection mechanism in
LimaCharlie: each rule has a detection component (what to look for) and
a response component (what to do when found).
"""

import json
import sys

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all D&R rules in the organization.  By default, rules from all
namespaces are returned.  Use --namespace to filter by namespace:

  general  - Custom rules created by users (the default namespace).
  managed  - Rules managed by LimaCharlie or extensions.
  service  - Rules created by services/replicants.

The output includes the rule name, namespace, enabled status, and the
detection and response components.  Use --output json to get the full
rule definitions for export or backup.
"""

_EXPLAIN_GET = """\
Get the full definition of a single D&R rule by name.  Returns the
detection component, response component, enabled status, and metadata.

Rule names are unique within a namespace.  If the rule is in the
'managed' or 'service' namespace, pass --namespace accordingly.
"""

_EXPLAIN_CREATE = """\
Create a new D&R rule.  You must provide the rule name and its detection
and response components.  Components can be provided inline as JSON via
--detect-file and --respond-file, or as a combined YAML/JSON file via
--input-file.

When using --input-file, the file should be a YAML or JSON document
with keys 'detect' and 'respond' (and optionally 'name', 'namespace',
'is_enabled').

If a rule with the same name already exists, the create will fail
unless you also pass --replace (or use the 'update' command instead).

D&R rules follow a stateless evaluation model: the detect component is
evaluated against each event independently, and if it matches, the
response actions are executed.  See 'limacharlie help d&r-rules' for
the full rule syntax and operator reference.

Examples:
  limacharlie rule create --name my-rule \\
    --detect-file detect.yaml --respond-file respond.yaml

  limacharlie rule create --name my-rule --input-file rule.yaml
"""

_EXPLAIN_UPDATE = """\
Update an existing D&R rule by replacing its detection and/or response
components.  This is equivalent to 'rule create --replace'.

The rule must already exist.  If it does not, use 'rule create' instead.
"""

_EXPLAIN_DELETE = """\
Delete a D&R rule by name.  This permanently removes the rule and stops
all detections based on it.  The --confirm flag is required to prevent
accidental deletion.

If the rule is in the 'managed' or 'service' namespace, pass --namespace
accordingly.
"""

register_explain("rule.list", _EXPLAIN_LIST)
register_explain("rule.get", _EXPLAIN_GET)
register_explain("rule.create", _EXPLAIN_CREATE)
register_explain("rule.update", _EXPLAIN_UPDATE)
register_explain("rule.delete", _EXPLAIN_DELETE)


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
    # Try YAML first (superset of JSON)
    try:
        return yaml.safe_load(content)
    except Exception:
        pass
    return json.loads(content)


def _load_json_or_yaml_file(path):
    """Load a file as JSON or YAML, returning the parsed dict/list."""
    return _load_file(path)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("rule")
def group():
    """Manage Detection & Response rules.

    D&R rules are the core detection mechanism in LimaCharlie.  Each
    rule has a detection component (what to look for in sensor telemetry)
    and a response component (what actions to take when a match occurs).
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option(
    "--namespace", default=None,
    type=click.Choice(["general", "managed", "service"], case_sensitive=False),
    help="Filter by namespace (default: all).",
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
        limacharlie rule list
        limacharlie rule list --namespace managed
    """
    org = _get_org(ctx)
    data = org.get_rules(namespace=namespace)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--namespace", default=None,
    type=click.Choice(["general", "managed", "service"], case_sensitive=False),
    help="Rule namespace (default: general).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, name, namespace):
    """Get the full definition of a D&R rule.

    Example:
        limacharlie rule get --name my-detection-rule
    """
    org = _get_org(ctx)
    rules = org.get_rules(namespace=namespace)
    if isinstance(rules, dict):
        rule = rules.get(name)
    else:
        rule = None

    if rule is None:
        ns_label = namespace or "general"
        click.echo(
            f"Error: Rule '{name}' not found in namespace '{ns_label}'.\n"
            "Suggestion: Use 'limacharlie rule list' to see available rules.",
            err=True,
        )
        ctx.exit(3)
        return

    _output(ctx, rule)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", default=None, help="Rule name (required unless using --input-file with 'name' key).")
@click.option("--detect-file", default=None, type=click.Path(exists=True), help="Path to detection component (JSON or YAML file).")
@click.option("--respond-file", default=None, type=click.Path(exists=True), help="Path to response component (JSON or YAML file).")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to combined rule file (JSON or YAML with 'detect' and 'respond' keys).")
@click.option(
    "--namespace", default=None,
    type=click.Choice(["general", "managed", "service"], case_sensitive=False),
    help="Rule namespace (default: general).",
)
@click.option("--replace", is_flag=True, default=False, help="Replace existing rule with the same name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name, detect_file, respond_file, input_file, namespace, replace):
    """Create a new D&R rule.

    Provide detection and response components either as separate files
    (--detect-file, --respond-file) or as a single combined file
    (--input-file).

    Examples:
        limacharlie rule create --name my-rule \\
            --detect-file detect.yaml --respond-file respond.yaml

        limacharlie rule create --input-file rule.yaml

        limacharlie rule create --name my-rule \\
            --detect-file detect.yaml --respond-file respond.yaml --replace
    """
    detection = None
    response = None

    if input_file:
        rule_data = _load_file(input_file)
        if not isinstance(rule_data, dict):
            click.echo("Error: --input-file must be a YAML/JSON object with 'detect' and 'respond' keys.", err=True)
            ctx.exit(4)
            return
        detection = rule_data.get("detect")
        response = rule_data.get("respond")
        if name is None:
            name = rule_data.get("name")
        if namespace is None:
            namespace = rule_data.get("namespace")
    else:
        if detect_file:
            detection = _load_file(detect_file)
        if respond_file:
            response = _load_file(respond_file)

    if name is None:
        click.echo("Error: --name is required (or include 'name' in --input-file).", err=True)
        ctx.exit(4)
        return
    if detection is None or response is None:
        click.echo(
            "Error: Both detection and response components are required.\n"
            "Suggestion: Use --detect-file and --respond-file, or --input-file with 'detect' and 'respond' keys.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.add_rule(
        name,
        detection,
        response,
        is_replace=replace,
        namespace=namespace,
    )
    if not ctx.obj.quiet:
        click.echo(f"Rule '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", default=None, help="Rule name (required unless using --input-file with 'name' key).")
@click.option("--detect-file", default=None, type=click.Path(exists=True), help="Path to detection component (JSON or YAML file).")
@click.option("--respond-file", default=None, type=click.Path(exists=True), help="Path to response component (JSON or YAML file).")
@click.option("--input-file", default=None, type=click.Path(exists=True), help="Path to combined rule file (JSON or YAML with 'detect' and 'respond' keys).")
@click.option(
    "--namespace", default=None,
    type=click.Choice(["general", "managed", "service"], case_sensitive=False),
    help="Rule namespace (default: general).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_UPDATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def update(ctx, name, detect_file, respond_file, input_file, namespace):
    """Update an existing D&R rule (replaces detection and response).

    Examples:
        limacharlie rule update --name my-rule \\
            --detect-file detect.yaml --respond-file respond.yaml

        limacharlie rule update --input-file rule.yaml
    """
    detection = None
    response = None

    if input_file:
        rule_data = _load_file(input_file)
        if not isinstance(rule_data, dict):
            click.echo("Error: --input-file must be a YAML/JSON object with 'detect' and 'respond' keys.", err=True)
            ctx.exit(4)
            return
        detection = rule_data.get("detect")
        response = rule_data.get("respond")
        if name is None:
            name = rule_data.get("name")
        if namespace is None:
            namespace = rule_data.get("namespace")
    else:
        if detect_file:
            detection = _load_file(detect_file)
        if respond_file:
            response = _load_file(respond_file)

    if name is None:
        click.echo("Error: --name is required (or include 'name' in --input-file).", err=True)
        ctx.exit(4)
        return
    if detection is None or response is None:
        click.echo(
            "Error: Both detection and response components are required.\n"
            "Suggestion: Use --detect-file and --respond-file, or --input-file with 'detect' and 'respond' keys.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.add_rule(
        name,
        detection,
        response,
        is_replace=True,
        namespace=namespace,
    )
    if not ctx.obj.quiet:
        click.echo(f"Rule '{name}' updated.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name to delete.")
@click.option(
    "--namespace", default=None,
    type=click.Choice(["general", "managed", "service"], case_sensitive=False),
    help="Rule namespace (default: general).",
)
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, name, namespace, confirm):
    """Delete a D&R rule.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie rule delete --name my-rule --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the rule.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.delete_rule(name, namespace=namespace)
    if not ctx.obj.quiet:
        click.echo(f"Rule '{name}' deleted.")
    _output(ctx, data)
