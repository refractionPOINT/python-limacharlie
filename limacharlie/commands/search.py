"""Search/LCQL commands for LimaCharlie CLI v2.

Commands for running and validating LCQL queries against historical
telemetry stored in LimaCharlie Insight.

Search results from the API contain wrapper objects (SearchResult) with
metadata like searchResultId, type, nextToken, and stats.  For human-
readable table output, these wrappers are unwrapped: event rows are
flattened into a single table, facets and timeseries are shown as
separate tables, and a stats summary is printed to stderr.  Machine-
readable formats (json, yaml, csv, jsonl) pass through the raw API
response unchanged.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..config import get_config_value
from ..sdk.organization import Organization
from ..sdk.search import Search
from ..sdk.hive import Hive, HiveRecord
from ..output import format_output, format_table, detect_output_format
from ..discovery import register_explain
from ._time_validation import validate_epoch_seconds

# Default token expiry for search queries (hours). Search queries can run
# for a long time (especially over large time ranges), so we default to
# a longer-lived token than the standard ~1 hour JWT.
# Override via: --token-expiry CLI flag, or search_token_expiry_hours in
# the config file (~/.limacharlie).
DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS: float = 4.0

# Config file key for overriding the default search token expiry.
CONFIG_KEY_SEARCH_TOKEN_EXPIRY = "search_token_expiry_hours"


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


def _make_progress_fn(ctx: click.Context) -> Callable[[str], None] | None:
    """Return a stderr progress callback for interactive terminals.

    Returns None when output is non-interactive (piped/redirected) or
    when --quiet is set, so the SDK skips progress messages entirely.
    """
    if ctx.obj.quiet:
        return None
    if not sys.stderr.isatty():
        return None
    def _progress(msg: str) -> None:
        click.echo(click.style(msg, dim=True), err=True)
        sys.stderr.flush()
    return _progress


def _flatten_event_row(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a SearchResultRow into a single-level dict for table display.

    Merges metadata (mtd) fields and flattens the nested event data one
    level deep.  For example, ``{"routing": {"event_type": "X"}}`` becomes
    ``{"routing.event_type": "X"}``.  Deeper nesting is kept as-is (the
    table formatter will render it as ``{N keys}``).

    The ``mtd.ts`` field (millisecond epoch) is converted to a human-readable
    UTC timestamp.
    """
    flat: dict[str, Any] = {}

    # Metadata fields.
    mtd = row.get("mtd", {})
    ts = mtd.get("ts")
    if ts is not None:
        try:
            flat["time"] = datetime.fromtimestamp(
                ts / 1000, tz=timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError, OverflowError):
            flat["time"] = str(ts)
    stream = mtd.get("stream")
    if stream:
        flat["stream"] = stream

    # Flatten event data one level.
    data = row.get("data", {})
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat[f"{key}.{sub_key}"] = sub_value
            else:
                flat[key] = value
    else:
        flat["data"] = data

    return flat


