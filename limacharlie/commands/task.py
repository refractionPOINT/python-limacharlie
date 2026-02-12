"""Sensor tasking commands for LimaCharlie CLI v2.

Commands for sending tasks (commands) to individual sensors.  Tasks are
the primary mechanism for interacting with endpoints: collecting data,
killing processes, downloading files, running YARA scans, and more.
"""

from __future__ import annotations

from typing import Any, Callable

import time

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.sensor import Sensor
from ..sdk.spout import Spout
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_SEND = """\
Send a task command to a sensor (fire-and-forget).  The task is queued
for delivery to the sensor.  If the sensor is online, the task is
delivered immediately; if offline, it will be delivered when the sensor
next connects.

The --task value is the full task command string exactly as documented
in the LimaCharlie sensor command reference.  Common task commands
include:

  os_processes          - List running processes
  os_services           - List OS services
  dir_list /path        - List a directory
  file_get /path        - Retrieve a file
  os_kill_process PID   - Kill a process
  mem_strings PID       - Dump strings from process memory
  yara_scan rule path   - Run a YARA scan

This command does not wait for a response.  To see results, use
'limacharlie stream events' or check the event history.

Related: 'limacharlie help sensors' for the full task command reference.
"""

_EXPLAIN_REQUEST = """\
Send a task command to a sensor and wait for the response.  Unlike
'task send', this command opens a temporary Spout to receive events
from the sensor and blocks until a response is received or the
timeout expires.

This is useful for interactive investigation: send a command and
immediately see the results without needing a separate streaming
session.

The --timeout value (default: 30 seconds) controls how long to wait
for a response.  If the sensor is offline or the task takes longer
than the timeout, the command exits with the data collected so far.

Related: 'limacharlie task send' for fire-and-forget tasking,
'limacharlie stream events' for continuous event streaming.
"""

_EXPLAIN_RELIABLE_SEND = """\
Send a task command with guaranteed delivery via the reliable-tasking
service.  Unlike regular tasking, reliable tasks are persisted and
will be delivered to the sensor even if it is currently offline.

Tasks are retried until the sensor comes online and acknowledges
receipt, or until the optional TTL expires.

Use --investigation-id to associate the task with an investigation
for tracking purposes.

Related: 'limacharlie task reliable-list' to see pending tasks,
'limacharlie task reliable-delete' to cancel a pending task.
"""

_EXPLAIN_RELIABLE_LIST = """\
List pending reliable tasks for a sensor.  Shows tasks that have
been submitted via 'task reliable-send' but have not yet been
delivered and acknowledged by the sensor.

Related: 'limacharlie task reliable-send' to submit a reliable task,
'limacharlie task reliable-delete' to cancel a pending task.
"""

_EXPLAIN_RELIABLE_DELETE = """\
Cancel a pending reliable task.  The task will be removed from the
queue and will not be delivered to the sensor.

You must provide the --task-id of the specific task to cancel.  Use
'limacharlie task reliable-list' to find task IDs.

Related: 'limacharlie task reliable-list' to find pending task IDs,
'limacharlie task reliable-send' to submit a reliable task.
"""

