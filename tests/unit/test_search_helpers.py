"""Unit tests for search command helper functions.

Tests the internal helper functions in limacharlie.commands.search that are
not covered by CLI-level integration tests. Focuses on correctness, edge cases,
and boundary conditions for:

- _flatten_event_row: event data flattening for table display
- _unwrap_search_results: separating events, facets, timeseries, stats
- _format_stats_summary: stats string formatting
- _limit_event_columns: column selection with priority/drop/cap
- _format_expanded_event_block: expanded event block formatting
- _stream_table_events: streaming table with sampled column widths
- _stream_table_from_file: two-pass file-based table streaming
- _stream_search_output: format-based streaming dispatch
- _output_checkpoint_results: checkpoint output routing
"""

from __future__ import annotations

import json
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import click
import pytest

# Import cli first to ensure auto-discovery registers all commands.
# This prevents import order issues when pytest collects this file before
# test_search_checkpoint_cli.py (which uses CliRunner with the `cli` group).
import limacharlie.cli  # noqa: F401

from limacharlie.commands.search import (
    _flatten_event_row,
    _unwrap_search_results,
    _format_stats_summary,
    _format_file_size,
    _format_expanded_event_block,
    _format_expanded_events,
    _limit_event_columns,
    _output_validate_or_estimate,
    _stream_expanded_events,
    _stream_search_output,
    _stream_table_events,
    _stream_table_from_file,
    _resolve_token_expiry,
    _is_token_expired_error,
    _build_fresh_query_cmd,
    _warn,
    _warn_cost_if_over_30_days,
    _MAX_EVENT_COLUMNS,
    _PRIORITY_COLUMNS,
    _DROP_COLUMNS,
    _TABLE_SAMPLE_PAGES,
    _LARGE_TIME_RANGE_WARN_SECONDS,
    _CHECKPOINT_RECOMMEND_SECONDS,
    _COST_NOTICE_SECONDS,
    DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS,
)


# ---------------------------------------------------------------------------
# _warn helper
# ---------------------------------------------------------------------------

class TestWarnHelper:
    """Tests for _warn - advisory warning output with suppression."""

    def _make_ctx(self, no_warnings=False, quiet=False):
        ctx = MagicMock(spec=click.Context)
        ctx.obj = MagicMock()
        ctx.obj.no_warnings = no_warnings
        ctx.obj.quiet = quiet
        return ctx

    def test_prints_to_stderr_by_default(self):
        ctx = self._make_ctx()
        with patch("click.echo") as mock_echo:
            _warn(ctx, "test warning")
        mock_echo.assert_called_once_with("test warning", err=True)

    def test_suppressed_by_no_warnings(self):
        ctx = self._make_ctx(no_warnings=True)
        with patch("click.echo") as mock_echo:
            _warn(ctx, "test warning")
        mock_echo.assert_not_called()

    def test_suppressed_by_quiet(self):
        ctx = self._make_ctx(quiet=True)
        with patch("click.echo") as mock_echo:
            _warn(ctx, "test warning")
        mock_echo.assert_not_called()

    def test_suppressed_by_both_flags(self):
        ctx = self._make_ctx(no_warnings=True, quiet=True)
        with patch("click.echo") as mock_echo:
            _warn(ctx, "test warning")
        mock_echo.assert_not_called()


# ---------------------------------------------------------------------------
# _flatten_event_row
# ---------------------------------------------------------------------------

class TestFlattenEventRow:
    """Tests for _flatten_event_row - event data flattening for table display."""

    def test_basic_event_with_routing(self):
        row = {
            "mtd": {"ts": 1700000000000, "stream": "event"},
            "data": {
                "routing": {"event_type": "NEW_PROCESS", "hostname": "web-1"},
                "event": {"FILE_PATH": "/bin/bash", "COMMAND_LINE": "bash"},
            },
        }
        flat = _flatten_event_row(row)
        assert flat["time"] == "2023-11-14 22:13:20"
        assert flat["stream"] == "event"
        assert flat["routing.event_type"] == "NEW_PROCESS"
        assert flat["routing.hostname"] == "web-1"
        assert flat["event.FILE_PATH"] == "/bin/bash"
        assert flat["event.COMMAND_LINE"] == "bash"

    def test_missing_mtd(self):
        row = {"data": {"event": {"pid": 123}}}
        flat = _flatten_event_row(row)
        assert "time" not in flat
        assert "stream" not in flat
        assert flat["event.pid"] == 123

    def test_empty_mtd(self):
        row = {"mtd": {}, "data": {"routing": {"event_type": "DNS_REQUEST"}}}
        flat = _flatten_event_row(row)
        assert "time" not in flat
        assert "stream" not in flat
        assert flat["routing.event_type"] == "DNS_REQUEST"

    def test_missing_data(self):
        row = {"mtd": {"ts": 1700000000000}}
        flat = _flatten_event_row(row)
        assert flat["time"] == "2023-11-14 22:13:20"
        # No data keys
        assert len([k for k in flat if k not in ("time", "stream")]) == 0

    def test_data_is_non_dict(self):
        """When data is a string or number instead of dict, it becomes flat['data']."""
        row = {"mtd": {"ts": 1700000000000}, "data": "raw_string_data"}
        flat = _flatten_event_row(row)
        assert flat["data"] == "raw_string_data"

    def test_data_is_list(self):
        row = {"mtd": {}, "data": [1, 2, 3]}
        flat = _flatten_event_row(row)
        assert flat["data"] == [1, 2, 3]

    def test_deeply_nested_data_not_flattened(self):
        """Only one level of nesting is flattened; deeper structures stay as-is."""
        row = {
            "mtd": {},
            "data": {
                "event": {
                    "deeply": {"nested": {"structure": True}},
                },
            },
        }
        flat = _flatten_event_row(row)
        # event.deeply should be a dict, not further flattened
        assert isinstance(flat["event.deeply"], dict)
        assert flat["event.deeply"]["nested"]["structure"] is True

    def test_non_dict_values_at_top_level_data(self):
        """Top-level data values that are not dicts should be kept as-is."""
        row = {
            "mtd": {},
            "data": {
                "count": 42,
                "label": "test",
                "tags": ["a", "b"],
                "routing": {"event_type": "X"},
            },
        }
        flat = _flatten_event_row(row)
        assert flat["count"] == 42
        assert flat["label"] == "test"
        assert flat["tags"] == ["a", "b"]
        assert flat["routing.event_type"] == "X"

    def test_ts_invalid_overflow(self):
        """Invalid/overflow timestamp falls back to string representation."""
        row = {"mtd": {"ts": 99999999999999999}, "data": {}}
        flat = _flatten_event_row(row)
        assert flat["time"] == "99999999999999999"

    def test_ts_negative(self):
        row = {"mtd": {"ts": -1000}, "data": {}}
        flat = _flatten_event_row(row)
        # Should be a string since negative timestamp may raise on some platforms
        assert "time" in flat

    def test_ts_zero(self):
        row = {"mtd": {"ts": 0}, "data": {}}
        flat = _flatten_event_row(row)
        assert flat["time"] == "1970-01-01 00:00:00"

    def test_empty_row(self):
        flat = _flatten_event_row({})
        assert flat == {}

    def test_stream_only_no_ts(self):
        row = {"mtd": {"stream": "detect"}, "data": {}}
        flat = _flatten_event_row(row)
        assert flat["stream"] == "detect"
        assert "time" not in flat