def _unwrap_search_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate raw SearchResult objects into events, facets, and timeseries.

    Returns a dict with:
        events: list of flattened event row dicts
        facets: list of facet dicts
        timeseries: list of timeseries point dicts
        stats: the last non-empty stats dict (contains cumulative totals)
    """
    events: list[dict[str, Any]] = []
    facets: list[dict[str, Any]] = []
    timeseries: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}

    for result in results:
        result_type = result.get("type", "")

        if result_type == "events":
            # Only take stats from events results - other result types
            # (facets, timeline) have their own stats that don't include
            # event-level counters and would overwrite the real values.
            result_stats = result.get("stats")
            if result_stats:
                stats = result_stats
            for row in result.get("rows") or []:
                events.append(_flatten_event_row(row))
        elif result_type == "facets":
            facets.extend(result.get("facets") or [])
        elif result_type == "timeline":
            timeseries.extend(result.get("timeseries") or [])

    return {
        "events": events,
        "facets": facets,
        "timeseries": timeseries,
        "stats": stats,
    }


def _format_stats_summary(stats: dict[str, Any]) -> str:
    """Format search stats as a one-line summary for stderr.

    Prefers cumulative stats (aggregated across all pages by the server)
    when available, falling back to the page-level stats.
    """
    # Use cumulative stats if available (server-aggregated across pages).
    effective = stats.get("cumulativeStats") or stats

    parts: list[str] = []
    matched = effective.get("eventsMatched")
    scanned = effective.get("eventsScanned")
    if matched is not None:
        parts.append(f"matched: {matched:,}")
    if scanned is not None:
        parts.append(f"scanned: {scanned:,}")
    bytes_scanned = effective.get("bytesScanned")
    if bytes_scanned is not None:
        if bytes_scanned >= 1_073_741_824:
            parts.append(f"bytes: {bytes_scanned / 1_073_741_824:.1f} GB")
        elif bytes_scanned >= 1_048_576:
            parts.append(f"bytes: {bytes_scanned / 1_048_576:.1f} MB")
        else:
            parts.append(f"bytes: {bytes_scanned:,}")
    walltime = effective.get("walltime")
    if walltime is not None:
        parts.append(f"time: {walltime:.1f}s")
    price = effective.get("estimatedPrice", {})
    if isinstance(price, dict) and price.get("amount") is not None:
        parts.append(f"cost: ${price['amount']:.4f}")
    return ", ".join(parts)


def _format_expanded_events(results: list[dict[str, Any]]) -> str:
    """Format events as individual JSON blocks separated by dividers.

    Each event is printed as pretty-printed JSON with a timestamp header,
    separated by a horizontal rule.  Useful for investigating individual
    events in detail.
    """
    parts: list[str] = []
    for result in results:
        if result.get("type") != "events":
            continue
        for row in result.get("rows") or []:
            mtd = row.get("mtd", {})
            ts = mtd.get("ts")
            header_parts: list[str] = []
            if ts is not None:
                try:
                    header_parts.append(
                        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    )
                except (OSError, ValueError, OverflowError):
                    header_parts.append(str(ts))
            stream = mtd.get("stream")
            if stream:
                header_parts.append(stream)
            data = row.get("data", {})
            # Try to get event type for the header.
            if isinstance(data, dict):
                etype = (
                    data.get("routing", {}).get("event_type")
                    or data.get("cat")
                    or data.get("etype")
                )
                if etype:
                    header_parts.append(etype)

            header = " | ".join(header_parts) if header_parts else "event"
            parts.append(f"--- {header} ---")
            parts.append(json.dumps(data, indent=2, default=str))
    return "\n".join(parts)


def _output_search_results(
    ctx: click.Context,
    results: list[dict[str, Any]],
    raw: bool = False,
    expand: bool = False,
) -> None:
    """Output search results with smart formatting for table mode.

    For table output: unwraps the SearchResult wrappers and displays
    events as a flat table.  Progress and stats go to stderr so stdout
    can be redirected cleanly (e.g., ``limacharlie search run ... > out.txt``).

    For --expand: prints each event as a pretty-printed JSON block with
    a header showing timestamp, stream, and event type.

    For machine-readable formats (json, yaml, csv, jsonl): passes the
    raw API results through unchanged.

    Args:
        ctx: Click context with output settings.
        results: Raw list of SearchResult dicts from the API.
        raw: If True, skip unwrapping even in table mode.
        expand: If True, show each event as a full JSON block.
    """
    if ctx.obj.quiet:
        return

    fmt = ctx.obj.output_format or detect_output_format()

    # Machine-readable formats get raw output.
    if fmt != "table" or raw:
        click.echo(format_output(results, fmt))
        return

    # Expand mode: each event as a full JSON block.
    if expand:
        output = _format_expanded_events(results)
        if output:
            click.echo(output)
        else:
            click.echo("No events")
        _print_stats_summary(results)
        return

    unwrapped = _unwrap_search_results(results)

    # Events table.
    events = unwrapped["events"]
    if events:
        display = events if ctx.obj.wide else _limit_event_columns(events)
        click.echo(format_table(display))
        click.echo(click.style(f"({len(events):,} event{'s' if len(events) != 1 else ''})", dim=True), err=True)
    else:
        click.echo("No events")

    # Stats summary to stderr (not stdout, so redirects stay clean).
    stats = unwrapped["stats"]
    if stats:
        summary = _format_stats_summary(stats)
        if summary:
            click.echo(click.style(f"Stats: {summary}", dim=True), err=True)
            sys.stderr.flush()


def _print_stats_summary(results: list[dict[str, Any]]) -> None:
    """Extract and print stats summary from raw results to stderr."""
    for result in reversed(results):
        if result.get("type") == "events":
            stats = result.get("stats")
            if stats:
                summary = _format_stats_summary(stats)
                if summary:
                    click.echo(click.style(f"Stats: {summary}", dim=True), err=True)
                    sys.stderr.flush()
                return


# Maximum number of columns to display in the events table.  The table
# formatter already drops columns that exceed terminal width, but with
# deeply nested events (e.g., 20+ routing.* fields) the output is still
# noisy.  This cap is applied before the table formatter so that only
# the most useful columns are shown.  Use --output json for full data.
_MAX_EVENT_COLUMNS = 15

# Columns to always show first (in order) when present.
_PRIORITY_COLUMNS = [
    "time",
    "stream",
    "routing.event_type",
    "cat",
    "etype",
    "routing.hostname",
]

# Columns to drop from table output - these are low-value routing
# metadata or duplicates that add noise without helping the user
# understand the event.
_DROP_COLUMNS = frozenset({
    # Duplicate of "time" (from mtd.ts).
    "ts",
    # Routing metadata - low-value for interactive display.
    "routing.oid",
    "routing.iid",
    "routing.plat",
    "routing.arch",
    "routing.tags",
    "routing.ext_ip",
    "routing.int_ip",
    "routing.sid",
    "routing.event_id",
    "routing.event_time",
    "routing.this",
    "routing.parent",
    "routing.investigate_id",
    "routing.moduleid",
})


def _limit_event_columns(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select the most useful columns for table display.

    Priority order:
        1. Columns in _PRIORITY_COLUMNS (always shown first if present)
        2. Non-routing event data columns (event.*, or flat projection fields)
        3. Remaining routing.* columns not in _DROP_COLUMNS

    Caps total columns at _MAX_EVENT_COLUMNS.  For projection queries
    (flat data, no routing.* prefix), all columns pass through since
    the user explicitly selected them.
    """
    # Collect all unique keys preserving first-seen order.
    all_keys: list[str] = []
    seen: set[str] = set()
    for row in events:
        for k in row:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    # If few enough columns, pass through unchanged.
    if len(all_keys) <= _MAX_EVENT_COLUMNS:
        return events

    # Build ordered selection.
    selected: list[str] = []
    used: set[str] = set()

    # 1. Priority columns.
    for col in _PRIORITY_COLUMNS:
        if col in seen and col not in used:
            selected.append(col)
            used.add(col)

    # 2. Non-routing, non-drop columns (event data, flat projection fields).
    for col in all_keys:
        if col not in used and col not in _DROP_COLUMNS:
            if not col.startswith("routing."):
                selected.append(col)
                used.add(col)

    # 3. Remaining routing columns not dropped.
    for col in all_keys:
        if col not in used and col not in _DROP_COLUMNS:
            selected.append(col)
            used.add(col)

    # Cap at max.
    selected = selected[:_MAX_EVENT_COLUMNS]
    selected_set = set(selected)

    return [{k: row[k] for k in selected if k in row} for row in events]


