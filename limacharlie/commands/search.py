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
import os
import shlex
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import click

from ..search_checkpoint import (
    CheckpointReader,
    CheckpointResumer,
    CheckpointWriter,
    list_checkpoints,
)
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
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
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


def _print_checkpoint_cancel(
    checkpoint_path: str,
    pages: int,
    result_count: int,
    total_events: int,
    last_token: str | None,
) -> None:
    """Print a detailed cancel message when a checkpointed search is interrupted.

    Shows session stats and the exact command to resume.
    """
    lines = [
        "",
        f"Search canceled. Checkpoint saved: {checkpoint_path}",
        f"  Pages fetched:  {pages}",
        f"  Results:        {result_count}",
        f"  Total events:   {total_events:,}",
    ]
    if last_token:
        lines.append(f"  Resume token:   {last_token}")
    else:
        lines.append("  Resume token:   (none - will re-fetch from start)")
    lines.append("")
    lines.append(f"  Resume with:    limacharlie search run --resume --checkpoint {checkpoint_path}")
    click.echo("\n".join(lines), err=True)
    sys.stderr.flush()


def _build_fresh_query_cmd(meta: dict[str, Any], checkpoint_path: str) -> str:
    """Build a CLI command string to re-run a checkpoint's query from scratch.

    Used when a resume fails because the pagination token has expired
    (server-side TTL is roughly 8 hours).

    Args:
        meta: Checkpoint metadata dict.
        checkpoint_path: Path to the checkpoint data file.

    Returns:
        A shell command string the user can copy-paste.
    """
    parts = ["limacharlie search run"]
    parts.append(f"--query {shlex.quote(meta.get('query', ''))}")
    parts.append(f"--start {meta.get('start_time', '')}")
    parts.append(f"--end {meta.get('end_time', '')}")
    if meta.get("stream"):
        parts.append(f"--stream {shlex.quote(str(meta['stream']))}")
    if meta.get("limit"):
        parts.append(f"--limit {meta['limit']}")
    parts.append(f"--checkpoint {shlex.quote(checkpoint_path)}")
    parts.append("--force")
    return " \\\n    ".join(parts)


# Keywords in SearchError messages that indicate an expired pagination
# token or query results that have been garbage-collected on the server.
# These are checked against SearchError only (not auth errors).
# Deliberately narrow to avoid false positives - "expired" alone would
# match JWT expiry errors wrapped in SearchError.
_TOKEN_EXPIRED_KEYWORDS = (
    "query not found",
    "results not found",
    "no longer available",
    "query does not exist",
    "invalid token",
    "unknown query",
    "token expired",
    "results expired",
)


def _is_token_expired_error(exc: Exception) -> bool:
    """Check if an exception indicates the server rejected a pagination token.

    This typically means the token is malformed, corrupt, or the server
    cannot process it. Used as a safety net during resume to provide a
    helpful error message with the command to re-run from scratch.

    NOT triggered for auth errors (401/403) - those are credential
    issues, not token problems.

    Args:
        exc: The exception from the search execution.

    Returns:
        True if the error likely indicates expired results/token.
    """
    from ..errors import (
        AuthenticationError,
        NotFoundError,
        PermissionDeniedError,
        RateLimitError,
        SearchError,
    )

    # Auth/permission/rate-limit errors are never token expiry.
    if isinstance(exc, (AuthenticationError, PermissionDeniedError, RateLimitError)):
        return False

    # 404 on the poll request strongly suggests the query/token expired.
    if isinstance(exc, NotFoundError):
        return True

    # Only check SearchError messages (not all exception types) to avoid
    # false positives from unrelated errors that happen to contain keywords.
    if isinstance(exc, SearchError):
        msg = str(exc).lower()
        return any(kw in msg for kw in _TOKEN_EXPIRED_KEYWORDS)

    return False


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

    Note: requires the full results list in memory. Table formatting
    needs all rows upfront to compute column widths. For large result
    sets, use ``--output jsonl`` which streams via
    ``CheckpointReader.iter_results()`` in the checkpoint-show path.

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

