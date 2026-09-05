"""Exercise ACL sync through CLI flags, YAML files, and the SDK wire payload."""

import base64
import copy
import gzip
import json
from unittest.mock import MagicMock

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.configs import Configs


@pytest.fixture
def sync_transport(monkeypatch):
    org = MagicMock()
    org.oid = "test-oid"
    org.client._jwt = "sync-test-jwt"
    monkeypatch.setattr("limacharlie.commands.sync._get_org", lambda _ctx: org)
    return org.client.request


def decode_request(method, path, *, params):
    assert method == "POST"
    assert path == "extension/request/ext-infrastructure"
    assert params["oid"] == "test-oid"
    assert params["impersonator_jwt"] == "sync-test-jwt"
    return params["action"], json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))


@pytest.mark.parametrize("flags", [["--hive-acl", "--hive-secret"], ["--all"]])
def test_acl_pull_push_preserves_records_and_tags(tmp_path, sync_transport, flags):
    original = {
        "version": 3,
        "hives": {
            "acl": {
                "finance": {
                    "data": {"members": [
                        {"type": "user", "id": "analyst@example.com"},
                        {"type": "api_key", "id": "test-key-id"},
                        {"type": "group", "id": "test-group-id"},
                    ]},
                    "usr_mtd": {"enabled": True, "tags": ["managed"], "comment": "IaC scope"},
                },
                "locked": {"data": {"members": []}, "usr_mtd": {"enabled": True}},
            },
            "secret": {
                "credential": {
                    "data": {"secret": "test-only-value"},
                    "usr_mtd": {"enabled": False, "tags": ["ordinary", "acl:finance", "acl:locked"],
                                "comment": "preserve classification", "expiry": 1900000000},
                },
            },
        },
    }
    requests = []

    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        requests.append((action, payload))
        hives = payload["options"]["sync_hives"]
        if action == "fetch":
            # Model the backend's selection: --all must actually request ACLs.
            selected = {name: records for name, records in original["hives"].items() if hives.get(name)}
            return {"data": {"org": {"version": 3, "hives": copy.deepcopy(selected)}}}
        assert action == "push"
        assert hives["acl"] is True
        assert hives["secret"] is True
        assert yaml.safe_load(payload["config"]) == original
        assert payload["options"]["is_force"] is False
        assert payload["options"]["ignore_inaccessible"] is False
        return {"data": {"ops": [{"type": "hive.acl", "name": "finance", "is_added": True}]}}

    sync_transport.side_effect = transport
    config_file = tmp_path / "org.yaml"
    runner = CliRunner()
    pulled = runner.invoke(cli, ["sync", "pull", "--config-file", str(config_file), *flags])
    assert pulled.exit_code == 0, pulled.output
    assert yaml.safe_load(config_file.read_text()) == original
    pushed = runner.invoke(cli, ["sync", "push", "--config-file", str(config_file), *flags])
    assert pushed.exit_code == 0, pushed.output
    assert "+ hive.acl: finance" in pushed.output
    assert [action for action, _ in requests] == ["fetch", "push"]
    assert "acl" in Configs.ALL_HIVES


def test_acl_sync_is_opt_in(tmp_path, sync_transport):
    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        assert action == "fetch"
        assert payload["options"]["sync_hives"] == {"secret": True}
        return {"data": {"org": {"version": 3, "hives": {"secret": {}}}}}

    sync_transport.side_effect = transport
    result = CliRunner().invoke(cli, [
        "sync", "pull", "--config-file", str(tmp_path / "secrets.yaml"), "--hive-secret",
    ])
    assert result.exit_code == 0, result.output
    sync_transport.assert_called_once()


def test_acl_push_permission_error_is_visible_and_nonzero(tmp_path, sync_transport):
    config_file = tmp_path / "org.yaml"
    config_file.write_text("version: 3\nhives:\n  acl:\n    finance:\n      data:\n        members: []\n")

    def transport(*args, **kwargs):
        action, payload = decode_request(*args, **kwargs)
        assert action == "push"
        assert payload["options"]["sync_hives"] == {"acl": True}
        return {"data": {"ops": [], "errors": [{"error": "acl.set required for hive.acl/finance"}]}}

    sync_transport.side_effect = transport
    result = CliRunner().invoke(cli, [
        "sync", "push", "--config-file", str(config_file), "--hive-acl",
    ])
    assert result.exit_code == 1, result.output
    assert "acl.set required for hive.acl/finance" in result.output
    sync_transport.assert_called_once()
