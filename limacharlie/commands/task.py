"""Sensor tasking commands for LimaCharlie CLI v2.

Commands for sending tasks (commands) to individual sensors.  Tasks are
the primary mechanism for interacting with endpoints: collecting data,
killing processes, downloading files, running YARA scans, and more.
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

register_explain("task.send", _EXPLAIN_SEND)


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


def _get_sensor(ctx, sid):
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    org = Organization(client)
    return Sensor(org, sid)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("task")
def group():
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
def send(ctx, sid, task, investigation_id):
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
