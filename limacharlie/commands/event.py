"""Event commands for LimaCharlie CLI v2.

Commands for listing and retrieving historical events from sensors
via LimaCharlie Insight.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.sensor import Sensor
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List historical events for a specific sensor.  Events are stored in
the Insight data lake and can be queried by time range and event type.

You must provide --sid (sensor ID) and a time range via --start and
--end (unix epoch seconds).

Use --event-type to filter for a specific event type.  Use --limit to
cap the number of events returned.

Common event types:
  NEW_PROCESS          - Process creation with FILE_PATH, COMMAND_LINE, USER_NAME
  TERMINATE_PROCESS    - Process exit
  DNS_REQUEST          - DNS query with DOMAIN_NAME, IP_ADDRESS, DNS_TYPE
  NETWORK_CONNECTIONS  - Active connections snapshot (NETWORK_ACTIVITY array)
  NEW_TCP4_CONNECTION  - New outbound TCP connection
  FILE_CREATE          - File created with FILE_PATH
  FILE_MODIFIED        - File changed with FILE_PATH, ACTION, HASH
  MODULE_LOAD          - DLL/shared library loaded
  CODE_IDENTITY        - Code signing info with HASH, SIGNATURE
  REGISTRY_WRITE       - Windows registry change
  WEL                  - Windows Event Log entries (nested EVENT structure)

Each returned event has a two-level structure:
  routing:  oid, sid, event_type, event_time (ms), hostname, ext_ip, int_ip, tags
  event:    fields vary by event_type (e.g. FILE_PATH, COMMAND_LINE, DOMAIN_NAME)

Events are linked by atom hashes: routing/this identifies the event,
routing/parent links to the parent process.  Use 'event get' and
'event children' to navigate the event tree.

Examples:
  limacharlie event list --sid <SID> --start 1700000000 --end 1700086400
  limacharlie event list --sid <SID> --start 1700000000 --end 1700086400 \\
      --event-type NEW_PROCESS --limit 100
"""

_EXPLAIN_GET = """\
Get a specific event by its atom identifier.  Every event in
LimaCharlie is assigned a unique atom hash (found in routing/this).
Atoms let you retrieve the exact event and navigate parent-child
relationships to reconstruct the full process tree.

The returned event has the standard two-level structure:
  routing:  oid, sid, event_type, event_time, hostname, this, parent
  event:    payload fields specific to the event_type

You must provide --sid (sensor ID) and --atom (the routing/this value).

Example:
  limacharlie event get --sid <SID> --atom <ATOM>
"""

_EXPLAIN_CHILDREN = """\
Get child events of a specific parent event atom.  In the LimaCharlie
event tree, every event has a parent atom (routing/parent) and may
have children.  Use this command to traverse the tree downward from a
given atom, e.g. to see all processes spawned by a parent process.

Returns a list of events, each with the standard routing + event
structure.  The routing/parent of each child matches the atom you
provided.

You must provide --sid (sensor ID) and --atom (parent event atom).

Example:
  limacharlie event children --sid <SID> --atom <ATOM>
"""

_EXPLAIN_OVERVIEW = """\
Get an event overview (timeline) for a sensor.  The overview provides
a high-level summary of event activity within a time range, showing
when events occurred without returning full event data.

You must provide --sid (sensor ID) and a time range via --start and
--end (unix epoch seconds).

Example:
  limacharlie event overview --sid <SID> --start 1700000000 --end 1700086400
"""

_EXPLAIN_TIMELINE = """\
Alias for 'event overview'.  Get an event timeline for a sensor showing
when events occurred within a time range.

Example:
  limacharlie event timeline --sid <SID> --start 1700000000 --end 1700086400
"""

_EXPLAIN_TYPES = """\
List available event types and their schemas.  Optionally filter by
platform (e.g., 'windows', 'linux', 'macos').

Returns the full list of event types the platform recognizes.  Some
common ones across platforms:
  NEW_PROCESS, TERMINATE_PROCESS, DNS_REQUEST, NETWORK_CONNECTIONS,
  NEW_TCP4_CONNECTION, FILE_CREATE, FILE_MODIFIED, FILE_DELETE,
  MODULE_LOAD, CODE_IDENTITY, REGISTRY_WRITE (Windows),
  WEL (Windows Event Log), USER_OBSERVED, CONNECTED, CLOUD_NOTIFICATION

Use 'event schema --event-type <TYPE>' to see the full field list for
any given event type.

Examples:
  limacharlie event types
  limacharlie event types --platform windows
"""

