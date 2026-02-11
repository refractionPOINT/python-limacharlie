"""Payload commands for LimaCharlie CLI v2.

Commands for listing and deleting payloads.  Payloads are binary
artifacts (executables, scripts, etc.) that can be deployed to
sensors via D&R response actions.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.payloads import Payloads
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all payloads stored in the organization.  Payloads are binary
artifacts (executables, scripts, configuration files) that can be
deployed to sensors via D&R response actions or tasking commands.

The output includes payload names and metadata.
"""

_EXPLAIN_DELETE = """\
Delete a payload by name.  This permanently removes the payload from
the organization.  Any D&R rules referencing this payload will fail
when triggered.  The --confirm flag is required to prevent accidental
deletion.
"""

register_explain("payload.list", _EXPLAIN_LIST)
register_explain("payload.delete", _EXPLAIN_DELETE)


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

@click.group("payload")
def group():
    """Manage payloads.

    Payloads are binary artifacts that can be deployed to sensors
    via D&R response actions or tasking commands.
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
def list_payloads(ctx):
    """List payloads.

    Example:
        limacharlie payload list
    """
    org = _get_org(ctx)
    payloads = Payloads(org)
    data = payloads.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Payload name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, name, confirm):
    """Delete a payload.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie payload delete --name my-payload --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the payload.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    payloads = Payloads(org)
    data = payloads.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Payload '{name}' deleted.")
    _output(ctx, data)
