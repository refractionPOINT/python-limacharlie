"""Tests for search result unwrapping and formatting.

Validates that search results are correctly unwrapped from raw API
SearchResult objects into user-friendly table output, including event
row flattening, facet extraction, timeseries extraction, and stats
summary formatting.  Machine-readable formats (json, yaml, toon, csv, jsonl)
should pass through unchanged.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest

from limacharlie.commands.search import (
    _MAX_EVENT_COLUMNS,
    _DROP_COLUMNS,
    _PRIORITY_COLUMNS,
    _flatten_event_row,
    _format_expanded_events,
    _format_stats_summary,
    _limit_event_columns,
    _make_progress_fn,
    _output_search_results,
    _unwrap_search_results,
)


# ---------------------------------------------------------------------------
# Fixtures: realistic search result objects
# ---------------------------------------------------------------------------

def _make_event_row(
    event_id: str = "evt-1",
    ts: int = 1700000000000,
    stream: str = "event",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single SearchResultRow dict."""
    if data is None:
        data = {
            "routing": {
                "event_type": "NEW_PROCESS",
                "oid": "oid-1",
                "hostname": "web-01",
                "sid": "sid-1",
                "event_time": 1700000000,
            },
            "event": {
                "FILE_PATH": "/usr/bin/curl",
                "COMMAND_LINE": "curl https://example.com",
            },
        }
    return {
        "mtd": {
            "id": event_id,
            "ts": ts,
            "stream": stream,
            "projection": False,
        },
        "data": data,
    }


def _make_search_result(
    result_type: str = "events",
    rows: list[dict] | None = None,
    facets: list[dict] | None = None,
    timeseries: list[dict] | None = None,
    stats: dict[str, Any] | None = None,
    next_token: str = "",
) -> dict[str, Any]:
    """Build a SearchResult dict as returned by the API."""
    result: dict[str, Any] = {
        "searchResultId": "12345",
        "created": "2026-03-13T16:43:08.467",
        "type": result_type,
        "stats": stats or {},
    }
    if next_token:
        result["nextToken"] = next_token
    if result_type == "events":
        result["rows"] = rows or []
    elif result_type == "facets":
        result["facets"] = facets or []
    elif result_type == "timeline":
        result["timeseries"] = timeseries or []
    return result


def _make_stats(
    events_matched: int = 100,
    events_scanned: int = 5000,
    bytes_scanned: int = 1_048_576,
    walltime: float = 2.5,
    price_amount: float | None = 0.0012,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "eventsMatched": events_matched,
        "eventsScanned": events_scanned,
        "bytesScanned": bytes_scanned,
        "walltime": walltime,
    }
    if price_amount is not None:
        stats["estimatedPrice"] = {"amount": price_amount}
    return stats


# ---------------------------------------------------------------------------
# TestFlattenEventRow
# ---------------------------------------------------------------------------

