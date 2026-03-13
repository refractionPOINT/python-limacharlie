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
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
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

_EXPLAIN_LIST = """\
List all available event schemas in the organization.  Schemas
define the structure (fields, types, descriptions) of each event
type produced by sensors.

Common event types include:
  NEW_PROCESS, TERMINATE_PROCESS, NEW_TCP4_CONNECTION,
  DNS_REQUEST, FILE_CREATE, MODULE_LOAD, REG_KEY_SET,
  CONNECTED, NEW_DOCUMENT, SENSITIVE_PROCESS_ACCESS

This is useful for understanding what fields are available when
writing D&R rules or LCQL queries.  For example, the NEW_PROCESS
schema shows that event/FILE_PATH, event/COMMAND_LINE, and
event/PARENT are available for detection logic.
"""
register_explain("schema.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_schemas(ctx) -> None:
    org = _get_org(ctx)
    data = org.get_schemas()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Get the full schema definition for a specific event type.  Returns
the field names, data types, descriptions, and any enumeration values.

The schema is used by D&R rules to reference event fields via dot
paths (e.g., event/FILE_PATH, event/COMMAND_LINE).

Examples:
  limacharlie schema get --name NEW_PROCESS
  limacharlie schema get --name DNS_REQUEST
  limacharlie schema get --name NEW_TCP4_CONNECTION
"""
register_explain("schema.get", _EXPLAIN_GET)


@group.command()
@click.option("--name", required=True, help="Event type / schema name (e.g., NEW_PROCESS).")
@pass_context
def get(ctx, name) -> None:
    org = _get_org(ctx)
    data = org.get_schema(name)
    _output(ctx, data)
