from __future__ import annotations

"""Output formatting for LimaCharlie CLI v2.

Supports multiple output formats: json, yaml, csv, table, jsonl.
Handles field selection, jmespath filtering, sorting, and auto-detection
of output mode based on whether stdout is a TTY.
"""

import csv
import io
import json
import shutil
import sys
from typing import Any

import yaml

try:
    import jmespath
except ImportError:
    jmespath = None

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None

# Module-level flags set by the CLI before any command runs.
_wide_mode: bool = False
_filter_expr: str | None = None


def set_wide_mode(enabled: bool) -> None:
    """Enable or disable wide (no-truncation) mode for table output."""
    global _wide_mode
    _wide_mode = enabled


def set_filter_expr(expr: str | None) -> None:
    """Set a JMESPath filter expression applied to all output."""
    global _filter_expr
    _filter_expr = expr


def detect_output_format() -> str:
    """Auto-detect the output format based on whether stdout is a TTY.

    Returns:
        'table' if stdout is a TTY, 'json' otherwise.
    """
    if sys.stdout.isatty():
        return "table"
    return "json"


def format_output(
    data: Any,
    fmt: str | None = None,
    fields: list[str] | None = None,
    filter_expr: str | None = None,
    sort_by: str | None = None,
    reverse: bool = False,
) -> str:
    """Format data for output.

    Args:
        data: The data to format (dict, list, or primitive).
        fmt: Output format ('json', 'yaml', 'csv', 'table', 'jsonl').
             None means auto-detect.
        fields: List of field names to include (for list-of-dicts data).
        filter_expr: JMESPath expression for filtering.
        sort_by: Field name to sort by.
        reverse: Reverse sort order.

    Returns:
        str: Formatted output string.
    """
    if fmt is None:
        fmt = detect_output_format()

    # Fall back to module-level filter if none passed explicitly.
    if filter_expr is None:
        filter_expr = _filter_expr

    # Apply jmespath filter
    if filter_expr and data is not None:
        if jmespath is None:
            raise ImportError("jmespath is required for --filter. Install with: pip install jmespath")
        data = jmespath.search(filter_expr, data)

    # Apply field selection
    if fields and isinstance(data, list):
        data = [_select_fields(item, fields) for item in data if isinstance(item, dict)]
    elif fields and isinstance(data, dict):
        data = _select_fields(data, fields)

    # Apply sorting
    if sort_by and isinstance(data, list):
        try:
            data = sorted(data, key=lambda x: x.get(sort_by, "") if isinstance(x, dict) else x, reverse=reverse)
        except TypeError:
            pass

    if fmt == "json":
        return format_json(data)
    elif fmt == "yaml":
        return format_yaml(data)
    elif fmt == "csv":
        return format_csv(data)
    elif fmt == "table":
        return format_table(data)
    elif fmt == "jsonl":
        return format_jsonl(data)
    else:
        return format_json(data)


def format_json(data: Any) -> str:
    """Format data as pretty-printed JSON."""
    return json.dumps(data, indent=2, default=str)


def format_yaml(data: Any) -> str:
    """Format data as YAML."""
    return yaml.dump(data, default_flow_style=False, allow_unicode=True).rstrip()


def format_csv(data: Any) -> str:
    """Format data as CSV with headers."""
    if not data:
        return ""

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return str(data)

    # Collect all keys for headers
    all_keys = []
    for item in data:
        if isinstance(item, dict):
            for k in item.keys():
                if k not in all_keys:
                    all_keys.append(k)

    if not all_keys:
        return str(data)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=all_keys, extrasaction="ignore")
    writer.writeheader()
    for item in data:
        if isinstance(item, dict):
            writer.writerow({k: _csv_value(v) for k, v in item.items()})
    return output.getvalue().rstrip()


def format_table(data: Any) -> str:
    """Format data as a table using tabulate."""
    if data is None:
        return "No data"

    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        if _is_list_of_dicts(data):
            # Dict-of-dicts → flatten to list-of-dicts for columnar display.
            # The dict key is added as a "name" column when not already present.
            rows_data = []
            for k, v in data.items():
                row = dict(v)
                if "name" not in row:
                    row = {"name": k, **row}
                rows_data.append(row)
            data = rows_data
            # Fall through to list-of-dicts handling below
        else:
            # Single record - show as key/value pairs
            rows = [[k, _table_value(v)] for k, v in data.items()]
            if tabulate is not None:
                return tabulate(rows, headers=["Field", "Value"], tablefmt="simple")
            return "\n".join(f"{k}: {v}" for k, v in rows)

    if isinstance(data, list):
        if not data:
            return "No results"

        if all(isinstance(item, dict) for item in data):
            # List of dicts - show as table
            all_keys = []
            for item in data:
                for k in item.keys():
                    if k not in all_keys:
                        all_keys.append(k)

            selected_keys, rows = _fit_columns(all_keys, data)
            dropped = len(all_keys) - len(selected_keys)

            if tabulate is not None:
                tbl = tabulate(rows, headers=selected_keys, tablefmt="simple")
            else:
                header = "  ".join(str(k) for k in selected_keys)
                lines = [header]
                for row in rows:
                    lines.append("  ".join(str(v) for v in row))
                tbl = "\n".join(lines)
            if dropped > 0:
                tbl += f"\n({dropped} more field{'s' if dropped != 1 else ''} hidden, use -W to show all or --output json for full data)"
            return tbl

        # List of primitives
        return "\n".join(str(item) for item in data)

    return str(data)


