"""Audit log commands for LimaCharlie CLI v2.

Commands for listing audit logs that record all administrative
actions performed on the organization.
"""

from __future__ import annotations

import time
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ._time_validation import validate_epoch_seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("audit")
def group() -> None:
    """View audit logs.

    Audit logs record all administrative actions performed on the
    organization, providing a complete activity trail for security
    and compliance purposes.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List audit logs for the organization.  Audit logs record all
administrative actions including rule changes, user management,
sensor operations, and API key usage.

Each audit entry contains:
  oid        - Organization ID
  ts         - Timestamp of the action (UTC string, "YYYY-MM-DD HH:MM:SS")
  etype      - Event type (e.g. hive_set, send_task, remove_sensor)
  msg        - Human-readable description of the action

V2 fields (preferred for new callers):
  time       - Timestamp (Unix milliseconds)
  ident      - Identity performing the action (email, API key hash,
               extension ID, or DR rule)
  entity     - Object the action is performed on (e.g. {sid: ...})
  mtd        - Characteristics of the action (action-specific metadata)

Legacy field (V1, retained for backward compatibility):
  origin     - Pre-V2 actor identity; superseded by ident.  When ident
               is empty, origin holds the actor.

Time range is specified with --start and --end as Unix timestamps
in seconds.  If not provided, defaults to the last 24 hours.

Use --limit to cap the number of results returned.

Filter results server-side with --event-type (e.g. hive_set, send_task,
remove_sensor) or --sid (limit to events relating to a specific sensor).

Examples:
  limacharlie audit list
  limacharlie audit list --start 1700000000 --end 1700100000
  limacharlie audit list --limit 50
  limacharlie audit list --event-type hive_set
  limacharlie audit list --sid 37270c5f-53b5-4215-b1ed-d4f60e818a7f
"""
register_explain("audit.list", _EXPLAIN_LIST)


@group.command("list")
@click.option(
    "--start", default=None, type=int,
    help="Start time (Unix seconds).  Defaults to 24 hours ago.",
)
@click.option(
    "--end", default=None, type=int,
    help="End time (Unix seconds).  Defaults to now.",
)
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option(
    "--event-type", "event_type", default=None,
    help="Server-side filter: only return events of this type (e.g. hive_set, send_task).",
)
@click.option(
    "--sid", default=None,
    help="Server-side filter: only return events relating to this sensor ID.",
)
@pass_context
def list_audit(ctx, start, end, limit, event_type, sid) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")

    now = int(time.time())
    if end is None:
        end = now
    if start is None:
        start = now - 86400  # 24 hours ago

    org = _get_org(ctx)
    data = list(org.get_audit_logs(
        start=start, end=end, limit=limit,
        event_type=event_type, sid=sid,
    ))
    _output(ctx, data)
