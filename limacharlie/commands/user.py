"""User commands for LimaCharlie CLI v2.

Commands for listing, inviting, and removing organization users.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.users import Users
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all users who have access to the organization.  The output
includes email addresses and associated metadata.

Example:
  limacharlie user list
"""

_EXPLAIN_INVITE = """\
Invite a user to the organization by email address.  The user will
receive an invitation and, once accepted, will have access to the
organization with the default permission set.

Use 'limacharlie user permissions' commands to manage fine-grained
permissions after the user has been added.

Example:
  limacharlie user invite --email user@example.com
"""

_EXPLAIN_REMOVE = """\
Remove a user from the organization by email address.  The user will
immediately lose access.  The --confirm flag is required to prevent
accidental removal.

Example:
  limacharlie user remove --email user@example.com --confirm
"""

register_explain("user.list", _EXPLAIN_LIST)
register_explain("user.invite", _EXPLAIN_INVITE)
register_explain("user.remove", _EXPLAIN_REMOVE)


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

@click.group("user")
def group():
    """Manage organization users.

    Invite, list, and remove users who have access to the organization.
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
def list_users(ctx):
    """List organization users.

    Example:
        limacharlie user list
    """
    org = _get_org(ctx)
    users = Users(org)
    data = users.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# invite
# ---------------------------------------------------------------------------

@group.command()
@click.option("--email", required=True, help="Email address of the user to invite.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_INVITE),
    help="Show detailed explanation of this command.",
)
@pass_context
def invite(ctx, email):
    """Invite a user to the organization.

    Example:
        limacharlie user invite --email user@example.com
    """
    org = _get_org(ctx)
    users = Users(org)
    data = users.invite(email)
    if not ctx.obj.quiet:
        click.echo(f"User '{email}' invited.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

@group.command()
@click.option("--email", required=True, help="Email address of the user to remove.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm removal (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_REMOVE),
    help="Show detailed explanation of this command.",
)
@pass_context
def remove(ctx, email, confirm):
    """Remove a user from the organization.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie user remove --email user@example.com --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to remove the user.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    users = Users(org)
    data = users.remove(email)
    if not ctx.obj.quiet:
        click.echo(f"User '{email}' removed.")
    _output(ctx, data)
