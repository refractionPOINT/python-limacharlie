"""Sensor commands for LimaCharlie CLI v2.

Commands for listing, inspecting, and managing sensors in an organization.
"""

from __future__ import annotations

from typing import Any

import json

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

_EXPLAIN_UPGRADE = """\
Upgrade sensors in the organization.  Optionally restrict to sensors
matching a selector expression (bexpr).  When no selector is given,
all sensors in the organization are upgraded.

This triggers the sensor to download and apply the latest version
configured for the organization.  Use 'limacharlie sensor set-version'
to set the target version before upgrading.

Related: 'limacharlie sensor set-version' to set the version branch,
'limacharlie sensor list' to see current sensor versions.
"""

_EXPLAIN_SET_VERSION = """\
Set the sensor version or branch for the organization.  This controls
which sensor binary version endpoints will run.  Sensors pick up the
new version on their next check-in or when explicitly upgraded.

Provide --version with a specific version string (e.g., '4.29.0').
Use --fallback to switch to the stable/fallback branch.
Use --sleep to put sensors into dormant mode.

Related: 'limacharlie sensor upgrade' to trigger sensors to apply
the new version immediately.
"""

_EXPLAIN_EXPORT = """\
Export the full sensor manifest for the organization.  Returns
comprehensive data for every sensor including hostname, platform,
architecture, version, IPs, tags, online status, and enrollment
details.

This is useful for fleet auditing, compliance reporting, and backup.
Use --selector to restrict the export to sensors matching a bexpr
expression.

Related: 'limacharlie sensor list' for a lighter listing,
'limacharlie sync pull' for full configuration export.
"""

_EXPLAIN_DUMP = """\
Trigger a full memory dump on a sensor.  This sends a request to the
LimaCharlie dumper service to collect a full memory image from the
target endpoint.

The dump is performed asynchronously.  Results are delivered as
artifacts that can be retrieved via 'limacharlie artifact list'.

This is a heavyweight operation.  Use --confirm to proceed.

Related: 'limacharlie task send' for lighter data collection,
'limacharlie artifact list' to retrieve the results.
"""

_EXPLAIN_SWEEP = """\
Run a sweep on a sensor with a custom configuration.  Sweeps allow
you to collect a broad set of forensic artifacts from an endpoint
in a single operation.

The --config parameter accepts either a JSON string or a path to a
JSON file containing the sweep configuration.

Related: 'limacharlie task send' for individual task commands,
'limacharlie sensor dump' for full memory dumps.
"""

register_explain("sensor.list", _EXPLAIN_LIST)
register_explain("sensor.get", _EXPLAIN_GET)
register_explain("sensor.delete", _EXPLAIN_DELETE)
register_explain("sensor.online", _EXPLAIN_ONLINE)
register_explain("sensor.wait-online", _EXPLAIN_WAIT_ONLINE)
register_explain("sensor.upgrade", _EXPLAIN_UPGRADE)
register_explain("sensor.set-version", _EXPLAIN_SET_VERSION)
register_explain("sensor.export", _EXPLAIN_EXPORT)
register_explain("sensor.dump", _EXPLAIN_DUMP)
register_explain("sensor.sweep", _EXPLAIN_SWEEP)


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


def _get_sensor(ctx: click.Context, sid: str) -> Sensor:
    org = _get_org(ctx)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("sensor")
def group() -> None:
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
@pass_context
def list_sensors(ctx: click.Context, tag: str | None, hostname: str | None, ip: str | None, limit: int | None, offset: int | None) -> None:
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
@pass_context
def get(ctx: click.Context, sid: str) -> None:
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
@pass_context
def delete(ctx: click.Context, sid: str, confirm: bool) -> None:
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
@pass_context
def online(ctx: click.Context, sid: str) -> None:
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
@pass_context
def wait_online(ctx: click.Context, sid: str, timeout: int) -> None:
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


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

