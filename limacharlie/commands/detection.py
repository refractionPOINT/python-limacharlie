"""Detection commands for LimaCharlie CLI v2.

Commands for listing and retrieving historical detections from
LimaCharlie Insight.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List historical detections for the organization.  Detections are
generated when D&R rules match against telemetry events.

You must provide a time range via --start and --end (unix epoch
seconds).  Use --cat to filter by detection category (e.g.,
'lateral_movement', 'exfiltration').  Use --limit to cap results.

Examples:
  limacharlie detection list --start 1700000000 --end 1700086400
  limacharlie detection list --start 1700000000 --end 1700086400 \\
      --cat lateral_movement --limit 50
"""

_EXPLAIN_GET = """\
Get a specific detection by its ID.  Returns the full detection
record including the matched rule, detection category, sensor
information, and the triggering event data.

Example:
  limacharlie detection get --id <DETECTION_ID>
"""

register_explain("detection.list", _EXPLAIN_LIST)
register_explain("detection.get", _EXPLAIN_GET)


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

@click.group("detection")
def group():
    """Query historical detections.

    Detections are generated when D&R rules match against telemetry
    events.  Use these commands to search and retrieve detection
    records stored in the Insight data lake.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--cat", default=None, help="Filter by detection category.")
@click.option("--limit", default=None, type=int, help="Maximum number of detections.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_detections(ctx, start, end, cat, limit):
    """List detections.

    Examples:
        limacharlie detection list --start 1700000000 --end 1700086400
        limacharlie detection list --start 1700000000 --end 1700086400 \\
            --cat lateral_movement --limit 50
    """
    org = _get_org(ctx)
    detections = list(org.get_detections(start, end, limit=limit, category=cat))
    _output(ctx, detections)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "detect_id", required=True, help="Detection ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, detect_id):
    """Get a detection by ID.

    Example:
        limacharlie detection get --id <DETECTION_ID>
    """
    org = _get_org(ctx)
    data = org.get_detection_by_id(detect_id)
    _output(ctx, data)
