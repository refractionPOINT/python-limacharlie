"""Search/LCQL commands for LimaCharlie CLI v2.

Commands for running and validating LCQL queries against historical
telemetry stored in LimaCharlie Insight.
"""

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.search import Search
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_RUN = """\
Execute an LCQL query against historical telemetry.  LCQL (LimaCharlie
Query Language) lets you search across events, detections, and audit
logs stored in Insight.

You must provide a time range via --start and --end (unix epoch
seconds).  Use --stream to specify the data stream ('event', 'detect',
'audit').  Use --limit to cap the number of results.

The query is executed asynchronously and results are streamed back
as they become available.

Examples:
  limacharlie search run --query "event_type == 'NEW_PROCESS'" \\
      --start 1700000000 --end 1700086400

  limacharlie search run --query "detect.cat == 'lateral_movement'" \\
      --start 1700000000 --end 1700086400 --stream detect --limit 100
"""

_EXPLAIN_VALIDATE = """\
Validate LCQL query syntax without executing it.  This is a
lightweight check that returns quickly and does not consume any
billing credits.  Use this to test queries before running them.

Example:
  limacharlie search validate --query "event_type == 'NEW_PROCESS'"
"""

register_explain("search.run", _EXPLAIN_RUN)
register_explain("search.validate", _EXPLAIN_VALIDATE)


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

@click.group("search")
def group():
    """Run and validate LCQL queries.

    LCQL (LimaCharlie Query Language) provides powerful search
    capabilities across historical events, detections, and audit logs.
    """


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@group.command()
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--stream", default=None, help="Stream type (event, detect, audit).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_RUN),
    help="Show detailed explanation of this command.",
)
@pass_context
def run(ctx, query, start, end, stream, limit):
    """Execute an LCQL query.

    Examples:
        limacharlie search run --query "event_type == 'NEW_PROCESS'" \\
            --start 1700000000 --end 1700086400

        limacharlie search run --query "detect.cat == 'lateral_movement'" \\
            --start 1700000000 --end 1700086400 --stream detect --limit 100
    """
    org = _get_org(ctx)
    search = Search(org)
    results = list(search.execute(query, start, end, stream=stream, limit=limit))
    _output(ctx, results)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@group.command()
@click.option("--query", required=True, help="LCQL query string to validate.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_VALIDATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def validate(ctx, query):
    """Validate LCQL query syntax.

    Example:
        limacharlie search validate --query "event_type == 'NEW_PROCESS'"
    """
    org = _get_org(ctx)
    search = Search(org)
    data = search.validate(query)
    _output(ctx, data)
