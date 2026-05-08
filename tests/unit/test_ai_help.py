"""Tests for the --ai-help feature (AI-oriented CLI help)."""

from __future__ import annotations

import click
import click.testing
import pytest

from limacharlie.ai_help import inject_ai_help, show_ai_help, _build_path


# ---------------------------------------------------------------------------
# Fixtures — build a minimal Click tree for testing
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_cli():
    """Build a small Click CLI tree for testing."""

    @click.group()
    def cli():
        """Top-level CLI for testing."""

    @cli.group("sensor")
    def sensor_group():
        """Manage endpoint sensors.

        Sensors are agents installed on endpoints.
        """

    @sensor_group.command("list")
    @click.option("--tag", help="Filter by tag.")
    @click.option("--limit", type=int, help="Max results.")
    def sensor_list(tag, limit):
        """List all sensors.

        Examples:
            limacharlie sensor list
            limacharlie sensor list --tag prod
        """

    @sensor_group.command("get")
    @click.option("--sid", required=True, help="Sensor ID.")
    def sensor_get(sid):
        """Get sensor details."""

    @cli.group("auth")
    def auth_group():
        """Authentication and identity management."""

    @auth_group.command("login")
    def auth_login():
        """Authenticate to LimaCharlie."""

    inject_ai_help(cli)
    return cli


# ---------------------------------------------------------------------------
# Injection tests
# ---------------------------------------------------------------------------

class TestInjectAiHelp:
    def test_flag_added_to_root(self, sample_cli):
        names = [p.name for p in sample_cli.params]
        assert "ai_help" in names

    def test_flag_added_to_group(self, sample_cli):
        sensor = sample_cli.commands["sensor"]
        names = [p.name for p in sensor.params]
        assert "ai_help" in names

    def test_flag_added_to_leaf_command(self, sample_cli):
        sensor_list = sample_cli.commands["sensor"].commands["list"]
        names = [p.name for p in sensor_list.params]
        assert "ai_help" in names

    def test_no_double_injection(self, sample_cli):
        # Inject again — should not duplicate
        inject_ai_help(sample_cli)
        ai_params = [p for p in sample_cli.params if p.name == "ai_help"]
        assert len(ai_params) == 1

    def test_flag_is_eager(self, sample_cli):
        opt = next(p for p in sample_cli.params if p.name == "ai_help")
        assert opt.is_eager is True

    def test_flag_not_exposed(self, sample_cli):
        opt = next(p for p in sample_cli.params if p.name == "ai_help")
        assert opt.expose_value is False


# ---------------------------------------------------------------------------
# Top-level help
# ---------------------------------------------------------------------------

class TestTopLevelHelp:
    def test_contains_header(self, sample_cli):
        result = _invoke(sample_cli, ["--ai-help"])
        assert "# LimaCharlie CLI" in result or "AI Help" in result

    def test_contains_getting_started(self, sample_cli):
        result = _invoke(sample_cli, ["--ai-help"])
        assert "Getting Started" in result

    def test_lists_all_groups(self, sample_cli):
        result = _invoke(sample_cli, ["--ai-help"])
        assert "sensor" in result
        assert "auth" in result

    def test_contains_global_options(self, sample_cli):
        result = _invoke(sample_cli, ["--ai-help"])
        assert "Global Options" in result

    def test_contains_drill_down_hint(self, sample_cli):
        result = _invoke(sample_cli, ["--ai-help"])
        assert "--ai-help" in result
        assert "Drill Down" in result


# ---------------------------------------------------------------------------
# Group-level help
# ---------------------------------------------------------------------------

class TestGroupHelp:
    def test_contains_group_name(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "--ai-help"])
        assert "sensor" in result

    def test_contains_group_description(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "--ai-help"])
        assert "endpoint sensors" in result.lower() or "agents" in result.lower()

    def test_lists_subcommands(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "--ai-help"])
        assert "### list" in result
        assert "### get" in result

    def test_shows_options_for_subcommands(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "--ai-help"])
        assert "--tag" in result
        assert "--sid" in result

    def test_extracts_examples(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "--ai-help"])
        assert "limacharlie sensor list --tag prod" in result

    def test_contains_drill_down_hint(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "--ai-help"])
        assert "Drill Down" in result


# ---------------------------------------------------------------------------
# Command-level help
# ---------------------------------------------------------------------------

class TestCommandHelp:
    def test_contains_command_name(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "list", "--ai-help"])
        assert "sensor list" in result

    def test_contains_description(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "list", "--ai-help"])
        assert "List all sensors" in result

    def test_contains_options_section(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "list", "--ai-help"])
        assert "Options" in result
        assert "--tag" in result
        assert "--limit" in result

    def test_contains_examples_section(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "list", "--ai-help"])
        assert "Examples" in result
        assert "limacharlie sensor list --tag prod" in result

    def test_contains_usage_section(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "list", "--ai-help"])
        assert "Usage" in result

    def test_required_option_shown(self, sample_cli):
        result = _invoke(sample_cli, ["sensor", "get", "--ai-help"])
        assert "--sid" in result
        assert "(required)" in result


# ---------------------------------------------------------------------------
# Integration with the real CLI
# ---------------------------------------------------------------------------

class TestRealCLI:
    def test_top_level_ai_help(self):
        from limacharlie.cli import cli
        result = _invoke(cli, ["--ai-help"])
        assert "LimaCharlie CLI" in result
        assert "sensor" in result

    def test_sensor_group_ai_help(self):
        from limacharlie.cli import cli
        result = _invoke(cli, ["sensor", "--ai-help"])
        assert "sensor" in result
        assert "### list" in result

    def test_sensor_list_ai_help(self):
        from limacharlie.cli import cli
        result = _invoke(cli, ["sensor", "list", "--ai-help"])
        assert "sensor list" in result
        assert "--tag" in result

    def test_endpoint_policy_ai_help(self):
        from limacharlie.cli import cli
        result = _invoke(cli, ["endpoint-policy", "--ai-help"])
        assert "isolate" in result
        assert "seal" in result

    def test_dr_ai_help(self):
        from limacharlie.cli import cli
        result = _invoke(cli, ["dr", "--ai-help"])
        assert "Detection" in result or "D&R" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke(cli, args: list[str]) -> str:
    """Invoke a Click CLI and capture output."""
    runner = click.testing.CliRunner()
    result = runner.invoke(cli, args, catch_exceptions=False)
    return result.output
