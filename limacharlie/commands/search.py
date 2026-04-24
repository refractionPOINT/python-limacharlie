"""Search/LCQL commands for LimaCharlie CLI v2.

Commands for running and validating LCQL queries against historical
telemetry stored in LimaCharlie Insight.

Search results from the API contain wrapper objects (SearchResult) with
metadata like searchResultId, type, nextToken, and stats.  For human-
readable table output, these wrappers are unwrapped: event rows are
flattened into a single table, facets and timeseries are shown as
separate tables, and a stats summary is printed to stderr.  Machine-
readable formats (json, yaml, toon, csv, jsonl) pass through the raw API
response unchanged.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import click
from ..json_compat import (
    dumps as _fast_dumps,
    dumps_pretty as _fast_dumps_pretty,
    loads as _fast_loads,
    backend_name as _json_backend_name,
)

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


def _warn(ctx: click.Context, msg: str) -> None:
    """Print an advisory warning to stderr unless suppressed.

    Suppressed by --no-warnings or --quiet. Not suppressed by --output
    format changes (warnings are always on stderr).

    Args:
        ctx: Click context with output settings.
        msg: Warning message to print.
    """
    if ctx.obj.quiet or ctx.obj.no_warnings:
        return
    click.echo(msg, err=True)


def _output_validate_or_estimate(ctx: click.Context, data: dict[str, Any]) -> None:
    """Output validate/estimate results with expanded stats for table mode.

    For table output: flattens nested dicts (stats, estimatedPrice) into
    individual columns so the full values are visible without truncation.
    For machine-readable formats: passes through the raw response unchanged.

    Args:
        ctx: Click context with output settings.
        data: Response dict from validate/estimate API.
    """
    if ctx.obj.quiet:
        return

    fmt = ctx.obj.output_format or detect_output_format()

    if fmt != "table":
        click.echo(format_output(data, fmt))
        return

    # Flatten stats and estimatedPrice into individual columns for table
    # display so values are fully visible (not truncated as "{N keys}").
    display = {}
    for key, value in data.items():
        if key == "stats" and isinstance(value, dict):
            for sk, sv in value.items():
                display[f"stats.{sk}"] = sv
        elif key == "estimatedPrice" and isinstance(value, dict):
            for pk, pv in value.items():
                display[f"price.{pk}"] = pv
        else:
            display[key] = value

    click.echo(format_output(display, fmt))


def _get_org(ctx: click.Context) -> Organization:
    client = Client(oid=ctx.obj.oid, environment=ctx.obj.environment, print_debug_fn=ctx.obj.debug_fn, debug_full_response=ctx.obj.debug_full, debug_curl=ctx.obj.debug_curl, debug_verbose=ctx.obj.debug_verbose)
    return Organization(client)



def _output_checkpoint_results(
    ctx: click.Context,
    checkpoint_path: str,
    raw: bool = False,
    expand: bool = False,
) -> None:
    """Output results from a checkpoint data file.

    Streaming behavior by format:
    - JSONL: streams one line at a time (constant memory)
    - JSON: streaming JSON array (constant memory)
    - expand: streams per event block (constant memory)
    - table: two-pass over the file - pass 1 computes exact column widths,
      pass 2 streams rows. O(columns) memory, not O(rows). Uses orjson
      for faster parsing when available.
    - CSV/YAML/raw: loads all results into memory (inherent to format)

    Args:
        ctx: Click context with output settings.
        checkpoint_path: Path to the checkpoint JSONL data file.
        raw: If True, skip unwrapping even in table mode.
        expand: If True, show each event as a full JSON block.
    """
    if ctx.obj.quiet:
        return

    fmt = ctx.obj.output_format or detect_output_format()

    # Table (non-raw, non-expand): use two-pass streaming from file.
    # This gives exact column widths (not sampled) with O(columns) memory.
    if fmt == "table" and not raw and not expand:
        _stream_table_from_file(checkpoint_path, wide=ctx.obj.wide)
        return

    # Try streaming for other formats (JSONL, JSON, expand).
    # _stream_search_output returns False without consuming the iterator
    # for formats that need the full list (CSV, YAML, raw).
    results_iter = CheckpointReader.iter_results(checkpoint_path)
    if _stream_search_output(ctx, results_iter, raw=raw, expand=expand):
        return

    # CSV/YAML/raw need the full list - consume the existing iterator
    # rather than opening the file a second time.
    results = list(results_iter)
    if not results:
        click.echo("No results.")
        return
    _output_search_results(ctx, results, raw=raw, expand=expand)


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


def _format_file_size(size_bytes: int) -> str:
    """Format a byte count as a human-friendly string (e.g. '1.2 MB').

    Uses binary units (1 KB = 1024 bytes) with one decimal place.

    Args:
        size_bytes: File size in bytes.

    Returns:
        Human-readable size string like '4.5 KB', '12.3 MB', '1.1 GB'.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size_bytes /= 1024
        if size_bytes < 1024 or unit == "TB":
            return f"{size_bytes:.1f} {unit}"
    return f"{size_bytes:.1f} TB"


