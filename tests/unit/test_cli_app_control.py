"""CLI tests for the app-control group (Application Control hives).

The group is a thin layer over the generic hive client: each subgroup must
target the right hive, send the record exactly as given, and leave validation
to the server.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.discovery import get_explain


def _record(data):
    rec = MagicMock()
    rec.to_dict.return_value = {
        "data": data,
        "usr_mtd": {"enabled": True},
        "sys_mtd": {"etag": "e1"},
    }
    return rec


_GROUPS = [
    ("policy", "app_control_policy"),
    ("rule", "app_control_rule"),
]


@pytest.fixture
def hive():
    with patch("limacharlie.commands._hive_shortcut.Client"), \
         patch("limacharlie.commands._hive_shortcut.Organization"), \
         patch("limacharlie.commands._hive_shortcut.Hive") as hive_cls:
        mock_hive = MagicMock()
        hive_cls.return_value = mock_hive
        yield hive_cls, mock_hive


class TestAppControlGroups:
    @pytest.mark.parametrize("sub,hive_name", _GROUPS)
    def test_list_targets_the_right_hive(self, hive, sub, hive_name):
        hive_cls, mock_hive = hive
        mock_hive.list.return_value = {"one": _record({"x": 1})}

        result = CliRunner().invoke(cli, ["--output", "json", "app-control", sub, "list"])

        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == hive_name
        assert json.loads(result.output)["one"]["data"] == {"x": 1}

    @pytest.mark.parametrize("sub,hive_name", _GROUPS)
    def test_get_targets_the_right_hive(self, hive, sub, hive_name):
        hive_cls, mock_hive = hive
        mock_hive.get.return_value = _record({"x": 1})

        result = CliRunner().invoke(cli, ["--output", "json", "app-control", sub, "get", "--key", "k1"])

        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == hive_name
        mock_hive.get.assert_called_once_with("k1")

    @pytest.mark.parametrize("sub,hive_name", _GROUPS)
    def test_delete_requires_confirm(self, hive, sub, hive_name):
        hive_cls, mock_hive = hive

        result = CliRunner().invoke(cli, ["app-control", sub, "delete", "--key", "k1"])
        assert result.exit_code != 0
        mock_hive.delete.assert_not_called()

        mock_hive.delete.return_value = {}
        result = CliRunner().invoke(cli, ["app-control", sub, "delete", "--key", "k1", "--confirm"])
        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == hive_name
        mock_hive.delete.assert_called_once_with("k1")

    def test_policy_set_sends_the_record_unvalidated(self, hive, tmp_path):
        hive_cls, mock_hive = hive
        mock_hive.set.return_value = {}
        # An out-of-vocabulary mode must reach the server untouched: the
        # server is the only validator.
        body = tmp_path / "policy.yaml"
        body.write_text(
            "priority: 10\nplatforms: [windows]\ntags: [lab]\n"
            "mode: not-a-real-mode\nstance: allowlist\ntrust_os_vendor: true\n"
        )

        result = CliRunner().invoke(cli, [
            "app-control", "policy", "set", "--key", "p1",
            "--input-file", str(body), "--enabled",
        ])

        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == "app_control_policy"
        record = mock_hive.set.call_args[0][0]
        assert record.name == "p1"
        assert record.data == {
            "priority": 10, "platforms": ["windows"], "tags": ["lab"],
            "mode": "not-a-real-mode", "stance": "allowlist", "trust_os_vendor": True,
        }
        assert record.enabled is True

    def test_rule_set_uses_key_as_rule_id(self, hive, tmp_path):
        hive_cls, mock_hive = hive
        mock_hive.set.return_value = {}
        body = tmp_path / "rule.json"
        body.write_text(json.dumps({
            "action": "deny", "kind": "sha256", "value": "ab" * 32, "policies": ["p1"],
        }))

        result = CliRunner().invoke(cli, [
            "app-control", "rule", "set", "--key", "block-x", "--input-file", str(body),
        ])

        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == "app_control_rule"
        record = mock_hive.set.call_args[0][0]
        assert record.name == "block-x"
        assert record.data["policies"] == ["p1"]


class TestAppControlHelp:
    @pytest.mark.parametrize("sub", ["policy", "rule"])
    def test_every_subcommand_has_explain_text_at_its_full_path(self, sub):
        # --ai-help looks explain text up by the full dotted command path, so a
        # nested hive group must register under 'app-control.<sub>', not '<sub>'.
        for cmd in ("list", "get", "set", "delete", "enable", "disable", "tag.set", "tag.add", "tag.rm"):
            assert get_explain(f"app-control.{sub}.{cmd}"), f"app-control.{sub}.{cmd}"
        assert get_explain("app-control")
        assert get_explain(f"app-control.{sub}")

    @pytest.mark.parametrize("sub,needle", [("policy", "trust_os_vendor"), ("rule", "signer_root")])
    def test_ai_help_for_set_documents_the_record(self, sub, needle):
        result = CliRunner().invoke(cli, ["app-control", sub, "set", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert needle in result.output

    def test_group_lists_both_subgroups(self):
        result = CliRunner().invoke(cli, ["app-control", "--help"])
        assert result.exit_code == 0, result.output
        assert "policy" in result.output
        assert "rule" in result.output
