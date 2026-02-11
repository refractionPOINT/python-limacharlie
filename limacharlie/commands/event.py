"""Event commands for LimaCharlie CLI v2.

Commands for listing and retrieving historical events from sensors
via LimaCharlie Insight.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
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

register_explain("event.list", _EXPLAIN_LIST)
register_explain("event.get", _EXPLAIN_GET)


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

@click.group("event")
def group():
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_events(ctx, sid, start, end, limit, event_type):
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
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, sid, atom):
    """Get an event by atom.

    Example:
        limacharlie event get --sid <SID> --atom <ATOM>
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)
    data = sensor.get_event_by_atom(atom)
    _output(ctx, data)
