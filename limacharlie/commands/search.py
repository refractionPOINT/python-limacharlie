"""Search/LCQL commands for LimaCharlie CLI v2.

Commands for running and validating LCQL queries against historical
telemetry stored in LimaCharlie Insight.
"""

from __future__ import annotations

from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.search import Search
from ..sdk.hive import Hive, HiveRecord
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

@click.group("search")
def group() -> None:
    """Run and validate LCQL queries.

    LCQL (LimaCharlie Query Language) provides powerful search
    capabilities across historical events, detections, and audit logs.
    """


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

_EXPLAIN_RUN = """\
Execute an LCQL query against historical telemetry.  LCQL (LimaCharlie
Query Language) lets you search across events, detections, and audit
logs stored in Insight.

You must provide a time range via --start and --end (unix epoch
seconds).  Use --stream to specify the data stream ('event', 'detect',
'audit').  Use --limit to cap the number of results.

LCQL query syntax (the --query value corresponds to the filter and
projection portions of LCQL):

  Filter operators:
    ==, !=, contains, not contains, starts with, ends with,
    is, is not, matches (regex), <, >, <=, >=

  Logical operators:  and, or, not  (parentheses supported)

  Paths use slash notation:  event/FILE_PATH, routing/hostname,
    event/PARENT/FILE_PATH, event/EVENT/EventData/LogonType

  Projections (after a pipe |):
    event/FILE_PATH as path          - rename a field
    COUNT(event) as total            - count events
    COUNT_UNIQUE(routing/sid) as n   - count distinct values
    GROUP BY(field1 field2)          - group results

Example queries:
  "event/COMMAND_LINE contains 'powershell'"
  "event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT(event) as count GROUP BY(domain)"
  "event/EVENT/System/EventID == '4625'"

Streams:
  event   - sensor telemetry (NEW_PROCESS, DNS_REQUEST, etc.)
  detect  - D&R rule detections (has cat, detect, detect_id fields)
  audit   - platform management logs (has etype, msg, ident fields)

Examples:
  limacharlie search run --query "event_type == 'NEW_PROCESS'" \\
      --start 1700000000 --end 1700086400

  limacharlie search run --query "event/DOMAIN_NAME contains 'example'" \\
      --start 1700000000 --end 1700086400 --stream event --limit 100
"""
register_explain("search.run", _EXPLAIN_RUN)


@group.command()
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--stream", default=None, help="Stream type (event, detect, audit).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@pass_context
def run(ctx: click.Context, query: str, start: int, end: int, stream: str | None, limit: int | None) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    search = Search(org)
    results = list(search.execute(query, start, end, stream=stream, limit=limit))
    _output(ctx, results)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

_EXPLAIN_VALIDATE = """\
Validate LCQL query syntax without executing it.  Returns quickly
and does not consume billing credits.  Use this to check for syntax
errors before running expensive queries.

The query string follows LCQL filter syntax, e.g.:
  "event/COMMAND_LINE contains 'powershell'"
  "event/DOMAIN_NAME starts with 'evil'"

Example:
  limacharlie search validate --query "event_type == 'NEW_PROCESS'"
"""
register_explain("search.validate", _EXPLAIN_VALIDATE)


@group.command()
@click.option("--query", required=True, help="LCQL query string to validate.")
@pass_context
def validate(ctx: click.Context, query: str) -> None:
    org = _get_org(ctx)
    search = Search(org)
    data = search.validate(query)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# estimate
# ---------------------------------------------------------------------------

_EXPLAIN_ESTIMATE = """\
Estimate the billing cost of an LCQL query without executing it.
Validates the query and returns an approximate worst-case cost based
on the data volume that would be scanned over the time range.

Use this before running expensive queries to understand costs.
You must provide --start and --end (unix epoch seconds).

Example:
  limacharlie search estimate --query "event_type == 'NEW_PROCESS'" \\
      --start 1700000000 --end 1700086400
"""
register_explain("search.estimate", _EXPLAIN_ESTIMATE)


@group.command()
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--stream", default=None, help="Stream type (event, detect, audit).")
@pass_context
def estimate(ctx: click.Context, query: str, start: int, end: int, stream: str | None) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    search = Search(org)
    data = search.estimate(query, start, end, stream=stream)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# saved-list
