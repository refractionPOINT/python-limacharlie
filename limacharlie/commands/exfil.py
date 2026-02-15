"""Exfil prevention commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting exfil prevention rules.
Exfil rules control which events and data are allowed to leave
sensors.  There are two types: watch rules (field-level matching)
and event rules (event-type matching).
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.exfil import Exfil as ExfilSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List all exfil prevention rules in the organization.  Rules are
grouped into two types:

  watch  - Match on specific field values within events.
  event  - Match on entire event types.

Use --output json to get the full rule definitions for export.
"""

_EXPLAIN_CREATE_WATCH = """\
Create an exfil watch rule that matches on a specific field value
within events.  Watch rules inspect individual event fields using
an operator and value comparison.

Required parameters:
  --name      Rule name.
  --event     Event type to watch (e.g., 'NEW_PROCESS').
  --operator  Comparison operator (e.g., 'is', 'contains', 'starts with').
  --value     Value to compare against.
  --path      Event field path to inspect (e.g., 'event/FILE_PATH').

Example:
  limacharlie exfil create-watch --name block-uploads \\
    --event NETWORK_SUMMARY --operator contains \\
    --value upload.example.com --path event/DOMAIN_NAME
"""

_EXPLAIN_CREATE_EVENT = """\
Create an exfil event rule that matches on entire event types.
Event rules specify which event types should be exfiltrated from
sensors.

Events are provided as a comma-separated list of event type names.

Example:
  limacharlie exfil create-event --name critical-events \\
    --events NEW_PROCESS,DNS_REQUEST,NETWORK_SUMMARY
"""

_EXPLAIN_DELETE = """\
Delete an exfil rule by name.  The --confirm flag is required to
prevent accidental deletion.

Example:
  limacharlie exfil delete --name block-uploads --confirm
"""

register_explain("exfil.list", _EXPLAIN_LIST)
register_explain("exfil.create-watch", _EXPLAIN_CREATE_WATCH)
register_explain("exfil.create-event", _EXPLAIN_CREATE_EVENT)
register_explain("exfil.delete", _EXPLAIN_DELETE)


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

@click.group("exfil")
def group() -> None:
    """Manage exfil prevention rules.

    Exfil rules control which events and data are allowed to leave
    sensors.  Watch rules match on specific field values while event
    rules match on entire event types.
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
    """List exfil prevention rules.

    Example:
        limacharlie exfil list
    """
    org = _get_org(ctx)
    sdk = ExfilSDK(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create-watch
# ---------------------------------------------------------------------------

@group.command("create-watch")
@click.option("--name", required=True, help="Rule name.")
@click.option("--event", required=True, help="Event type to watch (e.g., NEW_PROCESS).")
@click.option("--operator", required=True, help="Comparison operator (e.g., is, contains).")
@click.option("--value", required=True, help="Value to compare against.")
@click.option("--path", required=True, help="Event field path (e.g., event/FILE_PATH).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE_WATCH),
    help="Show detailed explanation of this command.",
)
@pass_context
def create_watch(ctx, name, event, operator, value, path) -> None:
    """Create an exfil watch rule (field-level matching).

    Example:
        limacharlie exfil create-watch --name block-uploads \\
            --event NETWORK_SUMMARY --operator contains \\
            --value upload.example.com --path event/DOMAIN_NAME
    """
    org = _get_org(ctx)
    sdk = ExfilSDK(org)
    data = sdk.create_watch(name, event, value, operator, path)
    if not ctx.obj.quiet:
        click.echo(f"Exfil watch rule '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create-event
# ---------------------------------------------------------------------------

@group.command("create-event")
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--events", required=True,
    help="Comma-separated list of event types (e.g., NEW_PROCESS,DNS_REQUEST).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_CREATE_EVENT),
    help="Show detailed explanation of this command.",
)
@pass_context
def create_event(ctx, name, events) -> None:
    """Create an exfil event rule (event-type matching).

    Example:
        limacharlie exfil create-event --name critical-events \\
            --events NEW_PROCESS,DNS_REQUEST,NETWORK_SUMMARY
    """
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    if not event_list:
        click.echo("Error: At least one event type is required.", err=True)
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = ExfilSDK(org)
    data = sdk.create_event(name, event_list)
    if not ctx.obj.quiet:
        click.echo(f"Exfil event rule '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--name", required=True, help="Rule name to delete.")
@click.option(
    "--type", "rule_type", default="event",
    type=click.Choice(["event", "watch"], case_sensitive=False),
    help="Rule type: 'event' or 'watch' (default: event).",
)
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, name, rule_type, confirm) -> None:
    """Delete an exfil rule.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie exfil delete --name block-uploads --confirm
        limacharlie exfil delete --name my-watch --type watch --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the exfil rule.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = ExfilSDK(org)
    if rule_type == "watch":
        data = sdk.delete_watch(name)
    else:
        data = sdk.delete_event(name)
    if not ctx.obj.quiet:
        click.echo(f"Exfil rule '{name}' deleted.")
    _output(ctx, data)
