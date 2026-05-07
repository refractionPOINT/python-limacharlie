"""User commands for LimaCharlie CLI v2.

Commands for listing, inviting, and removing organization users.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.users import Users
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

@click.group("user")
def group() -> None:
    """Manage organization users.

    Invite, list, and remove users who have access to the organization.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_PERM_LIST = """\
List all user permissions in the organization.  Returns a mapping of
user emails to their granted permissions.

Example:
  limacharlie user permissions list
"""
register_explain("user.permissions.list", _EXPLAIN_PERM_LIST)


@group.command("list")
@pass_context
def list_users(ctx) -> None:
    org = _get_org(ctx)
    users = Users(org)
    data = users.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# invite
# ---------------------------------------------------------------------------

_EXPLAIN_INVITE = """\
Invite a user to the organization by email address.  The user will
receive an invitation and, once accepted, will have access to the
organization with the default permission set.

Use 'limacharlie user permissions' commands to manage fine-grained
permissions after the user has been added.

Example:
  limacharlie user invite --email user@example.com
"""
register_explain("user.invite", _EXPLAIN_INVITE)


@group.command()
@click.option("--email", required=True, help="Email address of the user to invite.")
@pass_context
def invite(ctx, email) -> None:
    org = _get_org(ctx)
    users = Users(org)
    data = users.invite(email)
    if not ctx.obj.quiet:
        click.echo(f"User '{email}' invited.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

_EXPLAIN_PERM_REMOVE = """\
Revoke a specific permission from a user.  The permission is removed
immediately.  If the user does not have the specified permission, the
operation succeeds silently.

Example:
  limacharlie user permissions remove --email user@example.com --permission dr.set
"""
register_explain("user.permissions.remove", _EXPLAIN_PERM_REMOVE)


@group.command()
@click.option("--email", required=True, help="Email address of the user to remove.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm removal (required).")
@pass_context
def remove(ctx, email, confirm) -> None:
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
@pass_context
def perm_list(ctx) -> None:
    org = _get_org(ctx)
    users = Users(org)
    data = users.list_permissions()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# permissions add
# ---------------------------------------------------------------------------

_EXPLAIN_PERM_ADD = """\
Grant a specific permission to a user.  Permissions use the
category.action convention.  Common permission strings:

  org.get, org.conf.get, org.conf.set, org.del
  sensor.list, sensor.get, sensor.task, sensor.del, sensor.tag
  dr.list, dr.set, dr.del
  dr.list.managed, dr.set.managed, dr.del.managed
  fp.list, fp.set, fp.del
  output.list, output.set, output.del
  ikey.list, ikey.set, ikey.del
  apikey.ctrl, user.ctrl, billing.ctrl
  audit.get, hive.get, hive.set, hive.del

Example:
  limacharlie user permissions add --email user@example.com --permission dr.set
"""
register_explain("user.permissions.add", _EXPLAIN_PERM_ADD)


@permissions.command()
@click.option("--email", required=True, help="Email address of the user.")
@click.option("--permission", required=True, help="Permission string to grant (e.g. 'dr.set').")
@pass_context
def add(ctx, email, permission) -> None:
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
@pass_context
def perm_remove(ctx, email, permission) -> None:
    org = _get_org(ctx)
    users = Users(org)
    data = users.remove_permission(email, permission)
    if not ctx.obj.quiet:
        click.echo(f"Permission '{permission}' revoked from '{email}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# permissions set-role
# ---------------------------------------------------------------------------

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
register_explain("user.permissions.set-role", _EXPLAIN_PERM_SET_ROLE)


@permissions.command("set-role")
@click.option("--email", required=True, help="Email address of the user.")
@click.option(
    "--role", required=True,
    type=click.Choice(["Owner", "Administrator", "Operator", "Viewer", "Basic"], case_sensitive=False),
    help="Predefined role to assign (replaces all current permissions).",
)
@pass_context
def set_role(ctx, email, role) -> None:
    org = _get_org(ctx)
    users = Users(org)
    data = users.set_role(email, role)
    if not ctx.obj.quiet:
        click.echo(f"Role '{role}' set for '{email}'.")
    _output(ctx, data)
