from __future__ import annotations

"""Output formatting for LimaCharlie CLI v2.

Supports multiple output formats: json, yaml, csv, table, jsonl.
Handles field selection, jmespath filtering, sorting, and auto-detection
of output mode based on whether stdout is a TTY.
"""

import csv
import io
import json
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

    if isinstance(data, dict) and not _is_list_of_dicts(data):
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

            rows = []
            for item in data:
                rows.append([_table_value(item.get(k, "")) for k in all_keys])

            if tabulate is not None:
                return tabulate(rows, headers=all_keys, tablefmt="simple")
            # Fallback without tabulate
            header = "  ".join(str(k) for k in all_keys)
            lines = [header]
            for row in rows:
                lines.append("  ".join(str(v) for v in row))
            return "\n".join(lines)

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


def _table_value(v: Any) -> str:
    """Convert a value for table display."""
    if isinstance(v, dict):
        return json.dumps(v, default=str)
    if isinstance(v, list):
        if len(v) <= 3:
            return ", ".join(str(x) for x in v)
        return f"[{len(v)} items]"
    if v is None:
        return ""
    return str(v)


def _is_list_of_dicts(data: Any) -> bool:
    """Check if data is a dict that looks like a list-of-dicts."""
    return False


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
