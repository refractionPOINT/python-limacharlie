"""Tests for limacharlie.cli module."""

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli


class TestCLIBasics:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "5.0.0" in result.output

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "LimaCharlie CLI" in result.output
        assert "--oid" in result.output
        assert "--output" in result.output
        assert "--debug" in result.output

    def test_unknown_command(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0

    def test_output_format_choices(self):
        runner = CliRunner()
        # Verify the output format option accepts valid values
        result = runner.invoke(cli, ["--help"])
        assert "json" in result.output
        assert "yaml" in result.output
        assert "csv" in result.output
        assert "table" in result.output
        assert "jsonl" in result.output
