"""Schema commands for LimaCharlie CLI v2.

Commands for listing and viewing event schemas (ontology).  Schemas
define the structure and fields of events produced by sensors and
the LimaCharlie platform.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
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

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("schema")
def group() -> None:
    """View event schemas (ontology).

    Schemas define the structure and fields of events produced by
    sensors.  Use these commands to explore available event types
    and their field definitions.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@pass_context
def list_schemas(ctx) -> None:
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
@pass_context
def get(ctx, name) -> None:
    """Get the schema for a specific event type.

    Example:
        limacharlie schema get --name NEW_PROCESS
    """
    org = _get_org(ctx)
    data = org.get_schema(name)
    _output(ctx, data)