@group.command()
@pass_context
def upgrade(ctx: click.Context) -> None:
    """Upgrade sensors in the organization.

    Triggers all sensors to download and apply the currently configured version.

    Example:
        limacharlie sensor upgrade
    """
    org = _get_org(ctx)
    # Trigger upgrade by re-setting the current version (forces re-download).
    data = org.set_sensor_version()
    if not ctx.obj.quiet:
        click.echo("Sensor upgrade triggered for all sensors.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# set-version
# ---------------------------------------------------------------------------

@group.command("set-version")
@click.option("--version", "version_str", default=None, help="Specific sensor version string (e.g., '4.29.0').")
@click.option("--fallback", is_flag=True, default=False, help="Use the stable/fallback version branch.")
@click.option("--sleep", "is_sleep", is_flag=True, default=False, help="Put sensors into dormant mode.")
@pass_context
def set_version(ctx: click.Context, version_str: str | None, fallback: bool, is_sleep: bool) -> None:
    """Set the sensor version for the organization.

    Provide --version for a specific version, --fallback for the stable
    branch, or --sleep to put sensors into dormant mode.

    Examples:
        limacharlie sensor set-version --version 4.29.0
        limacharlie sensor set-version --fallback
        limacharlie sensor set-version --sleep
    """
    if not version_str and not fallback and not is_sleep:
        click.echo(
            "Error: At least one of --version, --fallback, or --sleep is required.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.set_sensor_version(
        version=version_str,
        is_fallback=fallback,
        is_sleep=is_sleep,
    )
    if not ctx.obj.quiet:
        if version_str:
            click.echo(f"Sensor version set to '{version_str}'.")
        elif fallback:
            click.echo("Sensor version set to fallback/stable branch.")
        elif is_sleep:
            click.echo("Sensors set to dormant mode.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@group.command("export")
@click.option("--selector", default=None, help="Sensor selector expression (bexpr) to filter exported sensors.")
@pass_context
def export_sensors(ctx: click.Context, selector: str | None) -> None:
    """Export full sensor data for the organization.

    Lists all sensors and outputs their complete data.  Use --selector
    to restrict to a subset of sensors.

    Examples:
        limacharlie sensor export
        limacharlie sensor export --selector "`linux` in tags" --output json
    """
    org = _get_org(ctx)

    if selector:
        sensors = list(org.list_sensors(selector=selector))
        _output(ctx, sensors)
    else:
        data = org.export_sensors()
        _output(ctx, data)


# ---------------------------------------------------------------------------
# dump
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to dump.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm the memory dump (required).")
@pass_context
def dump(ctx: click.Context, sid: str, confirm: bool) -> None:
    """Trigger a full memory dump on a sensor.

    This is a heavyweight operation.  Pass --confirm to proceed.

    Example:
        limacharlie sensor dump --sid <SID> --confirm
    """
    if not confirm:
        click.echo(
            "Error: Memory dump is a heavyweight operation and requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to trigger the dump.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    data = org.service_request("dumper", {"sid": sid}, is_async=True)
    if not ctx.obj.quiet:
        click.echo(f"Memory dump triggered for sensor {sid}.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to sweep.")
@click.option(
    "--config", "config_str", required=True,
    help="Sweep configuration as a JSON string or path to a JSON file.",
)
@pass_context
def sweep(ctx: click.Context, sid: str, config_str: str) -> None:
    """Run a sweep on a sensor with a custom configuration.

    The --config value can be a JSON string or a path to a JSON file.

    Examples:
        limacharlie sensor sweep --sid <SID> --config '{"os_processes": true}'
        limacharlie sensor sweep --sid <SID> --config sweep_config.json
    """
    # Try loading as a file first, then as a JSON string.
    try:
        with open(config_str, "r") as f:
            config = json.loads(f.read())
    except (OSError, IOError):
        config = json.loads(config_str)

    sensor = _get_sensor(ctx, sid)
    # Build the task list from the sweep config keys.
    tasks = []
    for task_name, task_args in config.items():
        if isinstance(task_args, bool) and task_args:
            tasks.append(task_name)
        elif isinstance(task_args, str):
            tasks.append(f"{task_name} {task_args}")
        elif isinstance(task_args, dict):
            tasks.append(task_name)
        else:
            tasks.append(str(task_name))
    data = sensor.task(tasks)
    if not ctx.obj.quiet:
        click.echo(f"Sweep sent to sensor {sid} ({len(tasks)} task(s)).")
    _output(ctx, data)