# ---------------------------------------------------------------------------

_EXPLAIN_SAVED_LIST = """\
List all saved LCQL queries stored in the organization.  Saved
queries are stored in the 'query' hive and can be reused for
recurring analysis.

Each saved query contains:
  query   - the LCQL query string
  start   - default start time (unix seconds, optional)
  end     - default end time (unix seconds, optional)
  stream  - default stream type (optional)

Related: 'search saved-get' to see a specific query,
'search saved-create' to save a new query.
"""
register_explain("search.saved-list", _EXPLAIN_SAVED_LIST)


@group.command("saved-list")
@pass_context
def saved_list(ctx: click.Context) -> None:
    org = _get_org(ctx)
    hive = Hive(org, "query")
    records = hive.list()
    data = {name: rec.to_dict() for name, rec in records.items()}
    _output(ctx, data)


# ---------------------------------------------------------------------------
# saved-get
# ---------------------------------------------------------------------------

_EXPLAIN_SAVED_GET = """\
Get a specific saved query by name.  Returns the full query
definition including the LCQL expression, time range, and metadata.

Related: 'limacharlie search saved-list' to find query names,
'limacharlie search saved-run' to execute a saved query.
"""
register_explain("search.saved-get", _EXPLAIN_SAVED_GET)


@group.command("saved-get")
@click.option("--name", required=True, help="Name of the saved query.")
@pass_context
def saved_get(ctx: click.Context, name: str) -> None:
    org = _get_org(ctx)
    hive = Hive(org, "query")
    record = hive.get(name)
    _output(ctx, record.to_dict())


# ---------------------------------------------------------------------------
# saved-create
# ---------------------------------------------------------------------------

_EXPLAIN_SAVED_CREATE = """\
Create a new saved query in the organization.  The query is stored
in the 'query' hive and can be retrieved and executed later.

Provide the query name and LCQL expression.  Optionally include
default start/end times (unix seconds) and a stream type so the
query can be executed directly with 'search saved-run'.

The saved record structure:
  query:  "event/COMMAND_LINE contains 'powershell'"
  start:  1700000000     # optional
  end:    1700086400     # optional
  stream: event          # optional (event, detect, audit)

Related: 'search saved-list' to see existing queries,
'search saved-run' to execute a saved query.
"""
register_explain("search.saved-create", _EXPLAIN_SAVED_CREATE)


@group.command("saved-create")
@click.option("--name", required=True, help="Name for the saved query.")
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", default=None, type=int, help="Default start time (unix seconds).")
@click.option("--end", default=None, type=int, help="Default end time (unix seconds).")
@click.option("--stream", default=None, help="Default stream type (event, detect, audit).")
@pass_context
def saved_create(ctx: click.Context, name: str, query: str, start: int | None, end: int | None, stream: str | None) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
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

_EXPLAIN_SAVED_DELETE = """\
Delete a saved query by name.  This permanently removes the query
from the 'query' hive.

Related: 'limacharlie search saved-list' to find query names.
"""
register_explain("search.saved-delete", _EXPLAIN_SAVED_DELETE)


@group.command("saved-delete")
@click.option("--name", required=True, help="Name of the saved query to delete.")
@pass_context
def saved_delete(ctx: click.Context, name: str) -> None:
    org = _get_org(ctx)
    hive = Hive(org, "query")
    result = hive.delete(name)
    if not ctx.obj.quiet:
        click.echo(f"Saved query '{name}' deleted.")
    _output(ctx, result)


# ---------------------------------------------------------------------------
# saved-run
# ---------------------------------------------------------------------------

_EXPLAIN_SAVED_RUN = """\
Execute a previously saved query.  The query is retrieved from the
'query' hive and executed with its stored parameters.

The saved query must include 'start' and 'end' times.  If they are
missing, the command will error -- use 'search run' with explicit
--start/--end instead, or update the saved query to include times.

Use --limit to cap the number of results returned.

Related: 'search saved-list' to find query names,
'search saved-get' to inspect a query before running.
"""
register_explain("search.saved-run", _EXPLAIN_SAVED_RUN)


@group.command("saved-run")
@click.option("--name", required=True, help="Name of the saved query to execute.")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@pass_context
def saved_run(ctx: click.Context, name: str, limit: int | None) -> None:
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
