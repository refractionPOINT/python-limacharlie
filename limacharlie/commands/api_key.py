"""API key management commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting organization API keys.
API keys provide programmatic access to the LimaCharlie REST API
with configurable permission scopes.
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
List all API keys in the organization.  Each key entry shows the
key name, hash, creation date, and associated permissions.

The actual secret key value is only returned at creation time and
cannot be retrieved later.  Use --output json to get the full
key metadata for auditing purposes.
"""

_EXPLAIN_CREATE = """\
Create a new API key with the specified name and permissions.

Permissions are provided as a comma-separated list of permission
strings (e.g., 'dr.list,dr.set,sensor.list').  The full list of
available permissions can be found in the LimaCharlie documentation.

IMPORTANT: The secret key value is only shown once at creation
time.  Store it securely -- it cannot be retrieved later.

Examples:
  limacharlie api-key create --name ci-key --permissions dr.list,dr.set
  limacharlie api-key create --name readonly --permissions sensor.list
"""

_EXPLAIN_DELETE = """\
Delete an API key by its key hash.  This immediately revokes all
access for the key.  The --confirm flag is required to prevent
accidental deletion.

Use 'limacharlie api-key list' to find the key hash for the key
you want to delete.
"""

register_explain("api-key.list", _EXPLAIN_LIST)
register_explain("api-key.create", _EXPLAIN_CREATE)
register_explain("api-key.delete", _EXPLAIN_DELETE)


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

@click.group("api-key")
def group():
    """Manage API keys.

    API keys provide programmatic access to the LimaCharlie REST
    API with configurable permission scopes.  Each key has a name
    and a set of permissions that control what operations it can
    perform.
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
    """List all API keys.

    Example:
        limacharlie api-key list
    """
    org = _get_org(ctx)
    data = org.get_api_keys()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="API key name.")
@click.option(
    "--permissions", required=True,
    help="Comma-separated list of permissions (e.g., 'dr.list,dr.set').",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name, permissions):
    """Create a new API key.

    The secret key value is only shown once at creation time.

    Examples:
        limacharlie api-key create --name ci-key --permissions dr.list,dr.set
        limacharlie api-key create --name readonly --permissions sensor.list
    """
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

@group.command()
@click.option("--key-hash", required=True, help="Key hash of the API key to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, key_hash, confirm):
    """Delete an API key.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie api-key delete --key-hash <hash> --confirm
    """
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
