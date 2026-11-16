"""CLI tests for the host-posture group (Host Posture extension and its rule hive)."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.discovery import get_explain


def _record(data):
    rec = MagicMock()
    rec.to_dict.return_value = {"data": data, "usr_mtd": {"enabled": True}, "sys_mtd": {"etag": "e1"}}
    return rec


@pytest.fixture
def hive():
    with patch("limacharlie.commands._hive_shortcut.Client"), \
         patch("limacharlie.commands._hive_shortcut.Organization"), \
         patch("limacharlie.commands._hive_shortcut.Hive") as hive_cls:
        mock_hive = MagicMock()
        hive_cls.return_value = mock_hive
        yield hive_cls, mock_hive


@pytest.fixture
def sdk():
    with patch("limacharlie.commands.host_posture.Client"), \
         patch("limacharlie.commands.host_posture.Organization"), \
         patch("limacharlie.commands.host_posture.HostPosture") as cls:
        inst = MagicMock()
        cls.return_value = inst
        yield inst


def run(args):
    return CliRunner().invoke(cli, ["--output", "json"] + args)


class TestRulesHive:
    def test_list_get_delete_target_the_rule_hive(self, hive):
        hive_cls, mock_hive = hive
        mock_hive.list.return_value = {"lc.a": _record({"rule": {"id": "lc.a"}})}
        mock_hive.get.return_value = _record({"rule": {"id": "lc.a"}})
        mock_hive.delete.return_value = {}

        assert run(["host-posture", "rules", "list"]).exit_code == 0
        assert hive_cls.call_args[0][1] == "host_posture_rule"
        assert run(["host-posture", "rules", "get", "--key", "lc.a"]).exit_code == 0
        mock_hive.get.assert_called_once_with("lc.a")
        # delete needs --confirm
        assert run(["host-posture", "rules", "delete", "--key", "lc.a"]).exit_code != 0
        mock_hive.delete.assert_not_called()
        assert run(["host-posture", "rules", "delete", "--key", "lc.a", "--confirm"]).exit_code == 0
        mock_hive.delete.assert_called_once_with("lc.a")

    def test_set_sends_the_record_unvalidated(self, hive, tmp_path):
        hive_cls, mock_hive = hive
        mock_hive.set.return_value = {}
        body = tmp_path / "rule.yaml"
        # Not a valid rule: the server is the only validator and must see it as is.
        body.write_text("rule: {id: acme.x, version: 1, nonsense: true}\nscope: {sensor_tags: [prod]}\n")

        result = run(["host-posture", "rules", "set", "--key", "acme.x", "--input-file", str(body), "--enabled"])

        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == "host_posture_rule"
        record = mock_hive.set.call_args[0][0]
        assert record.name == "acme.x" and record.enabled is True
        assert record.data == {"rule": {"id": "acme.x", "version": 1, "nonsense": True},
                               "scope": {"sensor_tags": ["prod"]}}

    def test_enable_and_disable_write_metadata_only(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.return_value = MagicMock(data=None)
        mock_hive.set.return_value = {}
        assert run(["host-posture", "rules", "disable", "--key", "lc.a"]).exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is False and record.data is None


class TestCommands:
    def test_scan(self, sdk):
        sdk.scan.return_value = {"job_id": "j", "sid": "s1", "platform": "linux", "tasks_issued": 1}
        result = run(["host-posture", "scan", "--sid", "s1"])
        assert result.exit_code == 0, result.output
        sdk.scan.assert_called_once_with("s1")
        assert json.loads(result.output)["job_id"] == "j"

    def test_scan_requires_sid(self, sdk):
        assert run(["host-posture", "scan"]).exit_code != 0

    def test_sweep_tags(self, sdk):
        sdk.sweep.return_value = {"job_id": "j", "sensors_tasked": 3}
        assert run(["host-posture", "sweep"]).exit_code == 0
        sdk.sweep.assert_called_with(None)
        assert run(["host-posture", "sweep", "--tag", "prod", "--tag", "web"]).exit_code == 0
        sdk.sweep.assert_called_with(["prod", "web"])

    def test_status(self, sdk):
        sdk.status.return_value = {"rules": 3}
        assert run(["host-posture", "status"]).exit_code == 0
        sdk.status.assert_called_once_with()

    def test_install_defaults_arguments_and_failure_exit(self, sdk):
        sdk.install_default_pack.return_value = {"created": [], "updated": [], "skipped": [], "failed": []}
        assert run(["host-posture", "install-defaults"]).exit_code == 0
        sdk.install_default_pack.assert_called_with(None, update=False, force=False, enabled=True, dry_run=False)
        assert run(["host-posture", "install-defaults", "--id", "a", "--id", "b", "--update", "--force", "--disabled", "--dry-run"]).exit_code == 0
        sdk.install_default_pack.assert_called_with(["a", "b"], update=True, force=True, enabled=False, dry_run=True)
        sdk.install_default_pack.return_value = {"created": [], "updated": [], "skipped": [], "failed": [{"id": "a"}]}
        assert run(["host-posture", "install-defaults"]).exit_code == 1

    def test_results_queries_pass_server_side_filters(self, sdk):
        sdk.query_hosts.return_value = {"hosts": [], "next_cursor": ""}
        run(["host-posture", "results", "hosts", "--platform", "windows", "--severity", "high",
             "--status", "fail", "--search", "srv", "--limit", "10", "--cursor", "c"])
        sdk.query_hosts.assert_called_with(
            platform="windows", severity="high", status="fail", search="srv", cursor="c", limit=10)
        sdk.query_rules.return_value = {"rules": []}
        run(["host-posture", "results", "rules", "--severity", "critical"])
        sdk.query_rules.assert_called_with(severity="critical", platform=None, search=None, cursor=None, limit=None)
        sdk.query_rule_hosts.return_value = {"hosts": []}
        run(["host-posture", "results", "rule-hosts", "--rule-id", "lc.a"])
        sdk.query_rule_hosts.assert_called_with("lc.a", "fail", cursor=None, limit=None)
        sdk.query_host.return_value = {}
        run(["host-posture", "results", "host", "--sid", "s1"])
        sdk.query_host.assert_called_with("s1")
        sdk.query_standards.return_value = {}
        run(["host-posture", "results", "standards", "--framework", "cis"])
        sdk.query_standards.assert_called_with("cis")
        sdk.query_summary.return_value = {}
        assert run(["host-posture", "results", "summary"]).exit_code == 0

    def test_filter_values_are_closed_sets(self, sdk):
        assert run(["host-posture", "results", "hosts", "--severity", "bogus"]).exit_code != 0
        assert run(["host-posture", "results", "rule-hosts", "--rule-id", "x", "--status", "unsupported"]).exit_code != 0
        assert run(["host-posture", "results", "hosts", "--limit", "201"]).exit_code != 0


class TestHelp:
    def test_every_command_has_explain_text_at_its_full_path(self):
        for path in (
            "host-posture", "host-posture.rules", "host-posture.install-defaults", "host-posture.scan",
            "host-posture.sweep", "host-posture.status", "host-posture.results",
            "host-posture.results.summary", "host-posture.results.hosts", "host-posture.results.host",
            "host-posture.results.rules", "host-posture.results.rule-hosts", "host-posture.results.standards",
        ):
            assert get_explain(path), path
        for cmd in ("list", "get", "set", "delete", "enable", "disable", "tag.set", "tag.add", "tag.rm"):
            assert get_explain(f"host-posture.rules.{cmd}"), cmd

    def test_permissions_are_documented_where_they_bite(self):
        assert "sensor.task" in get_explain("host-posture.rules.set")
        assert "sensor.task" in get_explain("host-posture.rules.enable")
        assert "sensor.task" in get_explain("host-posture.rules.disable")
        assert "host_posture.set" in get_explain("host-posture.rules.delete")

    def test_ai_help_for_set_documents_the_record(self):
        result = CliRunner().invoke(cli, ["host-posture", "rules", "set", "--ai-help"])
        assert result.exit_code == 0
        assert "exclude_sensor_tags" in result.output

    def test_hive_is_a_known_type(self):
        result = run(["hive", "list-types"])
        assert result.exit_code == 0 and "host_posture_rule" in result.output