def _resolve_token_expiry(cli_value: float | None, environment: str | None = None) -> float:
    """Resolve the effective token expiry for a search operation.

    Priority (highest first):
        1. Explicit --token-expiry CLI flag
        2. ``search_token_expiry_hours`` in the config file
        3. ``DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS`` constant

    Args:
        cli_value: Value from --token-expiry, or None if not provided.
        environment: Active named environment (for config lookup).

    Returns:
        Token expiry in hours (always > 0).
    """
    if cli_value is not None:
        return cli_value

    config_value = get_config_value(
        CONFIG_KEY_SEARCH_TOKEN_EXPIRY,
        default=None,
        environment=environment,
    )
    if config_value is not None:
        try:
            val = float(config_value)
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass

    return DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS


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

LCQL query format:

  The --query value is a full LCQL query string.  LCQL uses a
  pipe-separated format:

    [SENSOR_SELECTOR] | [EVENT_TYPES] | FILTER [| PROJECTION]

  The time range is provided separately via --start/--end (any time
  range already in the query is overridden).

  Sensor selector (optional, defaults to all sensors):
    plat == windows
    plat == linux and hostname matches '^web-'

  Event types (optional, defaults to all):
    NEW_PROCESS DNS_REQUEST          - space-separated list
    *                                - all event types

  Filter operators:
    ==, !=, contains, not contains, starts with, not starts with,
    ends with, not ends with, is, is not, matches (regex),
    not matches, <, >, cidr, exists

  Logical operators:  and, or, not  (parentheses supported)

  Paths use slash or dot notation:  event/FILE_PATH, routing/hostname,
    event/PARENT/FILE_PATH, event/EVENT/EventData/LogonType

  Projections (after a pipe |):
    event/FILE_PATH as path          - rename a field
    COUNT(event) as total            - count events
    COUNT_UNIQUE(routing/sid) as n   - count distinct values
    GROUP BY(field1 field2)          - group results
    ORDER BY(field ASC)              - sort results
    LIMIT n                          - cap results

