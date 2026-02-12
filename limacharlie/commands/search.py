"""Search/LCQL commands for LimaCharlie CLI v2.

Commands for running and validating LCQL queries against historical
telemetry stored in LimaCharlie Insight.
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.search import Search
from ..sdk.hive import Hive, HiveRecord
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

_EXPLAIN_ESTIMATE = """\
Estimate the billing cost of an LCQL query without executing it.
This is a lightweight check that validates the query and returns
an estimate of the data that would be scanned and the cost.

You must provide --start and --end (unix epoch seconds) to define
the time range for the estimate.

Example:
  limacharlie search estimate --query "event_type == 'NEW_PROCESS'" \\
      --start 1700000000 --end 1700086400
"""

_EXPLAIN_SAVED_LIST = """\
List all saved LCQL queries stored in the organization.  Saved
queries are stored in the 'query' hive and can be reused for
recurring analysis.

Related: 'limacharlie search saved-get' to see a specific query,
'limacharlie search saved-create' to save a new query.
"""

_EXPLAIN_SAVED_GET = """\
Get a specific saved query by name.  Returns the full query
definition including the LCQL expression, time range, and metadata.

Related: 'limacharlie search saved-list' to find query names,
'limacharlie search saved-run' to execute a saved query.
"""

_EXPLAIN_SAVED_CREATE = """\
Create a new saved query in the organization.  The query is stored
in the 'query' hive and can be retrieved and executed later.

Provide the query name, LCQL expression, and optionally start/end
times.

Related: 'limacharlie search saved-list' to see existing queries,
'limacharlie search saved-run' to execute a saved query.
"""

_EXPLAIN_SAVED_DELETE = """\
Delete a saved query by name.  This permanently removes the query
from the 'query' hive.

Related: 'limacharlie search saved-list' to find query names.
"""

_EXPLAIN_SAVED_RUN = """\
Execute a previously saved query.  The query is retrieved from the
'query' hive and executed with its stored parameters.

If the saved query includes start/end times, those are used.
Otherwise, you may need to override them via the query definition.

Related: 'limacharlie search saved-list' to find query names,
'limacharlie search saved-get' to inspect a query before running.
"""

register_explain("search.run", _EXPLAIN_RUN)
register_explain("search.validate", _EXPLAIN_VALIDATE)
register_explain("search.estimate", _EXPLAIN_ESTIMATE)
register_explain("search.saved-list", _EXPLAIN_SAVED_LIST)
register_explain("search.saved-get", _EXPLAIN_SAVED_GET)
register_explain("search.saved-create", _EXPLAIN_SAVED_CREATE)
register_explain("search.saved-delete", _EXPLAIN_SAVED_DELETE)
register_explain("search.saved-run", _EXPLAIN_SAVED_RUN)


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


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("search")
def group() -> None:
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
def run(ctx: click.Context, query: str, start: int, end: int, stream: str | None, limit: int | None) -> None:
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
def validate(ctx: click.Context, query: str) -> None:
    """Validate LCQL query syntax.

    Example:
        limacharlie search validate --query "event_type == 'NEW_PROCESS'"
    """
    org = _get_org(ctx)
    search = Search(org)
    data = search.validate(query)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# estimate
# ---------------------------------------------------------------------------

@group.command()
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--stream", default=None, help="Stream type (event, detect, audit).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_ESTIMATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def estimate(ctx: click.Context, query: str, start: int, end: int, stream: str | None) -> None:
    """Estimate billing cost for an LCQL query.

    Example:
        limacharlie search estimate --query "event_type == 'NEW_PROCESS'" \\
            --start 1700000000 --end 1700086400
    """
    org = _get_org(ctx)
    search = Search(org)
    data = search.estimate(query, start, end, stream=stream)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# saved-list
# ---------------------------------------------------------------------------

@group.command("saved-list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SAVED_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def saved_list(ctx: click.Context) -> None:
    """List saved LCQL queries.

    Example:
        limacharlie search saved-list
    """
    org = _get_org(ctx)
    hive = Hive(org, "query")
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    _output(ctx, data)


# ---------------------------------------------------------------------------
# saved-get
# ---------------------------------------------------------------------------

@group.command("saved-get")
@click.option("--name", required=True, help="Name of the saved query.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SAVED_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def saved_get(ctx: click.Context, name: str) -> None:
    """Get a saved query by name.

    Example:
        limacharlie search saved-get --name my-query
    """
    org = _get_org(ctx)
    hive = Hive(org, "query")
    record = hive.get(name)
    _output(ctx, record.to_dict())


# ---------------------------------------------------------------------------
# saved-create
# ---------------------------------------------------------------------------

@group.command("saved-create")
@click.option("--name", required=True, help="Name for the saved query.")
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", default=None, type=int, help="Default start time (unix seconds).")
@click.option("--end", default=None, type=int, help="Default end time (unix seconds).")
@click.option("--stream", default=None, help="Default stream type (event, detect, audit).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SAVED_CREATE),
    help="Show detailed explanation of this command.",
)
@pass_context
def saved_create(ctx: click.Context, name: str, query: str, start: int | None, end: int | None, stream: str | None) -> None:
    """Create a saved query.

    Examples:
        limacharlie search saved-create --name my-query \\
            --query "event_type == 'NEW_PROCESS'"

        limacharlie search saved-create --name daily-check \\
            --query "event_type == 'DNS_REQUEST'" \\
            --start 1700000000 --end 1700086400 --stream event
    """
    org = _get_org(ctx)
    hive = Hive(org, "query")

    query_data = {"query": query}
    if start is not None:
        query_data["start"] = start
    if end is not None:
        query_data["end"] = end
    if stream is not None:
        query_data["stream"] = stream

    record = HiveRecord(name, data=query_data)
    result = hive.set(record)
    if not ctx.obj.quiet:
        click.echo(f"Saved query '{name}' created.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# saved-delete
# ---------------------------------------------------------------------------

@group.command("saved-delete")
@click.option("--name", required=True, help="Name of the saved query to delete.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SAVED_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def saved_delete(ctx: click.Context, name: str) -> None:
    """Delete a saved query.

    Example:
        limacharlie search saved-delete --name my-query
    """
    org = _get_org(ctx)
    hive = Hive(org, "query")
    result = hive.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Saved query '{name}' deleted.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# saved-run
# ---------------------------------------------------------------------------

@group.command("saved-run")
@click.option("--name", required=True, help="Name of the saved query to execute.")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_SAVED_RUN),
    help="Show detailed explanation of this command.",
)
@pass_context
def saved_run(ctx: click.Context, name: str, limit: int | None) -> None:
    """Execute a saved query.

    Retrieves the query from the 'query' hive and executes it.

    Example:
        limacharlie search saved-run --name my-query
        limacharlie search saved-run --name daily-check --limit 100
    """
    org = _get_org(ctx)
    hive = Hive(org, "query")
    record = hive.get(name)
    query_data = record.data

    query_str = query_data.get("query")
    if not query_str:
        click.echo(
            "Error: Saved query does not contain a 'query' field.",
            err=True,
        )
        ctx.exit(4)
        return

    start_time = query_data.get("start")
    end_time = query_data.get("end")
    if start_time is None or end_time is None:
        click.echo(
            "Error: Saved query does not contain 'start' and 'end' time fields.\n"
            "Suggestion: Update the saved query with start/end times, or use "
            "'limacharlie search run' with explicit --start and --end.",
            err=True,
        )
        ctx.exit(4)
        return

    stream = query_data.get("stream")
    search = Search(org)
    results = list(search.execute(query_str, start_time, end_time, stream=stream, limit=limit))
    _output(ctx, results)
