"""End-to-end integration tests for the LimaCharlie CLI v2 using Click's CliRunner."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from click.testing import CliRunner
from limacharlie.cli import cli
from limacharlie.client import __version__


def test_v2_cli_help():
    """Verify 'limacharlie --help' exits successfully and shows usage."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"
    )
    assert "Usage" in result.output or "usage" in result.output.lower(), (
        f"Expected usage text in help output. Got:\n{result.output}"
    )


def test_v2_cli_version():
    """Verify 'limacharlie --version' shows the version string."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"
    )
    assert __version__ in result.output, (
        f"Expected version '{__version__}' in output. Got:\n{result.output}"
    )


def test_v2_cli_org_info(oid, key):
    """Verify 'limacharlie org info --oid OID' returns org information via CLI."""
    runner = CliRunner(env={"LC_API_KEY": key})
    result = runner.invoke(cli, ["--oid", oid, "--output", "json", "org", "info"])
    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"
    )
    # The JSON output should contain the oid
    assert oid in result.output, (
        f"Expected OID '{oid}' in org info output. Got:\n{result.output}"
    )
