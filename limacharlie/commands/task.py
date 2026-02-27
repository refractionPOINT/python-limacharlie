"""Sensor tasking commands for LimaCharlie CLI v2.

Commands for sending tasks (commands) to individual sensors.  Tasks are
the primary mechanism for interacting with endpoints: collecting data,
killing processes, downloading files, running YARA scans, and more.
"""

from __future__ import annotations

from typing import Any

import time
import uuid

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.sensor import Sensor
from ..sdk.spout import Spout
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

_EXPLAIN_SEND = """\
Send a task command to a sensor (fire-and-forget).  The task is queued
for delivery to the sensor.  If the sensor is online, the task is
delivered immediately; if offline, it will be delivered when the sensor
next connects.

The --task value is the full command string.  Common task commands:

  Process / service:
    os_processes                - List running processes
    os_services                 - List OS services
    os_kill_process <PID>       - Kill a process by PID
    os_suspend <PID>            - Suspend a process
    os_resume <PID>             - Resume a suspended process

  File system:
    dir_list <path>             - List a directory
    file_get <path>             - Retrieve a file as artifact
    file_del <path>             - Delete a file
    file_hash <path>            - Get hash of a file
    file_info <path>            - Get file metadata
    file_mov <src> <dst>        - Move/rename a file

  Memory / forensics:
    mem_map <PID>               - Memory map of a process
    mem_strings <PID>           - Dump strings from process memory
    mem_handles <PID>           - List handles (Windows only)
    hidden_module_scan <PID>    - Scan for hidden modules

  Network:
    netstat                     - List network connections
    dns_resolve <domain>        - Resolve a domain name
    segregate_network           - Isolate sensor from network
    rejoin_network              - Remove network isolation

  Scanning:
    yara_scan <rule> <path>     - YARA scan a file or directory
    artifact_get <path>         - Collect an artifact (file/log)

  System info:
    os_version                  - Get OS version info
    os_packages                 - List installed packages
    os_autoruns                 - List autorun entries
    os_users                    - List local user accounts (Win)
    history_dump                - Dump recent telemetry

This command does not wait for a response.  To see results, use
'limacharlie task request' (synchronous) or 'limacharlie stream events'.
"""
register_explain("task.send", _EXPLAIN_SEND)


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
@pass_context
def send(ctx: click.Context, sid: str, task: str, investigation_id: str | None) -> None:
    sensor = _get_sensor(ctx, sid)
    data = sensor.task(task, inv_id=investigation_id)
    if not ctx.obj.quiet:
        click.echo(f"Task sent to sensor {sid}.", err=True)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------

_EXPLAIN_REQUEST = """\
Send a task command to a sensor and wait for the response.  Unlike
'task send', this command opens a temporary Spout to receive events
from the sensor and blocks until a response is received or the
timeout expires.

This is the recommended way to interactively query a sensor, for
example: listing processes, reading files, or running YARA scans
while immediately viewing results in the terminal.

The --timeout value (default: 30 seconds) controls how long to wait.
If the sensor is offline or the task takes longer than the timeout,
the command exits with whatever data has been collected so far.

The response events vary by task command; for example os_processes
returns OS_PROCESSES_REP, dir_list returns DIR_LIST_REP, etc.

Related: 'limacharlie task send' for fire-and-forget tasking,
'limacharlie stream events' for continuous event streaming.
"""
register_explain("task.request", _EXPLAIN_REQUEST)


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
@pass_context
def request(ctx: click.Context, sid: str, task_command: str, timeout: int) -> None:
    org = _get_org(ctx)
    sensor = Sensor(org, sid)

    # Use an investigation_id to correlate the task with its response.
    inv_id = str(uuid.uuid4())

    # Ensure the JWT is available before creating the Spout.  JWTs are
    # normally generated lazily on the first client.request() call, but
    # the Spout reads client._jwt directly in its constructor.
    if org.client._jwt is None:
        org.client.refresh_jwt()

    # Create a Spout FIRST so the subscription is active before the task is sent.
    # The stream-tmp server sends {"__trace":"connected"} once the output
    # subscription has propagated (~1 s after HTTP 200).  We must wait for
    # that signal before sending the task, otherwise the response event
    # arrives before the subscription exists and is silently lost.
    spout = Spout(org, "event", inv_id=inv_id)
    try:
        spout.wait_connected(timeout=10)

        # Send the task with the same investigation_id.
        sensor.task(task_command, inv_id=inv_id)
        if not ctx.obj.quiet:
            click.echo(f"Task sent, waiting up to {timeout}s for response...", err=True)

        # Collect events until timeout.  CLOUD_NOTIFICATION is just a
        # delivery receipt from the cloud, not the actual sensor response.
        results = []
        deadline = time.time() + timeout
        got_result = False
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            event = spout.get(timeout=min(remaining, 2))
            if event is not None:
                routing = event.get("routing", {})
                if routing.get("event_type") == "CLOUD_NOTIFICATION":
                    continue
                results.append(event)
                if not got_result:
                    # After the first real result, shorten the deadline
                    # to collect any trailing events without waiting the
                    # full timeout.
                    got_result = True
                    deadline = min(deadline, time.time() + 2)
    finally:
        spout.shutdown()

    _output(ctx, results)


