"""User commands for LimaCharlie CLI v2.

Commands for listing, inviting, and removing organization users.
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
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

_EXPLAIN_PERM_LIST = """\
List all user permissions in the organization.  Returns a mapping of
user emails to their granted permissions.

Example:
  limacharlie user permissions list
"""

_EXPLAIN_PERM_ADD = """\
Grant a specific permission to a user.  Permissions are fine-grained
access controls such as 'dr.set', 'sensor.task', 'org.conf.set', etc.

Use 'limacharlie help permissions' for the full list of available
permission strings.

Example:
  limacharlie user permissions add --email user@example.com --permission dr.set
"""

_EXPLAIN_PERM_REMOVE = """\
Revoke a specific permission from a user.  The permission is removed
immediately.  If the user does not have the specified permission, the
operation succeeds silently.

Example:
  limacharlie user permissions remove --email user@example.com --permission dr.set
"""

_EXPLAIN_PERM_SET_ROLE = """\
Set a predefined role for a user, replacing all their current permissions
with the permissions defined by the role.  This is a convenience
operation that sets multiple permissions at once.

Valid roles (most to least privileged):
  - Owner: Full access to all features
  - Administrator: Owner minus apikey.ctrl and billing.ctrl
  - Operator: Operational access, no user/billing/apikey control
  - Viewer: Read-only access
  - Basic: Minimal access (org.get, sensor.list)

Example:
  limacharlie user permissions set-role --email user@example.com --role Operator
"""

register_explain("user.list", _EXPLAIN_LIST)
register_explain("user.invite", _EXPLAIN_INVITE)
register_explain("user.remove", _EXPLAIN_REMOVE)
register_explain("user.permissions.list", _EXPLAIN_PERM_LIST)
register_explain("user.permissions.add", _EXPLAIN_PERM_ADD)
register_explain("user.permissions.remove", _EXPLAIN_PERM_REMOVE)
register_explain("user.permissions.set-role", _EXPLAIN_PERM_SET_ROLE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


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

@click.group("user")
def group() -> None:
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
def list_users(ctx) -> None:
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
def invite(ctx, email) -> None:
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
def remove(ctx, email, confirm) -> None:
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


# ---------------------------------------------------------------------------
# permissions subgroup
# ---------------------------------------------------------------------------

@group.group("permissions")
def permissions() -> None:
    """Manage user permissions.

    Grant, revoke, and list fine-grained permissions for organization
    users.  Use 'set-role' to assign a predefined role that sets
    multiple permissions at once.
    """


# ---------------------------------------------------------------------------
# permissions list
# ---------------------------------------------------------------------------

@permissions.command("list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PERM_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def perm_list(ctx) -> None:
    """List user permissions.

    Example:
        limacharlie user permissions list
    """
    org = _get_org(ctx)
    users = Users(org)
    data = users.list_permissions()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# permissions add
# ---------------------------------------------------------------------------

@permissions.command()
@click.option("--email", required=True, help="Email address of the user.")
@click.option("--permission", required=True, help="Permission string to grant (e.g. 'dr.set').")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PERM_ADD),
    help="Show detailed explanation of this command.",
)
@pass_context
def add(ctx, email, permission) -> None:
    """Grant a permission to a user.

    Example:
        limacharlie user permissions add --email user@example.com --permission dr.set
    """
    org = _get_org(ctx)
    users = Users(org)
    data = users.add_permission(email, permission)
    if not ctx.obj.quiet:
        click.echo(f"Permission '{permission}' granted to '{email}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# permissions remove
# ---------------------------------------------------------------------------

@permissions.command("remove")
@click.option("--email", required=True, help="Email address of the user.")
@click.option("--permission", required=True, help="Permission string to revoke (e.g. 'dr.set').")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PERM_REMOVE),
    help="Show detailed explanation of this command.",
)
@pass_context
def perm_remove(ctx, email, permission) -> None:
    """Revoke a permission from a user.

    Example:
        limacharlie user permissions remove --email user@example.com --permission dr.set
    """
    org = _get_org(ctx)
    users = Users(org)
    data = users.remove_permission(email, permission)
    if not ctx.obj.quiet:
        click.echo(f"Permission '{permission}' revoked from '{email}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# permissions set-role
# ---------------------------------------------------------------------------

@permissions.command("set-role")
@click.option("--email", required=True, help="Email address of the user.")
@click.option(
    "--role", required=True,
    type=click.Choice(["Owner", "Administrator", "Operator", "Viewer", "Basic"], case_sensitive=False),
    help="Predefined role to assign (replaces all current permissions).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_PERM_SET_ROLE),
    help="Show detailed explanation of this command.",
)
@pass_context
def set_role(ctx, email, role) -> None:
    """Set a predefined role for a user.

    Replaces all existing permissions with those defined by the role.

    Example:
        limacharlie user permissions set-role --email user@example.com --role Operator
    """
    org = _get_org(ctx)
    users = Users(org)
    data = users.set_role(email, role)
    if not ctx.obj.quiet:
        click.echo(f"Role '{role}' set for '{email}'.")
    _output(ctx, data)