# ---------------------------------------------------------------------------
# _unwrap_search_results
# ---------------------------------------------------------------------------

class TestUnwrapSearchResults:
    """Tests for _unwrap_search_results - separating result types."""

    def test_events_only(self):
        results = [{
            "type": "events",
            "rows": [
                {"mtd": {"ts": 1700000000000, "stream": "event"},
                 "data": {"event": {"pid": 1}}},
            ],
            "stats": {"eventsScanned": 100},
        }]
        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 1
        assert unwrapped["events"][0]["event.pid"] == 1
        assert unwrapped["stats"]["eventsScanned"] == 100
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []

    def test_mixed_types(self):
        results = [
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"x": 1}}}]},
            {"type": "facets", "facets": [{"field": "hostname", "values": []}]},
            {"type": "timeline", "timeseries": [{"ts": 1, "count": 5}]},
        ]
        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 1
        assert len(unwrapped["facets"]) == 1
        assert len(unwrapped["timeseries"]) == 1

    def test_empty_results(self):
        unwrapped = _unwrap_search_results([])
        assert unwrapped["events"] == []
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []
        assert unwrapped["stats"] == {}

    def test_stats_from_last_events_result(self):
        """Stats should come from events results, not facets/timeline."""
        results = [
            {"type": "events", "rows": [], "stats": {"eventsScanned": 100}},
            {"type": "events", "rows": [], "stats": {"eventsScanned": 200}},
            {"type": "facets", "facets": [], "stats": {"totalFacets": 50}},
        ]
        unwrapped = _unwrap_search_results(results)
        # Should have the last events stats, not facets stats
        assert unwrapped["stats"]["eventsScanned"] == 200
        assert "totalFacets" not in unwrapped["stats"]

    def test_events_with_none_rows(self):
        results = [{"type": "events", "rows": None}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []

    def test_events_with_empty_rows(self):
        results = [{"type": "events", "rows": []}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []

    def test_unknown_type_ignored(self):
        results = [{"type": "unknown_future_type", "data": {}}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []
        assert unwrapped["facets"] == []
        assert unwrapped["timeseries"] == []

    def test_result_without_type(self):
        results = [{"rows": [{"mtd": {}, "data": {}}]}]
        unwrapped = _unwrap_search_results(results)
        assert unwrapped["events"] == []

    def test_multiple_pages_events_accumulated(self):
        results = [
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"i": 0}}}]},
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"i": 1}}}]},
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"i": 2}}}]},
        ]
        unwrapped = _unwrap_search_results(results)
        assert len(unwrapped["events"]) == 3


# ---------------------------------------------------------------------------
# _format_stats_summary
# ---------------------------------------------------------------------------

class TestFormatStatsSummary:
    """Tests for _format_stats_summary - stats line formatting."""

    def test_all_fields_present(self):
        stats = {
            "eventsMatched": 42,
            "eventsScanned": 1000,
            "bytesScanned": 5_000_000,
            "walltime": 2.5,
            "estimatedPrice": {"amount": 0.0012},
        }
        summary = _format_stats_summary(stats)
        assert "matched: 42" in summary
        assert "scanned: 1,000" in summary
        assert "4.8 MB" in summary
        assert "time: 2.5s" in summary
        assert "cost: $0.0012" in summary

    def test_cumulative_stats_preferred(self):
        stats = {
            "eventsMatched": 10,
            "cumulativeStats": {"eventsMatched": 100},
        }
        summary = _format_stats_summary(stats)
        assert "matched: 100" in summary

    def test_empty_stats(self):
        assert _format_stats_summary({}) == ""

    def test_bytes_in_gb(self):
        stats = {"bytesScanned": 2_147_483_648}
        summary = _format_stats_summary(stats)
        assert "2.0 GB" in summary

    def test_bytes_small(self):
        stats = {"bytesScanned": 500}
        summary = _format_stats_summary(stats)
        assert "bytes: 500" in summary

    def test_bytes_in_mb(self):
        stats = {"bytesScanned": 1_048_576}
        summary = _format_stats_summary(stats)
        assert "1.0 MB" in summary

    def test_price_none_amount(self):
        stats = {"estimatedPrice": {"amount": None}}
        summary = _format_stats_summary(stats)
        assert "cost" not in summary

    def test_price_not_dict(self):
        stats = {"estimatedPrice": "free"}
        summary = _format_stats_summary(stats)
        assert "cost" not in summary

    def test_walltime_only(self):
        summary = _format_stats_summary({"walltime": 0.1})
        assert summary == "time: 0.1s"

    def test_zero_values(self):
        stats = {"eventsMatched": 0, "eventsScanned": 0}
        summary = _format_stats_summary(stats)
        assert "matched: 0" in summary
        assert "scanned: 0" in summary


# ---------------------------------------------------------------------------
# _limit_event_columns
# ---------------------------------------------------------------------------

