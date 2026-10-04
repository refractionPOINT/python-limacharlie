"""Mail rules survive CLI pull/push with the Hive identity and metadata intact."""
import copy
import yaml
import pytest
from click.testing import CliRunner
from limacharlie.cli import cli
from tests.unit.test_cli_sync_acl import sync_transport, decode_request

@pytest.mark.parametrize("flags", [["--hive-dr-mail", "--hive-mailsec-policy"], ["--all"]])
def test_mail_rules_roundtrip(tmp_path, sync_transport, flags):
    config = {"version": 3, "hives": {
        "dr-mail": {"finance": {"data": {
            "name": "DMARC failure", "phase": "pre_verdict", "weight": 25,
            "detect": {"op": "is", "path": "auth/dmarc/result", "value": "fail"},
        }, "usr_mtd": {"enabled": False, "tags": ["acl:team"], "comment": "tuned"}}},
        "mailsec_policy": {"thresholds": {"data": {"policy_type": "thresholds", "suspicious_min": 40}, "usr_mtd": {"enabled": True}}},
    }}
    actions = []
    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        actions.append(action)
        assert payload["options"]["sync_hives"]["dr-mail"] is True
        assert payload["options"]["sync_hives"]["mailsec_policy"] is True
        if action == "fetch":
            return {"data": {"org": copy.deepcopy(config)}}
        assert yaml.safe_load(payload["config"]) == config
        return {"data": {"ops": []}}
    sync_transport.side_effect = transport
    path = tmp_path / "mailsec.yaml"
    for action in ["pull", "push"]:
        result = CliRunner().invoke(cli, ["sync", action, "--config-file", str(path), *flags])
        assert result.exit_code == 0, result.output
    assert actions == ["fetch", "push"]


@pytest.mark.parametrize("flags", [["--hive-app-control-policy", "--hive-app-control-rule"], ["--all"]])
def test_app_control_roundtrip(tmp_path, sync_transport, flags):
    config = {"version": 3, "hives": {
        "app_control_policy": {"workstations": {"data": {
            "priority": 10, "platforms": ["windows", "macos"], "tags": ["lab"],
            "mode": "permissive", "stance": "allowlist", "trust_os_vendor": True,
        }, "usr_mtd": {"enabled": True}}},
        "app_control_rule": {"block-x": {"data": {
            "action": "deny", "kind": "sha256", "value": "ab" * 32, "policies": ["workstations"],
        }, "usr_mtd": {"enabled": True, "comment": "known bad"}}},
    }}
    actions = []
    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        actions.append(action)
        assert payload["options"]["sync_hives"]["app_control_policy"] is True
        assert payload["options"]["sync_hives"]["app_control_rule"] is True
        if action == "fetch":
            return {"data": {"org": copy.deepcopy(config)}}
        assert yaml.safe_load(payload["config"]) == config
        return {"data": {"ops": []}}
    sync_transport.side_effect = transport
    path = tmp_path / "app-control.yaml"
    for action in ["pull", "push"]:
        result = CliRunner().invoke(cli, ["sync", action, "--config-file", str(path), *flags])
        assert result.exit_code == 0, result.output
    assert actions == ["fetch", "push"]
    assert yaml.safe_load(path.read_text()) == config


def test_app_control_flags_select_only_their_hives(tmp_path, sync_transport):
    seen = {}
    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        seen.update(payload["options"]["sync_hives"])
        return {"data": {"org": {"version": 3, "hives": {}}}}
    sync_transport.side_effect = transport
    result = CliRunner().invoke(cli, ["sync", "pull", "--config-file", str(tmp_path / "c.yaml"), "--hive-app-control-rule"])
    assert result.exit_code == 0, result.output
    assert seen.get("app_control_rule") is True
    assert not seen.get("app_control_policy")