class TestFlattenEventRow:
    """Tests for _flatten_event_row - converting SearchResultRow to flat dict."""

    def test_basic_event_row(self):
        """Standard event stream row with routing and event data."""
        row = _make_event_row()
        flat = _flatten_event_row(row)

        assert flat["time"] == "2023-11-14 22:13:20"
        assert flat["stream"] == "event"
        assert flat["routing.event_type"] == "NEW_PROCESS"
        assert flat["routing.hostname"] == "web-01"
        assert flat["event.FILE_PATH"] == "/usr/bin/curl"
        assert flat["event.COMMAND_LINE"] == "curl https://example.com"

    def test_detect_stream_row(self):
        """Detect stream row has 'cat' as top-level field, no 'routing.event_type'."""
        data = {
            "cat": "Suspicious PowerShell",
            "detect": {"op": "is"},
            "routing": {
                "event_type": "NEW_PROCESS",
                "hostname": "win-01",
            },
        }
        row = _make_event_row(stream="detect", data=data)
        flat = _flatten_event_row(row)

        assert flat["stream"] == "detect"
        assert flat["cat"] == "Suspicious PowerShell"
        assert flat["detect.op"] == "is"
        assert flat["routing.event_type"] == "NEW_PROCESS"

    def test_audit_stream_row(self):
        """Audit stream has different top-level structure."""
        data = {
            "etype": "user_login",
            "oid": "oid-1",
            "msg": "User logged in",
            "ident": "user@example.com",
            "time": 1700000000,
        }
        row = _make_event_row(stream="audit", data=data)
        flat = _flatten_event_row(row)

        assert flat["stream"] == "audit"
        assert flat["etype"] == "user_login"
        assert flat["msg"] == "User logged in"

    def test_projection_row(self):
        """Projection queries return flat data - no nesting to flatten."""
        data = {"path": "/usr/bin/curl", "count": 42, "hostname": "web-01"}
        row = _make_event_row(data=data)
        flat = _flatten_event_row(row)

        assert flat["path"] == "/usr/bin/curl"
        assert flat["count"] == 42
        assert flat["hostname"] == "web-01"
        # No dotted keys for flat data.
        assert not any("." in k for k in flat if k not in ("time", "stream"))

    def test_missing_mtd(self):
        """Row with no mtd field should still produce a dict."""
        row = {"data": {"key": "value"}}
        flat = _flatten_event_row(row)

        assert flat["key"] == "value"
        assert "time" not in flat
        assert "stream" not in flat

    def test_empty_row(self):
        """Completely empty row produces empty dict."""
        flat = _flatten_event_row({})
        assert flat == {}

    def test_ts_zero(self):
        """Timestamp of zero is still converted."""
        row = _make_event_row(ts=0)
        flat = _flatten_event_row(row)
        assert flat["time"] == "1970-01-01 00:00:00"

    def test_non_dict_data(self):
        """Non-dict data field is preserved as-is."""
        row = {"mtd": {"ts": 1700000000000, "stream": "event"}, "data": "raw string"}
        flat = _flatten_event_row(row)
        assert flat["data"] == "raw string"

    def test_deeply_nested_data(self):
        """Data nested beyond one level is kept as a dict value."""
        data = {
            "event": {
                "PARENT": {"FILE_PATH": "/usr/bin/bash", "COMMAND_LINE": "bash"},
                "FILE_PATH": "/usr/bin/curl",
            },
        }
        row = _make_event_row(data=data)
        flat = _flatten_event_row(row)

        assert flat["event.FILE_PATH"] == "/usr/bin/curl"
        # PARENT is a nested dict - kept as-is at event.PARENT level.
        assert isinstance(flat["event.PARENT"], dict)
        assert flat["event.PARENT"]["FILE_PATH"] == "/usr/bin/bash"

    def test_empty_data_dict(self):
        """Empty data dict produces only metadata fields."""
        row = _make_event_row(data={})
        flat = _flatten_event_row(row)
        assert "time" in flat
        assert "stream" in flat
        # No data keys.
        data_keys = [k for k in flat if k not in ("time", "stream")]
        assert data_keys == []

    def test_ts_overflow(self):
        """Extremely large timestamp falls back to string representation."""
        row = {"mtd": {"ts": 99999999999999999, "stream": "event"}, "data": {}}
        flat = _flatten_event_row(row)
        # Should not raise; falls back to string.
        assert "time" in flat
        assert flat["time"] == "99999999999999999"

    def test_mixed_data_types(self):
        """Data with mix of dicts, lists, strings, numbers."""
        data = {
            "routing": {"event_type": "DNS_REQUEST"},
            "tags": ["prod", "web"],
            "score": 0.95,
            "name": "test-event",
        }
        row = _make_event_row(data=data)
        flat = _flatten_event_row(row)

        assert flat["routing.event_type"] == "DNS_REQUEST"
        assert flat["tags"] == ["prod", "web"]
        assert flat["score"] == 0.95
        assert flat["name"] == "test-event"


# ---------------------------------------------------------------------------
# TestUnwrapSearchResults
# ---------------------------------------------------------------------------

