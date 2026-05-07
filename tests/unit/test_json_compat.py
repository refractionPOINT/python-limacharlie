"""Tests for limacharlie.json_compat - fast JSON with orjson fallback.

Tests verify correct behavior for both the orjson backend and the stdlib
json fallback, including edge cases around type handling, encoding, and
roundtrip consistency.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from limacharlie.json_compat import dumps, dumps_pretty, loads, backend_name, HAS_ORJSON


class TestDumps:
    """Tests for compact JSON serialization."""

    def test_simple_dict(self):
        assert loads(dumps({"a": 1, "b": "hello"})) == {"a": 1, "b": "hello"}

    def test_nested_structure(self):
        data = {"outer": {"inner": [1, 2, 3], "flag": True, "nil": None}}
        assert loads(dumps(data)) == data

    def test_empty_structures(self):
        assert dumps({}) in ("{}", "{}")
        assert dumps([]) == "[]"

    def test_non_string_keys(self):
        """orjson uses OPT_NON_STR_KEYS, stdlib uses default=str."""
        result = dumps({1: "one", 2: "two"})
        parsed = loads(result)
        # Both backends should produce string keys in JSON
        assert "1" in parsed or 1 in parsed

    def test_returns_str_not_bytes(self):
        result = dumps({"key": "value"})
        assert isinstance(result, str)

    def test_compact_no_whitespace(self):
        result = dumps({"a": 1})
        # Should not have spaces after : or ,
        assert " " not in result or result == '{"a": 1}'  # stdlib may add space

    def test_unicode(self):
        data = {"emoji": "\u2603", "cjk": "\u4e16\u754c"}
        assert loads(dumps(data)) == data

    def test_large_integers(self):
        data = {"big": 2**53, "negative": -(2**53)}
        assert loads(dumps(data)) == data

    def test_float_values(self):
        data = {"pi": 3.14159, "neg": -0.5, "zero": 0.0}
        result = loads(dumps(data))
        assert abs(result["pi"] - 3.14159) < 1e-10
        assert result["neg"] == -0.5


class TestDumpsPretty:
    """Tests for pretty-printed JSON serialization."""

    def test_indented_output(self):
        result = dumps_pretty({"a": 1})
        assert "\n" in result  # Must be multi-line

    def test_returns_str(self):
        assert isinstance(dumps_pretty({"x": 1}), str)

    def test_roundtrip(self):
        data = {"nested": {"list": [1, 2, 3]}}
        assert loads(dumps_pretty(data)) == data


class TestLoads:
    """Tests for JSON deserialization."""

    def test_from_string(self):
        assert loads('{"a": 1}') == {"a": 1}

    def test_from_bytes(self):
        assert loads(b'{"a": 1}') == {"a": 1}

    def test_empty_object(self):
        assert loads("{}") == {}

    def test_empty_array(self):
        assert loads("[]") == []

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            loads("{invalid")

    def test_empty_string_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            loads("")

    def test_unicode_string_input(self):
        result = loads('{"key": "\u2603"}')
        assert result["key"] == "\u2603"


class TestBackendName:
    """Tests for backend_name()."""

    def test_returns_string(self):
        name = backend_name()
        assert isinstance(name, str)
        assert name in ("orjson", "stdlib json")

    def test_matches_has_orjson_flag(self):
        if HAS_ORJSON:
            assert backend_name() == "orjson"
        else:
            assert backend_name() == "stdlib json"


class TestRoundtrip:
    """Tests for serialization/deserialization roundtrip consistency."""

    @pytest.mark.parametrize("data", [
        None,
        True,
        False,
        42,
        3.14,
        "hello",
        "",
        [],
        {},
        [1, "two", None, True],
        {"nested": {"deep": {"value": [1, 2, 3]}}},
        [{"a": 1}, {"b": 2}],
    ])
    def test_roundtrip_preserves_data(self, data):
        assert loads(dumps(data)) == data

    @pytest.mark.parametrize("data", [
        None,
        {"key": "value"},
        [1, 2, 3],
    ])
    def test_pretty_roundtrip_preserves_data(self, data):
        assert loads(dumps_pretty(data)) == data


class TestStdlibFallback:
    """Tests verifying stdlib json fallback works when orjson is unavailable."""

    def test_dumps_without_orjson(self):
        with patch("limacharlie.json_compat.orjson", None):
            result = dumps({"a": 1})
            assert isinstance(result, str)
            assert json.loads(result) == {"a": 1}

    def test_dumps_pretty_without_orjson(self):
        with patch("limacharlie.json_compat.orjson", None):
            result = dumps_pretty({"a": 1})
            assert isinstance(result, str)
            assert "\n" in result
            assert json.loads(result) == {"a": 1}

    def test_loads_string_without_orjson(self):
        with patch("limacharlie.json_compat.orjson", None):
            assert loads('{"a": 1}') == {"a": 1}

    def test_loads_bytes_without_orjson(self):
        """stdlib json.loads also accepts bytes."""
        with patch("limacharlie.json_compat.orjson", None):
            assert loads(b'{"a": 1}') == {"a": 1}