Example queries:
  "* | NEW_PROCESS | event/COMMAND_LINE contains 'powershell'"
  "plat == windows | DNS_REQUEST | event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT(event) as count GROUP BY(domain)"
  "plat == windows | WEL | event/EVENT/System/EventID == '4625'"

Streams:
  event   - sensor telemetry (NEW_PROCESS, DNS_REQUEST, etc.)
  detect  - D&R rule detections (has cat, detect, detect_id fields)
  audit   - platform management logs (has etype, msg, ident fields)

Examples:
  limacharlie search run \\
      --query "* | NEW_PROCESS | event/COMMAND_LINE contains 'powershell'" \\
      --start 1700000000 --end 1700086400

  limacharlie search run \\
      --query "plat == windows | DNS_REQUEST | event/DOMAIN_NAME contains 'example'" \\
      --start 1700000000 --end 1700086400 --stream event --limit 100

  # Override the default 4-hour token with an 8-hour token
  limacharlie search run \\
      --query "plat == windows | WEL | event/EVENT/System/EventID == '4625'" \\
      --start 1700000000 --end 1700086400 --token-expiry 8

Token expiry defaults to 4 hours to avoid mid-query JWT expiry on
long-running searches.  Override with --token-expiry or set
'search_token_expiry_hours' in ~/.limacharlie.

