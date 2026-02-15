"""Logging rule commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting log collection rules.
Logging rules control which log sources are collected and retained
from endpoints.
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.logging_rules import LoggingRules
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all log collection rules in the organization.  Each rule
defines a set of log path patterns to collect from endpoints.

Use --output json to get the full rule definitions for export.
"""

_EXPLAIN_CREATE = """\
Create a new log collection rule.  The rule defines which log
paths to collect from endpoints.

Patterns are provided as a comma-separated list of file path
patterns (e.g., '/var/log/syslog,/var/log/auth.log').

Examples:
  limacharlie logging create --name system-logs \\
    --patterns "/var/log/syslog,/var/log/auth.log"

  limacharlie logging create --name app-logs \\
    --patterns "/opt/myapp/logs/*.log"
"""

_EXPLAIN_DELETE = """\
Delete a log collection rule by name.  This stops collection of
the associated log paths.  The --confirm flag is required to
prevent accidental deletion.
"""

_EXPLAIN_GET = """\
Get the details of a single log collection rule by name.
Returns the rule definition including its log path patterns,
tags, platform filters, and retention settings.

Example:
  limacharlie logging get --name system-logs
"""

register_explain("logging.list", _EXPLAIN_LIST)
register_explain("logging.create", _EXPLAIN_CREATE)
register_explain("logging.delete", _EXPLAIN_DELETE)
register_explain("logging.get", _EXPLAIN_GET)


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

@click.group("logging")
def group() -> None:
    """Manage log collection rules.

    Logging rules control which log sources are collected and
    retained from endpoints.  Each rule specifies a set of file
    path patterns to collect.
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
def list_rules(ctx) -> None:
    """List log collection rules.

    Example:
        limacharlie logging list
    """
    org = _get_org(ctx)
    sdk = LoggingRules(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--patterns", required=True,
    help="Comma-separated list of log path patterns to collect.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def create(ctx, name, patterns) -> None:
    """Create a log collection rule.

    Examples:
        limacharlie logging create --name system-logs \\
            --patterns "/var/log/syslog,/var/log/auth.log"

        limacharlie logging create --name app-logs \\
            --patterns "/opt/myapp/logs/*.log"
    """
    pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]
    if not pattern_list:
        click.echo("Error: At least one pattern is required.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = LoggingRules(org)
    data = sdk.create(name, pattern_list)
    if not ctx.obj.quiet:
        click.echo(f"Logging rule '{name}' created.")
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
def delete(ctx, name, confirm) -> None:
    """Delete a log collection rule.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie logging delete --name system-logs --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the logging rule.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = LoggingRules(org)
    data = sdk.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Logging rule '{name}' deleted.")
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
def get(ctx, name) -> None:
    """Get a single log collection rule by name.

    Example:
        limacharlie logging get --name system-logs
    """
    org = _get_org(ctx)
    sdk = LoggingRules(org)
    data = sdk.get(name)
    if data is None:
        click.echo(f"Error: Logging rule '{name}' not found.", err=True)
        ctx.exit(4)
        return
    _output(ctx, data)
