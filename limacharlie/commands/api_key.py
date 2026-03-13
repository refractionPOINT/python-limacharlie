"""API key management commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting organization API keys.
API keys provide programmatic access to the LimaCharlie REST API
with configurable permission scopes.
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

@click.group("api-key")
def group() -> None:
    """Manage API keys.

    API keys provide programmatic access to the LimaCharlie REST
    API with configurable permission scopes.  Each key has a name
    and a set of permissions that control what operations it can
    perform.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all API keys in the organization.  Each key entry shows the
key name, hash, creation date, and associated permissions.

The actual secret key value is only returned at creation time and
cannot be retrieved later.  Use --output json to get the full
key metadata for auditing purposes.
"""
register_explain("api-key.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_keys(ctx) -> None:
    org = _get_org(ctx)
    data = org.get_api_keys()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new API key with the specified name and permissions.

Permissions are provided as a comma-separated list using the
category.action convention.  Common permissions:

  Organization:  org.get, org.conf.get, org.conf.set
  Sensors:       sensor.list, sensor.get, sensor.task, sensor.del, sensor.tag
  Install keys:  ikey.list, ikey.set, ikey.del
  D&R rules:     dr.list, dr.set, dr.del
  Managed D&R:   dr.list.managed, dr.set.managed, dr.del.managed
  FP rules:      fp.list, fp.set, fp.del
  Outputs:       output.list, output.set, output.del
  Access ctrl:   apikey.ctrl, user.ctrl, billing.ctrl
  Audit:         audit.get
  Hive:          hive.get, hive.set, hive.del

IMPORTANT: The secret key value is only shown once at creation
time.  Store it securely -- it cannot be retrieved later.

Examples:
  limacharlie api-key create --name ci-key --permissions dr.list,dr.set
  limacharlie api-key create --name readonly --permissions sensor.list,org.get
"""
register_explain("api-key.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--name", required=True, help="API key name.")
@click.option(
    "--permissions", required=True,
    help="Comma-separated list of permissions (e.g., 'dr.list,dr.set').",
)
@pass_context
def create(ctx, name, permissions) -> None:
    perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
    if not perm_list:
        click.echo("Error: At least one permission is required.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.add_api_key(name, perm_list)
    if not ctx.obj.quiet:
        click.echo(f"API key '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete an API key by its key hash.  This immediately revokes all
access for the key.  The --confirm flag is required to prevent
accidental deletion.

Use 'limacharlie api-key list' to find the key hash for the key
you want to delete.
"""
register_explain("api-key.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--key-hash", required=True, help="Key hash of the API key to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, key_hash, confirm) -> None:
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the API key.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.remove_api_key(key_hash)
    if not ctx.obj.quiet:
        click.echo(f"API key '{key_hash}' deleted.")
    _output(ctx, data)
