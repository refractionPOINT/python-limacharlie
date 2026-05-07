"""Detection commands for LimaCharlie CLI v2.

Commands for listing and retrieving historical detections from
LimaCharlie Insight.
"""

from __future__ import annotations

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

@click.group("detection")
def group() -> None:
    """Query historical detections.

    Detections are generated when D&R rules match against telemetry
    events.  Use these commands to search and retrieve detection
    records stored in the Insight data lake.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List historical detections for the organization.  Detections are
generated when D&R rules with a 'report' response action match
against telemetry events.  Requires Insight to be enabled.

You must provide a time range via --start and --end (unix epoch
seconds).  Use --cat to filter by detection category (the 'name'
field from the report action).  Use --limit to cap results.

Each detection record includes:
  cat          - detection name (from the report action's 'name')
  detect       - the event data that triggered the detection
  routing      - sensor routing info (sid, hostname, event_type, etc.)
  detect_mtd   - metadata from the report action (if any)
  priority     - priority level (if set in the report action)

Examples:
  limacharlie detection list --start 1700000000 --end 1700086400
  limacharlie detection list --start 1700000000 --end 1700086400 --cat lateral_movement --limit 50
"""
register_explain("detection.list", _EXPLAIN_LIST)


@group.command("list")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--cat", default=None, help="Filter by detection category.")
@click.option("--limit", default=None, type=int, help="Maximum number of detections.")
@pass_context
def list_detections(ctx: click.Context, start: int, end: int, cat: str | None, limit: int | None) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    detections = list(org.get_detections(start, end, limit=limit, category=cat))
    _output(ctx, detections)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

_EXPLAIN_GET = """\
Get a specific detection by its ID.  Returns the full detection
record including the detection category (cat), the triggering event
data (detect), sensor routing information (routing), and any
metadata (detect_mtd) from the rule's report action.

Detection IDs are returned by 'detection list' and are also present
in detection output streams and webhooks.

Example:
  limacharlie detection get --id <DETECTION_ID>
"""
register_explain("detection.get", _EXPLAIN_GET)


@group.command()
@click.option("--id", "detect_id", required=True, help="Detection ID.")
@pass_context
def get(ctx: click.Context, detect_id: str) -> None:
    org = _get_org(ctx)
    data = org.get_detection_by_id(detect_id)
    _output(ctx, data)
