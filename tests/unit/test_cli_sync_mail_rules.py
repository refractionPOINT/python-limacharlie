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
