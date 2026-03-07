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
        from limacharlie import __version__
        assert __version__ in result.output

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


class TestHelpTopicFallthrough:
    def test_help_topic_shortcut(self):
        """limacharlie help auth should work like limacharlie help topic auth."""
        runner = CliRunner()
        result = runner.invoke(cli, ["help", "auth"])
        assert result.exit_code == 0
        assert "Authentication" in result.output

    def test_help_topic_explicit(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["help", "topic", "auth"])
        assert result.exit_code == 0
        assert "Authentication" in result.output

    def test_help_unknown_topic(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["help", "nonexistent_xyz"])
        assert result.exit_code != 0

    def test_help_subcommands_still_work(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["help", "discover"])
        assert result.exit_code == 0


class TestAuthCommands:
    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = "test-uid"
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {"ident": "user@test.com", "perms": ["a", "b"]}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "whoami"])
        assert result.exit_code == 0
        assert "user@test.com" in result.output
        assert "test-oid" in result.output
        assert "test-uid" in result.output
        mock_org.who_am_i.assert_called_once()

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_quiet(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client_cls.return_value = mock_client

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
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = "test-uid"
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {"ident": "user@test.com", "perms": ["p1", "p2"]}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "auth", "whoami"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ident"] == "user@test.com"
        assert parsed["oid"] == "test-oid"
        assert parsed["uid"] == "test-uid"
        # Perms hidden by default
        assert "perms" not in parsed

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_hides_perms_by_default(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {"ident": "user@test.com", "perms": ["a", "b"]}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "auth", "whoami"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "perms" not in parsed
        assert parsed["ident"] == "user@test.com"

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_show_perms(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        perms = [f"perm{i}" for i in range(100)]
        mock_org.who_am_i.return_value = {"ident": "user@test.com", "perms": perms}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "whoami", "--show-perms"])
        assert result.exit_code == 0
        # Perms should be expanded, not shown as "[100 items]"
        assert "[100 items]" not in result.output
        assert "perm0" in result.output

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_check_perm_found(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {
            "ident": "user@test.com",
            "perms": ["ai_agent.operate", "sensor.list"],
        }
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "auth", "whoami", "--check-perm", "ai_agent.operate"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["has_perm"] is True
        assert parsed["perm"] == "ai_agent.operate"

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_check_perm_missing(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {
            "ident": "user@test.com",
            "perms": ["sensor.list"],
        }
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "auth", "whoami", "--check-perm", "ai_agent.operate"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["has_perm"] is False
        assert parsed["perm"] == "ai_agent.operate"

    @patch("limacharlie.commands.auth.Client")
    @patch("limacharlie.commands.auth.Organization")
    def test_whoami_check_perm_in_user_perms(self, mock_org_cls, mock_client_cls):
        mock_client = MagicMock()
        mock_client.oid = "test-oid"
        mock_client.uid = None
        mock_client_cls.return_value = mock_client

        mock_org = MagicMock()
        mock_org.who_am_i.return_value = {
            "ident": "user@test.com",
            "perms": [],
            "user_perms": {"some-oid": ["ai_agent.operate", "sensor.list"]},
        }
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "auth", "whoami", "--check-perm", "ai_agent.operate"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["has_perm"] is True

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
    def test_org_create_shows_url(self, mock_org_cls, mock_client_cls):
        oid = "d379729c-ab8c-492b-808e-5be1bb09774f"
        mock_org_cls.create_org.return_value = {
            "success": True,
            "data": {"code": "e3d54874270322f0", "loc": "usa", "oid": oid},
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "org", "create", "--name", "test-org"])
        assert result.exit_code == 0
        assert f"https://app.limacharlie.io/orgs/{oid}" in result.output
        mock_org_cls.create_org.assert_called_once()

    @patch("limacharlie.commands.org.Client")
    @patch("limacharlie.commands.org.Organization")
    def test_org_create_quiet_no_url(self, mock_org_cls, mock_client_cls):
        oid = "d379729c-ab8c-492b-808e-5be1bb09774f"
        mock_org_cls.create_org.return_value = {
            "success": True,
            "data": {"code": "abc", "loc": "usa", "oid": oid},
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["--quiet", "org", "create", "--name", "test-org"])
        assert result.exit_code == 0
        assert "app.limacharlie.io" not in result.output

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


class TestHiveEnableDisable:
    @staticmethod
    def _existing_record(name="my-rule", enabled=True):
        """Return an HiveRecord simulating existing metadata."""
        from limacharlie.sdk.hive import HiveRecord
        return HiveRecord(
            name=name, enabled=enabled,
            tags=["keep-me"], expiry=1234, comment="preserve this",
            etag="old-etag",
        )

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_hive_enable(self, mock_hive_cls, mock_org_cls, mock_client_cls):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = self._existing_record(enabled=False)
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["hive", "enable", "--hive-name", "dr-general", "--key", "my-rule"])
        assert result.exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is True
        assert record.data is None  # only metadata update
        assert record.tags == ["keep-me"]
        assert record.expiry == 1234
        assert record.comment == "preserve this"

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_hive_disable(self, mock_hive_cls, mock_org_cls, mock_client_cls):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = self._existing_record(enabled=True)
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["hive", "disable", "--hive-name", "dr-general", "--key", "my-rule"])
        assert result.exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is False
        assert record.data is None
        assert record.tags == ["keep-me"]

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_shortcut_enable(self, mock_hive_cls, mock_org_cls, mock_client_cls):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = self._existing_record("my-secret", enabled=False)
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["secret", "enable", "--key", "my-secret"])
        assert result.exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is True
        assert record.tags == ["keep-me"]

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_shortcut_disable(self, mock_hive_cls, mock_org_cls, mock_client_cls):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = self._existing_record("my-secret", enabled=True)
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["secret", "disable", "--key", "my-secret"])
        assert result.exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is False
        assert record.tags == ["keep-me"]