Checkpoint/Resume:
  Use --checkpoint to incrementally save results to a JSONL file.
  If the search is interrupted (Ctrl+C, network error), the checkpoint
  preserves all results fetched so far.  Use --resume --checkpoint
  to pick up where you left off.

  # Start with checkpointing
  limacharlie search run \\
      --query "..." --start X --end Y --checkpoint /tmp/search.jsonl

  # Resume after interruption
  limacharlie search run --resume --checkpoint /tmp/search.jsonl

  Resume uses the stored pagination token to skip directly to the
  next un-fetched page on the server.  The server re-runs the query
  from the cursor position embedded in the token, so resume works
  even after long delays between sessions.

  The --query, --start, --end, and --stream flags are incompatible
  with --resume (query parameters are loaded from the checkpoint).

IMPORTANT: Do not write LCQL queries from scratch. Use
'limacharlie ai generate-query --prompt "<description>"' to generate
a query from a natural language description, then pass the result to
this command.
"""
register_explain("search.run", _EXPLAIN_RUN)


@group.command()
@click.option("--query", default=None, help="LCQL query string.")
@click.option("--start", default=None, type=int, help="Start time (unix seconds).")
@click.option("--end", default=None, type=int, help="End time (unix seconds).")
@click.option("--stream", default=None, help="Stream type (event, detect, audit).")
@click.option("--limit", default=None, type=int, help="Maximum number of results.")
@click.option(
    "--token-expiry", default=None, type=float,
    help=f"JWT token validity in hours (default: {DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS}). "
         "Override the default via config key 'search_token_expiry_hours'.",
)
@click.option("--raw", is_flag=True, default=False, help="Show raw API result objects without unwrapping.")
@click.option("--expand", is_flag=True, default=False, help="Show each event as a full pretty-printed JSON block.")
@click.option("--checkpoint", "checkpoint_path", default=None, type=click.Path(),
              help="Write results incrementally to JSONL file at this path.")
@click.option("--resume", is_flag=True, default=False,
              help="Resume from existing checkpoint (requires --checkpoint).")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing checkpoint data file (use with --checkpoint).")
@pass_context
def run(ctx: click.Context, query: str | None, start: int | None, end: int | None,
        stream: str | None, limit: int | None, token_expiry: float | None,
        raw: bool, expand: bool, checkpoint_path: str | None, resume: bool,
        force: bool) -> None:
    # --- Validate flag combinations ---
    if resume:
        if not checkpoint_path:
            click.echo("Error: --resume requires --checkpoint.", err=True)
            ctx.exit(4)
            return
        # These flags are incompatible with --resume because overriding
        # them would produce inconsistent results (data file has results
        # from original query, new results would come from different query).
        forbidden = []
        if query is not None:
            forbidden.append("--query")
        if start is not None:
            forbidden.append("--start")
        if end is not None:
            forbidden.append("--end")
        if stream is not None:
            forbidden.append("--stream")
        if forbidden:
            click.echo(
                f"Error: {', '.join(forbidden)} cannot be used with --resume. "
                "Query parameters are loaded from the checkpoint.",
                err=True,
            )
            ctx.exit(4)
            return
    else:
        # Normal mode: query, start, end are required.
        if not query:
            click.echo("Error: --query is required (unless using --resume).", err=True)
            ctx.exit(4)
            return
        if start is None:
            click.echo("Error: --start is required (unless using --resume).", err=True)
            ctx.exit(4)
            return
        if end is None:
            click.echo("Error: --end is required (unless using --resume).", err=True)
            ctx.exit(4)
            return

    if resume:
        _run_resume(ctx, checkpoint_path, limit, token_expiry, raw, expand)
    elif checkpoint_path:
        _run_with_checkpoint(ctx, query, start, end, stream, limit,
                             token_expiry, raw, expand, checkpoint_path, force)
    else:
        _run_normal(ctx, query, start, end, stream, limit,
                    token_expiry, raw, expand)


def _run_normal(
    ctx: click.Context, query: str, start: int, end: int,
    stream: str | None, limit: int | None, token_expiry: float | None,
    raw: bool, expand: bool,
) -> None:
    """Execute a search without checkpointing."""
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


def _run_with_checkpoint(
    ctx: click.Context, query: str, start: int, end: int,
    stream: str | None, limit: int | None, token_expiry: float | None,
    raw: bool, expand: bool, checkpoint_path: str, force: bool = False,
) -> None:
    """Execute a search with checkpoint persistence."""
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    debug_fn = ctx.obj.debug_fn
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

    if debug_fn:
        debug_fn(f"Checkpoint: creating data file at {checkpoint_path} (force={force})")

    try:
        writer = CheckpointWriter(
            data_path=checkpoint_path,
            query=query,
            start_time=start,
            end_time=end,
            stream=stream,
            limit=limit,
            oid=org.oid,
            force=force,
        )
    except FileExistsError:
        # Give a context-aware message based on checkpoint state.
        try:
            existing_meta = CheckpointReader.read_metadata(checkpoint_path)
            if existing_meta.get("completed"):
                result_count = existing_meta.get("result_count", 0)
                total_events = existing_meta.get("total_events", 0)
                click.echo(
                    f"Error: Checkpoint already exists and is completed "
                    f"({result_count} results, {total_events:,} events).\n"
                    f"Use --force to overwrite with a new search, "
                    f"or delete the file and retry.\n"
                    f"\n"
                    f"  View results:  limacharlie search checkpoint-show --checkpoint {checkpoint_path}\n"
                    f"  Overwrite:     add --force to your command",
                    err=True,
                )
            else:
                result_count = existing_meta.get("result_count", 0)
                total_events = existing_meta.get("total_events", 0)
                page = existing_meta.get("page", 1)
                click.echo(
                    f"Error: Checkpoint already exists and is in-progress "
                    f"(page {page}, {result_count} results, {total_events:,} events).\n"
                    f"Use --resume to continue from where it left off, "
                    f"--force to overwrite, or delete the file and retry.\n"
                    f"\n"
                    f"  Resume:    limacharlie search run --resume --checkpoint {checkpoint_path}\n"
                    f"  Overwrite: add --force to your command",
                    err=True,
                )
        except (FileNotFoundError, Exception):
            # No metadata or can't read it - fall back to generic message.
            click.echo(
                f"Error: Checkpoint data file already exists: {os.path.abspath(checkpoint_path)}.\n"
                f"Use --force to overwrite, or delete the file and retry.",
                err=True,
            )
        ctx.exit(4)
        return

    results: list[dict] = []
    count = 0
    page = 1
    total_events = 0
    last_token: str | None = None
    last_event_ts: int | None = None
    try:
        with writer:
            for item in search.execute(query, start, end, stream=stream,
                                       limit=limit, progress_fn=progress_fn):
                writer.write_result(item)
                results.append(item)
                count += 1
                # Track token, page, events, and timestamps.
                if item.get("nextToken"):
                    last_token = item["nextToken"]
                    page += 1
                if item.get("type") == "events":
                    rows = item.get("rows") or []
                    total_events += len(rows)
                    for row in rows:
                        ts = (row.get("mtd") or {}).get("ts")
                        if ts is not None:
                            last_event_ts = ts
                writer.update_progress(page, count, completed=False,
                                       last_token=last_token,
                                       total_events=total_events,
                                       last_event_ts=last_event_ts)
            writer.update_progress(page, count, completed=True,
                                   last_token=last_token,
                                   total_events=total_events,
                                   last_event_ts=last_event_ts)
    except KeyboardInterrupt:
        _print_checkpoint_cancel(checkpoint_path, page, count,
                                 total_events, last_token)
        ctx.exit(130)
        return
    except Exception:
        if count > 0 and progress_fn:
            progress_fn(f"Search failed after {count} results. Checkpoint saved: {checkpoint_path}")
        raise

    if progress_fn:
        progress_fn(f"Checkpoint complete: {count} results saved to {checkpoint_path}")
    _output_search_results(ctx, results, raw=raw, expand=expand)


def _run_resume(
    ctx: click.Context, checkpoint_path: str,
    limit: int | None, token_expiry: float | None,
    raw: bool, expand: bool,
) -> None:
    """Resume a search from an existing checkpoint.

    Uses the stored pagination token to skip directly to the next
    un-fetched page on the server side, avoiding re-fetching already-
    checkpointed data.
    """
    debug_fn = ctx.obj.debug_fn
    if debug_fn:
        debug_fn(f"Checkpoint: resuming from {checkpoint_path}")

    try:
        resumer = CheckpointResumer(checkpoint_path)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(4)
        return

    meta = resumer.metadata
    last_token = meta.get("last_token")
    if debug_fn:
        debug_fn(f"Checkpoint metadata: query={meta.get('query')!r}, "
                 f"result_count={meta.get('result_count')}, "
                 f"page={meta.get('page')}, completed={meta.get('completed')}, "
                 f"last_token={last_token!r}")

    if meta.get("completed"):
        click.echo("Checkpoint is already completed. Nothing to resume.", err=True)
        # Output existing results from the data file.
        all_results = list(CheckpointReader.iter_results(checkpoint_path))
        _output_search_results(ctx, all_results, raw=raw, expand=expand)
        return

    query = meta["query"]
    start = meta["start_time"]
    end = meta["end_time"]
    stream = meta.get("stream")
    checkpoint_limit = meta.get("limit")
    existing_count = resumer.existing_count

    # Use the resume limit if provided, otherwise use the original limit.
    effective_limit = limit if limit is not None else checkpoint_limit

    if debug_fn:
        debug_fn(f"Checkpoint: {existing_count} existing results, "
                 f"effective_limit={effective_limit}, "
                 f"resuming from token={last_token!r}")

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

    resume_page = meta.get("page", 1)
    if progress_fn:
        if last_token:
            progress_fn(
                f"Resuming from page {resume_page} "
                f"({existing_count} results already fetched)..."
            )
        else:
            progress_fn(
                f"Resuming from start ({existing_count} results already "
                f"fetched, no pagination token - will re-fetch and skip)..."
            )

    count = existing_count
    page = resume_page
    total_events = meta.get("total_events", 0)
    last_token_new: str | None = last_token
    last_event_ts: int | None = meta.get("last_event_ts")
    try:
        with resumer:
            # Use start_token to skip directly to the next un-fetched page
            # on the server side. If no token is available (e.g. interrupted
            # on page 1 before any results), fall back to re-fetch + skip.
            gen = search.execute(
                query, start, end, stream=stream,
                limit=effective_limit, progress_fn=progress_fn,
                start_token=last_token,
                start_page=resume_page,
            )

            if last_token:
                # Server-side resume: token jumps us to the right page,
                # all results from the generator are new.
                for item in gen:
                    resumer.write_result(item)
                    count += 1
                    if item.get("nextToken"):
                        last_token_new = item["nextToken"]
                        page += 1
                    if item.get("type") == "events":
                        rows = item.get("rows") or []
                        total_events += len(rows)
                        for row in rows:
                            ts = (row.get("mtd") or {}).get("ts")
                            if ts is not None:
                                last_event_ts = ts
                    resumer.update_progress(page, count, completed=False,
                                            last_token=last_token_new,
                                            total_events=total_events,
                                            last_event_ts=last_event_ts)
            else:
                # No token available - re-fetch from start and skip
                # already-fetched results. This is the slow path that
                # only happens when the checkpoint has no token (e.g.
                # interrupted before any page completed).
                # NOTE: this assumes the server returns results in the
                # same order for identical queries. Non-deterministic
                # ordering could cause missed or duplicate results.
                skipped = 0
                for item in gen:
                    if skipped < existing_count:
                        skipped += 1
                        if debug_fn:
                            debug_fn(f"Checkpoint resume: skipping result {skipped}/{existing_count}")
                        continue
                    resumer.write_result(item)
                    count += 1
                    if item.get("nextToken"):
                        last_token_new = item["nextToken"]
                        page += 1
                    if item.get("type") == "events":
                        rows = item.get("rows") or []
                        total_events += len(rows)
                        for row in rows:
                            ts = (row.get("mtd") or {}).get("ts")
                            if ts is not None:
                                last_event_ts = ts
                    resumer.update_progress(page, count, completed=False,
                                            last_token=last_token_new,
                                            total_events=total_events,
                                            last_event_ts=last_event_ts)

            resumer.update_progress(page, count, completed=True,
                                    last_token=last_token_new,
                                    total_events=total_events,
                                    last_event_ts=last_event_ts)
    except KeyboardInterrupt:
        new_pages = page - resume_page
        _print_checkpoint_cancel(checkpoint_path, new_pages, count,
                                 total_events, last_token_new)
        ctx.exit(130)
        return
    except Exception as exc:
        if _is_token_expired_error(exc):
            # The server rejected the pagination token. Show a helpful
            # message with the command to start fresh.
            fresh_cmd = _build_fresh_query_cmd(meta, checkpoint_path)
            click.echo(
                f"\nError: Resume failed - the server rejected the pagination token.\n"
                f"\n"
                f"The token from this checkpoint may be invalid or the server\n"
                f"could not process it.\n"
                f"\n"
                f"To re-run the query from scratch (overwrites the checkpoint):\n"
                f"\n"
                f"  {fresh_cmd}\n",
                err=True,
            )
            sys.stderr.flush()
            ctx.exit(1)
            return
        if count > existing_count and progress_fn:
            progress_fn(f"Search failed after {count} results. Checkpoint saved: {checkpoint_path}")
        raise

    if progress_fn:
        new_count = count - existing_count
        progress_fn(f"Resume complete: {new_count} new results ({count} total) saved to {checkpoint_path}")

    # Read all results from the checkpoint file (existing + new) for output.
    # The data file now contains everything; no need to keep results in memory
    # during the search loop.
    all_results = list(CheckpointReader.iter_results(checkpoint_path))
    _output_search_results(ctx, all_results, raw=raw, expand=expand)


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


# ---------------------------------------------------------------------------
# checkpoints
# ---------------------------------------------------------------------------

_EXPLAIN_CHECKPOINTS = """\
List all search checkpoints stored locally.  Shows the data file path,
query, time range, result count, and completion status for each
checkpoint.  Use this to find interrupted searches that can be resumed
with 'search run --resume --checkpoint <path>'.
"""
register_explain("search.checkpoints", _EXPLAIN_CHECKPOINTS)


@group.command("checkpoints")
@pass_context
def checkpoints_list(ctx: click.Context) -> None:
    """List local search checkpoints. Automatically cleans up stale metadata."""
    cps = list_checkpoints(cleanup=True, debug_fn=ctx.obj.debug_fn)
    if not cps:
        if not ctx.obj.quiet:
            click.echo("No checkpoints found.")
        return

    fmt = ctx.obj.output_format or detect_output_format()
    if fmt != "table":
        click.echo(format_output(cps, fmt))
        return

    rows: list[dict[str, Any]] = []
    for cp in cps:
        start_ts = cp.get("start_time")
        end_ts = cp.get("end_time")
        try:
            start_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if start_ts else ""
        except (OSError, ValueError, OverflowError, TypeError):
            start_str = str(start_ts)
        try:
            end_str = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if end_ts else ""
        except (OSError, ValueError, OverflowError, TypeError):
            end_str = str(end_ts)

        query_str = cp.get("query", "")
        if len(query_str) > 50:
            query_str = query_str[:47] + "..."

        status = "completed" if cp.get("completed") else "in-progress"
        if not cp.get("data_file_exists", True):
            status += " (data missing)"

        page = cp.get("page", 1)
        total_events = cp.get("total_events", 0)

        # Compute time range progress percentage from last_event_ts.
        progress_str = ""
        last_event_ts = cp.get("last_event_ts")
        if last_event_ts is not None and start_ts and end_ts and end_ts > start_ts:
            # last_event_ts is in milliseconds, start/end are in seconds.
            last_sec = last_event_ts / 1000
            total_range = end_ts - start_ts
            covered = max(0, min(last_sec - start_ts, total_range))
            pct = (covered / total_range) * 100
            progress_str = f"{pct:.0f}%"
            # Also show the last event timestamp.
            try:
                last_ts_str = datetime.fromtimestamp(
                    last_sec, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M")
                progress_str = f"{pct:.0f}% ({last_ts_str})"
            except (OSError, ValueError, OverflowError, TypeError):
                pass

        # Format created_at for display
        created = cp.get("created_at", "")
        if created:
            try:
                created = created[:19].replace("T", " ")  # "2026-03-16 10:30:00"
            except (TypeError, IndexError):
                pass

        updated = cp.get("updated_at", "")
        if updated:
            try:
                updated = updated[:19].replace("T", " ")
            except (TypeError, IndexError):
                pass

        # Truncate token for display (show suffix since prefix is always the same).
        token_display = ""
        cp_token = cp.get("last_token")
        if cp_token:
            token_display = "..." + cp_token[-12:] if len(cp_token) > 16 else cp_token

        rows.append({
            "data_file": cp.get("data_file", ""),
            "query": query_str,
            "range": f"{start_str} - {end_str}" if start_str and end_str else "",
            "pages": page,
            "events": f"{total_events:,}" if total_events else "0",
            "progress": progress_str,
            "status": status,
            "token": token_display,
            "created": created,
            "updated": updated,
        })

    click.echo(format_table(rows))


# ---------------------------------------------------------------------------
# checkpoint-show
# ---------------------------------------------------------------------------

_EXPLAIN_CHECKPOINT_SHOW = """\
Display results from a checkpoint data file.  Reads the JSONL data file
and renders it through the same output pipeline as a live search -
table unwrapping, --expand, --raw, and all --output formats work.