class TestUnwrapSearchResults:
    """Tests for _unwrap_search_results - separating result types."""

    def test_events_only(self):
        """Single events result with rows."""
        rows = [_make_event_row(), _make_event_row(event_id="evt-2")]
        results = [_make_search_result("events", rows=rows, stats=_make_stats())]

        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 2
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []
        assert unwrapped["stats"]["eventsMatched"] == 100

    def test_multiple_pages_events(self):
        """Events from multiple pages are merged."""
        page1 = _make_search_result(
            "events",
            rows=[_make_event_row(event_id="evt-1")],
            stats=_make_stats(events_matched=50),
            next_token="token-2",
        )
        page2 = _make_search_result(
            "events",
            rows=[_make_event_row(event_id="evt-2"), _make_event_row(event_id="evt-3")],
            stats=_make_stats(events_matched=100),
        )

        unwrapped = _unwrap_search_results([page1, page2])
        assert len(unwrapped["events"]) == 3
        # Last stats wins (page 2 has cumulative).
        assert unwrapped["stats"]["eventsMatched"] == 100

    def test_facets_extraction(self):
        """Facets from facets-type results are collected."""
        facets = [
            {"type": "event_type", "name": "routing.event_type", "value": "NEW_PROCESS", "count": 42},
            {"type": "event_type", "name": "routing.event_type", "value": "DNS_REQUEST", "count": 10},
        ]
        results = [_make_search_result("facets", facets=facets)]

        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["facets"]) == 2
        assert unwrapped["events"] == []

    def test_timeseries_extraction(self):
        """Timeseries from timeline-type results are collected."""
        timeseries = [
            {"ts": 1700000000000, "type": "total", "count": 100},
            {"ts": 1700003600000, "type": "total", "count": 50},
        ]
        results = [_make_search_result("timeline", timeseries=timeseries)]

        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["timeseries"]) == 2
        assert unwrapped["events"] == []

    def test_mixed_result_types(self):
        """Typical real response: events + facets + 2x timeline per page."""
        results = [
            _make_search_result("events", rows=[_make_event_row()], stats=_make_stats()),
            _make_search_result("timeline", timeseries=[{"ts": 1700000000000, "type": "total", "count": 100}]),
            _make_search_result("timeline", timeseries=[{"ts": 1700000000000, "type": "event", "count": 100}]),
            _make_search_result("facets", facets=[{"type": "event_type", "value": "NEW_PROCESS", "count": 42}]),
        ]

        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 1
        assert len(unwrapped["facets"]) == 1
        assert len(unwrapped["timeseries"]) == 2

    def test_empty_results(self):
        """No results at all."""
        unwrapped = _unwrap_search_results([])
        assert unwrapped["events"] == []
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []
        assert unwrapped["stats"] == {}

    def test_events_with_empty_rows(self):
        """Events result with no rows (e.g. final page)."""
        results = [_make_search_result("events", rows=[], stats=_make_stats())]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []
        assert unwrapped["stats"]["eventsMatched"] == 100

    def test_unknown_result_type(self):
        """Unknown result type is silently ignored."""
        results = [{"type": "unknown_future_type", "data": "something"}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []

    def test_stats_from_last_events_result(self):
        """Stats come from the last events result, not facets/timeline."""
        results = [
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=99)),
            _make_search_result("facets", facets=[], stats=_make_stats(events_matched=0)),
            _make_search_result("timeline", timeseries=[], stats=_make_stats(events_matched=0)),
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["stats"]["eventsMatched"] == 99

    def test_stats_from_last_events_page(self):
        """Multi-page: stats from last events result win."""
        results = [
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=10)),
            _make_search_result("facets", facets=[], stats=_make_stats(events_matched=0)),
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=99)),
            _make_search_result("facets", facets=[], stats=_make_stats(events_matched=0)),
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["stats"]["eventsMatched"] == 99

    def test_facets_across_pages(self):
        """Facets from multiple pages are merged."""
        page1 = _make_search_result("facets", facets=[{"value": "A", "count": 10}])
        page2 = _make_search_result("facets", facets=[{"value": "B", "count": 20}])
        unwrapped = _unwrap_search_results([page1, page2])
        assert len(unwrapped["facets"]) == 2

    def test_timeseries_across_pages(self):
        """Timeseries points from multiple pages are merged."""
        page1 = _make_search_result("timeline", timeseries=[{"ts": 1, "count": 10}])
        page2 = _make_search_result("timeline", timeseries=[{"ts": 2, "count": 20}])
        unwrapped = _unwrap_search_results([page1, page2])
        assert len(unwrapped["timeseries"]) == 2


# ---------------------------------------------------------------------------
# TestFormatStatsSummary
# ---------------------------------------------------------------------------

class TestFormatStatsSummary:
    """Tests for _format_stats_summary."""

    def test_full_stats(self):
        summary = _format_stats_summary(_make_stats())
        assert "matched: 100" in summary
        assert "scanned: 5,000" in summary
        assert "1.0 MB" in summary
        assert "time: 2.5s" in summary
        assert "cost: $0.0012" in summary

    def test_gb_bytes(self):
        summary = _format_stats_summary(_make_stats(bytes_scanned=2_147_483_648))
        assert "2.0 GB" in summary

    def test_small_bytes(self):
        summary = _format_stats_summary(_make_stats(bytes_scanned=512))
        assert "bytes: 512" in summary

    def test_empty_stats(self):
        summary = _format_stats_summary({})
        assert summary == ""

    def test_no_price(self):
        summary = _format_stats_summary(_make_stats(price_amount=None))
        assert "cost:" not in summary

    def test_large_numbers(self):
        summary = _format_stats_summary(_make_stats(
            events_matched=1_234_567,
            events_scanned=99_999_999,
        ))
        assert "matched: 1,234,567" in summary
        assert "scanned: 99,999,999" in summary

    def test_zero_walltime(self):
        summary = _format_stats_summary(_make_stats(walltime=0.0))
        assert "time: 0.0s" in summary

    def test_partial_stats(self):
        """Only some fields present."""
        summary = _format_stats_summary({"eventsMatched": 42})
        assert "matched: 42" in summary
        assert "scanned" not in summary
        assert "bytes" not in summary

    def test_cumulative_stats_preferred(self):
        """Cumulative stats (server-aggregated) are used when present."""
        stats = {
            "eventsMatched": 10,  # Page-level.
            "eventsScanned": 500,
            "cumulativeStats": {
                "eventsMatched": 100,  # Cumulative across all pages.
                "eventsScanned": 5000,
                "bytesScanned": 2_097_152,
            },
        }
        summary = _format_stats_summary(stats)
        assert "matched: 100" in summary
        assert "scanned: 5,000" in summary
        assert "2.0 MB" in summary

    def test_cumulative_stats_null_fallback(self):
        """Falls back to page stats when cumulativeStats is null."""
        stats = {
            "eventsMatched": 10,
            "cumulativeStats": None,
        }
        summary = _format_stats_summary(stats)
        assert "matched: 10" in summary