# ---------------------------------------------------------------------------
# reliable-send
# ---------------------------------------------------------------------------

_EXPLAIN_RELIABLE_SEND = """\
Send a task command with guaranteed delivery via the reliable-tasking
service.  Unlike regular tasking, reliable tasks are persisted and
will be delivered to the sensor even if it is currently offline.

Tasks are retried until the sensor comes online and acknowledges
receipt, or until the optional --ttl expires (default: one week).

This is useful for scenarios where the endpoint may be powered off
or disconnected, such as laptop fleets or intermittent systems.

Use --investigation-id to associate the task with an investigation
for tracking purposes.

Related: 'limacharlie task reliable-list' to see pending tasks,
'limacharlie task reliable-delete' to cancel a pending task.
"""
register_explain("task.reliable-send", _EXPLAIN_RELIABLE_SEND)


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
@pass_context
def reliable_send(ctx: click.Context, sid: str, task_command: str, investigation_id: str | None, ttl: int | None) -> None:
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
        click.echo(f"Reliable task sent to sensor {sid}.", err=True)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# reliable-list
# ---------------------------------------------------------------------------

_EXPLAIN_RELIABLE_LIST = """\
List pending reliable tasks for a sensor.  Shows tasks that have
been submitted via 'task reliable-send' but have not yet been
delivered and acknowledged by the sensor.

Related: 'limacharlie task reliable-send' to submit a reliable task,
'limacharlie task reliable-delete' to cancel a pending task.
"""
register_explain("task.reliable-list", _EXPLAIN_RELIABLE_LIST)


@group.command("reliable-list")
@click.option("--sid", required=True, help="Sensor ID (UUID) to list pending tasks for.")
@pass_context
def reliable_list(ctx: click.Context, sid: str) -> None:
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

_EXPLAIN_RELIABLE_DELETE = """\
Cancel a pending reliable task.  The task will be removed from the
queue and will not be delivered to the sensor.

You must provide the --task-id of the specific task to cancel.  Use
'limacharlie task reliable-list' to find task IDs.

Related: 'limacharlie task reliable-list' to find pending task IDs,
'limacharlie task reliable-send' to submit a reliable task.
"""
register_explain("task.reliable-delete", _EXPLAIN_RELIABLE_DELETE)


@group.command("reliable-delete")
@click.option("--sid", required=True, help="Sensor ID (UUID).")
@click.option("--task-id", required=True, help="Task ID to cancel.")
@pass_context
def reliable_delete(ctx: click.Context, sid: str, task_id: str) -> None:
    org = _get_org(ctx)
    req = {
        "action": "untask",
        "sid": sid,
        "task_id": task_id,
    }
    data = org.service_request("reliable-tasking", req, is_async=True)
    if not ctx.obj.quiet:
        click.echo(f"Reliable task {task_id} cancelled for sensor {sid}.", err=True)
    _output(ctx, data)
