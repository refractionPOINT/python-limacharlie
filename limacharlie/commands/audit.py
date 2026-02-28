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
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment)
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
  ts         - Timestamp of the action
  who        - Email or API key hash of the actor
  action     - Action performed (e.g. dr.set, sensor.del)
  target     - Resource affected
  details    - Action-specific context

Time range is specified with --start and --end as Unix timestamps
in seconds.  If not provided, defaults to the last 24 hours.

Use --limit to cap the number of results returned.

Examples:
  limacharlie audit list
  limacharlie audit list --start 1700000000 --end 1700100000
  limacharlie audit list --limit 50
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
@pass_context
def list_audit(ctx, start, end, limit) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")

    now = int(time.time())
    if end is None:
        end = now
    if start is None:
        start = now - 86400  # 24 hours ago

    org = _get_org(ctx)
    data = list(org.get_audit_logs(start=start, end=end, limit=limit))
    _output(ctx, data)
