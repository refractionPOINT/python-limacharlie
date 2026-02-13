"""Tests for limacharlie.output module."""

import json
from unittest.mock import patch

import yaml

from limacharlie.output import (
    format_output,
    format_json,
    format_yaml,
    format_csv,
    format_table,
    format_jsonl,
    detect_output_format,
    set_wide_mode,
    set_filter_expr,
    _truncate,
    _max_value_width,
    _table_value,
)


class TestFormatJson:
    def test_dict(self):
        result = format_json({"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_list(self):
        result = format_json([1, 2, 3])
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_pretty_printed(self):
        result = format_json({"a": 1})
        assert "\n" in result  # Pretty-printed has newlines

    def test_none(self):
        result = format_json(None)
        assert result == "null"


class TestFormatYaml:
    def test_dict(self):
        result = format_yaml({"key": "value"})
        parsed = yaml.safe_load(result)
        assert parsed == {"key": "value"}

    def test_list(self):
        result = format_yaml([1, 2, 3])
        parsed = yaml.safe_load(result)
        assert parsed == [1, 2, 3]


class TestFormatCsv:
    def test_list_of_dicts(self):
        data = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
        result = format_csv(data)
        lines = result.strip().split("\n")
        assert "name" in lines[0]
        assert "value" in lines[0]
        assert len(lines) == 3  # header + 2 data rows

    def test_single_dict(self):
        result = format_csv({"name": "a", "value": 1})
        lines = result.strip().split("\n")
        assert len(lines) == 2  # header + 1 row

    def test_empty_data(self):
        assert format_csv([]) == ""
        assert format_csv(None) == ""

    def test_nested_values_json_serialized(self):
        data = [{"name": "a", "config": {"nested": True}}]
        result = format_csv(data)
        # CSV writer may double-quote nested JSON, just verify the nested key is present
        assert "nested" in result
        assert "true" in result.lower()


class TestFormatTable:
    def test_list_of_dicts(self):
        data = [{"name": "sensor1", "status": "online"}, {"name": "sensor2", "status": "offline"}]
        result = format_table(data)
        assert "sensor1" in result
        assert "sensor2" in result
        assert "name" in result
        assert "status" in result

    def test_single_dict(self):
        result = format_table({"name": "test", "value": 42})
        assert "name" in result
        assert "test" in result

    def test_empty_list(self):
        result = format_table([])
        assert "No results" in result

    def test_none(self):
        result = format_table(None)
        assert "No data" in result

    def test_string_passthrough(self):
        result = format_table("hello")
        assert result == "hello"


class TestFormatJsonl:
    def test_list(self):
        data = [{"a": 1}, {"b": 2}]
        result = format_jsonl(data)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_single_item(self):
        result = format_jsonl({"a": 1})
        assert json.loads(result) == {"a": 1}


class TestFormatOutput:
    def test_json_format(self):
        result = format_output({"key": "val"}, fmt="json")
        assert json.loads(result) == {"key": "val"}

    def test_yaml_format(self):
        result = format_output({"key": "val"}, fmt="yaml")
        assert yaml.safe_load(result) == {"key": "val"}

    def test_csv_format(self):
        result = format_output([{"a": 1}], fmt="csv")
        assert "a" in result

    def test_table_format(self):
        result = format_output([{"a": 1}], fmt="table")
        assert "a" in result

    def test_jsonl_format(self):
        result = format_output([{"a": 1}, {"b": 2}], fmt="jsonl")
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_field_selection(self):
        data = [{"name": "a", "value": 1, "extra": "x"}]
        result = format_output(data, fmt="json", fields=["name", "value"])
        parsed = json.loads(result)
        assert "extra" not in parsed[0]
        assert parsed[0]["name"] == "a"

    def test_jmespath_filter(self):
        data = {"items": [1, 2, 3]}
        result = format_output(data, fmt="json", filter_expr="items[0]")
        assert json.loads(result) == 1

    def test_sort_by(self):
        data = [{"n": "b"}, {"n": "a"}, {"n": "c"}]
        result = format_output(data, fmt="json", sort_by="n")
        parsed = json.loads(result)
        assert [item["n"] for item in parsed] == ["a", "b", "c"]

    def test_sort_reverse(self):
        data = [{"n": "a"}, {"n": "c"}, {"n": "b"}]
        result = format_output(data, fmt="json", sort_by="n", reverse=True)
        parsed = json.loads(result)
        assert [item["n"] for item in parsed] == ["c", "b", "a"]


class TestTruncate:
    def test_shorter_than_width(self):
        assert _truncate("hello", 10) == "hello"

    def test_exactly_at_width(self):
        assert _truncate("hello", 5) == "hello"

    def test_longer_than_width(self):
        result = _truncate("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8


class TestMaxValueWidth:
    @patch("limacharlie.output.shutil.get_terminal_size")
    def test_normal_terminal(self, mock_size):
        mock_size.return_value.columns = 120
        assert _max_value_width() == 100

    @patch("limacharlie.output.shutil.get_terminal_size")
    def test_narrow_terminal_clamped(self, mock_size):
        mock_size.return_value.columns = 40
        assert _max_value_width() == 40

    @patch("limacharlie.output.shutil.get_terminal_size", side_effect=OSError)
    def test_exception_fallback(self, mock_size):
        assert _max_value_width() == 60  # fallback 80 - 20


class TestTableValue:
    def setup_method(self):
        set_wide_mode(False)

    def teardown_method(self):
        set_wide_mode(False)

    @patch("limacharlie.output._max_value_width", return_value=100)
    def test_small_dict_inline(self, _):
        d = {"a": 1}
        result = _table_value(d)
        assert result == json.dumps(d, default=str)

    @patch("limacharlie.output._max_value_width", return_value=10)
    def test_large_dict_summary(self, _):
        d = {"key1": "value1", "key2": "value2", "key3": "value3"}
        result = _table_value(d)
        assert result == "{3 keys}"

    @patch("limacharlie.output._max_value_width", return_value=100)
    def test_small_list_joined(self, _):
        result = _table_value(["a", "b", "c"])
        assert result == "a, b, c"

    @patch("limacharlie.output._max_value_width", return_value=5)
    def test_small_list_too_long(self, _):
        result = _table_value(["aaa", "bbb", "ccc"])
        assert result == "[3 items]"

    @patch("limacharlie.output._max_value_width", return_value=100)
    def test_large_list_summary(self, _):
        result = _table_value(["a", "b", "c", "d"])
        assert result == "[4 items]"

    def test_none_returns_empty(self):
        assert _table_value(None) == ""

    @patch("limacharlie.output._max_value_width", return_value=10)
    def test_long_string_truncated(self, _):
        result = _table_value("a" * 20)
        assert result.endswith("...")
        assert len(result) == 10

    @patch("limacharlie.output._max_value_width", return_value=100)
    def test_normal_string_unchanged(self, _):
        assert _table_value("hello") == "hello"


class TestWideMode:
    def setup_method(self):
        set_wide_mode(False)

    def teardown_method(self):
        set_wide_mode(False)

    def test_wide_dict_full_json(self):
        set_wide_mode(True)
        d = {"key1": "value1", "key2": "value2", "key3": "value3"}
        result = _table_value(d)
        assert result == json.dumps(d, default=str)

    def test_wide_list_comma_joined(self):
        set_wide_mode(True)
        result = _table_value(["a", "b", "c", "d", "e"])
        assert result == "a, b, c, d, e"

    @patch("limacharlie.output._max_value_width", return_value=10)
    def test_non_wide_dict_summary(self, _):
        set_wide_mode(False)
        d = {"key1": "value1", "key2": "value2", "key3": "value3"}
        result = _table_value(d)
        assert result == "{3 keys}"


class TestFilterExpr:
    def setup_method(self):
        set_filter_expr(None)

    def teardown_method(self):
        set_filter_expr(None)

    def test_module_level_filter(self):
        set_filter_expr("items")
        data = {"items": [1, 2, 3], "other": "x"}
        result = format_output(data, fmt="json")
        assert json.loads(result) == [1, 2, 3]

    def test_explicit_param_overrides_module(self):
        set_filter_expr("items")
        data = {"items": [1, 2, 3], "other": "x"}
        result = format_output(data, fmt="json", filter_expr="other")
        assert json.loads(result) == "x"

    def test_clear_filter(self):
        set_filter_expr("items")
        set_filter_expr(None)
        data = {"items": [1, 2, 3]}
        result = format_output(data, fmt="json")
        assert json.loads(result) == {"items": [1, 2, 3]}


class TestDetectOutputFormat:
    @patch("limacharlie.output.sys.stdout")
    def test_tty_returns_table(self, mock_stdout):
        mock_stdout.isatty.return_value = True
        assert detect_output_format() == "table"

    @patch("limacharlie.output.sys.stdout")
    def test_non_tty_returns_json(self, mock_stdout):
        mock_stdout.isatty.return_value = False
        assert detect_output_format() == "json"
