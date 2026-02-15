"""Tests for limacharlie.cli module."""

import json
from unittest.mock import patch, MagicMock

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


class TestCLIGlobalOptions:
    def test_wide_in_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "--wide" in result.output

    def test_filter_in_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "--filter" in result.output

    def test_wide_flag_sets_wide_mode(self):
        import limacharlie.output as output_mod
        original = output_mod._wide_mode
        try:
            runner = CliRunner()
            # Use --help on a subcommand to avoid needing auth mocks
            result = runner.invoke(cli, ["--wide", "auth", "whoami", "--help"])
            assert result.exit_code == 0
            assert output_mod._wide_mode is True
        finally:
            output_mod._wide_mode = original

    def test_filter_flag_sets_filter_expr(self):
        import limacharlie.output as output_mod
        original = output_mod._filter_expr
        try:
            runner = CliRunner()
            result = runner.invoke(cli, ["--filter", "items[0]", "auth", "whoami", "--help"])
            assert result.exit_code == 0
            assert output_mod._filter_expr == "items[0]"
        finally:
            output_mod._filter_expr = original


class TestAuthCommands:
    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {"ident": "user@test.com"}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "whoami"])
        assert result.exit_code == 0
        assert "user@test.com" in result.output
        mock_org.who_am_i.assert_called_once()

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_quiet(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {"ident": "user@test.com"}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--quiet", "auth", "whoami"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_json(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {"ident": "user@test.com"}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "auth", "whoami"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ident"] == "user@test.com"

    @patch("limacharlie.commands.auth.Client")
    def test_auth_test_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "test"])
        assert result.exit_code == 0
        assert "successful" in result.output
        mock_client.refresh_jwt.assert_called_once()

    @patch("limacharlie.commands.auth.list_environments", return_value=["default", "staging"])
    @patch("limacharlie.commands.auth.load_config", return_value={"current_env": "default"})
    def test_list_envs(self, mock_config, mock_list):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "list-envs"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "staging" in result.output


class TestOrgCommands:
    @patch("limacharlie.commands.org.Client")
    @patch("limacharlie.commands.org.Organization")
    def test_org_info(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.get_info.return_value = {"name": "TestOrg", "sensor_count": 42}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "org", "info"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["name"] == "TestOrg"
        mock_org.get_info.assert_called_once()

    @patch("limacharlie.commands.org.Client")
    @patch("limacharlie.commands.org.Organization")
    def test_org_urls(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.get_urls.return_value = {"main": "https://app.limacharlie.io"}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "org", "urls"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "main" in parsed
        mock_org.get_urls.assert_called_once()

    @patch("limacharlie.commands.org.Client")
    @patch("limacharlie.commands.org.Organization")
    def test_org_errors(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.get_errors.return_value = [{"component": "output-s3", "error": "access denied"}]
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "org", "errors"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["component"] == "output-s3"
        mock_org.get_errors.assert_called_once()


class TestSensorCommands:
    @patch("limacharlie.commands.sensor.Client")
    @patch("limacharlie.commands.sensor.Organization")
    def test_sensor_list(self, mock_org_cls, mock_client_cls):
        mock_org = MagicMock()
        mock_org.list_sensors.return_value = iter([
            {"sid": "sid-1", "hostname": "host1"},
            {"sid": "sid-2", "hostname": "host2"},
        ])
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "sensor", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 2
        assert parsed[0]["sid"] == "sid-1"

    @patch("limacharlie.commands.sensor.Client")
    @patch("limacharlie.commands.sensor.Sensor")
    @patch("limacharlie.commands.sensor.Organization")
    def test_sensor_get(self, mock_org_cls, mock_sensor_cls, mock_client_cls):
        mock_sensor = MagicMock()
        mock_sensor.get_info.return_value = {"sid": "sid-1", "hostname": "host1", "platform": "windows"}
        mock_sensor_cls.return_value = mock_sensor

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "sensor", "get", "--sid", "sid-1"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["sid"] == "sid-1"

    @patch("limacharlie.commands.sensor.Client")
    def test_sensor_delete_without_confirm(self, mock_client_cls):
        runner = CliRunner()
        result = runner.invoke(cli, ["sensor", "delete", "--sid", "sid-1"])
        assert result.exit_code != 0


class TestDRCommands:
    @patch("limacharlie.commands.dr.Client")
    @patch("limacharlie.commands.dr.Organization")
    @patch("limacharlie.commands.dr.Hive")
    def test_dr_list(self, mock_hive_cls, mock_org_cls, mock_client_cls):
        mock_record = MagicMock()
        mock_record.to_dict.return_value = {"detect": {"op": "is"}, "respond": [{"action": "report"}]}
        mock_hive = MagicMock()
        mock_hive.list.return_value = {"my-rule": mock_record}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "dr", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "my-rule" in parsed
        mock_hive.list.assert_called_once()