_EXPLAIN_SCHEMA = """\
Get the schema definition for a specific event type.  The schema
describes every field in the event payload, its type, and meaning.

For example, the NEW_PROCESS schema documents fields like FILE_PATH,
COMMAND_LINE, PROCESS_ID, USER_NAME, PARENT (nested object with its
own FILE_PATH/PROCESS_ID), and HASH.

Use this to understand what fields are available for D&R rule
detection conditions, LCQL query filters, or exfil watch rules.

Example:
  limacharlie event schema --event-type NEW_PROCESS
"""

_EXPLAIN_RETENTION = """\
Get event retention statistics for a sensor.  Shows how many events
are stored in the Insight data lake for the given time range.  Use
--detailed to get a breakdown by event type.

Example:
  limacharlie event retention --sid <SID> --start 1700000000 --end 1700086400
  limacharlie event retention --sid <SID> --start 1700000000 --end 1700086400 --detailed
"""

register_explain("event.list", _EXPLAIN_LIST)
register_explain("event.get", _EXPLAIN_GET)
register_explain("event.children", _EXPLAIN_CHILDREN)
register_explain("event.overview", _EXPLAIN_OVERVIEW)
register_explain("event.timeline", _EXPLAIN_TIMELINE)
register_explain("event.types", _EXPLAIN_TYPES)
register_explain("event.schema", _EXPLAIN_SCHEMA)
register_explain("event.retention", _EXPLAIN_RETENTION)


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

@click.group("event")
def group() -> None:
    """Query historical sensor events.

    Retrieve events stored in the Insight data lake for individual
    sensors.  Events include process creation, network activity,
    file operations, and more.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--sid", required=True, help="Sensor ID.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--limit", default=None, type=int, help="Maximum number of events.")
@click.option("--event-type", default=None, help="Filter by event type (e.g., NEW_PROCESS).")
@pass_context
def list_events(ctx: click.Context, sid: str, start: int, end: int, limit: int | None, event_type: str | None) -> None:
    """List events for a sensor.

    Examples:
        limacharlie event list --sid <SID> --start 1700000000 --end 1700086400
        limacharlie event list --sid <SID> --start 1700000000 --end 1700086400 \\
            --event-type NEW_PROCESS --limit 100
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    events = list(sensor.get_events(start, end, limit=limit, event_type=event_type))
    _output(ctx, events)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID.")
@click.option("--atom", required=True, help="Event atom identifier.")
@pass_context
def get(ctx: click.Context, sid: str, atom: str) -> None:
    """Get an event by atom.

    Example:
        limacharlie event get --sid <SID> --atom <ATOM>
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    data = sensor.get_event_by_atom(atom)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# children
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID.")
@click.option("--atom", required=True, help="Parent event atom identifier.")
@pass_context
def children(ctx: click.Context, sid: str, atom: str) -> None:
    """Get child events of an atom.

    Example:
        limacharlie event children --sid <SID> --atom <ATOM>
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    data = sensor.get_children_events(atom)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@pass_context
def overview(ctx: click.Context, sid: str, start: int, end: int) -> None:
    """Get event overview for a sensor.

    Example:
        limacharlie event overview --sid <SID> --start 1700000000 --end 1700086400
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    data = sensor.get_overview(start, end)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# timeline (alias for overview)
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@pass_context
def timeline(ctx: click.Context, sid: str, start: int, end: int) -> None:
    """Get event timeline for a sensor (alias for overview).

    Example:
        limacharlie event timeline --sid <SID> --start 1700000000 --end 1700086400
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    data = sensor.get_overview(start, end)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------

@group.command()
@click.option("--platform", default=None, help="Filter by platform (e.g., windows, linux, macos).")
@pass_context
def types(ctx: click.Context, platform: str | None) -> None:
    """List available event types.

    Examples:
        limacharlie event types
        limacharlie event types --platform windows
    """
    org = _get_org(ctx)
    data = org.get_schemas(platform=platform)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

@group.command()
@click.option("--event-type", required=True, help="Event type name (e.g., NEW_PROCESS).")
@pass_context
def schema(ctx: click.Context, event_type: str) -> None:
    """Get schema for a specific event type.

    Example:
        limacharlie event schema --event-type NEW_PROCESS
    """
    org = _get_org(ctx)
    data = org.get_schema(event_type)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# retention
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--detailed", is_flag=True, default=False, help="Include detailed breakdown by event type.")
@pass_context
def retention(ctx: click.Context, sid: str, start: int, end: int, detailed: bool) -> None:
    """Get event retention statistics for a sensor.

    Examples:
        limacharlie event retention --sid <SID> --start 1700000000 --end 1700086400
        limacharlie event retention --sid <SID> --start 1700000000 --end 1700086400 --detailed
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    data = sensor.get_event_retention(start, end, is_detailed=detailed)
    _output(ctx, data)