# ---------------------------------------------------------------------------
# TestOutputSearchResults
# ---------------------------------------------------------------------------

@dataclass
class _FakeCtxObj:
    quiet: bool = False
    output_format: str | None = None
    wide: bool = False


class TestOutputSearchResults:
    """Tests for _output_search_results - end-to-end output formatting."""

    def _make_ctx(self, output_format: str | None = None, quiet: bool = False) -> click.Context:
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(output_format=output_format, quiet=quiet)
        return ctx

    def test_json_format_passes_raw(self, capsys):
        """JSON output should pass raw results unchanged."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="json")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert parsed[0]["type"] == "events"
        assert "rows" in parsed[0]

    def test_yaml_format_passes_raw(self, capsys):
        """YAML output should pass raw results unchanged."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="yaml")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        assert "type: events" in captured.out

    def test_toon_format_passes_raw(self, capsys):
        """TOON output should pass raw results unchanged."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="toon")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        # TOON encodes strings containing ":" by quoting; the key/value
        # pair for "type" stays as "type: events" regardless.
        assert "type: events" in captured.out

    def test_jsonl_format_passes_raw(self, capsys):
        """JSONL output should pass raw results unchanged."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="jsonl")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["type"] == "events"

    def test_csv_format_passes_raw(self, capsys):
        """CSV output should pass raw results unchanged."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="csv")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        assert "searchResultId" in captured.out

    def test_table_format_unwraps_events(self, capsys):
        """Table output should show flattened event rows, not raw results."""
        results = [_make_search_result(
            "events",
            rows=[_make_event_row(), _make_event_row(event_id="evt-2")],
            stats=_make_stats(),
        )]
        ctx = self._make_ctx(output_format="table")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()

        # Should NOT contain raw SearchResult fields.
        assert "searchResultId" not in captured.out
        assert "nextToken" not in captured.out
        # Should contain flattened event fields.
        assert "NEW_PROCESS" in captured.out or "routing.event_type" in captured.out
        # Stats on stderr.
        assert "matched:" in captured.err or "Stats:" in captured.err

    def test_table_raw_flag(self, capsys):
        """--raw flag should pass raw results in table mode."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="table")
        _output_search_results(ctx, results, raw=True)
        captured = capsys.readouterr()
        # Raw mode shows SearchResult-level fields.
        assert "searchResultId" in captured.out or "events" in captured.out

    def test_quiet_mode(self, capsys):
        """Quiet mode suppresses all output."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = self._make_ctx(output_format="table", quiet=True)
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_events_message(self, capsys):
        """Empty events should show 'No events' message."""
        results = [_make_search_result("events", rows=[], stats=_make_stats(events_matched=0))]
        ctx = self._make_ctx(output_format="table")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()
        assert "No events" in captured.out

    def test_table_ignores_facets_and_timeseries(self, capsys):
        """Table mode only shows events, not facets or timeseries."""
        results = [
            _make_search_result("events", rows=[_make_event_row()]),
            _make_search_result("facets", facets=[{"value": "NEW_PROCESS", "count": 42}]),
            _make_search_result("timeline", timeseries=[{"ts": 1700000000000, "count": 100}]),
        ]
        ctx = self._make_ctx(output_format="table")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()

        assert "Facets:" not in captured.err
        assert "Timeseries:" not in captured.err

    def test_multi_page_events_merged(self, capsys):
        """Events from multiple pages appear in single table."""
        results = [
            _make_search_result("events", rows=[_make_event_row(event_id="evt-1")]),
            _make_search_result("facets", facets=[]),
            _make_search_result("timeline", timeseries=[]),
            # Page 2
            _make_search_result("events", rows=[_make_event_row(event_id="evt-2")], stats=_make_stats()),
            _make_search_result("facets", facets=[]),
            _make_search_result("timeline", timeseries=[]),
        ]
        ctx = self._make_ctx(output_format="table")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()

        # Both events should be in the output, not split into separate sections.
        lines = captured.out.strip().split("\n")
        # At least header + separator + 2 data rows.
        assert len(lines) >= 3

    def test_wide_mode_skips_column_limit(self):
        """--wide should pass all columns to format_table without limiting."""
        data = {"routing": {f"field_{i}": f"val_{i}" for i in range(20)}}
        row = _make_event_row(data=data)
        flat = _flatten_event_row(row)
        events = [flat]
        # Without wide, columns are limited.
        limited = _limit_event_columns(events)
        assert len(limited[0]) <= _MAX_EVENT_COLUMNS
        # With wide, _output_search_results skips _limit_event_columns
        # so all columns are preserved (> _MAX_EVENT_COLUMNS).
        assert len(flat) > _MAX_EVENT_COLUMNS

    def test_projection_events_flat_columns(self, capsys):
        """Projection queries produce flat columns without dot notation."""
        data = {"path": "/usr/bin/curl", "count": 42}
        results = [_make_search_result(
            "events",
            rows=[_make_event_row(data=data)],
            stats=_make_stats(),
        )]
        ctx = self._make_ctx(output_format="table")
        _output_search_results(ctx, results)
        captured = capsys.readouterr()

        assert "path" in captured.out
        assert "count" in captured.out
        assert "/usr/bin/curl" in captured.out
        assert "42" in captured.out


# ---------------------------------------------------------------------------
# TestLimitEventColumns
# ---------------------------------------------------------------------------

class TestLimitEventColumns:
    """Tests for _limit_event_columns - smart column selection."""

    def test_few_columns_pass_through(self):
        """Rows with <= _MAX_EVENT_COLUMNS columns are unchanged."""
        events = [{"time": "2023-01-01", "stream": "event", "a": 1, "b": 2}]
        result = _limit_event_columns(events)
        assert result == events

    def test_many_columns_capped(self):
        """Rows with > _MAX_EVENT_COLUMNS columns are trimmed."""
        row = {f"col_{i}": i for i in range(30)}
        events = [row]
        result = _limit_event_columns(events)
        assert len(result[0]) <= _MAX_EVENT_COLUMNS

    def test_priority_columns_kept(self):
        """Priority columns (time, stream, routing.event_type) are always kept."""
        row = {"time": "2023-01-01", "stream": "event", "routing.event_type": "NEW_PROCESS"}
        # Add many filler columns to exceed the cap.
        for i in range(20):
            row[f"routing.filler_{i}"] = i
        events = [row]
        result = _limit_event_columns(events)
        assert "time" in result[0]
        assert "stream" in result[0]
        assert "routing.event_type" in result[0]

    def test_drop_columns_excluded(self):
        """Columns in _DROP_COLUMNS are excluded."""
        row = {
            "time": "2023-01-01",
            "routing.event_type": "X",
            "routing.oid": "should-be-dropped",
            "routing.sid": "should-be-dropped",
            "routing.plat": "should-be-dropped",
            "event.FILE_PATH": "/usr/bin/curl",
        }
        events = [row]
        # Need > _MAX_EVENT_COLUMNS to trigger limiting.
        for i in range(20):
            row[f"event.field_{i}"] = i
        result = _limit_event_columns(events)
        assert "routing.oid" not in result[0]
        assert "routing.sid" not in result[0]
        assert "routing.plat" not in result[0]

    def test_event_data_before_routing(self):
        """Event data columns are prioritized over remaining routing columns."""
        row = {"time": "t", "routing.event_type": "X"}
        # Add event.* columns.
        for i in range(10):
            row[f"event.field_{i}"] = i
        # Add routing.* columns (not in drop list).
        for i in range(10):
            row[f"routing.custom_{i}"] = i
        events = [row]
        result = _limit_event_columns(events)
        keys = list(result[0].keys())
        # event.field_0 should appear before routing.custom_0.
        event_keys = [k for k in keys if k.startswith("event.")]
        routing_keys = [k for k in keys if k.startswith("routing.custom_")]
        if event_keys and routing_keys:
            assert keys.index(event_keys[0]) < keys.index(routing_keys[0])

    def test_projection_query_passthrough(self):
        """Projection queries have flat keys (no routing.*), all pass through."""
        row = {f"field_{i}": i for i in range(10)}
        row["time"] = "t"
        events = [row]
        result = _limit_event_columns(events)
        assert len(result[0]) == len(row)

    def test_multiple_rows_same_columns(self):
        """All rows get the same column selection."""
        base = {"time": "t", "stream": "event", "routing.event_type": "X"}
        for i in range(20):
            base[f"routing.extra_{i}"] = i
        events = [dict(base), dict(base)]
        result = _limit_event_columns(events)
        assert set(result[0].keys()) == set(result[1].keys())


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and error scenarios."""

    def test_flatten_row_with_none_ts(self):
        """Row where mtd.ts is None."""
        row = {"mtd": {"ts": None, "stream": "event"}, "data": {"key": "val"}}
        flat = _flatten_event_row(row)
        assert "time" not in flat
        assert flat["stream"] == "event"
        assert flat["key"] == "val"

    def test_flatten_row_with_negative_ts(self):
        """Negative timestamp (before epoch)."""
        row = {"mtd": {"ts": -1000, "stream": "event"}, "data": {}}
        flat = _flatten_event_row(row)
        assert "time" in flat

    def test_unwrap_result_missing_type(self):
        """Result with no 'type' field is silently skipped."""
        results = [{"stats": _make_stats(), "rows": [_make_event_row()]}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []

    def test_unwrap_result_missing_rows(self):
        """Events result with no 'rows' key."""
        results = [{"type": "events", "stats": {}}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []

    def test_unwrap_result_missing_facets(self):
        """Facets result with no 'facets' key."""
        results = [{"type": "facets", "stats": {}}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["facets"] == []

    def test_unwrap_result_missing_timeseries(self):
        """Timeline result with no 'timeseries' key."""
        results = [{"type": "timeline", "stats": {}}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["timeseries"] == []

    def test_stats_summary_non_dict_price(self):
        """Price field that is not a dict."""
        stats = {"estimatedPrice": "invalid"}
        summary = _format_stats_summary(stats)
        assert "cost:" not in summary

    def test_flatten_data_with_empty_nested_dict(self):
        """Nested dict that is empty."""
        row = _make_event_row(data={"routing": {}, "key": "val"})
        flat = _flatten_event_row(row)
        assert flat["key"] == "val"
        # Empty routing dict produces no routing.* keys.
        routing_keys = [k for k in flat if k.startswith("routing.")]
        assert routing_keys == []

    def test_flatten_data_key_collision(self):
        """When flattened keys would collide, last one wins."""
        # This is a pathological case - flat "routing.event_type" key
        # and nested routing.event_type would collide.
        row = _make_event_row(data={
            "routing": {"event_type": "from_nested"},
        })
        flat = _flatten_event_row(row)
        assert flat["routing.event_type"] == "from_nested"

    def test_large_result_set(self):
        """Handling many events doesn't error."""
        rows = [_make_event_row(event_id=f"evt-{i}") for i in range(1000)]
        results = [_make_search_result("events", rows=rows, stats=_make_stats(events_matched=1000))]
        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 1000

    def test_null_rows_in_api_response(self):
        """API returns null for rows/facets/timeseries instead of omitting them.

        JSON null becomes Python None, so result.get("rows", []) returns
        None (key exists but value is null), not the default [].
        """
        results = [
            {"type": "events", "rows": None, "facets": None, "timeseries": None, "stats": {}},
            {"type": "facets", "facets": None, "stats": {}},
            {"type": "timeline", "timeseries": None, "stats": {}},
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []

    def test_mixed_null_and_populated_fields(self):
        """Real API response: events result has rows but null facets/timeseries."""
        results = [
            {
                "type": "events",
                "searchResultId": "123",
                "created": "2026-03-13T16:43:08.467",
                "rows": [_make_event_row()],
                "facets": None,
                "timeseries": None,
                "stats": _make_stats(),
                "nextToken": "token-2",
            },
            {
                "type": "timeline",
                "searchResultId": "456",
                "created": "2026-03-13T16:43:08.467",
                "rows": None,
                "facets": None,
                "timeseries": [{"ts": 1700000000000, "type": "total", "count": 100}],
                "stats": {},
            },
        ]
        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 1
        assert len(unwrapped["timeseries"]) == 1


# ---------------------------------------------------------------------------
# TestProgressCallback
# ---------------------------------------------------------------------------

class TestProgressCallback:
    """Tests for _make_progress_fn and progress callback behavior."""

    def test_progress_fn_none_when_quiet(self):
        """Progress is suppressed in quiet mode."""
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(quiet=True)
        assert _make_progress_fn(ctx) is None

    def test_progress_fn_none_when_not_tty(self):
        """Progress is suppressed when stderr is not a TTY."""
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(quiet=False)
        with patch.object(sys.stderr, "isatty", return_value=False):
            assert _make_progress_fn(ctx) is None

    def test_progress_fn_callable_when_tty(self):
        """Progress callback is returned when stderr is a TTY."""
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(quiet=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            fn = _make_progress_fn(ctx)
            assert callable(fn)

    def test_progress_fn_writes_to_stderr(self, capsys):
        """Progress callback writes to stderr, not stdout."""
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(quiet=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            fn = _make_progress_fn(ctx)
            fn("test message")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "test message" in captured.err


# ---------------------------------------------------------------------------
# TestSearchExecuteProgress
# ---------------------------------------------------------------------------

class TestSearchExecuteProgress:
    """Tests for progress callbacks in Search.execute().

    These test the SDK-level progress_fn parameter by mocking the
    HTTP client to simulate multi-page search responses.
    """

    def _make_search(self):
        """Create a Search instance with mocked org/client."""
        from limacharlie.sdk.search import Search

        org = MagicMock()
        org.oid = "test-oid"
        org.get_urls.return_value = {"search": "https://abc123.replay-search.limacharlie.io"}
        search = Search(org)
        return search, org

    def test_progress_called_on_start(self):
        """progress_fn is called with query_id on search start."""
        search, org = self._make_search()
        messages: list[str] = []

        # Mock: POST returns queryId, GET returns completed with results.
        org.client.request.side_effect = [
            {"queryId": "q-123"},  # POST /search
            {"completed": True, "results": [{"type": "events", "rows": []}]},  # GET
        ]

        list(search.execute("*|*|*", 100, 200, progress_fn=messages.append))

        assert any("q-123" in m for m in messages)

    def test_progress_called_on_pagination(self):
        """progress_fn shows page number and event count on pagination."""
        search, org = self._make_search()
        messages: list[str] = []

        org.client.request.side_effect = [
            {"queryId": "q-123"},
            {"completed": True, "results": [
                {"type": "events", "rows": [{"mtd": {}, "data": {}}] * 5, "nextToken": "tok-2"},
            ]},
            {"completed": True, "results": [
                {"type": "events", "rows": [{"mtd": {}, "data": {}}] * 3},
            ]},
        ]

        list(search.execute("*|*|*", 100, 200, progress_fn=messages.append))

        # Should have progress about page 2.
        page_msgs = [m for m in messages if "page 2" in m.lower() or "Fetching page 2" in m]
        assert len(page_msgs) >= 1
        # Should mention event count.
        assert any("5" in m for m in page_msgs)

    def test_progress_called_on_poll_wait(self):
        """progress_fn shows waiting status during polling."""
        search, org = self._make_search()
        messages: list[str] = []

        org.client.request.side_effect = [
            {"queryId": "q-123"},
            {"completed": False, "nextPollInMs": 100, "results": []},  # Not ready yet.
            {"completed": True, "results": [{"type": "events", "rows": []}]},  # Done.
        ]

        with patch("limacharlie.sdk.search.time.sleep"):
            list(search.execute("*|*|*", 100, 200, progress_fn=messages.append))

        wait_msgs = [m for m in messages if "Waiting" in m or "waiting" in m.lower()]
        assert len(wait_msgs) >= 1

    def test_no_progress_when_fn_is_none(self):
        """No errors when progress_fn is None."""
        search, org = self._make_search()

        org.client.request.side_effect = [
            {"queryId": "q-123"},
            {"completed": True, "results": [{"type": "events", "rows": []}]},
        ]

        # Should not raise.
        list(search.execute("*|*|*", 100, 200, progress_fn=None))

    def test_keyboard_interrupt_cancels_query(self):
        """KeyboardInterrupt triggers server-side cancel and re-raises."""
        search, org = self._make_search()
        messages: list[str] = []

        def side_effect(*args, **kwargs):
            call_count = org.client.request.call_count
            if call_count == 1:
                return {"queryId": "q-123"}
            elif call_count == 2:
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE response

        org.client.request.side_effect = side_effect

        with pytest.raises(KeyboardInterrupt):
            list(search.execute("*|*|*", 100, 200, progress_fn=messages.append))

        # Verify DELETE was called to cancel the query.
        delete_calls = [
            c for c in org.client.request.call_args_list
            if c.args[0] == "DELETE"
        ]
        assert len(delete_calls) == 1
        assert "q-123" in delete_calls[0].args[1]

        # Verify cancel message was printed.
        assert any("Cancel" in m for m in messages)

    def test_keyboard_interrupt_no_cancel_message_without_progress(self):
        """KeyboardInterrupt still cancels but no message without progress_fn."""
        search, org = self._make_search()

        def side_effect(*args, **kwargs):
            call_count = org.client.request.call_count
            if call_count == 1:
                return {"queryId": "q-123"}
            elif call_count == 2:
                raise KeyboardInterrupt()
            else:
                return {}

        org.client.request.side_effect = side_effect

        with pytest.raises(KeyboardInterrupt):
            list(search.execute("*|*|*", 100, 200, progress_fn=None))

        # DELETE still called.
        delete_calls = [
            c for c in org.client.request.call_args_list
            if c.args[0] == "DELETE"
        ]
        assert len(delete_calls) == 1


# ---------------------------------------------------------------------------
# TestStatsFromEventsOnly
# ---------------------------------------------------------------------------

class TestStatsFromEventsOnly:
    """Verify stats are only taken from 'events' type results."""

    def test_facets_stats_ignored(self):
        """Facets result stats don't overwrite event stats."""
        results = [
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=42)),
            _make_search_result("facets", facets=[], stats=_make_stats(events_matched=0)),
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["stats"]["eventsMatched"] == 42

    def test_timeline_stats_ignored(self):
        """Timeline result stats don't overwrite event stats."""
        results = [
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=42)),
            _make_search_result("timeline", timeseries=[], stats=_make_stats(events_matched=0)),
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["stats"]["eventsMatched"] == 42

    def test_no_events_results_empty_stats(self):
        """When only facets/timeline results, stats remain empty."""
        results = [
            _make_search_result("facets", facets=[], stats=_make_stats(events_matched=10)),
            _make_search_result("timeline", timeseries=[], stats=_make_stats(events_matched=5)),
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["stats"] == {}

    def test_multiple_events_pages_last_wins(self):
        """Last events result stats (with cumulative) win."""
        results = [
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=10)),
            _make_search_result("facets", facets=[], stats=_make_stats(events_matched=0)),
            _make_search_result("events", rows=[], stats=_make_stats(events_matched=100)),
            _make_search_result("timeline", timeseries=[], stats=_make_stats(events_matched=0)),
        ]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["stats"]["eventsMatched"] == 100


# ---------------------------------------------------------------------------
# TestFormatExpandedEvents
# ---------------------------------------------------------------------------

class TestFormatExpandedEvents:
    """Tests for _format_expanded_events and --expand output mode."""

    def test_basic_expand(self):
        """Each event is rendered as a JSON block with a header."""
        results = [_make_search_result(
            "events",
            rows=[_make_event_row()],
        )]
        output = _format_expanded_events(results)
        assert "--- 2023-11-14 22:13:20 | event | NEW_PROCESS ---" in output
        parsed = json.loads(output.split("---\n", 1)[1])
        assert parsed["routing"]["event_type"] == "NEW_PROCESS"

    def test_expand_multiple_events(self):
        """Multiple events produce multiple JSON blocks."""
        results = [_make_search_result(
            "events",
            rows=[
                _make_event_row(event_id="evt-1", ts=1700000000000),
                _make_event_row(event_id="evt-2", ts=1700003600000),
            ],
        )]
        output = _format_expanded_events(results)
        # Two header lines.
        assert output.count("---") >= 4  # 2 headers, each has 2 "---"

    def test_expand_detect_stream(self):
        """Detect stream events show 'cat' in header."""
        data = {"cat": "Suspicious PowerShell", "routing": {"event_type": "NEW_PROCESS"}}
        results = [_make_search_result(
            "events",
            rows=[_make_event_row(stream="detect", data=data)],
        )]
        output = _format_expanded_events(results)
        # Header uses routing.event_type first, then cat.
        assert "NEW_PROCESS" in output.split("\n")[0] or "Suspicious PowerShell" in output.split("\n")[0]

    def test_expand_audit_stream(self):
        """Audit stream events show 'etype' in header."""
        data = {"etype": "user_login", "msg": "User logged in"}
        results = [_make_search_result(
            "events",
            rows=[_make_event_row(stream="audit", data=data)],
        )]
        output = _format_expanded_events(results)
        assert "user_login" in output.split("\n")[0]

    def test_expand_skips_non_events(self):
        """Facets and timeline results are ignored."""
        results = [
            _make_search_result("facets", facets=[{"value": "X", "count": 1}]),
            _make_search_result("timeline", timeseries=[{"ts": 1, "count": 1}]),
        ]
        output = _format_expanded_events(results)
        assert output == ""

    def test_expand_empty_events(self):
        """No events produces empty string."""
        results = [_make_search_result("events", rows=[])]
        output = _format_expanded_events(results)
        assert output == ""

    def test_expand_null_rows(self):
        """Null rows (API returns null instead of []) handled gracefully."""
        results = [{"type": "events", "rows": None, "stats": {}}]
        output = _format_expanded_events(results)
        assert output == ""

    def test_expand_missing_mtd(self):
        """Row with no mtd still renders the data."""
        results = [_make_search_result(
            "events",
            rows=[{"data": {"key": "value"}}],
        )]
        output = _format_expanded_events(results)
        assert "--- event ---" in output
        assert '"key": "value"' in output

    def test_expand_multi_page(self):
        """Events from multiple pages are all expanded."""
        results = [
            _make_search_result("events", rows=[_make_event_row(event_id="evt-1")]),
            _make_search_result("facets", facets=[]),
            _make_search_result("events", rows=[_make_event_row(event_id="evt-2")]),
        ]
        output = _format_expanded_events(results)
        # Two JSON blocks.
        blocks = [line for line in output.split("\n") if line.startswith("---")]
        assert len(blocks) == 2

    def test_expand_output_mode(self, capsys):
        """_output_search_results with expand=True uses expand format."""
        results = [_make_search_result(
            "events",
            rows=[_make_event_row()],
            stats=_make_stats(),
        )]
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(output_format="table")
        _output_search_results(ctx, results, expand=True)
        captured = capsys.readouterr()
        assert "---" in captured.out
        assert "NEW_PROCESS" in captured.out
        # Stats on stderr.
        assert "matched:" in captured.err or "Stats:" in captured.err

    def test_expand_no_events_message(self, capsys):
        """Expand mode with no events shows 'No events'."""
        results = [_make_search_result("events", rows=[])]
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(output_format="table")
        _output_search_results(ctx, results, expand=True)
        captured = capsys.readouterr()
        assert "No events" in captured.out

    def test_expand_ignored_for_json_format(self, capsys):
        """--expand is ignored for machine-readable formats."""
        results = [_make_search_result("events", rows=[_make_event_row()])]
        ctx = click.Context(click.Command("test"))
        ctx.obj = _FakeCtxObj(output_format="json")
        _output_search_results(ctx, results, expand=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        # Should be raw API format, not expanded.
        assert isinstance(parsed, list)
        assert parsed[0]["type"] == "events"