This is useful for reviewing results from an interrupted or completed
search without re-running the query.

Examples:
  # Table output (default)
  limacharlie search checkpoint-show --checkpoint /tmp/my_search.jsonl

  # Expanded JSON events
  limacharlie search checkpoint-show --checkpoint /tmp/my_search.jsonl --expand

  # JSON for scripting
  limacharlie search checkpoint-show --checkpoint /tmp/my_search.jsonl --output json

  # Pipe to jq
  limacharlie search checkpoint-show --checkpoint /tmp/my_search.jsonl --output jsonl | jq '.rows[].data'

Related: 'search checkpoints' to list all checkpoints,
'search run --resume' to continue an interrupted search.
"""
register_explain("search.checkpoint-show", _EXPLAIN_CHECKPOINT_SHOW)


@group.command("checkpoint-show")
@click.option("--checkpoint", "checkpoint_path", required=True, type=click.Path(exists=True),
              help="Path to the checkpoint JSONL data file.")
@click.option("--raw", is_flag=True, default=False, help="Show raw API result objects without unwrapping.")
@click.option("--expand", is_flag=True, default=False, help="Show each event as a full pretty-printed JSON block.")
@pass_context
def checkpoint_show(ctx: click.Context, checkpoint_path: str, raw: bool, expand: bool) -> None:
    """Display results from a checkpoint data file.

    Streams results lazily for JSONL output (``--output jsonl``) to
    avoid loading the entire file into memory. For table, expand, JSON,
    and CSV formats, loads all results into memory because those formats
    require the full data set (table needs all rows for column widths,
    JSON needs the complete array, etc.). For large checkpoints, use
    ``--output jsonl`` and pipe to jq or other streaming tools.
    """
    try:
        meta = CheckpointReader.read_metadata(checkpoint_path)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(4)
        return

    # Print checkpoint summary to stderr (like stats from a live search).
    if not ctx.obj.quiet and sys.stderr.isatty():
        total_events = meta.get("total_events", 0)
        pages = meta.get("page", 1)
        result_count = meta.get("result_count", 0)
        status = "completed" if meta.get("completed") else "in-progress"
        query = meta.get("query", "")
        if len(query) > 80:
            query = query[:77] + "..."
        click.echo(click.style(
            f"Checkpoint: {status}, {pages} pages, "
            f"{total_events:,} events, {result_count} results",
            dim=True,
        ), err=True)
        click.echo(click.style(f"Query: {query}", dim=True), err=True)
        sys.stderr.flush()

    if ctx.obj.quiet:
        return

    fmt = ctx.obj.output_format or detect_output_format()

    # JSONL: stream one result per line without loading all into memory.
    if fmt == "jsonl":
        has_results = False
        for result in CheckpointReader.iter_results(checkpoint_path):
            has_results = True
            click.echo(json.dumps(result, default=str))
        if not has_results:
            click.echo("Checkpoint is empty (no results).")
        return

    # All other formats need the full list.
    try:
        _, results = CheckpointReader.read(checkpoint_path)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(4)
        return

    if not results:
        click.echo("Checkpoint is empty (no results).")
        return

    _output_search_results(ctx, results, raw=raw, expand=expand)