class TestLimitEventColumns:
    """Tests for _limit_event_columns - column selection and capping."""

    def test_few_columns_pass_through(self):
        """Under _MAX_EVENT_COLUMNS, all columns pass through."""
        events = [{"a": 1, "b": 2, "c": 3}]
        result = _limit_event_columns(events)
        assert result == events

    def test_exactly_max_columns_pass_through(self):
        events = [{f"col_{i}": i for i in range(_MAX_EVENT_COLUMNS)}]
        result = _limit_event_columns(events)
        assert result == events

    def test_over_max_columns_capped(self):
        events = [{f"col_{i}": i for i in range(_MAX_EVENT_COLUMNS + 10)}]
        result = _limit_event_columns(events)
        assert len(result[0]) == _MAX_EVENT_COLUMNS

    def test_priority_columns_first(self):
        """Priority columns appear first when present."""
        # Create an event with priority columns mixed in with many others
        event = {}
        for i in range(20):
            event[f"extra_{i}"] = i
        event["time"] = "2023-01-01"
        event["stream"] = "event"
        event["routing.event_type"] = "NEW_PROCESS"

        result = _limit_event_columns([event])
        keys = list(result[0].keys())
        # Priority columns should appear first
        assert keys[0] == "time"
        assert keys[1] == "stream"
        assert keys[2] == "routing.event_type"

    def test_drop_columns_excluded(self):
        """Columns in _DROP_COLUMNS are excluded."""
        event = {"time": "t", "stream": "event"}
        for drop_col in list(_DROP_COLUMNS)[:5]:
            event[drop_col] = "should_be_dropped"
        # Add extra non-drop columns to exceed MAX
        for i in range(20):
            event[f"event.field_{i}"] = i

        result = _limit_event_columns([event])
        result_keys = set(result[0].keys())
        for drop_col in _DROP_COLUMNS:
            assert drop_col not in result_keys

    def test_non_routing_columns_before_routing(self):
        """Non-routing event data columns should come before remaining routing.* columns."""
        event = {
            "time": "t",
            "routing.event_type": "X",
            "routing.hostname": "h",
            "routing.custom_field": "c",
            "event.FILE_PATH": "/bin/bash",
            "event.COMMAND_LINE": "cmd",
        }
        # Add enough extra to exceed max
        for i in range(20):
            event[f"extra_{i}"] = i

        result = _limit_event_columns([event])
        keys = list(result[0].keys())
        # event.* should appear before routing.custom_field
        if "event.FILE_PATH" in keys and "routing.custom_field" in keys:
            assert keys.index("event.FILE_PATH") < keys.index("routing.custom_field")

    def test_empty_events_list(self):
        result = _limit_event_columns([])
        assert result == []

    def test_multiple_rows_same_columns(self):
        events = [
            {"a": 1, "b": 2},
            {"a": 3, "b": 4},
        ]
        result = _limit_event_columns(events)
        assert result == events

    def test_sparse_rows_all_keys_collected(self):
        """Keys from all rows are collected, not just the first."""
        cols = {f"col_{i}": i for i in range(_MAX_EVENT_COLUMNS + 5)}
        events = [
            {f"col_{i}": i for i in range(5)},
            {f"col_{i}": i for i in range(5, _MAX_EVENT_COLUMNS + 5)},
        ]
        result = _limit_event_columns(events)
        # Should be capped
        assert max(len(row) for row in result) <= _MAX_EVENT_COLUMNS


# ---------------------------------------------------------------------------
# _stream_table_events
# ---------------------------------------------------------------------------

class TestStreamTableEvents:
    """Tests for _stream_table_events - streaming table with sampled widths."""

    def setup_method(self):
        from limacharlie.output import set_wide_mode
        set_wide_mode(False)

    def teardown_method(self):
        from limacharlie.output import set_wide_mode
        set_wide_mode(False)

    def _make_results(self, n_pages, rows_per_page=2):
        """Generate N pages of event results."""
        results = []
        for page in range(n_pages):
            rows = []
            for j in range(rows_per_page):
                rows.append({
                    "mtd": {"ts": (1700000000 + page * 100 + j) * 1000, "stream": "event"},
                    "data": {
                        "routing": {"event_type": "NEW_PROCESS"},
                        "event": {"pid": page * rows_per_page + j},
                    },
                })
            result = {"type": "events", "rows": rows}
            if page == n_pages - 1:
                result["stats"] = {"eventsScanned": 1000, "eventsMatched": n_pages * rows_per_page}
            results.append(result)
        return results

    def _capture_stream_table(self, results_iter, wide=False):
        """Capture stdout and stderr from _stream_table_events."""
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        with patch("sys.stdout", stdout_capture), \
             patch("click.echo") as mock_echo:
            # click.echo writes to stdout/stderr based on err param
            stdout_lines = []
            stderr_lines = []

            def echo_side_effect(msg="", err=False, nl=True, **kwargs):
                target = stderr_lines if err else stdout_lines
                target.append(str(msg))

            mock_echo.side_effect = echo_side_effect
            _stream_table_events(results_iter, wide=wide)
        return "\n".join(stdout_lines), "\n".join(stderr_lines)

    def test_empty_iterator(self):
        stdout, _ = self._capture_stream_table(iter([]))
        assert "No events" in stdout

    def test_non_event_types_only(self):
        results = [{"type": "facets", "data": {}}]
        stdout, _ = self._capture_stream_table(iter(results))
        assert "No events" in stdout

    def test_events_with_empty_rows(self):
        results = [{"type": "events", "rows": []}]
        stdout, _ = self._capture_stream_table(iter(results))
        assert "No events" in stdout

    def test_single_page_renders_header_and_rows(self):
        results = self._make_results(1, rows_per_page=3)
        stdout, stderr = self._capture_stream_table(iter(results))
        assert "time" in stdout
        assert "routing.event_type" in stdout
        assert "event.pid" in stdout
        # Check event count on stderr
        assert "3 events" in stderr

    def test_multi_page_streams_beyond_sample(self):
        """Results beyond the sample pages should still be rendered."""
        n_pages = _TABLE_SAMPLE_PAGES + 3
        results = self._make_results(n_pages, rows_per_page=2)
        stdout, stderr = self._capture_stream_table(iter(results))
        total = n_pages * 2
        assert f"{total} events" in stderr

    def test_stats_shown_on_stderr(self):
        results = [{
            "type": "events",
            "rows": [{"mtd": {"ts": 1700000000000}, "data": {"event": {"x": 1}}}],
            "stats": {"eventsScanned": 500, "eventsMatched": 10, "walltime": 1.2},
        }]
        _, stderr = self._capture_stream_table(iter(results))
        assert "Stats:" in stderr
        assert "scanned: 500" in stderr

    def test_wide_mode_does_not_limit_columns(self):
        """Wide mode should show all columns without truncation."""
        # Create an event with many columns
        data = {}
        for i in range(25):
            data[f"field_{i}"] = f"value_{i}"
        results = [{
            "type": "events",
            "rows": [{"mtd": {"ts": 1700000000000}, "data": data}],
        }]
        stdout, _ = self._capture_stream_table(iter(results), wide=True)
        # In wide mode, all 25 fields should be present
        for i in range(25):
            assert f"field_{i}" in stdout

    def test_generator_input(self):
        """Accepts a generator (not just a list)."""
        def gen():
            for r in self._make_results(2):
                yield r
        stdout, stderr = self._capture_stream_table(gen())
        assert "4 events" in stderr

    def test_none_rows_handled(self):
        results = [{"type": "events", "rows": None}]
        stdout, _ = self._capture_stream_table(iter(results))
        assert "No events" in stdout


# ---------------------------------------------------------------------------
# _stream_table_from_file
# ---------------------------------------------------------------------------

