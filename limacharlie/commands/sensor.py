"""Sensor commands for LimaCharlie CLI v2.

Commands for listing, inspecting, and managing sensors in an organization.
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
List sensors enrolled in the organization.  Results can be filtered by
tag (using the sensor selector expression 'tag in tags'), by hostname
prefix, or by IP address.  The --limit and --offset options control
pagination; by default all sensors are returned.

Sensors are returned with their SID, hostname, platform, external and
internal IPs, online status, and other metadata.  Use --output json to
get the full sensor records for scripting.

Related: 'limacharlie tag find' to find sensors by a specific tag,
'limacharlie sensor get --sid <SID>' for detailed info on one sensor.
"""

_EXPLAIN_GET = """\
Get full details for a single sensor identified by its SID (Sensor ID).
Returns hostname, platform, architecture, version, enrollment time, IPs,
online status, isolation status, tags, and other metadata.

The SID is a UUID that uniquely identifies a sensor across the
LimaCharlie platform.  You can obtain SIDs from 'limacharlie sensor list',
'limacharlie tag find', or 'limacharlie ioc search'.
"""

_EXPLAIN_DELETE = """\
Permanently delete a sensor from the organization.  This removes the
sensor record and all associated metadata.  The sensor will need to be
re-enrolled if you want it back.  Historical telemetry for this sensor
is retained according to your retention policy.

This is a destructive operation.  You must pass --confirm to proceed.
"""

_EXPLAIN_ONLINE = """\
Check whether a specific sensor is currently online (connected to the
LimaCharlie cloud).  Returns a simple boolean result.  This is a
lightweight check useful for scripts that need to verify connectivity
before sending tasks.
"""

_EXPLAIN_WAIT_ONLINE = """\
Block until a sensor comes online or the timeout expires.  This is
useful in deployment scripts or automated workflows where you need to
wait for a sensor to check in before sending tasks to it.

The command polls the sensor status periodically.  Use --timeout to
set the maximum wait time in seconds (default: 300).
"""

register_explain("sensor.list", _EXPLAIN_LIST)
register_explain("sensor.get", _EXPLAIN_GET)
register_explain("sensor.delete", _EXPLAIN_DELETE)
register_explain("sensor.online", _EXPLAIN_ONLINE)
register_explain("sensor.wait-online", _EXPLAIN_WAIT_ONLINE)


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


def _get_sensor(ctx, sid):
    org = _get_org(ctx)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("sensor")
def group():
    """List, inspect, and manage sensors.

    Sensors are the agents installed on endpoints.  Use these commands
    to enumerate the fleet, check sensor status, and perform lifecycle
    operations such as deletion.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--tag", default=None, help="Filter by tag (sensors with this tag).")
@click.option("--hostname", default=None, help="Filter by hostname prefix.")
@click.option("--ip", default=None, help="Filter by IP address.")
@click.option("--limit", default=None, type=int, help="Maximum number of sensors to return.")
@click.option("--offset", default=None, type=int, help="Pagination offset (not used directly; controls client-side skip).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_sensors(ctx, tag, hostname, ip, limit, offset):
    """List sensors in the organization.

    Examples:
        limacharlie sensor list
        limacharlie sensor list --tag production --limit 50
        limacharlie sensor list --hostname web-server
        limacharlie sensor list --ip 10.0.0.5
    """
    org = _get_org(ctx)

    selector = None
    if tag:
        selector = f"`{tag}` in tags"

    # When offset is used, we need to fetch offset+limit from the API
    api_limit = None
    if limit and offset:
        api_limit = limit + offset
    elif limit:
        api_limit = limit

    sensors = []
    count = 0
    for s in org.list_sensors(
        selector=selector,
        limit=api_limit,
        with_ip=ip,
        with_hostname_prefix=hostname,
    ):
        if offset and count < offset:
            count += 1
            continue
        sensors.append(s)
        count += 1
        if limit and len(sensors) >= limit:
            break

    _output(ctx, sensors)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, sid):
    """Get full details for a sensor.

    Example:
        limacharlie sensor get --sid <SID>
    """
    sensor = _get_sensor(ctx, sid)
    data = sensor.get_info()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, sid, confirm):
    """Permanently delete a sensor.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie sensor delete --sid <SID> --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the sensor.",
            err=True,
        )
        ctx.exit(4)
        return

    sensor = _get_sensor(ctx, sid)
    data = sensor.delete()
    if not ctx.obj.quiet:
        click.echo(f"Sensor {sid} deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# online
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_ONLINE),
    help="Show detailed explanation of this command.",
)
@pass_context
def online(ctx, sid):
    """Check if a sensor is currently online.

    Example:
        limacharlie sensor online --sid <SID>
    """
    sensor = _get_sensor(ctx, sid)
    is_online = sensor.is_online()
    _output(ctx, {"sid": sid, "is_online": is_online})


# ---------------------------------------------------------------------------
# wait-online
# ---------------------------------------------------------------------------

@group.command("wait-online")
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option("--timeout", default=300, type=int, help="Maximum seconds to wait (default: 300).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_WAIT_ONLINE),
    help="Show detailed explanation of this command.",
)
@pass_context
def wait_online(ctx, sid, timeout):
    """Wait for a sensor to come online.

    Blocks until the sensor is online or the timeout expires.
    Exits with code 0 if the sensor came online, 1 if timed out.

    Example:
        limacharlie sensor wait-online --sid <SID> --timeout 120
    """
    sensor = _get_sensor(ctx, sid)
    if not ctx.obj.quiet:
        click.echo(f"Waiting up to {timeout}s for sensor {sid} to come online...")
    came_online = sensor.wait_online(timeout)
    if came_online:
        _output(ctx, {"sid": sid, "is_online": True})
    else:
        if not ctx.obj.quiet:
            click.echo(f"Sensor {sid} did not come online within {timeout}s.", err=True)
        ctx.exit(1)
