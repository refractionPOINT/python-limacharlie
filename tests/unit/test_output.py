"""Tests for limacharlie.output module."""

import json

import pytest
import yaml

from limacharlie.output import (
    format_output,
    format_json,
    format_yaml,
    format_csv,
    format_table,
    format_jsonl,
    detect_output_format,
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