class TestStreamTableFromFile:
    """Tests for _stream_table_from_file - two-pass file-based streaming."""

    def setup_method(self):
        from limacharlie.output import set_wide_mode
        set_wide_mode(False)

    def teardown_method(self):
        from limacharlie.output import set_wide_mode
        set_wide_mode(False)

    def _make_jsonl_file(self, tmp_path, results):
        """Write results to a JSONL file."""
        path = str(tmp_path / "test.jsonl")
        with open(path, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        return path

    def _capture_file_table(self, path, wide=False):
        stdout_lines = []
        stderr_lines = []

        def echo_side_effect(msg="", err=False, nl=True, **kwargs):
            target = stderr_lines if err else stdout_lines
            target.append(str(msg))

        with patch("click.echo") as mock_echo:
            mock_echo.side_effect = echo_side_effect
            _stream_table_from_file(path, wide=wide)
        return "\n".join(stdout_lines), "\n".join(stderr_lines)

    def test_single_event(self, tmp_path):
        results = [{
            "type": "events",
            "rows": [{"mtd": {"ts": 1700000000000, "stream": "event"},
                      "data": {"routing": {"event_type": "X"}, "event": {"pid": 1}}}],
        }]
        path = self._make_jsonl_file(tmp_path, results)
        stdout, stderr = self._capture_file_table(path)
        assert "event.pid" in stdout
        assert "1 event" in stderr

    def test_multiple_events(self, tmp_path):
        results = [{
            "type": "events",
            "rows": [
                {"mtd": {"ts": 1700000000000}, "data": {"event": {"pid": i}}}
                for i in range(5)
            ],
        }]
        path = self._make_jsonl_file(tmp_path, results)
        stdout, stderr = self._capture_file_table(path)
        assert "5 events" in stderr

    def test_wide_mode(self, tmp_path):
        data = {}
        for i in range(25):
            data[f"field_{i}"] = f"val_{i}"
        results = [{
            "type": "events",
            "rows": [{"mtd": {"ts": 1700000000000}, "data": data}],
        }]
        path = self._make_jsonl_file(tmp_path, results)
        stdout, _ = self._capture_file_table(path, wide=True)
        for i in range(25):
            assert f"field_{i}" in stdout

    def test_stats_displayed(self, tmp_path):
        results = [{
            "type": "events",
            "rows": [{"mtd": {}, "data": {"event": {"x": 1}}}],
            "stats": {"eventsScanned": 999, "eventsMatched": 1},
        }]
        path = self._make_jsonl_file(tmp_path, results)
        _, stderr = self._capture_file_table(path)
        assert "Stats:" in stderr
        assert "scanned: 999" in stderr

    def test_mixed_result_types(self, tmp_path):
        """Non-event results should be skipped."""
        results = [
            {"type": "facets", "facets": [{"field": "host"}]},
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"x": 1}}}]},
            {"type": "timeline", "timeseries": []},
        ]
        path = self._make_jsonl_file(tmp_path, results)
        stdout, stderr = self._capture_file_table(path)
        assert "1 event" in stderr

    def test_events_across_multiple_lines(self, tmp_path):
        """Each JSONL line is a separate SearchResult."""
        results = [
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"i": 0}}}]},
            {"type": "events", "rows": [{"mtd": {}, "data": {"event": {"i": 1}}}]},
        ]
        path = self._make_jsonl_file(tmp_path, results)
        _, stderr = self._capture_file_table(path)
        assert "2 events" in stderr

    def test_column_widths_exact_across_all_rows(self, tmp_path):
        """Two-pass approach computes exact widths from all rows.

        In wide mode, values are not truncated by terminal width,
        so both short and long values appear in full.
        """
        results = [
            {"type": "events", "rows": [
                {"mtd": {}, "data": {"event": {"name": "short"}}},
            ]},
            {"type": "events", "rows": [
                {"mtd": {}, "data": {"event": {"name": "this_is_a_much_longer_value"}}},
            ]},
        ]
        path = self._make_jsonl_file(tmp_path, results)
        # Use wide mode so terminal width doesn't truncate
        stdout, _ = self._capture_file_table(path, wide=True)
        assert "short" in stdout
        assert "this_is_a_much_longer_value" in stdout


# ---------------------------------------------------------------------------
# _stream_search_output - format dispatch
# ---------------------------------------------------------------------------

class TestStreamSearchOutputDispatch:
    """Tests for _stream_search_output format dispatching."""

    def _make_ctx(self, fmt="table", quiet=False, wide=False):
        ctx = MagicMock(spec=click.Context)
        ctx.obj = MagicMock()
        ctx.obj.output_format = fmt
        ctx.obj.quiet = quiet
        ctx.obj.wide = wide
        return ctx

    def test_quiet_mode_returns_true_without_consuming(self):
        ctx = self._make_ctx(quiet=True)
        consumed = []
        def gen():
            consumed.append(1)
            yield {"type": "events", "rows": []}
        result = _stream_search_output(ctx, gen())
        assert result is True
        # Generator should NOT be consumed
        assert consumed == []

    def test_jsonl_format_handled(self):
        ctx = self._make_ctx(fmt="jsonl")
        results = [{"type": "events", "rows": []}]
        result = _stream_search_output(ctx, iter(results))
        assert result is True

    def test_json_format_handled(self):
        ctx = self._make_ctx(fmt="json")
        results = [{"type": "events", "rows": []}]
        result = _stream_search_output(ctx, iter(results))
        assert result is True

    def test_table_expand_handled(self):
        ctx = self._make_ctx(fmt="table")
        results = [{"type": "events", "rows": [
            {"mtd": {"ts": 1700000000000}, "data": {"event": {"x": 1}}},
        ]}]
        result = _stream_search_output(ctx, iter(results), expand=True)
        assert result is True

    def test_table_non_expand_handled(self):
        ctx = self._make_ctx(fmt="table")
        results = [{"type": "events", "rows": [
            {"mtd": {"ts": 1700000000000}, "data": {"event": {"x": 1}}},
        ]}]
        result = _stream_search_output(ctx, iter(results))
        assert result is True

    def test_csv_not_handled(self):
        ctx = self._make_ctx(fmt="csv")
        consumed = []
        def gen():
            consumed.append(1)
            yield {"type": "events"}
        result = _stream_search_output(ctx, gen())
        assert result is False
        assert consumed == []  # Should not consume

    def test_yaml_not_handled(self):
        ctx = self._make_ctx(fmt="yaml")
        result = _stream_search_output(ctx, iter([]))
        assert result is False

    def test_table_raw_not_handled(self):
        ctx = self._make_ctx(fmt="table")
        consumed = []
        def gen():
            consumed.append(1)
            yield {"type": "events"}
        result = _stream_search_output(ctx, gen(), raw=True)
        assert result is False
        assert consumed == []


# ---------------------------------------------------------------------------
# _resolve_token_expiry
# ---------------------------------------------------------------------------

