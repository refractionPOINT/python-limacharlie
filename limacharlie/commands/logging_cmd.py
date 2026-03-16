"""Logging rule commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting log collection rules.
Logging rules control which log sources are collected and retained
from endpoints.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.logging_rules import LoggingRules
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

_EXPLAIN_LIST = """\
List all log collection rules in the organization.  Each rule
defines a set of log path patterns to collect from endpoints.

Use --output json to get the full rule definitions for export.
"""
register_explain("logging.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_rules(ctx) -> None:
    org = _get_org(ctx)
    sdk = LoggingRules(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE = """\
Create a new log collection rule.  The rule defines which log
paths to collect from endpoints.  Collected logs are uploaded as
artifacts and available via 'limacharlie artifact list'.

Patterns are provided as a comma-separated list of file path
patterns.  Glob wildcards (* and ?) are supported.

Examples:
  limacharlie logging create --name system-logs \\
    --patterns "/var/log/syslog,/var/log/auth.log"

  limacharlie logging create --name app-logs \\
    --patterns "/opt/myapp/logs/*.log"

  limacharlie logging create --name windows-evtx \\
    --patterns "C:\\Windows\\System32\\winevt\\Logs\\Security.evtx"
"""
register_explain("logging.create", _EXPLAIN_CREATE)


@group.command()
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--patterns", required=True,
    help="Comma-separated list of log path patterns to collect.",
)
@pass_context
def create(ctx, name, patterns) -> None:
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

_EXPLAIN_DELETE = """\
Delete a log collection rule by name.  This stops collection of
the associated log paths.  The --confirm flag is required to
prevent accidental deletion.
"""
register_explain("logging.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--name", required=True, help="Rule name to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, name, confirm) -> None:
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

_EXPLAIN_GET = """\
Get the details of a single log collection rule by name.
Returns the rule definition including its log path patterns,
tags, platform filters, and retention settings.

Example:
  limacharlie logging get --name system-logs
"""
register_explain("logging.get", _EXPLAIN_GET)


@group.command()
@click.option("--name", required=True, help="Rule name to retrieve.")
@pass_context
def get(ctx, name) -> None:
    org = _get_org(ctx)
    sdk = LoggingRules(org)
    data = sdk.get(name)
    if data is None:
        click.echo(f"Error: Logging rule '{name}' not found.", err=True)
        ctx.exit(4)
        return
    _output(ctx, data)
