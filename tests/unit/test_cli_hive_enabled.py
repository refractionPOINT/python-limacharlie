"""Check CLI metadata intent at the HTTP request boundary."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli


@pytest.mark.parametrize("payload", [
    {"data": {"policy_type": "classification", "classification": {}}},
    {"policy_type": "classification", "classification": {}},
])
def test_data_only_leaves_metadata_to_the_hive(payload):
    params = _set_request(payload)
    assert "usr_mtd" not in params
    assert json.loads(params["data"]) == {"policy_type": "classification", "classification": {}}


@pytest.mark.parametrize("metadata,flags,want", [
    ({}, [], {"enabled": False}),
    ({"enabled": None}, [], {"enabled": False}),
    ({"enabled": False}, [], {"enabled": False}),
    ({"enabled": True}, [], {"enabled": True}),
    ({"comment": "staged"}, [], {"enabled": False, "comment": "staged"}),
    ({"enabled": False, "tags": ["draft"]}, ["--enabled"], {"enabled": True, "tags": ["draft"]}),
    ({"enabled": True, "comment": "stage"}, ["--disabled"], {"enabled": False, "comment": "stage"}),
])
def test_explicit_metadata_and_flags_remain_authoritative(metadata, flags, want):
    params = _set_request({"data": {"a": 1}, "usr_mtd": metadata}, flags)
    assert json.loads(params["usr_mtd"]) == want


@pytest.mark.parametrize("flag,want", [("--enabled", True), ("--disabled", False)])
def test_enablement_flag_without_input_metadata(flag, want):
    params = _set_request({"data": {"a": 1}}, [flag])
    assert json.loads(params["usr_mtd"]) == {"enabled": want}


def _set_request(payload, flags=()):
    client = MagicMock()
    client.oid = "test-oid"
    client.request.return_value = {"guid": "test-guid"}
    # Keep the real Organization, HiveRecord and Hive serializers: checking a
    # mocked Hive.set call would not prove whether metadata reaches the API.
    with patch("limacharlie.commands.hive.Client", return_value=client):
        result = CliRunner().invoke(cli, [
            "hive", "set", "--hive-name", "cloudsec_policy", "--key", "policy",
            *flags,
        ], input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    client.request.assert_called_once()
    args, kwargs = client.request.call_args
    assert args == ("POST", "hive/cloudsec_policy/test-oid/policy/data")
    return kwargs["params"]
