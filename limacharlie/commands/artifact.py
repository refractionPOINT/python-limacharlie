"""Artifact commands for LimaCharlie CLI v2.

Commands for listing and retrieving artifacts (uploaded logs and
files) stored in LimaCharlie Insight.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.artifacts import Artifacts
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List artifacts stored in Insight for the organization.  Artifacts are
uploaded log files and binary data associated with sensors or ingested
externally.

Use --sid to filter artifacts for a specific sensor.  Without filters,
all artifacts in the organization are listed.

The output includes artifact IDs, source info, and timestamps.
"""

_EXPLAIN_GET = """\
Get details of a specific artifact by its ID.  Returns the full
metadata for the artifact including source, upload time, retention,
and download URL.
"""

register_explain("artifact.list", _EXPLAIN_LIST)
register_explain("artifact.get", _EXPLAIN_GET)


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

@click.group("artifact")
def group():
    """Manage artifacts and uploaded logs.

    Artifacts are log files and binary data stored in LimaCharlie
    Insight.  They can be uploaded from sensors or ingested externally.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--sid", default=None, help="Filter by sensor ID.")
@click.option("--type", "artifact_type", default=None, help="Filter by artifact type.")
@click.option("--start", default=None, type=int, help="Start time (unix seconds).")
@click.option("--end", default=None, type=int, help="End time (unix seconds).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_artifacts(ctx, sid, artifact_type, start, end, limit):
    """List artifacts.

    Examples:
        limacharlie artifact list
        limacharlie artifact list --sid <SID>
        limacharlie artifact list --sid <SID> --output json
    """
    org = _get_org(ctx)
    artifacts = Artifacts(org)
    data = artifacts.list(sid=sid)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "artifact_id", required=True, help="Artifact ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, artifact_id):
    """Get artifact details by ID.

    Example:
        limacharlie artifact get --id <ARTIFACT_ID>
    """
    org = _get_org(ctx)
    artifacts = Artifacts(org)
    data = artifacts.get(artifact_id)
    _output(ctx, data)