def _format_expanded_event_block(row: dict[str, Any]) -> str:
    """Format a single event row as a header + JSON block.

    Args:
        row: A SearchResultRow dict with 'mtd' and 'data' fields.

    Returns:
        A string like "--- 2023-11-15 00:12:34 | event | NEW_PROCESS ---\\n{json}"
    """
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
    if isinstance(data, dict):
        etype = (
            data.get("routing", {}).get("event_type")
            or data.get("cat")
            or data.get("etype")
        )
        if etype:
            header_parts.append(etype)

    header = " | ".join(header_parts) if header_parts else "event"
    body = _fast_dumps_pretty(data)
    return f"--- {header} ---\n{body}"


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
            parts.append(_format_expanded_event_block(row))
    return "\n".join(parts)


def _stream_expanded_events(results_iter: Any) -> bool:
    """Stream expanded event blocks to stdout one at a time.

    Each event is printed immediately without buffering all events
    in memory. Suitable for large result sets.

    Args:
        results_iter: Iterable of SearchResult dicts.

    Returns:
        True if at least one event was printed.
    """
    has_events = False
    for result in results_iter:
        if result.get("type") != "events":
            continue
        for row in result.get("rows") or []:
            has_events = True
            click.echo(_format_expanded_event_block(row))
    return has_events


def _stream_search_output(
    ctx: click.Context,
    results_iter: Any,
    raw: bool = False,
    expand: bool = False,
) -> bool:
    """Try to stream search results without buffering in memory.

    Handles formats that can be streamed one result at a time:
    - JSONL: one JSON line per result (constant memory)
    - JSON: streaming JSON array (``[`` + items + ``]``, constant memory)
    - expand: one event block at a time (constant memory)

    For formats that require the full data set (table, CSV, YAML), returns
    False so the caller can fall back to buffered output.

    Args:
        ctx: Click context with output settings.
        results_iter: Iterable (generator or list) of SearchResult dicts.
        raw: If True, skip unwrapping even in table mode.
        expand: If True, show each event as a full JSON block.

    Returns:
        True if output was handled (streamed). False if the caller should
        fall back to buffered output (the iterator was NOT consumed).
    """
    if ctx.obj.quiet:
        return True  # Nothing to do, consider it handled.

    fmt = ctx.obj.output_format or detect_output_format()

    # JSONL: stream one result per line.
    if fmt == "jsonl":
        for result in results_iter:
            click.echo(_fast_dumps(result))
        return True

    # JSON: stream as array without building the full list in memory.
    # Write "[", then each item separated by commas, then "]".
    if fmt == "json":
        first = True
        for result in results_iter:
            if first:
                click.echo("[")
                first = False
            else:
                click.echo(",")
            click.echo(f"  {_fast_dumps(result)}", nl=False)
        if first:
            # No results at all.
            click.echo("[]")
        else:
            click.echo("\n]")
        return True

    # Expand mode (table format): stream each event block individually.
    if fmt == "table" and expand and not raw:
        has_events = _stream_expanded_events(results_iter)
        if not has_events:
            click.echo("No events")
        return True

    # Table (non-expand, non-raw): stream with sampled column widths.
    if fmt == "table" and not raw:
        _stream_table_events(results_iter, wide=ctx.obj.wide)
        return True

    # CSV, YAML, TOON, raw: cannot stream - need full list.
    return False