IMPORTANT: Do not write LCQL queries from scratch. Use
'limacharlie ai generate-query --prompt "<description>"' to generate
a query from a natural language description, then pass the result to
this command.
"""
register_explain("search.run", _EXPLAIN_RUN)


@group.command()
@click.option("--query", required=True, help="LCQL query string.")
@click.option("--start", required=True, type=int, help="Start time (unix seconds).")
@click.option("--end", required=True, type=int, help="End time (unix seconds).")
@click.option("--stream", default=None, help="Stream type (event, detect, audit).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option(
    "--token-expiry", default=None, type=float,
    help=f"JWT token validity in hours (default: {DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS}). "
         "Override the default via config key 'search_token_expiry_hours'.",
)
@click.option("--raw", is_flag=True, default=False, help="Show raw API result objects without unwrapping.")
@click.option("--expand", is_flag=True, default=False, help="Show each event as a full pretty-printed JSON block.")
@pass_context
def run(ctx: click.Context, query: str, start: int, end: int, stream: str | None,
        limit: int | None, token_expiry: float | None, raw: bool, expand: bool) -> None:
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    effective_expiry = _resolve_token_expiry(token_expiry, environment=ctx.obj.environment)
    if effective_expiry > 24:
        click.echo(
            f"Warning: generating a token valid for {effective_expiry} hours. "
            "Long-lived tokens increase security exposure if leaked.",
            err=True,
        )
    org.client.get_jwt(expiry_hours=effective_expiry)
    search = Search(org)
    progress_fn = _make_progress_fn(ctx)
    try:
        results = list(search.execute(query, start, end, stream=stream, limit=limit, progress_fn=progress_fn))
    except KeyboardInterrupt:
        click.echo("\nSearch canceled.", err=True)
        sys.stderr.flush()
        ctx.exit(130)
        return
    _output_search_results(ctx, results, raw=raw, expand=expand)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

_EXPLAIN_VALIDATE = """\
Validate LCQL query syntax without executing it.  Returns quickly
and does not consume billing credits.  Use this to check for syntax
errors before running expensive queries.

The query string follows LCQL syntax (see 'search run --explain'), e.g.:
  "* | NEW_PROCESS | event/COMMAND_LINE contains 'powershell'"
  "plat == windows | DNS_REQUEST | event/DOMAIN_NAME starts with 'evil'"

Example:
  limacharlie search validate \\
      --query "* | NEW_PROCESS | event/COMMAND_LINE contains 'powershell'"

IMPORTANT: Do not write LCQL queries from scratch. Use
'limacharlie ai generate-query --prompt "<description>"' to generate
the query, then validate it with this command.
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
  limacharlie search estimate \\
      --query "* | NEW_PROCESS | event/COMMAND_LINE contains 'powershell'" \\
      --start 1700000000 --end 1700086400

IMPORTANT: Do not write LCQL queries from scratch. Use
'limacharlie ai generate-query --prompt "<description>"' to generate
the query, then estimate its cost with this command.
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

IMPORTANT: Do not write LCQL queries from scratch. Use
'limacharlie ai generate-query --prompt "<description>"' to generate
the query expression, then save it with this command.
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
@click.option(
    "--token-expiry", default=None, type=float,
    help=f"JWT token validity in hours (default: {DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS}). "
         "Override the default via config key 'search_token_expiry_hours'.",
)
@click.option("--raw", is_flag=True, default=False, help="Show raw API result objects without unwrapping.")
@click.option("--expand", is_flag=True, default=False, help="Show each event as a full pretty-printed JSON block.")
@pass_context
def saved_run(ctx: click.Context, name: str, limit: int | None, token_expiry: float | None, raw: bool, expand: bool) -> None:
    org = _get_org(ctx)

    effective_expiry = _resolve_token_expiry(token_expiry, environment=ctx.obj.environment)
    if effective_expiry > 24:
        click.echo(
            f"Warning: generating a token valid for {effective_expiry} hours. "
            "Long-lived tokens increase security exposure if leaked.",
            err=True,
        )
    org.client.get_jwt(expiry_hours=effective_expiry)

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
    progress_fn = _make_progress_fn(ctx)
    try:
        results = list(search.execute(query_str, start_time, end_time, stream=stream, limit=limit, progress_fn=progress_fn))
    except KeyboardInterrupt:
        click.echo("\nSearch canceled.", err=True)
        sys.stderr.flush()
        ctx.exit(130)
        return
    _output_search_results(ctx, results, raw=raw, expand=expand)
