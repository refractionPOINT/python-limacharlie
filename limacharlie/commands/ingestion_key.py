"""Ingestion key commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting ingestion keys.
Ingestion keys authenticate external log/telemetry sources pushing
data into LimaCharlie via the USP (Universal Sensor Protocol) or
direct API ingestion.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.ingestion_keys import IngestionKeys
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

@click.group("ingestion-key")
def group() -> None:
    """Manage ingestion keys.

    Ingestion keys authenticate external data sources pushing
    telemetry into LimaCharlie via USP or the ingestion API.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all ingestion keys for the organization.  Ingestion keys are
used to authenticate external data sources pushing telemetry into
LimaCharlie via USP (Universal Sensor Protocol) or the ingestion API.

Unlike installation keys (for endpoint sensors), ingestion keys are
used for third-party log sources such as AWS CloudTrail, syslog
forwarders, or custom integrations via the adapter binary.

The output includes key names and associated configuration.
"""
register_explain("ingestion-key.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_keys(ctx) -> None:
    org = _get_org(ctx)
    keys = IngestionKeys(org)
    data = keys.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new ingestion key.  The --name is required and should
identify the data source (e.g., 'aws-cloudtrail', 'zeek-logs').

Example:
  limacharlie ingestion-key create --name aws-cloudtrail
"""
register_explain("ingestion-key.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--name", required=True, help="Ingestion key name.")
@pass_context
def create(ctx, name) -> None:
    org = _get_org(ctx)
    keys = IngestionKeys(org)
    data = keys.create(name)
    if not ctx.obj.quiet:
        click.echo(f"Ingestion key '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete an ingestion key by name.  External sources using this key
will immediately lose the ability to push data.  The --confirm flag
is required to prevent accidental deletion.

Example:
  limacharlie ingestion-key delete --name aws-cloudtrail --confirm
"""
register_explain("ingestion-key.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--name", required=True, help="Ingestion key name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, name, confirm) -> None:
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
