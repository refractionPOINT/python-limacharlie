"""Sanitized upload preflight and offline command privacy boundary."""
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from limacharlie.commands.cloudsec import code_iac_map
from limacharlie.sdk.cloudsec import CloudSec
from limacharlie.sdk.iac_map import MAX_BYTES, validate_iac_map

GOLDEN = Path(__file__).parent / "fixtures" / "iac-map-v1.json"


def test_shared_extractor_golden_and_server_tenant_route():
    raw = GOLDEN.read_bytes().rstrip(b"\n")
    assert hashlib.sha256(raw).hexdigest() == "f4794551c6fc1b70037c207dd937d7ebac948a4ee37f4ad7052e894af41411ff"
    assert validate_iac_map(raw) == raw
    org = MagicMock(oid="tenant-a")
    CloudSec(org).push_iac_map(raw)
    org.client.request.assert_called_once_with("POST", "cloudsec/tenant-a/code/iac-map", raw_body=raw, content_type="application/json")


@pytest.mark.parametrize("raw", [b'{"values":{"password":"SENSITIVE_CANARY"}}',
    b'{"schema":"x","schema":"y"}', b"[" * 5000, b" " * (MAX_BYTES + 1),
    b'{"token":"SENSITIVE_CANARY"}', b'"\\ud800"'])
def test_refuse_before_network_and_never_echo(raw):
    org = MagicMock(oid="tenant-a")
    with pytest.raises(ValueError) as exc:
        CloudSec(org).push_iac_map(raw)
    assert "SENSITIVE_CANARY" not in str(exc.value)
    org.client.request.assert_not_called()


def test_forbidden_resource_fields_and_desired_values():
    for field, value in [("secret", "SENSITIVE_CANARY"), ("desired", {"password": True}), ("desired", {"force_destroy": "SENSITIVE_CANARY"})]:
        doc = json.loads(GOLDEN.read_bytes())
        doc["resources"][0][field] = value
        with pytest.raises(ValueError):
            validate_iac_map(json.dumps(doc))
    doc = json.loads(GOLDEN.read_bytes())
    doc["oid"] = "tenant-b"
    with pytest.raises(ValueError):
        validate_iac_map(json.dumps(doc))


def test_offline_extract_does_not_authenticate_or_inherit_tokens(tmp_path):
    source = tmp_path / "terraform.json"
    source.write_text('{"values":{"secret":"SENSITIVE_CANARY"}}')
    def run(args, **kwargs):
        assert kwargs["env"] == {"PATH": __import__("os").defpath}
        assert kwargs["timeout"] == 10
        assert args[0] == "/trusted/iac-map-extract"
        kwargs["stdout"].write(GOLDEN.read_bytes())
        return MagicMock(returncode=0)
    with patch("shutil.which", return_value="/trusted/iac-map-extract"), patch("limacharlie.commands.cloudsec.subprocess.run", side_effect=run), patch("limacharlie.commands.cloudsec._get_cloudsec") as auth:
        result = CliRunner().invoke(code_iac_map, ["extract", "--input", str(source), "--source-kind", "state_identity", "--repository", "owner/repo", "--commit", "a" * 40])
    assert result.exit_code == 0, result.output
    assert "SENSITIVE_CANARY" not in result.output
    assert json.loads(result.output)["schema"] == "lc-iac-map/v1"
    auth.assert_not_called()


def test_s3_map_is_supported_and_state_stays_identity_only():
    doc = json.loads(GOLDEN.read_bytes())
    resource = doc["resources"][0]
    resource.update(address="aws_s3_bucket.assets", type="aws_s3_bucket", provider="aws", scope={"account": "123456789012"}, identity={"name": "assets"})
    validate_iac_map(json.dumps(doc))
    resource["desired"] = {"force_destroy": True}
    with pytest.raises(ValueError):
        validate_iac_map(json.dumps(doc))
    doc["source_kind"] = "plan_desired"
    validate_iac_map(json.dumps(doc))
