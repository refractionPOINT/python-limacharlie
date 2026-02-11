"""Group management commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting organization groups.
Groups provide multi-tenancy and permission management across
multiple LimaCharlie organizations.
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
List all groups accessible to the current user.  Groups provide
multi-tenancy by grouping multiple LimaCharlie organizations under
a single management umbrella with shared permissions.

Use --output json to get the full group definitions for export.
"""

_EXPLAIN_GET = """\
Get the details of a specific group by its ID.  Returns the group
name, members, owners, associated organizations, and permissions.

Use 'limacharlie group list' to find available group IDs.
"""

_EXPLAIN_CREATE = """\
Create a new group.  Groups allow you to manage multiple
organizations under a single umbrella with shared user permissions.

After creating a group, use the LimaCharlie web UI or API to add
members, owners, and organizations to the group.
"""

_EXPLAIN_DELETE = """\
Delete a group by its ID.  This permanently removes the group and
all associated membership and permission data.  The --confirm flag
is required to prevent accidental deletion.

This does NOT delete the organizations within the group.
"""

register_explain("group.list", _EXPLAIN_LIST)
register_explain("group.get", _EXPLAIN_GET)
register_explain("group.create", _EXPLAIN_CREATE)
register_explain("group.delete", _EXPLAIN_DELETE)


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

@click.group("group")
def group():
    """Manage organization groups.

    Groups provide multi-tenancy by grouping multiple LimaCharlie
    organizations under a single management umbrella with shared
    permissions and user management.
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
def list_groups(ctx):
    """List all groups.

    Example:
        limacharlie group list
    """
    org = _get_org(ctx)
    data = org.get_groups()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "group_id", required=True, help="Group ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, group_id):
    """Get details of a specific group.

    Example:
        limacharlie group get --id <group-id>
    """
    org = _get_org(ctx)
    data = org.get_group(group_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Group name.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name):
    """Create a new group.

    Example:
        limacharlie group create --name my-group
    """
    org = _get_org(ctx)
    data = org.create_group(name)
    if not ctx.obj.quiet:
        click.echo(f"Group '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "group_id", required=True, help="Group ID to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, group_id, confirm):
    """Delete a group.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie group delete --id <group-id> --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the group.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.delete_group(group_id)
    if not ctx.obj.quiet:
        click.echo(f"Group '{group_id}' deleted.")
    _output(ctx, data)
