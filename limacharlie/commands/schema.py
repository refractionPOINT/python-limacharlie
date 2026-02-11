"""Schema commands for LimaCharlie CLI v2.

Commands for listing and viewing event schemas (ontology).  Schemas
define the structure and fields of events produced by sensors and
the LimaCharlie platform.
"""

import click

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
List all available event schemas in the organization.  Schemas
define the structure (fields, types, descriptions) of each event
type produced by sensors.

This is useful for understanding what fields are available when
writing D&R rules or LCQL queries.
"""

_EXPLAIN_GET = """\
Get the full schema definition for a specific event type.  Returns
the field names, types, descriptions, and any enumeration values.

Example:
  limacharlie schema get --name NEW_PROCESS
  limacharlie schema get --name DNS_REQUEST
"""

register_explain("schema.list", _EXPLAIN_LIST)
register_explain("schema.get", _EXPLAIN_GET)


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

@click.group("schema")
def group():
    """View event schemas (ontology).

    Schemas define the structure and fields of events produced by
    sensors.  Use these commands to explore available event types
    and their field definitions.
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
def list_schemas(ctx):
    """List available event schemas.

    Example:
        limacharlie schema list
    """
    org = _get_org(ctx)
    data = org.get_schemas()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Event type / schema name (e.g., NEW_PROCESS).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, name):
    """Get the schema for a specific event type.

    Example:
        limacharlie schema get --name NEW_PROCESS
    """
    org = _get_org(ctx)
    data = org.get_schema(name)
    _output(ctx, data)
