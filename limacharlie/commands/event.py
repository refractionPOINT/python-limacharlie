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

Use --event-type to filter for a specific event type (e.g.,
'NEW_PROCESS', 'DNS_REQUEST', 'NETWORK_SUMMARY').  Use --limit to
cap the number of events returned.

Examples:
  limacharlie event list --sid <SID> --start 1700000000 --end 1700086400
  limacharlie event list --sid <SID> --start 1700000000 --end 1700086400 \\
      --event-type NEW_PROCESS --limit 100
"""

_EXPLAIN_GET = """\
Get a specific event by its atom identifier.  Atoms are unique
identifiers assigned to every event and can be used to retrieve
the exact event, navigate parent-child relationships, and build
event trees.

You must provide --sid (sensor ID) and --atom (event atom).

Example:
  limacharlie event get --sid <SID> --atom <ATOM>
"""

_EXPLAIN_CHILDREN = """\
Get child events of a specific parent event atom.  In the LimaCharlie
event tree, every event has a parent atom and may have child events.
Use this command to traverse the event tree downward from a given atom.

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

Examples:
  limacharlie event types
  limacharlie event types --platform windows
"""

_EXPLAIN_SCHEMA = """\
Get the schema definition for a specific event type.  The schema
describes the fields and structure of events of this type.

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
