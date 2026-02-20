"""
Unit tests for the USP (Universal Sensor Protocol) CLI module.

Tests the USP validation CLI functionality including argument parsing,
file loading, and error handling.
"""

import json
import os
import sys
import tempfile
import pytest
import yaml

from limacharlie.USP import (
    _load_file_content,
    _load_mapping,
    main,
    printData,
    reportError,
)


class TestLoadFileContent:
    """Tests for the _load_file_content helper function."""

    def test_load_text_file(self, tmp_path):
        """Test loading a plain text file."""
        test_content = "line1\nline2\nline3"
        test_file = tmp_path / "test.txt"
        test_file.write_text(test_content)

        result = _load_file_content(str(test_file), as_json=False)
        assert result == test_content

    def test_load_json_file(self, tmp_path):
        """Test loading a JSON file."""
        test_data = [{"key": "value"}, {"key2": "value2"}]
        test_file = tmp_path / "test.json"
        test_file.write_text(json.dumps(test_data))

        result = _load_file_content(str(test_file), as_json=True)
        assert result == test_data

    def test_load_nonexistent_file(self):
        """Test that loading a nonexistent file exits with error."""
        with pytest.raises(SystemExit) as exc_info:
            _load_file_content("/nonexistent/path/file.txt", as_json=False)
        assert exc_info.value.code == 1

    def test_load_invalid_json(self, tmp_path):
        """Test that loading invalid JSON exits with error."""
        test_file = tmp_path / "invalid.json"
        test_file.write_text("not valid json {{{")

        with pytest.raises(SystemExit) as exc_info:
            _load_file_content(str(test_file), as_json=True)
        assert exc_info.value.code == 1


class TestLoadMapping:
    """Tests for the _load_mapping helper function."""

    def test_load_mapping_from_yaml_file(self, tmp_path):
        """Test loading mapping from a YAML file."""
        mapping_data = {
            "parsing_re": r"(?P<timestamp>\S+) (?P<msg>.*)",
            "event_type_path": "event_type"
        }
        yaml_file = tmp_path / "mapping.yaml"
        yaml_file.write_text(yaml.dump(mapping_data))

        # Use object instance to avoid class-scope variable access issues
        class Args:
            pass
        args = Args()
        args.mapping_file = str(yaml_file)
        args.mapping = None

        result = _load_mapping(args)
        assert result == mapping_data

    def test_load_mapping_from_json_file(self, tmp_path):
        """Test loading mapping from a JSON file."""
        mapping_data = {
            "parsing_re": r"(?P<timestamp>\S+) (?P<msg>.*)",
        }
        json_file = tmp_path / "mapping.json"
        json_file.write_text(json.dumps(mapping_data))

        # Use object instance to avoid class-scope variable access issues
        class Args:
            pass
        args = Args()
        args.mapping_file = str(json_file)
        args.mapping = None

        result = _load_mapping(args)
        assert result == mapping_data

    def test_load_mapping_from_inline_json(self):
        """Test loading mapping from inline JSON argument."""
        mapping_json = '{"parsing_re": "(?P<ts>\\\\S+)"}'

        class Args:
            mapping_file = None
            mapping = mapping_json

        result = _load_mapping(Args())
        assert result == {"parsing_re": r"(?P<ts>\S+)"}

    def test_load_mapping_invalid_inline_json(self):
        """Test that invalid inline JSON exits with error."""
        class Args:
            mapping_file = None
            mapping = "not valid json"

        with pytest.raises(SystemExit) as exc_info:
            _load_mapping(Args())
        assert exc_info.value.code == 1

    def test_load_mapping_returns_none_if_not_provided(self):
        """Test that no mapping returns None."""
        class Args:
            mapping_file = None
            mapping = None

        result = _load_mapping(Args())
        assert result is None


class TestPrintData:
    """Tests for the printData helper function."""

    def test_print_string(self, capsys):
        """Test printing a plain string."""
        printData("test message")
        captured = capsys.readouterr()
        assert "test message" in captured.out

    def test_print_dict(self, capsys):
        """Test printing a dictionary (as YAML)."""
        printData({"key": "value"})
        captured = capsys.readouterr()
        assert "key: value" in captured.out


class TestReportError:
    """Tests for the reportError helper function."""

    def test_report_error_exits(self):
        """Test that reportError exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            reportError("test error")
        assert exc_info.value.code == 1

    def test_report_error_writes_to_stderr(self, capsys):
        """Test that reportError writes to stderr."""
        with pytest.raises(SystemExit):
            reportError("error message")
        captured = capsys.readouterr()
        assert "error message" in captured.err


class TestMainArgParsing:
    """Tests for the main CLI argument parsing."""

    def test_main_shows_help(self, capsys):
        """Test that --help works."""
        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "--help"])
        # argparse exits with 0 on --help
        assert exc_info.value.code == 0

    def test_main_requires_action(self, capsys):
        """Test that missing action shows error."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2  # argparse error code

    def test_main_validates_platform_choices(self, capsys):
        """Test that invalid platform shows error."""
        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "--platform", "invalid_platform"])
        assert exc_info.value.code == 2  # argparse error code

    def test_main_accepts_valid_platforms(self, capsys):
        """Test that valid platforms are accepted."""
        valid_platforms = ["text", "json", "cef", "gcp", "aws"]
        for platform in valid_platforms:
            # This will fail due to missing input, but platform should be accepted
            with pytest.raises(SystemExit) as exc_info:
                main(["validate", "--platform", platform])
            # Exit code 1 means it got past argument parsing (missing input error)
            assert exc_info.value.code == 1

    def test_main_accepts_output_formats(self, capsys):
        """Test that output format choices are valid."""
        valid_formats = ["summary", "json", "yaml"]
        for fmt in valid_formats:
            with pytest.raises(SystemExit) as exc_info:
                main(["validate", "--output-format", fmt])
            # Exit code 1 means it got past argument parsing
            assert exc_info.value.code == 1