# Number of SearchResult pages to buffer for column width sampling.
# Each page typically has ~2000 event rows, so 3 pages = ~6000 rows
# which is enough to determine representative column widths.
_TABLE_SAMPLE_PAGES = 3

# Time range threshold (seconds) above which a warning is emitted for
# searches without --checkpoint. Searches over large time ranges produce
# many results that may cause high memory usage without checkpointing.
# Default: 7 days (604800 seconds).
_LARGE_TIME_RANGE_WARN_SECONDS = 7 * 24 * 3600

# Time range threshold (seconds) above which we recommend --checkpoint
# for resumability. Long searches are more likely to be interrupted
# (network issues, token expiry, Ctrl-C) and losing hours of progress
# is painful. Default: 14 days (1209600 seconds).
_CHECKPOINT_RECOMMEND_SECONDS = 14 * 24 * 3600

# Time range threshold (seconds) above which a billing cost notice is
# shown. LimaCharlie includes the last 30 days of telemetry in the
# base price; searching beyond that window may incur additional
# per-query charges. The server-side threshold is strictly >30 days
# (replay uses 31*24h, insight-go uses 30*24h with >), so we warn
# at >30 days to match.
_COST_NOTICE_SECONDS = 30 * 24 * 3600


def _warn_cost_if_over_30_days(
    ctx: click.Context,
    query: str, start: int, end: int,
    stream: str | None, checkpoint_path: str | None,
) -> None:
    """Print a billing cost notice when the search spans more than 30 days.

    LimaCharlie includes the last 30 days of telemetry in the base
    subscription price. Queries that reach beyond the 30-day window may
    incur additional per-query charges based on the volume of data
    scanned.

    Shows the ``search estimate`` command the user can run to check
    the cost before executing.

    Suppressed by ``--no-warnings`` or ``--quiet``.

    Args:
        ctx: Click context with output settings.
        query: LCQL query string.
        start: Start time (unix seconds).
        end: End time (unix seconds).
        stream: Stream type or None.
        checkpoint_path: Checkpoint path (for building the estimate cmd).
    """
    time_range = end - start
    if time_range <= _COST_NOTICE_SECONDS:
        return

    days = time_range / 86400
    estimate_parts = [
        "limacharlie search estimate",
        f"--query {shlex.quote(query)}",
        f"--start {start}",
        f"--end {end}",
    ]
    if stream:
        estimate_parts.append(f"--stream {shlex.quote(stream)}")
    estimate_cmd = " \\\n    ".join(estimate_parts)

    _warn(
        ctx,
        f"Notice: this search spans {days:.0f} days. Searches over data "
        f"older than 30 days may incur additional costs.\n"
        f"To estimate the cost before running:\n\n"
        f"  {estimate_cmd}\n",
    )


