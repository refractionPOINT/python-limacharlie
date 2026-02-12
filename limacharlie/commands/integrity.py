"""Integrity monitoring commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting integrity monitoring
rules.  Integrity rules watch for file system changes on endpoints
and generate events when monitored files or directories are modified.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.integrity import Integrity as IntegritySDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all integrity monitoring rules in the organization.  Each rule
specifies a set of file path patterns to monitor for changes.

Use --output json to get the full rule definitions for export.
"""

_EXPLAIN_CREATE = """\
Create a new integrity monitoring rule.  The rule defines which
file paths to watch for modifications.

Patterns are provided as a comma-separated list of file path
glob patterns.  Monitored paths generate events when files are
created, modified, or deleted.

Examples:
  limacharlie integrity create --name critical-configs \\
    --patterns "/etc/passwd,/etc/shadow,/etc/hosts"

  limacharlie integrity create --name web-root \\
    --patterns "/var/www/html/**"
"""

_EXPLAIN_DELETE = """\
Delete an integrity monitoring rule by name.  This stops monitoring
the associated file paths.  The --confirm flag is required to
prevent accidental deletion.
"""

_EXPLAIN_GET = """\
Get the details of a single integrity monitoring rule by name.
Returns the rule definition including its file path patterns,
tags, and platform filters.

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

@click.group("integrity")
def group():
    """Manage integrity monitoring rules.

    Integrity monitoring watches for file system changes on
    endpoints.  Rules define which file paths to monitor and
    generate events when changes are detected.
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
def list_rules(ctx):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name, patterns):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, name, confirm):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, name):
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
