"""False Positive rule commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting false positive rules.  FP
rules suppress specific detections that have been determined to be benign,
preventing them from generating alerts or triggering response actions.
"""

import json

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
List all false positive rules in the organization.  FP rules are
evaluated after D&R rules and suppress detections that match their
criteria.  Each FP rule has a name and a rule definition that specifies
which detections to suppress.

Use --output json to get the full rule definitions for export or backup.
"""

_EXPLAIN_GET = """\
Get the full definition of a single false positive rule by name.
Returns the FP rule definition including the match criteria used to
suppress detections.

FP rule names are unique within an organization.  Use
'limacharlie fp list' to see available rule names.
"""

_EXPLAIN_CREATE = """\
Create a new false positive rule.  The rule definition specifies which
detections to suppress.  Provide the definition as a JSON or YAML file
via --input-file.

The input file should contain the FP rule definition.  At minimum it
should specify the detection name or pattern to suppress and any
additional matching criteria (event fields, sensor tags, etc.).

Example input file (YAML):
  op: is
  name: my-detection-rule
  value:
    event/FILE_PATH: C:\\\\Windows\\\\System32\\\\svchost.exe

If a rule with the same name already exists, the create will fail.  To
update an existing FP rule, delete it first and re-create.

Related: 'limacharlie help detections' for more on how false positives
interact with D&R rules.
"""

_EXPLAIN_DELETE = """\
Delete a false positive rule by name.  This permanently removes the
rule and allows previously-suppressed detections to generate alerts
again.  The --confirm flag is required to prevent accidental deletion.
"""

register_explain("fp.list", _EXPLAIN_LIST)
register_explain("fp.get", _EXPLAIN_GET)
register_explain("fp.create", _EXPLAIN_CREATE)
register_explain("fp.delete", _EXPLAIN_DELETE)


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

@click.group("fp")
def group():
    """Manage false positive rules.

    False positive rules suppress specific detections that have been
    verified as benign.  They are evaluated after D&R rules and prevent
    matching detections from generating alerts.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_fps(ctx):
    """List all false positive rules.

    Example:
        limacharlie fp list
    """
    org = _get_org(ctx)
    data = org.get_fps()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="FP rule name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, name):
    """Get the full definition of a false positive rule.

    Example:
        limacharlie fp get --name my-fp-rule
    """
    org = _get_org(ctx)
    fps = org.get_fps()
    if isinstance(fps, dict):
        fp = fps.get(name)
    else:
        fp = None

    if fp is None:
        click.echo(
            f"Error: FP rule '{name}' not found.\n"
            "Suggestion: Use 'limacharlie fp list' to see available FP rules.",
            err=True,
        )
        ctx.exit(3)
        return

    _output(ctx, fp)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="FP rule name.")
@click.option(
    "--input-file", required=True, type=click.Path(exists=True),
    help="Path to FP rule definition file (JSON or YAML).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name, input_file):
    """Create a new false positive rule from a file.

    Examples:
        limacharlie fp create --name my-fp --input-file fp_rule.yaml
    """
    rule = _load_file(input_file)

    org = _get_org(ctx)
    data = org.add_fp(name, rule)
    if not ctx.obj.quiet:
        click.echo(f"FP rule '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="FP rule name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, name, confirm):
    """Delete a false positive rule.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie fp delete --name my-fp --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the FP rule.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.delete_fp(name)
    if not ctx.obj.quiet:
        click.echo(f"FP rule '{name}' deleted.")
    _output(ctx, data)
