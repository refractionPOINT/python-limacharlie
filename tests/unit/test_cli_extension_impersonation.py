"""Extension writes can explicitly use the caller's existing authorization."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli


@pytest.mark.parametrize("impersonate", [False, True])
def test_request_forwards_caller_identity_only_when_selected(impersonate):
    org = MagicMock()
    org.oid = "11111111-2222-3333-4444-555555555555"
    org.client._jwt = "synthetic-caller-jwt"
    org.client.request.return_value = {"data": {"ok": True}}
    args = ["--oid", org.oid, "--output", "json", "extension", "request",
            "--name", "test-extension", "--action", "run", "--data", '{"value":1}']
    if impersonate:
        args.append("--impersonate")
    with patch("limacharlie.commands.extension._get_org", return_value=org):
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    org.client.request.assert_called_once()
    params = org.client.request.call_args.kwargs["params"]
    assert ("impersonator_jwt" in params) is impersonate
    if impersonate:
        assert params["impersonator_jwt"] == "synthetic-caller-jwt"
    org.client.refresh_jwt.assert_not_called()