class TestResolveTokenExpiry:
    """Tests for _resolve_token_expiry - priority chain for token expiry."""

    def test_cli_value_takes_precedence(self):
        assert _resolve_token_expiry(8.0) == 8.0

    def test_default_when_no_cli_no_config(self):
        with patch("limacharlie.commands.search.get_config_value", return_value=None):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_config_value_used_when_no_cli(self):
        with patch("limacharlie.commands.search.get_config_value", return_value="12"):
            assert _resolve_token_expiry(None) == 12.0

    def test_invalid_config_value_falls_back_to_default(self):
        with patch("limacharlie.commands.search.get_config_value", return_value="not_a_number"):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_zero_config_value_falls_back_to_default(self):
        with patch("limacharlie.commands.search.get_config_value", return_value="0"):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_negative_config_value_falls_back_to_default(self):
        with patch("limacharlie.commands.search.get_config_value", return_value="-5"):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_cli_value_zero_still_used(self):
        """CLI value 0 is technically valid (user explicitly passed it)."""
        assert _resolve_token_expiry(0.0) == 0.0


# ---------------------------------------------------------------------------
# _is_token_expired_error (extended edge cases)
# ---------------------------------------------------------------------------

class TestIsTokenExpiredErrorExtended:
    """Extended edge cases for _is_token_expired_error."""

    def test_search_error_with_mixed_case(self):
        from limacharlie.errors import SearchError
        exc = SearchError("Query Not Found on server")
        assert _is_token_expired_error(exc) is True

    def test_search_error_partial_keyword_match(self):
        from limacharlie.errors import SearchError
        # "query" alone shouldn't match
        exc = SearchError("query failed with timeout")
        assert _is_token_expired_error(exc) is False

    def test_not_found_error_always_true(self):
        from limacharlie.errors import NotFoundError
        exc = NotFoundError("404: resource not found")
        assert _is_token_expired_error(exc) is True

    def test_regular_exception_not_matched(self):
        exc = RuntimeError("something went wrong")
        assert _is_token_expired_error(exc) is False

    def test_connection_error_not_matched(self):
        exc = ConnectionError("connection refused")
        assert _is_token_expired_error(exc) is False

    def test_search_error_token_expired_keyword(self):
        from limacharlie.errors import SearchError
        exc = SearchError("token expired for query abc123")
        assert _is_token_expired_error(exc) is True


# ---------------------------------------------------------------------------
# _build_fresh_query_cmd
# ---------------------------------------------------------------------------

class TestBuildFreshQueryCmdExtended:
    """Extended tests for _build_fresh_query_cmd."""

    def test_minimal_metadata(self):
        meta = {"query": "q", "start_time": 100, "end_time": 200}
        cmd = _build_fresh_query_cmd(meta, "/tmp/data.jsonl")
        assert "--query" in cmd
        assert "--start 100" in cmd
        assert "--end 200" in cmd
        assert "--force" in cmd
        assert "--checkpoint" in cmd

    def test_with_all_fields(self):
        meta = {"query": "q", "start_time": 100, "end_time": 200,
                "stream": "event", "limit": 500}
        cmd = _build_fresh_query_cmd(meta, "/tmp/data.jsonl")
        assert "--stream" in cmd
        assert "--limit 500" in cmd

    def test_empty_metadata_fields(self):
        meta = {"query": "", "start_time": "", "end_time": ""}
        cmd = _build_fresh_query_cmd(meta, "/tmp/data.jsonl")
        assert "--query" in cmd
        assert "--force" in cmd

    def test_path_with_spaces_quoted(self):
        meta = {"query": "q", "start_time": 100, "end_time": 200}
        cmd = _build_fresh_query_cmd(meta, "/tmp/my search data.jsonl")
        assert "my search data" in cmd


# ---------------------------------------------------------------------------
# _format_expanded_event_block / _format_expanded_events
# ---------------------------------------------------------------------------

class TestFormatExpandedEvents:
    """Tests for expanded event formatting functions."""

    def test_format_expanded_events_multiple_results(self):
        results = [
            {"type": "events", "rows": [
                {"mtd": {"ts": 1700000000000, "stream": "event"},
                 "data": {"routing": {"event_type": "X"}, "event": {"a": 1}}},
                {"mtd": {"ts": 1700000001000, "stream": "event"},
                 "data": {"routing": {"event_type": "Y"}, "event": {"b": 2}}},
            ]},
        ]
        output = _format_expanded_events(results)
        assert output.count("---") >= 2
        assert "X" in output
        assert "Y" in output

    def test_format_expanded_events_non_event_types_skipped(self):
        results = [
            {"type": "facets", "rows": [{"mtd": {}, "data": {}}]},
            {"type": "events", "rows": [
                {"mtd": {"ts": 1700000000000}, "data": {"event": {"a": 1}}},
            ]},
        ]
        output = _format_expanded_events(results)
        assert "---" in output

    def test_format_expanded_events_empty(self):
        output = _format_expanded_events([])
        assert output == ""

    def test_format_expanded_events_no_event_rows(self):
        results = [{"type": "events", "rows": []}]
        output = _format_expanded_events(results)
        assert output == ""

    def test_block_with_cat_field(self):
        row = {"mtd": {}, "data": {"cat": "detection_name"}}
        block = _format_expanded_event_block(row)
        assert "detection_name" in block

    def test_block_with_etype_field(self):
        row = {"mtd": {}, "data": {"etype": "audit_event"}}
        block = _format_expanded_event_block(row)
        assert "audit_event" in block

    def test_block_routing_event_type_preferred(self):
        """routing.event_type takes precedence over cat and etype."""
        row = {
            "mtd": {},
            "data": {
                "routing": {"event_type": "NEW_PROCESS"},
                "cat": "detection",
                "etype": "audit",
            },
        }
        block = _format_expanded_event_block(row)
        assert "NEW_PROCESS" in block

    def test_block_no_data(self):
        row = {"mtd": {"ts": 1700000000000}}
        block = _format_expanded_event_block(row)
        assert "---" in block
        assert "2023-11-14" in block

    def test_block_body_is_valid_json(self):
        row = {"mtd": {}, "data": {"event": {"nested": {"deep": True}}}}
        block = _format_expanded_event_block(row)
        # Extract body (after the --- header --- line)
        lines = block.split("\n")
        body = "\n".join(lines[1:])
        parsed = json.loads(body)
        assert parsed["event"]["nested"]["deep"] is True


# ---------------------------------------------------------------------------
# _stream_expanded_events
# ---------------------------------------------------------------------------