register_explain("task.send", _EXPLAIN_SEND)
register_explain("task.request", _EXPLAIN_REQUEST)
register_explain("task.reliable-send", _EXPLAIN_RELIABLE_SEND)
register_explain("task.reliable-list", _EXPLAIN_RELIABLE_LIST)
register_explain("task.reliable-delete", _EXPLAIN_RELIABLE_DELETE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[..., None]:
    def callback(ctx: click.Context, param: click.Parameter, value: Any) -> None:
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


def _get_sensor(ctx: click.Context, sid: str) -> Sensor:
    org = _get_org(ctx)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("task")
def group() -> None:
    """Send tasks (commands) to sensors.

    Tasks are the primary mechanism for interacting with endpoints.
    Use 'limacharlie task send' to send a fire-and-forget command to a
    sensor.
    """


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to task.")
@click.option(
    "--task", required=True,
    help="Task command string (e.g. 'os_processes', 'dir_list /tmp').",
)
@click.option(
    "--investigation-id", default=None,
    help="Optional investigation ID to associate with this task.",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SEND),
    help="Show detailed explanation of this command.",
)
@pass_context
def send(ctx: click.Context, sid: str, task: str, investigation_id: str | None) -> None:
    """Send a task to a sensor (fire-and-forget).

    Examples:
        limacharlie task send --sid <SID> --task os_processes
        limacharlie task send --sid <SID> --task "dir_list /tmp"
        limacharlie task send --sid <SID> --task "file_get /etc/passwd" --investigation-id inv-001
    """
    sensor = _get_sensor(ctx, sid)
    data = sensor.task(task, inv_id=investigation_id)
    if not ctx.obj.quiet:
        click.echo(f"Task sent to sensor {sid}.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------

@group.command()
@click.option("--sid", required=True, help="Sensor ID (UUID) to task.")
@click.option(
    "--command", "task_command", required=True,
    help="Task command string (e.g. 'os_processes', 'dir_list /tmp').",
)
@click.option(
    "--timeout", default=30, type=int,
    help="Seconds to wait for a response (default: 30).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_REQUEST),
    help="Show detailed explanation of this command.",
)
@pass_context
def request(ctx: click.Context, sid: str, task_command: str, timeout: int) -> None:
    """Send a task and wait for the response.

    Opens a temporary event stream, sends the task, collects events
    until the timeout expires, and outputs the results.

    Examples:
        limacharlie task request --sid <SID> --command os_processes
        limacharlie task request --sid <SID> --command "dir_list /tmp" --timeout 60
    """
    org = _get_org(ctx)
    sensor = Sensor(org, sid)

    # Create a Spout to receive events from this sensor.
    spout = Spout(org, "event", sid=sid)
    try:
        # Send the task.
        sensor.task(task_command)
        if not ctx.obj.quiet:
            click.echo(f"Task sent, waiting up to {timeout}s for response...")

        # Collect events until timeout.
        results = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            event = spout.get(timeout=min(remaining, 2))
            if event is not None:
                results.append(event)
    finally:
        spout.shutdown()

    _output(ctx, results)


# ---------------------------------------------------------------------------
# reliable-send
# ---------------------------------------------------------------------------

@group.command("reliable-send")
@click.option("--sid", required=True, help="Sensor ID (UUID) to task.")
@click.option(
    "--command", "task_command", required=True,
    help="Task command string for reliable delivery.",
)
@click.option(
    "--investigation-id", default=None,
    help="Optional investigation ID to associate with this task.",
)
@click.option(
    "--ttl", default=None, type=int,
    help="Seconds before the task expires if undelivered (default: one week).",
)
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RELIABLE_SEND),
    help="Show detailed explanation of this command.",
)
@pass_context
def reliable_send(ctx: click.Context, sid: str, task_command: str, investigation_id: str | None, ttl: int | None) -> None:
    """Send a task with guaranteed delivery.

    The task is persisted and will be delivered even if the sensor
    is currently offline.

    Examples:
        limacharlie task reliable-send --sid <SID> --command os_processes
        limacharlie task reliable-send --sid <SID> --command "file_get /etc/passwd" --ttl 3600
    """
    org = _get_org(ctx)
    req = {
        "action": "task",
        "task": task_command,
        "sid": sid,
    }
    if investigation_id:
        req["inv_id"] = investigation_id
    if ttl is not None:
        req["ttl"] = ttl
    data = org.service_request("reliable-tasking", req, is_async=True)
    if not ctx.obj.quiet:
        click.echo(f"Reliable task sent to sensor {sid}.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# reliable-list
# ---------------------------------------------------------------------------

@group.command("reliable-list")
@click.option("--sid", required=True, help="Sensor ID (UUID) to list pending tasks for.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RELIABLE_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def reliable_list(ctx: click.Context, sid: str) -> None:
    """List pending reliable tasks for a sensor.

    Example:
        limacharlie task reliable-list --sid <SID>
    """
    org = _get_org(ctx)
    req = {
        "action": "list",
        "sid": sid,
    }
    data = org.service_request("reliable-tasking", req, is_async=False)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# reliable-delete
# ---------------------------------------------------------------------------

@group.command("reliable-delete")
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option("--task-id", required=True, help="Task ID to cancel.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RELIABLE_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def reliable_delete(ctx: click.Context, sid: str, task_id: str) -> None:
    """Cancel a pending reliable task.

    Example:
        limacharlie task reliable-delete --sid <SID> --task-id <TASK_ID>
    """
    org = _get_org(ctx)
    req = {
        "action": "untask",
        "sid": sid,
        "task_id": task_id,
    }
    data = org.service_request("reliable-tasking", req, is_async=True)
    if not ctx.obj.quiet:
        click.echo(f"Reliable task {task_id} cancelled for sensor {sid}.")
    _output(ctx, data)
