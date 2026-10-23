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

_EXPLAIN_LIST = """\
List all installation keys for the organization.  Installation keys
are used to enroll new sensors and adapters.  The result is a map
keyed by iid, not an array.

Each key record contains:
  iid      - Installation key ID (UUID).  ADAPTERS (USP, cloud and
             external adapters) use THIS value as
             client_options.identity.installation_key.  Sensors
             enrolled with the key report it as their "iid".
  key      - Base64 key for NATIVE SENSORS (EDR agents) only.  Pass
             it to the sensor installer:
               ./lc_sensor_64 -i <VALUE_OF_key>
  json_key - Base64 JSON key for BROWSER SENSORS only.
  desc     - Human-readable description of the key's purpose.
  tags     - Comma-separated tags applied to sensors at enrollment.
  created  - Unix timestamp in SECONDS (10 digits), not milliseconds.
             Set when the key was last written: editing a key resets
             it.  It is NOT an expiry; installation keys never expire.
  quota_total / quota_remaining
           - Only present when the key has an enrollment quota.
             Enrollment is refused once quota_remaining reaches 0.

IMPORTANT: When a user asks to "install a sensor", they need the
"key" field.  When configuring an adapter, they need the "iid".
"json_key" is only for browser sensors.  Do NOT confuse them.

Use separate keys per deployment segment (e.g., 'production-linux',
'staging-windows') so tags automatically classify sensors at
enrollment time.
"""
register_explain("installation-key.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_keys(ctx) -> None:
    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Get a specific installation key by its IID.  Returns the same record
as one entry of "installation-key list":

  iid      - Use this UUID for adapters
             (client_options.identity.installation_key).
  key      - Use this for native sensor installers:
               ./lc_sensor_64 -i <VALUE_OF_key>
  json_key - Browser sensors only.
  created  - Unix timestamp in SECONDS, reset whenever the key is
             edited.  Not an expiry: keys never expire.

Example:
  limacharlie installation-key get --iid <IID>
"""
register_explain("installation-key.get", _EXPLAIN_GET)


@group.command("get")
@click.option("--iid", required=True, help="Installation key ID.")
@pass_context
def get_key(ctx, iid) -> None:
    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.get(iid)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new installation key.  The --description is required and
should identify the purpose of the key (e.g., 'production-linux',
'staging-windows').  Before creating one, check whether an existing
key already has a matching description and tags.

Use --tags to apply tags to sensors enrolled with this key.  Multiple
tags can be comma-separated.  Tags are applied automatically at
enrollment and can be used in sensor selectors, D&R rule targeting,
and fleet filtering.

Without --get, the response contains only "oid" and "iid".  Pass
--get (or run "installation-key get") to obtain the key strings:

  iid      - For ADAPTERS (client_options.identity.installation_key).
  key      - For NATIVE SENSOR installation:
               ./lc_sensor_64 -i <VALUE_OF_key>
  json_key - For BROWSER SENSORS only.

Never pass an empty value to an installer.

Examples:
  limacharlie installation-key create --description "production linux"
  limacharlie installation-key create --description "staging" --tags "env:staging,os:windows"
  limacharlie installation-key create --description "prod" --get
"""
register_explain("installation-key.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--description", required=True, help="Key description.")
@click.option("--tags", default=None, help="Comma-separated tags to apply to enrolled sensors.")
@click.option("--get", "get_after", is_flag=True, default=False, help="Fetch the full key details after creation.")
@pass_context
def create(ctx, description, tags, get_after) -> None:
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    org = _get_org(ctx)
    keys = InstallationKeys(org)
    data = keys.create(description, tags=tag_list)
    if not ctx.obj.quiet:
        click.echo("Installation key created.")

    if get_after:
        iid = data.get("iid") if isinstance(data, dict) else None
        if iid:
            data = keys.get(iid)

    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

_EXPLAIN_DELETE = """\
Delete an installation key by its IID.  No new sensors can enroll
with it afterwards.  Native sensors (EDR agents) already enrolled
keep working, but ADAPTERS configured with this key's iid are refused
the next time they connect, because they authenticate with the iid on
every connection.  The --confirm flag is required to prevent
accidental deletion.

Example:
  limacharlie installation-key delete --iid <IID> --confirm
"""
register_explain("installation-key.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--iid", required=True, help="Installation key ID to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, iid, confirm) -> None:
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