class TestStreamExpandedEventsUnit:
    """Unit tests for _stream_expanded_events."""

    def test_returns_true_when_events_exist(self):
        results = [{"type": "events", "rows": [
            {"mtd": {"ts": 1700000000000}, "data": {"event": {"x": 1}}},
        ]}]
        with patch("click.echo"):
            result = _stream_expanded_events(iter(results))
        assert result is True

    def test_returns_false_when_no_events(self):
        results = [{"type": "facets", "data": {}}]
        with patch("click.echo"):
            result = _stream_expanded_events(iter(results))
        assert result is False

    def test_returns_false_for_empty_iterator(self):
        with patch("click.echo"):
            result = _stream_expanded_events(iter([]))
        assert result is False

    def test_multiple_events_across_pages(self):
        results = [
            {"type": "events", "rows": [
                {"mtd": {}, "data": {"event": {"i": 0}}},
            ]},
            {"type": "events", "rows": [
                {"mtd": {}, "data": {"event": {"i": 1}}},
                {"mtd": {}, "data": {"event": {"i": 2}}},
            ]},
        ]
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(msg)):
            result = _stream_expanded_events(iter(results))
        assert result is True
        assert len(echoed) == 3  # 3 events, 3 echo calls


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

class TestConstants:
    """Sanity checks for module constants."""

    def test_max_event_columns_reasonable(self):
        assert 5 <= _MAX_EVENT_COLUMNS <= 50

    def test_priority_columns_no_duplicates(self):
        assert len(_PRIORITY_COLUMNS) == len(set(_PRIORITY_COLUMNS))

    def test_drop_columns_no_overlap_with_priority(self):
        overlap = set(_PRIORITY_COLUMNS) & _DROP_COLUMNS
        assert overlap == set(), f"Overlap: {overlap}"

    def test_table_sample_pages_positive(self):
        assert _TABLE_SAMPLE_PAGES > 0

    def test_large_time_range_warn_seconds(self):
        assert _LARGE_TIME_RANGE_WARN_SECONDS == 7 * 24 * 3600

    def test_checkpoint_recommend_seconds(self):
        assert _CHECKPOINT_RECOMMEND_SECONDS == 14 * 24 * 3600

    def test_cost_notice_seconds(self):
        assert _COST_NOTICE_SECONDS == 30 * 24 * 3600

    def test_cost_notice_larger_than_checkpoint_recommend(self):
        assert _COST_NOTICE_SECONDS > _CHECKPOINT_RECOMMEND_SECONDS

    def test_checkpoint_recommend_larger_than_warn(self):
        assert _CHECKPOINT_RECOMMEND_SECONDS > _LARGE_TIME_RANGE_WARN_SECONDS

    def test_default_token_expiry_positive(self):
        assert DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS > 0


# ---------------------------------------------------------------------------
# _format_file_size edge cases
# ---------------------------------------------------------------------------

class TestFormatFileSizeEdgeCases:
    """Extended edge cases for _format_file_size."""

    def test_zero_bytes(self):
        assert _format_file_size(0) == "0 B"

    def test_one_byte(self):
        assert _format_file_size(1) == "1 B"

    def test_1023_bytes(self):
        assert _format_file_size(1023) == "1023 B"

    def test_exactly_1024_bytes(self):
        result = _format_file_size(1024)
        assert "KB" in result
        assert "1.0" in result

    def test_exactly_1_mb(self):
        result = _format_file_size(1024 * 1024)
        assert "MB" in result
        assert "1.0" in result

    def test_exactly_1_gb(self):
        result = _format_file_size(1024 ** 3)
        assert "GB" in result

    def test_exactly_1_tb(self):
        result = _format_file_size(1024 ** 4)
        assert "TB" in result

    def test_very_large_file(self):
        result = _format_file_size(1024 ** 5)
        assert "TB" in result  # Should cap at TB


# ---------------------------------------------------------------------------
# _warn_cost_if_over_30_days
# ---------------------------------------------------------------------------

class TestWarnCostIfOver30Days:
    """Tests for the billing cost notice when search spans > 30 days.

    LimaCharlie includes the last 30 days of telemetry in the base
    subscription. Searches beyond that window may incur additional charges.
    The server-side threshold is strictly >30 days.
    """

    def _make_ctx(self, no_warnings=False, quiet=False):
        ctx = MagicMock(spec=click.Context)
        ctx.obj = MagicMock()
        ctx.obj.no_warnings = no_warnings
        ctx.obj.quiet = quiet
        return ctx

    def _capture_warning(self, query, start, end, stream=None, checkpoint_path=None,
                         no_warnings=False):
        """Call _warn_cost_if_over_30_days and capture stderr output."""
        ctx = self._make_ctx(no_warnings=no_warnings)
        stderr_lines = []

        def echo_side_effect(msg="", err=False, **kwargs):
            if err:
                stderr_lines.append(str(msg))

        with patch("click.echo", side_effect=echo_side_effect):
            _warn_cost_if_over_30_days(ctx, query, start, end, stream, checkpoint_path)
        return "\n".join(stderr_lines)

    def test_no_warning_under_30_days(self):
        """Searches within 30 days should not trigger the notice."""
        start = 1700000000
        end = start + 29 * 86400  # 29 days
        output = self._capture_warning("* | * | *", start, end)
        assert output == ""

    def test_no_warning_exactly_30_days(self):
        """Exactly 30 days should not trigger (threshold is strictly >30)."""
        start = 1700000000
        end = start + 30 * 86400  # exactly 30 days
        output = self._capture_warning("* | * | *", start, end)
        assert output == ""

    def test_warning_at_30_days_plus_one_second(self):
        """One second over 30 days should trigger the notice."""
        start = 1700000000
        end = start + 30 * 86400 + 1
        output = self._capture_warning("* | * | *", start, end)
        assert "may incur additional costs" in output

    def test_warning_at_31_days(self):
        start = 1700000000
        end = start + 31 * 86400
        output = self._capture_warning("* | * | *", start, end)
        assert "31 days" in output
        assert "may incur additional costs" in output

    def test_warning_at_90_days(self):
        start = 1700000000
        end = start + 90 * 86400
        output = self._capture_warning("* | * | *", start, end)
        assert "90 days" in output

    def test_warning_includes_estimate_command(self):
        """The notice should show the estimate command."""
        start = 1700000000
        end = start + 45 * 86400
        output = self._capture_warning("* | NEW_PROCESS | *", start, end)
        assert "limacharlie search estimate" in output
        assert "--query" in output
        assert f"--start {start}" in output
        assert f"--end {end}" in output

    def test_estimate_command_includes_stream(self):
        """When stream is provided, estimate command should include --stream."""
        start = 1700000000
        end = start + 45 * 86400
        output = self._capture_warning("q", start, end, stream="event")
        assert "--stream" in output
        assert "event" in output

    def test_estimate_command_no_stream_when_none(self):
        """When stream is None, estimate command should not include --stream."""
        start = 1700000000
        end = start + 45 * 86400
        output = self._capture_warning("q", start, end, stream=None)
        assert "--stream" not in output

    def test_query_with_special_chars_quoted(self):
        """Queries with special characters should be shell-quoted."""
        start = 1700000000
        end = start + 45 * 86400
        query = "* | NEW_PROCESS | event/COMMAND_LINE contains 'curl'"
        output = self._capture_warning(query, start, end)
        # Should be shell-quoted (single quotes escaped)
        assert "contains" in output
        assert "--query" in output

    def test_no_warning_for_short_range(self):
        """1-hour search should produce no warning."""
        start = 1700000000
        end = start + 3600
        output = self._capture_warning("q", start, end)
        assert output == ""

    def test_constant_matches_30_days(self):
        """Verify _COST_NOTICE_SECONDS is exactly 30 days."""
        assert _COST_NOTICE_SECONDS == 30 * 24 * 3600

    def test_no_warnings_flag_suppresses(self):
        """--no-warnings should suppress the cost notice."""
        start = 1700000000
        end = start + 45 * 86400
        output = self._capture_warning("q", start, end, no_warnings=True)
        assert output == ""


