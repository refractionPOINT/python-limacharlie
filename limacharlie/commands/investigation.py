"""Investigation commands for LimaCharlie CLI v2.

Commands for listing, creating, viewing, and deleting investigations.
Investigations group related events and detections for incident
response and threat hunting workflows.
"""

import json

import click
import yaml

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.investigations import Investigations as InvestigationsSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all investigations in the organization.  Investigations group
related events and detections for incident response workflows.

Use --output json to get the full investigation data for export.
"""

_EXPLAIN_GET = """\
Get the full details of a specific investigation by its ID.
Returns the investigation metadata, associated events, detections,
and any notes or status information.

Example:
  limacharlie investigation get --id <investigation-id>
"""

_EXPLAIN_CREATE = """\
Create a new investigation from a JSON or YAML input file.  The
input file should contain the investigation definition including
any initial parameters.

Example:
  limacharlie investigation create --input-file investigation.yaml
"""

_EXPLAIN_DELETE = """\
Delete an investigation by its ID.  This permanently removes the
investigation and all associated data.  The --confirm flag is
required to prevent accidental deletion.
"""

_EXPLAIN_UPDATE = """\
Update an existing investigation.  Provide the investigation ID and
updated data via --input-file (JSON/YAML) or stdin.

Example:
  limacharlie investigation update --id <investigation-id> \\
      --input-file update.yaml
"""

_EXPLAIN_EXPAND = """\
Expand an investigation timeline.  Optionally specify a sensor ID
and/or events to add to the investigation.

Examples:
  limacharlie investigation expand --id <investigation-id> --sid <SID>
  limacharlie investigation expand --id <investigation-id> \\
      --events '[{"event_type": "NEW_PROCESS", "atom": "..."}]'
"""

register_explain("investigation.list", _EXPLAIN_LIST)
register_explain("investigation.get", _EXPLAIN_GET)
register_explain("investigation.create", _EXPLAIN_CREATE)
register_explain("investigation.delete", _EXPLAIN_DELETE)
register_explain("investigation.update", _EXPLAIN_UPDATE)
register_explain("investigation.expand", _EXPLAIN_EXPAND)


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

@click.group("investigation")
def group():
    """Manage investigations.

    Investigations group related events and detections for incident
    response and threat hunting workflows.
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
def list_investigations(ctx):
    """List all investigations.

    Example:
        limacharlie investigation list
    """
    org = _get_org(ctx)
    sdk = InvestigationsSDK(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "investigation_id", required=True, help="Investigation ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, investigation_id):
    """Get investigation details.

    Example:
        limacharlie investigation get --id <investigation-id>
    """
    org = _get_org(ctx)
    sdk = InvestigationsSDK(org)
    data = sdk.get(investigation_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option(
    "--input-file", required=True, type=click.Path(exists=True),
    help="Path to investigation definition file (JSON or YAML).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, input_file):
    """Create a new investigation from a file.

    Example:
        limacharlie investigation create --input-file investigation.yaml
    """
    data_in = _load_file(input_file)

    org = _get_org(ctx)
    sdk = InvestigationsSDK(org)
    data = sdk.create(data_in)
    if not ctx.obj.quiet:
        click.echo("Investigation created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "investigation_id", required=True, help="Investigation ID to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, investigation_id, confirm):
    """Delete an investigation.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie investigation delete --id <investigation-id> --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the investigation.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = InvestigationsSDK(org)
    data = sdk.delete(investigation_id)
    if not ctx.obj.quiet:
        click.echo(f"Investigation '{investigation_id}' deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "investigation_id", required=True, help="Investigation ID to update.")
@click.option(
    "--input-file", default=None, type=click.Path(exists=True),
    help="Path to update data file (JSON or YAML). Reads stdin if omitted.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_UPDATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def update(ctx, investigation_id, input_file):
    """Update an existing investigation.

    Example:
        limacharlie investigation update --id <investigation-id> \\
            --input-file update.yaml
    """
    import sys

    if input_file:
        data_in = _load_file(input_file)
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
        try:
            data_in = yaml.safe_load(content)
        except Exception:
            data_in = json.loads(content)
    else:
        raise click.UsageError("Provide data via --input-file or pipe to stdin.")

    org = _get_org(ctx)
    sdk = InvestigationsSDK(org)
    data = sdk.update(investigation_id, data_in)
    if not ctx.obj.quiet:
        click.echo(f"Investigation '{investigation_id}' updated.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# expand
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "investigation_id", required=True, help="Investigation ID to expand.")
@click.option("--sid", default=None, help="Sensor ID to add to the investigation.")
@click.option("--events", default=None, help="JSON string of events to add.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_EXPAND),
    help="Show detailed explanation of this command.",
)
@pass_context
def expand(ctx, investigation_id, sid, events):
    """Expand an investigation timeline.

    Examples:
        limacharlie investigation expand --id <investigation-id> --sid <SID>
        limacharlie investigation expand --id <investigation-id> \\
            --events '[{"event_type": "NEW_PROCESS", "atom": "..."}]'
    """
    parsed_events = None
    if events is not None:
        parsed_events = json.loads(events)
    org = _get_org(ctx)
    sdk = InvestigationsSDK(org)
    data = sdk.expand(investigation_id, sid=sid, events=parsed_events)
    _output(ctx, data)