def format_jsonl(data: Any) -> str:
    """Format data as newline-delimited JSON."""
    if isinstance(data, list):
        return "\n".join(json.dumps(item, default=str) for item in data)
    return json.dumps(data, default=str)


def _select_fields(item: Any, fields: list[str]) -> Any:
    """Select specific fields from a dict."""
    if not isinstance(item, dict):
        return item
    return {k: item[k] for k in fields if k in item}


def _csv_value(v: Any) -> Any:
    """Convert a value for CSV output."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return v


def _max_value_width() -> int:
    """Return the max width for a table value based on terminal size."""
    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    return max(40, cols - 20)


def _term_width() -> int:
    """Return the current terminal width."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def _fit_columns(
    keys: list[str],
    rows_raw: list[dict[str, Any]],
) -> tuple[list[str], list[list[str]]]:
    """Select and truncate columns to fit the terminal width.

    Returns (selected_keys, formatted_rows) where columns that
    would push the table past the terminal width are dropped,
    preferring to drop the sparsest (most-empty) columns first.
    """
    term = _term_width()
    num_rows = len(rows_raw)

    if _wide_mode or num_rows == 0:
        # No column dropping in wide mode.
        rows = []
        for item in rows_raw:
            rows.append([_table_value(item.get(k, "")) for k in keys])
        return keys, rows

    # Per-cell max: reasonable cap so one column can't eat all space.
    cell_max = max(20, min(60, term // 3))

    # Pre-compute cell strings and actual widths per column.
    col_cells: dict[str, list[str]] = {}
    col_width: dict[str, int] = {}
    col_fill: dict[str, int] = {}  # number of non-empty cells
    for k in keys:
        cells = [_table_value(item.get(k, ""), width=cell_max) for item in rows_raw]
        col_cells[k] = cells
        # Column display width: tabulate uses max(header + MIN_PADDING, content).
        max_cell = max((len(c) for c in cells), default=0)
        col_width[k] = max(len(k) + 2, max_cell)
        col_fill[k] = sum(1 for c in cells if c != "")

    # Greedily select columns that fit.  Sort candidates so the
    # sparsest columns are dropped first (lowest fill count last).
    # Among equal fill, keep original key order.
    priority = sorted(keys, key=lambda k: (-col_fill[k], keys.index(k)))

    selected: list[str] = []
    used = 0
    for k in priority:
        # 2-char separator between columns
        needed = col_width[k] + (2 if selected else 0)
        if used + needed <= term:
            selected.append(k)
            used += needed

    # Restore original key order for display.
    selected_set = set(selected)
    selected = [k for k in keys if k in selected_set]

    rows = []
    for i in range(num_rows):
        rows.append([col_cells[k][i] for k in selected])
    return selected, rows


def _truncate(s: str, width: int) -> str:
    """Truncate a string to *width* characters, adding '...' if needed."""
    if len(s) <= width:
        return s
    return s[:width - 3] + "..."


def _table_value(v: Any, width: int | None = None) -> str:
    """Convert a value for table display.

    Args:
        v: The value to convert.
        width: Max character width for this cell.  When None, falls back
               to the terminal-based default from _max_value_width().
    """
    if _wide_mode:
        if isinstance(v, dict):
            return json.dumps(v, default=str)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        if v is None:
            return ""
        return str(v)
    if width is None:
        width = _max_value_width()
    if isinstance(v, dict):
        s = json.dumps(v, default=str)
        if len(s) <= width:
            return s
        return f"{{{len(v)} keys}}"
    if isinstance(v, list):
        if len(v) <= 3:
            s = ", ".join(str(x) for x in v)
            if len(s) <= width:
                return s
        return f"[{len(v)} items]"
    if v is None:
        return ""
    return _truncate(str(v), width)


def _is_list_of_dicts(data: Any) -> bool:
    """Check if data is a dict-of-dicts that should render as a table.

    Returns True when all values are dicts (e.g. payloads keyed by name),
    so we can flatten them into rows instead of showing key/JSON pairs.
    Requires more than one entry to avoid treating single-record responses
    as tables.
    """
    if not isinstance(data, dict) or len(data) <= 1:
        return False
    return all(isinstance(v, dict) for v in data.values())


def print_output(data: Any, fmt: str | None = None, fields: list[str] | None = None, filter_expr: str | None = None,
                 sort_by: str | None = None, reverse: bool = False, file: Any = None) -> None:
    """Format and print data to stdout (or specified file).

    Convenience function that calls format_output and prints the result.
    """
    result = format_output(
        data,
        fmt=fmt,
        fields=fields,
        filter_expr=filter_expr,
        sort_by=sort_by,
        reverse=reverse,
    )
    print(result, file=file or sys.stdout)
