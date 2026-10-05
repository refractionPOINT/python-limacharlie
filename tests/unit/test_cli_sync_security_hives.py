"""Selected security hives round-trip without resolving credential references."""
import copy

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.configs import Configs
from tests.unit.test_cli_sync_acl import sync_transport, decode_request

HIVES = {
    "cloudsec_provider": {"github": {"data": {
        "provider_type": "github", "github_org": "acme", "github_app_id": "123",
        "github_installation_id": "456", "credentials": "hive://secret/scan-key",
        "github_actions_app_id": "789", "github_actions_installation_id": "321",
        "actions_credentials": "hive://secret/write-key"},
        "usr_mtd": {"enabled": True, "tags": ["acl:team"], "comment": "scan connection"}}},
    "cloudsec_policy": {"scan": {"data": {"policy_type": "code_scanning",
        "code_scanning": {"enabled": True, "scanners": {"sca": True, "sast": False}}},
        "usr_mtd": {"enabled": False}}},
    "cloudsec_query": {"saved": {"data": {"query": {}}, "usr_mtd": {"enabled": True}}},
    "cloudsec_code_rule": {"no-eval": {"data": {"rules": [{"id": "no-eval",
        "languages": ["python"], "severity": "ERROR", "message": "Avoid eval", "pattern": "eval(...)"}]},
        "usr_mtd": {"enabled": True}}},
    "mailsec_provider": {"mail": {"data": {"provider_type": "microsoft365",
        "credentials": "hive://secret/mail-key"}, "usr_mtd": {"enabled": True}}},
}


@pytest.mark.parametrize("selection", [[name] for name in HIVES] + [list(HIVES), "all"])
def test_security_hives_pull_push_roundtrip(tmp_path, sync_transport, selection):
    names = list(HIVES) if selection == "all" else selection
    flags = ["--all"] if selection == "all" else ["--hive-" + name.replace("_", "-") for name in names]
    expected = {"version": 3, "hives": {name: copy.deepcopy(HIVES[name]) for name in names}}
    seen = []
    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        selected = payload["options"]["sync_hives"]
        assert all(selected[name] is True for name in names)
        if selection != "all":
            assert set(selected) == set(names)
        seen.append(action)
        if action == "fetch":
            return {"data": {"org": copy.deepcopy(expected)}}
        assert action == "push"
        assert yaml.safe_load(payload["config"]) == expected
        return {"data": {"ops": []}}
    sync_transport.side_effect = transport
    destination = tmp_path / "security.yaml"
    for action in ("pull", "push"):
        result = CliRunner().invoke(cli, ["sync", action, "--config-file", str(destination), *flags])
        assert result.exit_code == 0, result.output
    assert yaml.safe_load(destination.read_text()) == expected
    assert seen == ["fetch", "push"]
    assert set(names) <= Configs.ALL_HIVES
