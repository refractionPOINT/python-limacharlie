"""Exfil prevention commands for LimaCharlie CLI v2.

Commands for listing, creating, and deleting exfil prevention rules.
Exfil rules control which events and data are allowed to leave
sensors.  There are two types: watch rules (field-level matching)
and event rules (event-type matching).
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.exfil import Exfil as ExfilSDK
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

_EXPLAIN_LIST = """\
List all exfil (event collection) rules in the organization.  These
rules control which real-time events sensors send to the LimaCharlie
cloud.  By default sensors send a standard profile; exfil rules
customize this.

Rules are grouped into three types:

  event  - Specify which event types to collect from sensors.
           Each rule has a list of event type names, optional tags,
           and optional platform filters.
  watch  - Conditional collection: only send events matching a
           field-level condition (e.g. MODULE_LOAD where FILE_PATH
           ends with "wininet.dll").
  perf   - Performance rules for high-I/O servers (Windows only).
           Applied via tag to reduce processing overhead.

Rule changes sync to sensors every few minutes.

Use --output json to get the full rule definitions for export.
"""
register_explain("exfil.list", _EXPLAIN_LIST)


@group.command("list")
@pass_context
def list_rules(ctx) -> None:
    org = _get_org(ctx)
    sdk = ExfilSDK(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create-watch
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE_WATCH = """\
Create an exfil watch rule that conditionally collects events based
on a field-level match.  Only events where the specified field matches
the operator/value condition are sent from the sensor to the cloud.

This is useful for high-volume event types where you only care about
specific values (e.g. only MODULE_LOAD events for a particular DLL).

Required parameters:
  --name      Rule name (unique identifier).
  --event     Event type to watch (e.g., MODULE_LOAD, DNS_REQUEST).
  --operator  Comparison: 'is', 'is not', 'contains', 'not contains',
              'starts with', 'ends with', 'matches' (regex).
  --value     Value to compare against.
  --path      Event field path to inspect (e.g., event/FILE_PATH,
              event/DOMAIN_NAME, event/COMMAND_LINE).

Example watch rule: only collect MODULE_LOAD events where FILE_PATH
ends with wininet.dll:
  limacharlie exfil create-watch --name wininet-loading \\
    --event MODULE_LOAD --operator "ends with" \\
    --value wininet.dll --path event/FILE_PATH

Example: collect DNS_REQUEST only for a specific domain:
  limacharlie exfil create-watch --name track-uploads \\
    --event DNS_REQUEST --operator contains \\
    --value upload.example.com --path event/DOMAIN_NAME
"""
register_explain("exfil.create-watch", _EXPLAIN_CREATE_WATCH)


@group.command("create-watch")
@click.option("--name", required=True, help="Rule name.")
@click.option("--event", required=True, help="Event type to watch (e.g., NEW_PROCESS).")
@click.option("--operator", required=True, help="Comparison operator (e.g., is, contains).")
@click.option("--value", required=True, help="Value to compare against.")
@click.option("--path", required=True, help="Event field path (e.g., event/FILE_PATH).")
@pass_context
def create_watch(ctx, name, event, operator, value, path) -> None:
    org = _get_org(ctx)
    sdk = ExfilSDK(org)
    data = sdk.create_watch(name, event, value, operator, path)
    if not ctx.obj.quiet:
        click.echo(f"Exfil watch rule '{name}' created.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# create-event
# ---------------------------------------------------------------------------

_EXPLAIN_CREATE_EVENT = """\
Create an exfil event collection rule that specifies which event
types sensors should send to the cloud.  This is the primary way
to customize what telemetry is collected from endpoints.

Events are provided as a comma-separated list of event type names.
Common event types to collect:
  NEW_PROCESS, TERMINATE_PROCESS, DNS_REQUEST, NETWORK_CONNECTIONS,
  NEW_TCP4_CONNECTION, NEW_TCP6_CONNECTION, FILE_CREATE, FILE_MODIFIED,
  MODULE_LOAD, CODE_IDENTITY, REGISTRY_WRITE, WEL

Be careful enabling all events at once -- this can produce very high
traffic volume.  Start with specific event types and expand as needed.
See 'event types' for the full list of available event types.

Examples:
  limacharlie exfil create-event --name critical-events \\
    --events NEW_PROCESS,DNS_REQUEST,NETWORK_CONNECTIONS

  limacharlie exfil create-event --name tcp-monitoring \\
    --events NEW_TCP4_CONNECTION,NEW_TCP6_CONNECTION
"""
register_explain("exfil.create-event", _EXPLAIN_CREATE_EVENT)


@group.command("create-event")
@click.option("--name", required=True, help="Rule name.")
@click.option(
    "--events", required=True,
    help="Comma-separated list of event types (e.g., NEW_PROCESS,DNS_REQUEST).",
)
@pass_context
def create_event(ctx, name, events) -> None:
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

_EXPLAIN_DELETE = """\
Delete an exfil rule by name.  Use --type to specify whether it is
an 'event' rule or a 'watch' rule (defaults to 'event').

The --confirm flag is required to prevent accidental deletion.
Deleting an event collection rule will cause sensors to stop
collecting those event types (sync takes a few minutes).

Examples:
  limacharlie exfil delete --name critical-events --confirm
  limacharlie exfil delete --name wininet-loading --type watch --confirm
"""
register_explain("exfil.delete", _EXPLAIN_DELETE)


@group.command()
@click.option("--name", required=True, help="Rule name to delete.")
@click.option(
    "--type", "rule_type", default="event",
    type=click.Choice(["event", "watch"], case_sensitive=False),
    help="Rule type: 'event' or 'watch' (default: event).",
)
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
def delete(ctx, name, rule_type, confirm) -> None:
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
