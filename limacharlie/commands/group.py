"""Group management commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting organization groups.
Groups provide multi-tenancy and permission management across
multiple LimaCharlie organizations.
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

@click.group("group")
def group() -> None:
    """Manage organization groups.

    Groups provide multi-tenancy by grouping multiple LimaCharlie
    organizations under a single management umbrella with shared
    permissions and user management.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all groups accessible to the current user.  Groups provide
multi-tenancy by grouping multiple LimaCharlie organizations under
a single management umbrella with shared permissions.

A group has:
  - Members: users who inherit the group's permissions on all
    associated organizations
  - Owners: users who can manage the group itself
  - Organizations: the set of orgs the group's permissions apply to
  - Permissions: the permission set inherited by members

Use --output json to get the full group definitions for export.
"""
register_explain("group.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_groups(ctx) -> None:
    org = _get_org(ctx)
    data = org.get_groups()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Get the details of a specific group by its ID.  Returns the group
name, members, owners, associated organizations, and permissions.

Use 'limacharlie group list' to find available group IDs.
"""
register_explain("group.get", _EXPLAIN_GET)


@group.command()
@click.option("--id", "group_id", required=True, help="Group ID.")
@pass_context
def get(ctx, group_id) -> None:
    org = _get_org(ctx)
    data = org.get_group(group_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new group.  Groups allow you to manage multiple
organizations under a single umbrella with shared user permissions.

After creating a group, use the LimaCharlie web UI or API to add
members, owners, and organizations to the group.
"""
register_explain("group.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--name", required=True, help="Group name.")
@pass_context
def create(ctx, name) -> None:
    org = _get_org(ctx)
    data = org.create_group(name)
    if not ctx.obj.quiet:
        click.echo(f"Group '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete a group by its ID.  This permanently removes the group and
all associated membership and permission data.  The --confirm flag
is required to prevent accidental deletion.

This does NOT delete the organizations within the group.
"""
register_explain("group.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--id", "group_id", required=True, help="Group ID to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, group_id, confirm) -> None:
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


# ---------------------------------------------------------------------------
# member-add
# ---------------------------------------------------------------------------

_EXPLAIN_MEMBER_ADD = """\
Add a user as a member of a group.  Members inherit the group's
permissions across all organizations associated with the group.

Example:
  limacharlie group member-add --gid <group-id> --email user@example.com
"""
register_explain("group.member-add", _EXPLAIN_MEMBER_ADD)


@group.command("member-add")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--email", required=True, help="Email address of the user to add as member.")
@pass_context
def member_add(ctx, gid, email) -> None:
    org = _get_org(ctx)
    data = org.add_group_member(gid, email)
    if not ctx.obj.quiet:
        click.echo(f"Member '{email}' added to group '{gid}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# member-remove
# ---------------------------------------------------------------------------

_EXPLAIN_MEMBER_REMOVE = """\
Remove a user from a group's member list.  The user will immediately
lose any permissions inherited through this group membership.

Example:
  limacharlie group member-remove --gid <group-id> --email user@example.com
"""
register_explain("group.member-remove", _EXPLAIN_MEMBER_REMOVE)


@group.command("member-remove")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--email", required=True, help="Email address of the member to remove.")
@pass_context
def member_remove(ctx, gid, email) -> None:
    org = _get_org(ctx)
    data = org.remove_group_member(gid, email)
    if not ctx.obj.quiet:
        click.echo(f"Member '{email}' removed from group '{gid}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# owner-add
# ---------------------------------------------------------------------------

_EXPLAIN_OWNER_ADD = """\
Add a user as an owner of a group.  Owners can manage the group's
membership, permissions, and associated organizations.

Example:
  limacharlie group owner-add --gid <group-id> --email user@example.com
"""
register_explain("group.owner-add", _EXPLAIN_OWNER_ADD)


@group.command("owner-add")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--email", required=True, help="Email address of the user to add as owner.")
@pass_context
def owner_add(ctx, gid, email) -> None:
    org = _get_org(ctx)
    data = org.add_group_owner(gid, email)
    if not ctx.obj.quiet:
        click.echo(f"Owner '{email}' added to group '{gid}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# owner-remove
# ---------------------------------------------------------------------------

_EXPLAIN_OWNER_REMOVE = """\
Remove a user from a group's owner list.  The user will lose the
ability to manage the group but may retain member access if they
are still listed as a member.

Example:
  limacharlie group owner-remove --gid <group-id> --email user@example.com
"""
register_explain("group.owner-remove", _EXPLAIN_OWNER_REMOVE)


@group.command("owner-remove")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--email", required=True, help="Email address of the owner to remove.")
@pass_context
def owner_remove(ctx, gid, email) -> None:
    org = _get_org(ctx)
    data = org.remove_group_owner(gid, email)
    if not ctx.obj.quiet:
        click.echo(f"Owner '{email}' removed from group '{gid}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# permissions-set
# ---------------------------------------------------------------------------

_EXPLAIN_PERMISSIONS_SET = """\
Set the permissions for a group.  This replaces all existing group
permissions with the specified list.  Members of the group will
inherit these permissions across all associated organizations.

Permissions use the same category.action format as user permissions
(e.g., sensor.list, dr.set, org.get).  See 'limacharlie user
permissions add' explain text for the full list.

Example:
  limacharlie group permissions-set --gid <group-id> --permissions 'sensor.list,sensor.get,dr.list'
"""
register_explain("group.permissions-set", _EXPLAIN_PERMISSIONS_SET)


@group.command("permissions-set")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--permissions", required=True, help="Comma-separated list of permissions (e.g. 'sensor.list,sensor.get,dr.list').")
@pass_context
def permissions_set(ctx, gid, permissions) -> None:
    perms = [p.strip() for p in permissions.split(",") if p.strip()]
    org = _get_org(ctx)
    data = org.set_group_permissions(gid, perms)
    if not ctx.obj.quiet:
        click.echo(f"Permissions set for group '{gid}': {', '.join(perms)}")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# org-add
# ---------------------------------------------------------------------------

_EXPLAIN_ORG_ADD = """\
Associate an organization with a group.  Group members will gain
the group's permissions on the specified organization.

Example:
  limacharlie group org-add --gid <group-id> --oid <org-id>
"""
register_explain("group.org-add", _EXPLAIN_ORG_ADD)


@group.command("org-add")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--oid", required=True, help="Organization ID to associate with the group.")
@pass_context
def org_add(ctx, gid, oid) -> None:
    org = _get_org(ctx)
    data = org.add_group_org(gid, oid)
    if not ctx.obj.quiet:
        click.echo(f"Organization '{oid}' added to group '{gid}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# org-remove
# ---------------------------------------------------------------------------

_EXPLAIN_ORG_REMOVE = """\
Remove an organization from a group.  Group members will lose
the group's permissions on the specified organization.

Example:
  limacharlie group org-remove --gid <group-id> --oid <org-id>
"""
register_explain("group.org-remove", _EXPLAIN_ORG_REMOVE)


@group.command("org-remove")
@click.option("--gid", required=True, help="Group ID.")
@click.option("--oid", required=True, help="Organization ID to remove from the group.")
@pass_context
def org_remove(ctx, gid, oid) -> None:
    org = _get_org(ctx)
    data = org.remove_group_org(gid, oid)
    if not ctx.obj.quiet:
        click.echo(f"Organization '{oid}' removed from group '{gid}'.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

_EXPLAIN_LOGS = """\
Get audit logs for a group.  Returns a list of actions performed
on the group such as membership changes, permission updates, and
organization associations.

Example:
  limacharlie group logs --gid <group-id>
"""
register_explain("group.logs", _EXPLAIN_LOGS)


@group.command()
@click.option("--gid", required=True, help="Group ID.")
@pass_context
def logs(ctx, gid) -> None:
    org = _get_org(ctx)
    data = org.get_group_logs(gid)
    _output(ctx, data)
