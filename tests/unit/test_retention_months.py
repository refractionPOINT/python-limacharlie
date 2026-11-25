"""retention_months: the org value carrying data retention in months.

Sync runs on the server, so the SDK's job is to carry the value in both
directions untouched and to surface the API's refusal (a value above 12 needs
a paid plan and billing.ctrl) instead of swallowing it.
"""

import base64
import gzip
import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.client import Client
from limacharlie.errors import LimaCharlieError
from limacharlie.sdk.organization import Organization


@pytest.fixture
def sync_transport(monkeypatch):
    org = MagicMock()
    org.oid = "test-oid"
    org.client._jwt = "sync-test-jwt"
    monkeypatch.setattr("limacharlie.commands.sync._get_org", lambda _ctx: org)
    return org.client.request


def _decode(params):
    return params["action"], json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))


def test_org_value_roundtrips_through_sync_as_a_string(tmp_path, sync_transport):
    pushed = []

    def transport(method, path, *, params):
        action, payload = _decode(params)
        if action == "fetch":
            assert payload["options"]["sync_org_values"] is True
            return {"data": {"org": {"version": 3, "org-value": {"retention_months": "24", "otx": "k"}}}}
        pushed.append(payload)
        return {"data": {"ops": [{"type": "org-value", "name": "retention_months", "is_added": True}]}}

    sync_transport.side_effect = transport
    config_file = tmp_path / "org.yaml"
    runner = CliRunner()
    pulled = runner.invoke(cli, ["sync", "pull", "--config-file", str(config_file), "--org-values"])
    assert pulled.exit_code == 0, pulled.output
    assert yaml.safe_load(config_file.read_text())["org-value"]["retention_months"] == "24"

    result = runner.invoke(cli, ["sync", "push", "--config-file", str(config_file), "--org-values"])
    assert result.exit_code == 0, result.output
    assert "+ org-value: retention_months" in result.output
    # Quoted on the wire: a numeric-looking value must not turn into an int.
    assert yaml.safe_load(pushed[0]["config"])["org-value"]["retention_months"] == "24"
    assert pushed[0]["options"]["sync_org_values"] is True


def test_push_surfaces_the_apis_retention_refusal(tmp_path, sync_transport):
    config_file = tmp_path / "org.yaml"
    config_file.write_text('version: 3\norg-value:\n  retention_months: "24"\n')
    reason = "retention_months: unauthorized, missing permission: billing.ctrl"

    def transport(method, path, *, params):
        return {"data": {"ops": [], "errors": [{"error": reason}]}}

    sync_transport.side_effect = transport
    result = CliRunner().invoke(cli, ["sync", "push", "--config-file", str(config_file), "--org-values"])
    assert result.exit_code == 1, result.output
    assert reason in result.output


@pytest.mark.parametrize("status,body,reason", [
    (403, {"error": "unauthorized, missing permission: billing.ctrl"}, "billing.ctrl"),
    (402, {"error": "extended retention requires a paid plan"}, "requires a paid plan"),
])
def test_set_config_refusal_reaches_the_caller(status, body, reason):
    jwt_response = MagicMock()
    jwt_response.read.return_value = json.dumps({"jwt": "test-jwt"}).encode()
    jwt_response.getheaders.return_value = []

    with patch("limacharlie.client.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            jwt_response,
            HTTPError("https://api.limacharlie.io", status, "refused", {}, io.BytesIO(json.dumps(body).encode())),
        ]
        org = Organization(Client(oid="test-oid", api_key="test-key"))
        with pytest.raises(LimaCharlieError) as exc:
            org.set_config("retention_months", "24")
    assert reason in str(exc.value)


def test_config_set_help_documents_retention_months():
    result = CliRunner().invoke(cli, ["org", "config-set", "--ai-help"])
    assert result.exit_code == 0, result.output
    assert "retention_months" in result.output
    assert "billing.ctrl" in result.output
    assert "org config-set --name retention_months --value 24" in result.output