class TestValidateAction:
    """Tests for the validate action end-to-end."""

    def test_validate_requires_mapping_or_mappings(self, capsys):
        """Test that validation fails without mapping."""
        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "--input", "test data"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "mapping" in captured.err.lower()

    def test_validate_requires_input(self, capsys, tmp_path):
        """Test that validation fails without input."""
        mapping_file = tmp_path / "mapping.yaml"
        mapping_file.write_text(yaml.dump({"parsing_re": ".*"}))

        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "--mapping-file", str(mapping_file)])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "input" in captured.err.lower()

    def test_validate_json_input_must_be_array(self, capsys, tmp_path):
        """Test that JSON input must be an array."""
        mapping_file = tmp_path / "mapping.yaml"
        mapping_file.write_text(yaml.dump({"parsing_re": ".*"}))

        # Create a JSON file with an object instead of array
        input_file = tmp_path / "input.json"
        input_file.write_text('{"key": "value"}')

        with pytest.raises(SystemExit) as exc_info:
            main([
                "validate",
                "--mapping-file", str(mapping_file),
                "--input-file", str(input_file),
                "--json-input"
            ])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "array" in captured.err.lower()

    def test_validate_mappings_file_must_be_array(self, capsys, tmp_path):
        """Test that mappings file must contain an array."""
        mappings_file = tmp_path / "mappings.json"
        mappings_file.write_text('{"not": "array"}')

        with pytest.raises(SystemExit) as exc_info:
            main([
                "validate",
                "--mappings-file", str(mappings_file),
                "--input", "test"
            ])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "array" in captured.err.lower()

    def test_validate_indexing_file_must_be_array(self, capsys, tmp_path):
        """Test that indexing file must contain an array."""
        mapping_file = tmp_path / "mapping.yaml"
        mapping_file.write_text(yaml.dump({"parsing_re": ".*"}))

        indexing_file = tmp_path / "indexing.json"
        indexing_file.write_text('{"not": "array"}')

        with pytest.raises(SystemExit) as exc_info:
            main([
                "validate",
                "--mapping-file", str(mapping_file),
                "--input", "test",
                "--indexing-file", str(indexing_file)
            ])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "array" in captured.err.lower()


class TestValidateEmptyResults:
    """Tests for empty results handling in validation."""

    def test_empty_results_exits_with_error(self, capsys, monkeypatch):
        """Test that empty parsing results cause exit with error code 1."""
        # Create a mock Manager class that returns empty results
        class MockManager:
            def __init__(self, *args, **kwargs):
                pass

            def validateUSP(self, **kwargs):
                return {
                    'errors': [],
                    'results': []  # Empty results
                }

        # Patch the Manager class in the USP module
        import limacharlie.USP as usp_module
        monkeypatch.setattr(usp_module, 'Manager', MockManager)

        with pytest.raises(SystemExit) as exc_info:
            main([
                "validate",
                "--platform", "cef",  # Built-in parser, no mapping needed
                "--input", "test data"
            ])
        assert exc_info.value.code == 1

    def test_empty_results_shows_warning_message(self, capsys, monkeypatch):
        """Test that empty results display helpful warning message."""
        class MockManager:
            def __init__(self, *args, **kwargs):
                pass

            def validateUSP(self, **kwargs):
                return {
                    'errors': [],
                    'results': []
                }

        import limacharlie.USP as usp_module
        monkeypatch.setattr(usp_module, 'Manager', MockManager)

        with pytest.raises(SystemExit):
            main([
                "validate",
                "--platform", "cef",
                "--input", "test data"
            ])

        captured = capsys.readouterr()
        # Check that warning message is displayed
        assert "No events were parsed" in captured.out
        assert "VALIDATION FAILED" in captured.out

    def test_empty_results_shows_suggestions(self, capsys, monkeypatch):
        """Test that empty results show troubleshooting suggestions."""
        class MockManager:
            def __init__(self, *args, **kwargs):
                pass

            def validateUSP(self, **kwargs):
                return {
                    'errors': [],
                    'results': []
                }

        import limacharlie.USP as usp_module
        monkeypatch.setattr(usp_module, 'Manager', MockManager)

        with pytest.raises(SystemExit):
            main([
                "validate",
                "--platform", "cef",
                "--input", "test data"
            ])

        captured = capsys.readouterr()
        # Check that suggestions are displayed
        assert "parsing_re" in captured.out.lower() or "regex" in captured.out.lower()
        assert "platform" in captured.out.lower()

    def test_non_empty_results_succeeds(self, capsys, monkeypatch):
        """Test that non-empty results succeed without error."""
        class MockManager:
            def __init__(self, *args, **kwargs):
                pass

            def validateUSP(self, **kwargs):
                return {
                    'errors': [],
                    'results': [{'event_type': 'test', 'data': 'parsed'}]
                }

        import limacharlie.USP as usp_module
        monkeypatch.setattr(usp_module, 'Manager', MockManager)

        # Should not raise SystemExit
        main([
            "validate",
            "--platform", "cef",
            "--input", "test data"
        ])

        captured = capsys.readouterr()
        assert "VALIDATION SUCCESSFUL" in captured.out
        assert "Parsed 1 event(s)" in captured.out