class TestCostWarningCli:
    """CLI-level tests for the billing cost notice.

    Tests that the notice appears in actual CLI invocations via CliRunner.
    """

    @pytest.fixture
    def mock_org(self):
        client = MagicMock()
        client.oid = "test-oid"
        client.get_jwt.return_value = "fake-jwt"
        org = MagicMock()
        org.oid = "test-oid"
        org.client = client
        org.get_urls.return_value = {"search": "abc.replay-search.limacharlie.io"}
        return org

    def _make_search_responses(self, pages=1):
        responses = [{"queryId": "q-test"}]
        for i in range(pages):
            is_last = i == pages - 1
            result = {
                "type": "events",
                "rows": [{"mtd": {"ts": 1700000000000}, "data": {"event": {"x": 1}}}],
            }
            if not is_last:
                result["nextToken"] = f"tok-{i + 1}"
            responses.append({"results": [result], "completed": True})
        responses.append({})  # DELETE cleanup
        return responses

    def _invoke(self, mock_org, start, end, output_fmt="jsonl", extra_args=None):
        from click.testing import CliRunner
        from limacharlie.cli import cli
        mock_org.client.request.side_effect = self._make_search_responses(1)
        runner = CliRunner()
        args = ["--oid", "test-oid", "--output", output_fmt,
                "search", "run",
                "--query", "* | * | *",
                "--start", str(start), "--end", str(end)]
        if extra_args:
            args.extend(extra_args)
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, args)

    def test_cost_notice_shown_for_31_day_search(self, mock_org):
        start = 1700000000
        end = start + 31 * 86400
        result = self._invoke(mock_org, start, end)
        assert result.exit_code == 0, result.output
        # Notice goes to stderr, which CliRunner mixes into output
        assert "may incur additional costs" in result.output

    def test_cost_notice_not_shown_for_29_day_search(self, mock_org):
        start = 1700000000
        end = start + 29 * 86400
        result = self._invoke(mock_org, start, end)
        assert result.exit_code == 0, result.output
        assert "may incur additional costs" not in result.output

    def test_cost_notice_shown_with_checkpoint(self, mock_org, tmp_path):
        """Cost notice should also fire when using --checkpoint."""
        start = 1700000000
        end = start + 45 * 86400
        checkpoint_path = str(tmp_path / "cost_test.jsonl")
        result = self._invoke(mock_org, start, end,
                              extra_args=["--checkpoint", checkpoint_path])
        assert result.exit_code == 0, result.output
        assert "may incur additional costs" in result.output
        assert "limacharlie search estimate" in result.output

    def test_cost_notice_includes_estimate_cmd(self, mock_org):
        start = 1700000000
        end = start + 45 * 86400
        result = self._invoke(mock_org, start, end)
        assert "limacharlie search estimate" in result.output
        assert f"--start {start}" in result.output
        assert f"--end {end}" in result.output

    def test_cost_notice_not_shown_exactly_30_days(self, mock_org):
        start = 1700000000
        end = start + 30 * 86400
        result = self._invoke(mock_org, start, end)
        assert result.exit_code == 0, result.output
        assert "may incur additional costs" not in result.output

    def test_cost_notice_shown_for_all_output_formats(self, mock_org):
        """Cost notice should fire regardless of output format."""
        start = 1700000000
        end = start + 45 * 86400
        for fmt in ("jsonl", "json", "table"):
            result = self._invoke(mock_org, start, end, output_fmt=fmt)
            assert "may incur additional costs" in result.output, \
                f"Cost notice missing for --output {fmt}"

    def test_no_warnings_flag_suppresses_cost_notice(self, mock_org):
        """--no-warnings should suppress the cost notice at CLI level."""
        start = 1700000000
        end = start + 45 * 86400
        result = self._invoke(mock_org, start, end,
                              extra_args=["--no-warnings"])
        assert result.exit_code == 0, result.output
        assert "may incur additional costs" not in result.output

    def test_no_warnings_flag_suppresses_checkpoint_warning(self, mock_org):
        """--no-warnings should suppress the checkpoint recommendation."""
        start = 1700000000
        end = start + 15 * 86400  # 15 days, triggers checkpoint recommendation
        result = self._invoke(mock_org, start, end,
                              extra_args=["--no-warnings"])
        assert result.exit_code == 0, result.output
        assert "all progress will be lost" not in result.output

    def test_no_warnings_still_shows_results(self, mock_org):
        """--no-warnings should NOT suppress actual results output."""
        start = 1700000000
        end = start + 45 * 86400
        result = self._invoke(mock_org, start, end,
                              extra_args=["--no-warnings"])
        assert result.exit_code == 0, result.output
        # JSONL output should still have the result
        assert "events" in result.output or "{" in result.output


# ---------------------------------------------------------------------------
# _output_validate_or_estimate
# ---------------------------------------------------------------------------

