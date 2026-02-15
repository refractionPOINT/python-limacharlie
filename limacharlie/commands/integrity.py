"""Integrity monitoring commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting integrity monitoring
rules.  Integrity rules watch for file system changes on endpoints
and generate events when monitored files or directories are modified.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.integrity import Integrity as IntegritySDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all integrity monitoring rules in the organization.  Integrity
rules are managed by the ext-integrity extension and provide File
Integrity Monitoring (FIM) and Registry Integrity Monitoring (RIM).

Each rule specifies patterns (file/registry paths with wildcards),
optional sensor tags to target, and optional platform filters.
When a monitored path changes, a FIM_HIT event is generated on the
sensor's timeline.

Use --output json to get the full rule definitions for export.
"""

_EXPLAIN_CREATE = """\
Create a new integrity monitoring rule via the ext-integrity
extension.  The rule defines file or registry paths to watch for
modifications.  Changes trigger FIM_HIT events on the sensor.

Patterns are provided as a comma-separated list.  Wildcards:
  *  - matches any sequence of characters in a path component
  ?  - matches any single character (also matches drive letter on Windows)
  +  - matches one or more subdirectory levels

Pattern examples by platform:

  Linux FIM:
    /etc/passwd
    /etc/shadow
    /root/.ssh/*
    /home/*/.ssh/authorized_keys

  macOS FIM:
    /Users/*/Library/Keychains/*
    /Library/Keychains

  Windows FIM:
    ?:\\Windows\\System32\\drivers
    C:\\Windows\\System32\\specialfile.exe
    ?:\\inetpub\\wwwroot

  Windows RIM (must start with \\REGISTRY):
    \\REGISTRY\\MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run*
    \\REGISTRY\\USER\\S-*\\Software\\Microsoft\\Windows\\CurrentVersion\\Run*

Note: Windows paths require double backslash escaping in patterns.

Examples:
  limacharlie integrity create --name critical-configs \\
    --patterns "/etc/passwd,/etc/shadow,/etc/hosts"

  limacharlie integrity create --name win-autorun \\
    --patterns "?:\\Windows\\System32\\drivers,\\REGISTRY\\MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run*"
"""

_EXPLAIN_DELETE = """\
Delete an integrity monitoring rule by name.  This stops monitoring
the associated file paths and registry keys.  Sensors will no longer
generate FIM_HIT events for the patterns in this rule.  The --confirm
flag is required to prevent accidental deletion.
"""

_EXPLAIN_GET = """\
Get the details of a single integrity monitoring rule by name.
Returns the full rule definition including:

  name      - rule name
  patterns  - list of file/registry path patterns being monitored
  tags      - sensor tags this rule targets (empty = all sensors)
  platforms - OS filter (linux, windows, macos; empty = all)

Example:
  limacharlie integrity get --name critical-configs
"""

register_explain("integrity.list", _EXPLAIN_LIST)
register_explain("integrity.create", _EXPLAIN_CREATE)
register_explain("integrity.delete", _EXPLAIN_DELETE)
register_explain("integrity.get", _EXPLAIN_GET)


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

@click.group("integrity")
def group() -> None:
    """Manage integrity monitoring rules.

    Integrity monitoring watches for file system changes on
    endpoints.  Rules define which file paths to monitor and
    generate events when changes are detected.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@pass_context
def list_rules(ctx) -> None:
    """List integrity monitoring rules.

    Example:
        limacharlie integrity list
    """
    org = _get_org(ctx)
    sdk = IntegritySDK(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--patterns", required=True,
    help="Comma-separated list of file path patterns to monitor.",
)
@pass_context
def create(ctx, name, patterns) -> None:
    """Create an integrity monitoring rule.

    Examples:
        limacharlie integrity create --name critical-configs \\
            --patterns "/etc/passwd,/etc/shadow"

        limacharlie integrity create --name web-root \\
            --patterns "/var/www/html/**"
    """
    pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]
    if not pattern_list:
        click.echo("Error: At least one pattern is required.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = IntegritySDK(org)
    data = sdk.create(name, pattern_list)
    if not ctx.obj.quiet:
        click.echo(f"Integrity rule '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, name, confirm) -> None:
    """Delete an integrity monitoring rule.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie integrity delete --name critical-configs --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the rule.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = IntegritySDK(org)
    data = sdk.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Integrity rule '{name}' deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name to retrieve.")
@pass_context
def get(ctx, name) -> None:
    """Get a single integrity monitoring rule by name.

    Example:
        limacharlie integrity get --name critical-configs
    """
    org = _get_org(ctx)
    sdk = IntegritySDK(org)
    data = sdk.get(name)
    if data is None:
        click.echo(f"Error: Integrity rule '{name}' not found.", err=True)
        ctx.exit(4)
        return
    _output(ctx, data)
