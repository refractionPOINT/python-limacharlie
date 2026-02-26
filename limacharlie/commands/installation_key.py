"""Installation key commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting installation keys.
Installation keys are used to enroll new sensors into an organization.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.installation_keys import InstallationKeys
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all installation keys for the organization.  Installation keys
are Base64-encoded strings used to enroll new sensors and adapters.

Each key contains four components:
  OID   - Organization ID the sensor enrolls into
  IID   - Installer ID (auto-generated, unique per key)
  tags  - List of tags automatically applied at enrollment
  desc  - Human-readable description of the key's purpose

The output includes the key ID (IID), description, tags, and
creation date.  Use separate keys per deployment segment (e.g.,
'production-linux', 'staging-windows') so tags automatically
classify sensors at enrollment time.
"""

_EXPLAIN_CREATE = """\
Create a new installation key.  The --description is required and
should identify the purpose of the key (e.g., 'production-linux',
'staging-windows').

Use --tags to apply tags to sensors enrolled with this key.  Multiple
tags can be comma-separated.  Tags are applied automatically at
enrollment and can be used in sensor selectors, D&R rule targeting,
and fleet filtering.

The returned output includes the full Base64-encoded installation key
string that should be provided to the sensor installer:
  ./lc_sensor_64 -i <INSTALLATION_KEY>

Examples:
  limacharlie installation-key create --description "production linux"
  limacharlie installation-key create --description "staging" --tags "env:staging,os:windows"
"""

_EXPLAIN_GET = """\
Get a specific installation key by its IID.  Returns the key's
description, tags, creation date, and the full Base64-encoded
installation key string.

Example:
  limacharlie installation-key get --iid <IID>
"""

_EXPLAIN_DELETE = """\
Delete an installation key by its IID.  Sensors already enrolled
with this key will not be affected, but no new sensors can enroll
using it.  The --confirm flag is required to prevent accidental
deletion.

Example:
  limacharlie installation-key delete --iid <IID> --confirm
"""

register_explain("installation-key.list", _EXPLAIN_LIST)
register_explain("installation-key.get", _EXPLAIN_GET)
register_explain("installation-key.create", _EXPLAIN_CREATE)
register_explain("installation-key.delete", _EXPLAIN_DELETE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

@click.group("installation-key")
def group() -> None:
    """Manage installation keys.

    Installation keys are used to enroll new sensors into the
    organization.  Each key can have tags that are automatically
    applied to sensors at enrollment time.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@pass_context
def list_keys(ctx) -> None:
    """List installation keys.

    Example:
        limacharlie installation-key list
    """
    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command("get")
@click.option("--iid", required=True, help="Installation key ID.")
@pass_context
def get_key(ctx, iid) -> None:
    """Get a specific installation key.

    Example:
        limacharlie installation-key get --iid <IID>
    """
    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.get(iid)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--description", required=True, help="Key description.")
@click.option("--tags", default=None, help="Comma-separated tags to apply to enrolled sensors.")
@pass_context
def create(ctx, description, tags) -> None:
    """Create a new installation key.

    Examples:
        limacharlie installation-key create --description "production linux"
        limacharlie installation-key create --description "staging" \\
            --tags "env:staging,os:windows"
    """
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.create(description, tags=tag_list)
    if not ctx.obj.quiet:
        click.echo("Installation key created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--iid", required=True, help="Installation key ID to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, iid, confirm) -> None:
    """Delete an installation key.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie installation-key delete --iid <IID> --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the installation key.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.delete(iid)
    if not ctx.obj.quiet:
        click.echo(f"Installation key '{iid}' deleted.")
    _output(ctx, data)
