"""Tests for limacharlie.output module."""

import json
import sys
from unittest.mock import patch

import pytest
import yaml

import limacharlie.output as output_mod
from limacharlie.output import (
    format_output,
    format_json,
    format_yaml,
    format_toon,
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

try:
    import toon_format
except ImportError:  # toon_format ships in the optional 'toon' extra.
    toon_format = None

requires_toon = pytest.mark.skipif(
    toon_format is None,
    reason="requires the optional 'toon' extra: pip install 'limacharlie[toon]'",
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


@requires_toon
class TestFormatToon:
    def test_dict_roundtrip(self):
        data = {"name": "Alice", "age": 30}
        result = format_toon(data)
        assert toon_format.decode(result) == data

    def test_list_of_dicts_roundtrip(self):
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = format_toon(data)
        assert toon_format.decode(result) == data

    def test_list_of_primitives_roundtrip(self):
        data = [1, 2, 3]
        result = format_toon(data)
        assert toon_format.decode(result) == data

    def test_none(self):
        assert toon_format.decode(format_toon(None)) is None

    def test_list_of_dicts_uses_tabular_form(self):
        """Uniform list-of-dicts should emit the compact tabular form
        ([N]{fields}:) rather than repeating keys per row. This is the
        whole point of TOON for token-efficient LLM prompts."""
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = format_toon(data)
        # Header line declares length + field names once.
        first_line = result.splitlines()[0]
        assert first_line.startswith("[2]")
        assert "a" in first_line and "b" in first_line

    def test_nested_structure_roundtrip(self):
        data = {"org": "acme", "sensors": [{"sid": "s1", "plat": "win"}]}
        result = format_toon(data)
        assert toon_format.decode(result) == data

    def test_unicode(self):
        data = {"name": "héllo 🎉"}
        result = format_toon(data)
        assert toon_format.decode(result) == data

    def test_empty_list(self):
        assert toon_format.decode(format_toon([])) == []

    def test_ensure_format_available_passes_when_installed(self):
        """With the extra present the CLI's pre-flight check lets TOON through."""
        output_mod.ensure_format_available("toon")


class TestFormatToonMissingExtra:
    """TOON output is opt-in: toon_format lives in the 'toon' extra, so a
    default install has no encoder and every path into TOON has to say so."""

    @pytest.fixture(autouse=True)
    def _toon_unavailable(self, monkeypatch):
        monkeypatch.setattr(output_mod, "_toon_format", None)

    def test_format_toon_error_points_at_the_extra(self):
        """The error has to name the extra, not the bare package: installing
        toon_format by hand next to a pipx/uv-managed CLI does not put it on
        the CLI's path."""
        with pytest.raises(ImportError) as excinfo:
            format_toon({"a": 1})
        assert "limacharlie[toon]" in str(excinfo.value)

    def test_format_output_toon_error_points_at_the_extra(self):
        """--output toon routes through format_output, not format_toon."""
        with pytest.raises(ImportError) as excinfo:
            format_output({"a": 1}, fmt="toon")
        assert "limacharlie[toon]" in str(excinfo.value)

    def test_format_toon_error_offers_a_uv_form(self):
        """`uv pip install 'limacharlie[toon]'` does not work on uv before 0.12:
        toon_format's only in-range release is a pre-release, and those versions
        honour pre-release specifiers on direct requirements only. Told to
        install the extra, they silently backtrack to a limacharlie old enough
        not to want it. The error has to give those users a form that names
        toon-format directly."""
        with pytest.raises(ImportError) as excinfo:
            format_toon({"a": 1})
        message = str(excinfo.value)
        assert "uv" in message
        assert "toon-format>=0.9.0b1" in message

    def test_ensure_format_available_rejects_toon(self):
        """The pre-flight guard the CLI calls before dispatching a command."""
        with pytest.raises(ImportError) as excinfo:
            output_mod.ensure_format_available("toon")
        assert "limacharlie[toon]" in str(excinfo.value)

    @pytest.mark.parametrize("fmt", ["json", "yaml", "csv", "table", "jsonl", None])
    def test_ensure_format_available_passes_other_formats(self, fmt):
        """TOON is the only format whose encoder ships in an extra."""
        output_mod.ensure_format_available(fmt)

    def test_both_toon_guards_give_the_same_message(self):
        """One install hint, so the pre-flight and render-time paths cannot
        drift into telling users two different things."""
        with pytest.raises(ImportError) as pre_flight:
            output_mod.ensure_format_available("toon")
        with pytest.raises(ImportError) as render_time:
            format_toon({"a": 1})
        assert str(pre_flight.value) == str(render_time.value)

    def test_cli_reports_the_extra_without_a_traceback(self, monkeypatch, tmp_path, capsys):
        """End users see a one-line hint and exit 1, not a stack trace."""
        from limacharlie.cli import main

        # main() prints a traceback when LC_DEBUG is set, so a developer with
        # it exported would otherwise see this fail for the wrong reason.
        monkeypatch.delenv("LC_DEBUG", raising=False)
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            sys, "argv", ["limacharlie", "--output", "toon", "config", "show-paths"]
        )
        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "limacharlie[toon]" in err
        assert "Traceback" not in err

    def test_cli_rejects_toon_before_running_the_command(self, monkeypatch, tmp_path, capsys):
        """The refusal comes from the root group, not from rendering.

        A search that reaches format time has already run, been billed, and
        buffered every page; finding the encoder missing there wastes all of
        it. Checked on the cheapest subcommand there is: its callback never
        runs.
        """
        from limacharlie.cli import cli, main

        show_paths = cli.get_command(None, "config").get_command(None, "show-paths")
        ran = []
        monkeypatch.setattr(show_paths, "callback", lambda *a, **kw: ran.append(True))

        monkeypatch.delenv("LC_DEBUG", raising=False)
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            sys, "argv", ["limacharlie", "--output", "toon", "config", "show-paths"]
        )
        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        assert ran == [], "subcommand ran despite the missing TOON encoder"
        assert "limacharlie[toon]" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "argv",
        [
            ["limacharlie", "--output", "toon", "--help"],
            ["limacharlie", "--output", "toon", "config", "--help"],
            ["limacharlie", "--output", "toon", "config", "show-paths", "--help"],
        ],
    )
    def test_help_works_without_the_encoder(self, monkeypatch, tmp_path, capsys, argv):
        """Describing a command must not depend on an optional output encoder.

        The root callback runs before a subcommand parses its own --help, so a
        pre-flight check that did not exempt help would break every
        `--output toon <command> --help` on a default install.
        """
        from limacharlie.cli import main

        monkeypatch.delenv("LC_DEBUG", raising=False)
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(sys, "argv", argv)
        # click returns 0 instead of raising when standalone_mode is off, so a
        # help run falls off the end of main() and the process exits 0. A
        # rejected --output would raise SystemExit(1) out of this call.
        main()

        assert "Usage:" in capsys.readouterr().out

    def test_other_formats_still_work(self):
        """Only TOON degrades; the rest of --output is unaffected."""
        assert json.loads(format_output({"a": 1}, fmt="json")) == {"a": 1}
        assert yaml.safe_load(format_output({"a": 1}, fmt="yaml")) == {"a": 1}


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

    def test_dict_of_dicts_renders_as_table(self):
        """Dict-of-dicts (e.g. payloads) should render as columnar table, not key/JSON pairs."""
        data = {
            "p1": {"name": "p1", "size": 100},
            "p2": {"name": "p2", "size": 200},
        }
        result = format_table(data)
        # Should have column headers, not Field/Value
        assert "Field" not in result
        assert "name" in result
        assert "size" in result
        assert "p1" in result
        assert "p2" in result

    def test_dict_of_dicts_adds_name_column_when_missing(self):
        """When values lack a 'name' key, the dict key becomes the 'name' column."""
        data = {
            "my-rule": {"detect": "op1"},
            "other-rule": {"detect": "op2"},
        }
        result = format_table(data)
        assert "name" in result
        assert "my-rule" in result
        assert "other-rule" in result

    def test_single_key_dict_stays_as_key_value(self):
        """A dict with only one key should still render as Field/Value."""
        data = {"only-key": {"nested": "data"}}
        result = format_table(data)
        assert "only-key" in result


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

    @requires_toon
    def test_toon_format(self):
        result = format_output({"key": "val"}, fmt="toon")
        assert toon_format.decode(result) == {"key": "val"}

    @requires_toon
    def test_toon_respects_field_selection(self):
        data = [{"name": "a", "value": 1, "extra": "x"}]
        result = format_output(data, fmt="toon", fields=["name", "value"])
        decoded = toon_format.decode(result)
        assert decoded == [{"name": "a", "value": 1}]

    @requires_toon
    def test_toon_respects_jmespath_filter(self):
        data = {"items": [1, 2, 3]}
        result = format_output(data, fmt="toon", filter_expr="items[0]")
        assert toon_format.decode(result) == 1

    @requires_toon
    def test_toon_respects_sort(self):
        data = [{"n": "b"}, {"n": "a"}, {"n": "c"}]
        result = format_output(data, fmt="toon", sort_by="n")
        decoded = toon_format.decode(result)
        assert [item["n"] for item in decoded] == ["a", "b", "c"]

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
        # orjson omits space after colon (compact format)
        assert result == '{"a":1}'

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
        # orjson compact format (no space after colon)
        assert result == '{"key1":"value1","key2":"value2","key3":"value3"}'

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
