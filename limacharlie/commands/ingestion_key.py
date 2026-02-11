"""Ingestion key commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting ingestion keys.
Ingestion keys authenticate external log/telemetry sources pushing
data into LimaCharlie via the USP (Universal Sensor Protocol) or
direct API ingestion.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.ingestion_keys import IngestionKeys
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all ingestion keys for the organization.  Ingestion keys are
used to authenticate external data sources pushing telemetry into
LimaCharlie via USP or the ingestion API.

The output includes key names and associated configuration.
"""

_EXPLAIN_CREATE = """\
Create a new ingestion key.  The --name is required and should
identify the data source (e.g., 'aws-cloudtrail', 'zeek-logs').

Example:
  limacharlie ingestion-key create --name aws-cloudtrail
"""

_EXPLAIN_DELETE = """\
Delete an ingestion key by name.  External sources using this key
will immediately lose the ability to push data.  The --confirm flag
is required to prevent accidental deletion.

Example:
  limacharlie ingestion-key delete --name aws-cloudtrail --confirm
"""

register_explain("ingestion-key.list", _EXPLAIN_LIST)
register_explain("ingestion-key.create", _EXPLAIN_CREATE)
register_explain("ingestion-key.delete", _EXPLAIN_DELETE)


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


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("ingestion-key")
def group():
    """Manage ingestion keys.

    Ingestion keys authenticate external data sources pushing
    telemetry into LimaCharlie via USP or the ingestion API.
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
def list_keys(ctx):
    """List ingestion keys.

    Example:
        limacharlie ingestion-key list
    """
    org = _get_org(ctx)
    keys = IngestionKeys(org)
    data = keys.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Ingestion key name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name):
    """Create a new ingestion key.

    Example:
        limacharlie ingestion-key create --name aws-cloudtrail
    """
    org = _get_org(ctx)
    keys = IngestionKeys(org)
    data = keys.create(name)
    if not ctx.obj.quiet:
        click.echo(f"Ingestion key '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Ingestion key name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, name, confirm):
    """Delete an ingestion key.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie ingestion-key delete --name aws-cloudtrail --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the ingestion key.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    keys = IngestionKeys(org)
    data = keys.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Ingestion key '{name}' deleted.")
    _output(ctx, data)