class TestOutputValidateOrEstimate:
    """Tests for validate/estimate output formatting."""

    def _make_ctx(self, fmt="table", quiet=False):
        ctx = MagicMock(spec=click.Context)
        ctx.obj = MagicMock()
        ctx.obj.output_format = fmt
        ctx.obj.quiet = quiet
        return ctx

    def test_table_flattens_stats(self):
        """Stats dict should be flattened into stats.* columns."""
        ctx = self._make_ctx(fmt="table")
        data = {
            "query": "* | * | *",
            "stats": {"bytesScanned": 0, "eventsScanned": 0, "walltime": 0},
        }
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(str(msg))):
            _output_validate_or_estimate(ctx, data)
        output = "\n".join(echoed)
        assert "stats.bytesScanned" in output
        assert "stats.eventsScanned" in output
        assert "stats.walltime" in output
        # The nested dict should NOT appear as "{N keys}"
        assert "{3 keys}" not in output

    def test_table_flattens_estimated_price(self):
        """estimatedPrice dict should be flattened into price.* columns."""
        ctx = self._make_ctx(fmt="table")
        data = {
            "query": "q",
            "estimatedPrice": {"value": 0, "currency": "USD cents"},
        }
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(str(msg))):
            _output_validate_or_estimate(ctx, data)
        output = "\n".join(echoed)
        assert "price.value" in output
        assert "price.currency" in output
        assert "USD cents" in output

    def test_table_shows_error_field(self):
        ctx = self._make_ctx(fmt="table")
        data = {
            "query": "bad query",
            "error": "failed to transcode query: syntax error",
            "stats": {"bytesScanned": 0},
        }
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(str(msg))):
            _output_validate_or_estimate(ctx, data)
        output = "\n".join(echoed)
        assert "failed to transcode query" in output

    def test_json_format_passthrough(self):
        """JSON output should pass through raw data unchanged."""
        ctx = self._make_ctx(fmt="json")
        data = {
            "query": "q",
            "stats": {"bytesScanned": 0},
            "estimatedPrice": {"value": 0, "currency": "USD cents"},
        }
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(str(msg))):
            _output_validate_or_estimate(ctx, data)
        import json
        parsed = json.loads(echoed[0])
        # Original nested structure preserved
        assert isinstance(parsed["stats"], dict)
        assert isinstance(parsed["estimatedPrice"], dict)

    def test_quiet_suppresses_output(self):
        ctx = self._make_ctx(quiet=True)
        data = {"query": "q", "stats": {}}
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(str(msg))):
            _output_validate_or_estimate(ctx, data)
        assert echoed == []

    def test_table_non_dict_stats_kept_as_is(self):
        """If stats is not a dict (unlikely), it should not crash."""
        ctx = self._make_ctx(fmt="table")
        data = {"query": "q", "stats": "not_a_dict"}
        echoed = []
        with patch("click.echo", side_effect=lambda msg, **kw: echoed.append(str(msg))):
            _output_validate_or_estimate(ctx, data)
        output = "\n".join(echoed)
        assert "not_a_dict" in output


class TestValidateEstimateExitCode:
    """Tests that validate and estimate exit non-zero on error responses."""

    @pytest.fixture
    def mock_org(self):
        client = MagicMock()
        client.oid = "test-oid"
        client.get_jwt.return_value = "fake-jwt"
        org = MagicMock()
        org.oid = "test-oid"
        org.client = client
        org.get_urls.return_value = {"search": "abc.replay-search.limacharlie.io"}
        return org

    def _invoke_validate(self, mock_org, response):
        from click.testing import CliRunner
        from limacharlie.cli import cli
        mock_org.client.request.return_value = response
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, [
                "--oid", "test-oid", "search", "validate",
                "--query", "bad query",
            ])

    def _invoke_estimate(self, mock_org, response):
        from click.testing import CliRunner
        from limacharlie.cli import cli
        mock_org.client.request.return_value = response
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            return runner.invoke(cli, [
                "--oid", "test-oid", "search", "estimate",
                "--query", "bad query",
                "--start", "1700000000", "--end", "1700086400",
            ])

    def test_validate_error_exits_nonzero(self, mock_org):
        response = {
            "query": "bad query",
            "error": "failed to transcode query: syntax error",
            "stats": {"bytesScanned": 0, "eventsScanned": 0},
        }
        result = self._invoke_validate(mock_org, response)
        assert result.exit_code == 1

    def test_validate_success_exits_zero(self, mock_org):
        response = {
            "query": "* | * | *",
            "startTime": "1700000000",
            "endTime": "1700086400",
            "stats": {"bytesScanned": 1000, "eventsScanned": 50},
        }
        result = self._invoke_validate(mock_org, response)
        assert result.exit_code == 0

    def test_validate_error_shows_error_message(self, mock_org):
        response = {
            "query": "bad",
            "error": "failed to transcode query: no match found",
            "stats": {"bytesScanned": 0},
        }
        result = self._invoke_validate(mock_org, response)
        assert "failed to transcode query" in result.output

    def test_estimate_error_exits_nonzero(self, mock_org):
        response = {
            "query": "bad query",
            "error": "failed to transcode query: syntax error",
            "stats": {"bytesScanned": 0},
            "estimatedPrice": {"value": 0, "currency": "USD cents"},
        }
        result = self._invoke_estimate(mock_org, response)
        assert result.exit_code == 1

    def test_estimate_success_exits_zero(self, mock_org):
        response = {
            "query": "* | * | *",
            "stats": {"bytesScanned": 5000},
            "estimatedPrice": {"value": 42, "currency": "USD cents"},
        }
        result = self._invoke_estimate(mock_org, response)
        assert result.exit_code == 0

    def test_estimate_success_shows_price(self, mock_org):
        response = {
            "query": "* | * | *",
            "stats": {"bytesScanned": 5000},
            "estimatedPrice": {"value": 42, "currency": "USD cents"},
        }
        result = self._invoke_estimate(mock_org, response)
        assert "42" in result.output
        assert "USD cents" in result.output

    def test_validate_table_shows_all_stats_fields(self, mock_org):
        """Table output should show all stats fields individually, not truncated."""
        response = {
            "query": "* | * | *",
            "stats": {
                "bytesScanned": 1234,
                "eventsScanned": 5678,
                "eventsMatched": 100,
                "eventsProcessed": 200,
                "rulesEvaluated": 0,
                "walltime": 0,
            },
            "estimatedPrice": {"value": 0, "currency": "USD cents"},
        }
        mock_org.client.request.return_value = response
        from click.testing import CliRunner
        from limacharlie.cli import cli
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "table",
                "search", "validate",
                "--query", "* | * | *",
            ])
        assert result.exit_code == 0
        # All stats fields should be individually visible
        assert "stats.bytesScanned" in result.output
        assert "1234" in result.output
        assert "stats.eventsScanned" in result.output
        assert "5678" in result.output
        assert "price.value" in result.output
        assert "price.currency" in result.output

    def test_estimate_json_preserves_nested_structure(self, mock_org):
        """JSON output should preserve the original nested dict structure."""
        response = {
            "query": "* | * | *",
            "stats": {"bytesScanned": 1000},
            "estimatedPrice": {"value": 42, "currency": "USD cents"},
        }
        mock_org.client.request.return_value = response
        from click.testing import CliRunner
        from limacharlie.cli import cli
        runner = CliRunner()
        with patch("limacharlie.commands.search.Client", return_value=mock_org.client), \
             patch("limacharlie.commands.search.Organization", return_value=mock_org):
            result = runner.invoke(cli, [
                "--oid", "test-oid", "--output", "json",
                "search", "estimate",
                "--query", "* | * | *",
                "--start", "1700000000", "--end", "1700086400",
            ])
        assert result.exit_code == 0
        import json
        parsed = json.loads(result.output)
        assert isinstance(parsed["stats"], dict)
        assert parsed["stats"]["bytesScanned"] == 1000
        assert parsed["estimatedPrice"]["value"] == 42