def _stream_table_events(results_iter: Any, wide: bool = False) -> None:
    """Stream search results as a table, sampling first pages for column widths.

    Buffers the first few pages of results to determine column names and
    widths, prints the header and buffered rows, then streams remaining
    rows one at a time using the computed layout. Rows with values wider
    than the sampled widths are truncated.

    Memory usage: O(sample_rows * columns) for the sample buffer, then
    O(columns) for the streaming phase. Much less than O(all_rows) for
    large result sets.

    Args:
        results_iter: Iterable of SearchResult dicts from the API.
        wide: If True, don't limit columns or truncate values.
    """
    from ..output import _table_value, _term_width, _wide_mode
    import shutil

    # Phase 1: Sample first N pages to determine columns and widths.
    sample_results: list[dict[str, Any]] = []
    remaining_results: list[dict[str, Any]] = []
    sample_count = 0
    stats: dict[str, Any] = {}
    total_events = 0

    for result in results_iter:
        if result.get("type") == "events":
            result_stats = result.get("stats")
            if result_stats:
                stats = result_stats
        if sample_count < _TABLE_SAMPLE_PAGES:
            sample_results.append(result)
            sample_count += 1
        else:
            remaining_results.append(result)
            # After collecting one extra to prove there are more,
            # break out and stream the rest later.
            break

    if not sample_results:
        click.echo("No events")
        return

    # Flatten sample events to determine columns.
    sample_flat: list[dict[str, Any]] = []
    for result in sample_results:
        if result.get("type") != "events":
            continue
        for row in result.get("rows") or []:
            sample_flat.append(_flatten_event_row(row))

    if not sample_flat:
        click.echo("No events")
        return

    # Apply column selection (priority columns, drop columns, cap).
    if not wide:
        sample_display = _limit_event_columns(sample_flat)
    else:
        sample_display = sample_flat

    # Determine columns from sample.
    columns: list[str] = []
    seen: set[str] = set()
    for row in sample_display:
        for k in row:
            if k not in seen:
                columns.append(k)
                seen.add(k)

    if not columns:
        click.echo("No events")
        return

    # Compute column widths from sample.
    term = shutil.get_terminal_size().columns if not wide else 9999
    cell_max = max(20, min(60, term // 3)) if not wide else 9999

    col_widths: dict[str, int] = {}
    for col in columns:
        header_w = len(col)
        max_val_w = 0
        for row in sample_display:
            val = _table_value(row.get(col, ""), width=cell_max)
            max_val_w = max(max_val_w, len(val))
        col_widths[col] = max(header_w, min(max_val_w, cell_max))

    # Build format string.
    def _render_row(values: list[str]) -> str:
        parts = []
        for col, val in zip(columns, values):
            w = col_widths[col]
            if len(val) > w:
                val = val[:w - 3] + "..." if w > 3 else val[:w]
            parts.append(val.ljust(w))
        return "  ".join(parts)

    # Print header.
    header_vals = [col.ljust(col_widths[col]) for col in columns]
    click.echo("  ".join(header_vals))
    separator = "  ".join("-" * col_widths[col] for col in columns)
    click.echo(separator)

    # Phase 2: Print sample rows.
    for row in sample_display:
        vals = [_table_value(row.get(col, ""), width=cell_max) for col in columns]
        click.echo(_render_row(vals))
        total_events += 1

    # Phase 3: Stream remaining results.
    def _process_remaining(results):
        nonlocal total_events, stats
        for result in results:
            if result.get("type") == "events":
                result_stats = result.get("stats")
                if result_stats:
                    stats = result_stats
                for row in result.get("rows") or []:
                    flat = _flatten_event_row(row)
                    if not wide:
                        flat = {k: flat[k] for k in columns if k in flat}
                    vals = [_table_value(flat.get(col, ""), width=cell_max) for col in columns]
                    click.echo(_render_row(vals))
                    total_events += 1

    # First process any extra results we buffered.
    _process_remaining(remaining_results)
    # Then stream the rest from the iterator.
    _process_remaining(results_iter)

    # Stats summary to stderr.
    click.echo(click.style(
        f"({total_events:,} event{'s' if total_events != 1 else ''})",
        dim=True,
    ), err=True)
    if stats:
        summary = _format_stats_summary(stats)
        if summary:
            click.echo(click.style(f"Stats: {summary}", dim=True), err=True)
    sys.stderr.flush()


def _stream_table_from_file(checkpoint_path: str, wide: bool = False) -> None:
    """Two-pass streaming table renderer for checkpoint files.

    Pass 1: Scans the entire JSONL file to compute exact column widths.
    Only stores {column: max_width} - O(columns) memory, not O(rows).
    Pass 2: Streams the file again, rendering each row immediately with
    the computed layout.

    Uses orjson for fast JSON parsing on both passes (~3-6x faster than
    stdlib json).

    This gives perfectly accurate column widths (unlike the sample-based
    approach for live searches) while keeping memory constant regardless
    of file size.

    Args:
        checkpoint_path: Path to the checkpoint JSONL data file.
        wide: If True, don't limit columns or truncate values.
    """
    from ..output import _table_value

    term = shutil.get_terminal_size().columns if not wide else 9999
    cell_max = max(20, min(60, term // 3)) if not wide else 9999

    # --- Pass 1: compute all columns and their widths ---
    # We collect all unique column names and track the max rendered width
    # for each. This is O(columns) memory, not O(rows).
    all_columns: list[str] = []
    seen_cols: set[str] = set()
    col_widths: dict[str, int] = {}
    stats: dict[str, Any] = {}
    total_events = 0

    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                result = _fast_loads(stripped)
            except (json.JSONDecodeError, ValueError):
                continue

            if result.get("type") != "events":
                continue
            result_stats = result.get("stats")
            if result_stats:
                stats = result_stats
            for row in result.get("rows") or []:
                flat = _flatten_event_row(row)
                total_events += 1
                for k, v in flat.items():
                    val_str = _table_value(v, width=cell_max)
                    val_w = len(val_str)
                    if k not in seen_cols:
                        all_columns.append(k)
                        seen_cols.add(k)
                        col_widths[k] = max(len(k), val_w)
                    else:
                        col_widths[k] = max(col_widths[k], val_w)

    if not all_columns:
        click.echo("No events")
        return

    # Apply column selection (priority columns, drop columns, column cap).
    # Build a fake single-row dict with all columns to let _limit_event_columns
    # determine the final column set and order.
    if not wide:
        fake_row = {k: "" for k in all_columns}
        selected = _limit_event_columns([fake_row])
        columns = list(selected[0].keys()) if selected else all_columns
    else:
        columns = all_columns

    # Filter col_widths to only selected columns.
    col_widths = {k: col_widths.get(k, len(k)) for k in columns}

    def _render_row(values: list[str]) -> str:
        parts = []
        for col, val in zip(columns, values):
            w = col_widths.get(col, len(col))
            if len(val) > w:
                val = val[:w - 3] + "..." if w > 3 else val[:w]
            parts.append(val.ljust(w))
        return "  ".join(parts)

    # Print header.
    header_vals = [col.ljust(col_widths.get(col, len(col))) for col in columns]
    click.echo("  ".join(header_vals))
    click.echo("  ".join("-" * col_widths.get(col, len(col)) for col in columns))

    # --- Pass 2: stream rows ---
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                result = _fast_loads(stripped)
            except (json.JSONDecodeError, ValueError):
                continue

            if result.get("type") != "events":
                continue
            for row in result.get("rows") or []:
                flat = _flatten_event_row(row)
                vals = [_table_value(flat.get(col, ""), width=cell_max) for col in columns]
                click.echo(_render_row(vals))

    # Stats summary to stderr.
    click.echo(click.style(
        f"({total_events:,} event{'s' if total_events != 1 else ''})",
        dim=True,
    ), err=True)
    if stats:
        summary = _format_stats_summary(stats)
        if summary:
            click.echo(click.style(f"Stats: {summary}", dim=True), err=True)
    sys.stderr.flush()


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

    For machine-readable formats (json, yaml, toon, csv, jsonl): passes the
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

Output formats:
  By default, results are rendered as a table (TTY) or JSON (piped).
  Use --output to choose: json, jsonl, yaml, toon, csv, table.

  Streaming behavior (constant memory):
    --output jsonl  - one JSON object per line, streamed immediately
    --output json   - streaming JSON array, no full buffering
    --output table  - streams rows after sampling column widths from
                      the first few pages (default for TTY)

  Buffered (loads all results into memory):
    --output csv    - needs all rows for column headers
    --output yaml   - needs all rows for YAML structure
    --output toon   - needs all rows to infer tabular schema

  Use --expand to show each event as a full pretty-printed JSON block
  with a header showing timestamp, stream, and event type. Useful for
  investigating individual events in detail.

  Use --raw to show the raw SearchResult API objects without
  unwrapping. Useful for debugging or accessing metadata like
  searchResultId, nextToken, and stats.

  For large result sets (100K+ events), prefer --output jsonl or
  --checkpoint to avoid high memory usage.

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
    """Execute an LCQL query against historical telemetry."""
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
    """Execute a search without checkpointing.

    Streams results for JSONL, JSON, and expand output formats to avoid
    buffering all results in memory. Falls back to buffered output for
    table/CSV/YAML which need the full data set.
    """
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")

    # Warn about large time ranges without --checkpoint.
    time_range = end - start
    fmt = ctx.obj.output_format or detect_output_format()
    _warn_cost_if_over_30_days(ctx, query, start, end, stream, checkpoint_path=None)
    if time_range > _LARGE_TIME_RANGE_WARN_SECONDS and fmt in ("csv", "yaml", "toon"):
        days = time_range / 86400
        _warn(
            ctx,
            f"Warning: searching {days:.0f} days without --checkpoint. "
            f"With --output {fmt}, all results are buffered in memory.\n"
            f"Consider --output jsonl or --output table which stream with "
            f"constant memory, or use --checkpoint for incremental saves.",
        )
    if time_range > _CHECKPOINT_RECOMMEND_SECONDS:
        days = time_range / 86400
        _warn(
            ctx,
            f"Warning: searching {days:.0f} days without --checkpoint. "
            f"If the search is interrupted, all progress will be lost.\n"
            f"Consider using --checkpoint <path> so the search can be "
            f"resumed later with --resume.",
        )

    org = _get_org(ctx)
    effective_expiry = _resolve_token_expiry(token_expiry, environment=ctx.obj.environment)
    if effective_expiry > 24:
        _warn(
            ctx,
            f"Warning: generating a token valid for {effective_expiry} hours. "
            "Long-lived tokens increase security exposure if leaked.",
        )
    org.client.get_jwt(expiry_hours=effective_expiry)
    search = Search(org)
    progress_fn = _make_progress_fn(ctx)
    try:
        gen = search.execute(query, start, end, stream=stream, limit=limit, progress_fn=progress_fn)
        # Try streaming output first (JSONL, JSON, expand). If the format
        # requires buffering (table, CSV, YAML), fall back to list().
        if _stream_search_output(ctx, gen, raw=raw, expand=expand):
            return
        # Format needs full list - consume the generator.
        results = list(gen)
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
    _warn_cost_if_over_30_days(ctx, query, start, end, stream, checkpoint_path)
    org = _get_org(ctx)
    debug_fn = ctx.obj.debug_fn
    effective_expiry = _resolve_token_expiry(token_expiry, environment=ctx.obj.environment)
    if effective_expiry > 24:
        _warn(
            ctx,
            f"Warning: generating a token valid for {effective_expiry} hours. "
            "Long-lived tokens increase security exposure if leaked.",
        )
    org.client.get_jwt(expiry_hours=effective_expiry)
    search = Search(org)
    progress_fn = _make_progress_fn(ctx)

    if debug_fn:
        json_backend = _json_backend_name()
        debug_fn(f"Checkpoint: creating data file at {checkpoint_path} (force={force}), json backend: {json_backend}")

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

    # Do NOT accumulate results in memory during the search loop.
    # Large searches (100K+ events) would cause OOM on constrained VMs.
    # Results are persisted to the JSONL file and read back for output
    # at the end (or streamed for JSONL output format).
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

    # Read results back from the checkpoint file for output.
    # For JSONL this streams lazily; for table/JSON it loads into memory
    # but that is inherent to those formats.
    _output_checkpoint_results(ctx, checkpoint_path, raw=raw, expand=expand)


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
        _output_checkpoint_results(ctx, checkpoint_path, raw=raw, expand=expand)
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
        _warn(
            ctx,
            f"Warning: generating a token valid for {effective_expiry} hours. "
            "Long-lived tokens increase security exposure if leaked.",
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

    # Output results from the checkpoint file (existing + new).
    # Streams for JSONL; loads for table/JSON (inherent to those formats).
    _output_checkpoint_results(ctx, checkpoint_path, raw=raw, expand=expand)


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
    """Validate LCQL query syntax without executing."""
    org = _get_org(ctx)
    search = Search(org)
    data = search.validate(query)
    _output_validate_or_estimate(ctx, data)
    if data.get("error"):
        ctx.exit(1)


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
    """Estimate the billing cost of an LCQL query."""
    validate_epoch_seconds(start, "start")
    validate_epoch_seconds(end, "end")
    org = _get_org(ctx)
    search = Search(org)
    data = search.estimate(query, start, end, stream=stream)
    _output_validate_or_estimate(ctx, data)
    if data.get("error"):
        ctx.exit(1)


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
    """List all saved LCQL queries."""
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
    """Get a saved query by name."""
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
    """Create a new saved query."""
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
    """Delete a saved query by name."""
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
    """Execute a saved query."""
    org = _get_org(ctx)

    effective_expiry = _resolve_token_expiry(token_expiry, environment=ctx.obj.environment)
    if effective_expiry > 24:
        _warn(
            ctx,
            f"Warning: generating a token valid for {effective_expiry} hours. "
            "Long-lived tokens increase security exposure if leaked.",
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
        gen = search.execute(query_str, start_time, end_time, stream=stream, limit=limit, progress_fn=progress_fn)
        if _stream_search_output(ctx, gen, raw=raw, expand=expand):
            return
        results = list(gen)
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

        # Format file size for display.
        file_size = cp.get("data_file_size")
        size_str = _format_file_size(file_size) if file_size is not None else ""

        rows.append({
            "created": created,
            "data_file": cp.get("data_file", ""),
            "size": size_str,
            "query": query_str,
            "range": f"{start_str} - {end_str}" if start_str and end_str else "",
            "pages": page,
            "events": f"{total_events:,}" if total_events else "0",
            "progress": progress_str,
            "status": status,
            "token": token_display,
            "updated": updated,
        })

    # Sort by created timestamp descending (most recent first).
    rows.sort(key=lambda r: r.get("created", ""), reverse=True)
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
@click.option("--checkpoint", "checkpoint_path", default=None, type=click.Path(exists=True),
              help="Path to the checkpoint JSONL data file.")
@click.option("--raw", is_flag=True, default=False, help="Show raw API result objects without unwrapping.")
@click.option("--expand", is_flag=True, default=False, help="Show each event as a full pretty-printed JSON block.")
@pass_context
def checkpoint_show(ctx: click.Context, checkpoint_path: str | None, raw: bool, expand: bool) -> None:
    """Display results from a checkpoint data file.

    Streams results with constant memory for most output formats:
    - table: two-pass streaming (pass 1 computes column widths, pass 2
      streams rows) - O(columns) memory, not O(rows)
    - jsonl: one JSON line at a time
    - json: streaming JSON array
    - expand: one event block at a time

    For CSV and YAML, loads all results into memory (inherent to those
    formats). For large checkpoints with these formats, use ``--output
    jsonl`` and pipe to external tools.
    """
    if not checkpoint_path:
        click.echo("Error: --checkpoint is required.", err=True)
        ctx.exit(4)
        return

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

    _output_checkpoint_results(ctx, checkpoint_path, raw=raw, expand=expand)
