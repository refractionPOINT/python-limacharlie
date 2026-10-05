"""Read-only status and safe product routing for security billing CLI."""
import json
from unittest.mock import patch

from click.testing import CliRunner
import pytest
from limacharlie.cli import cli


def invoke(args):
    with patch("limacharlie.commands.billing._get_org"), \
         patch("limacharlie.commands.billing.BillingSDK") as sdk:
        sdk.return_value.get_security.return_value = {"status": {"phase": "pending"}}
        result = CliRunner().invoke(cli, ["--output", "json", "billing", "security"] + args)
        return result, sdk.return_value


@pytest.mark.parametrize("product", ["mail_security", "code_security"])
def test_get_preserves_pending(product):
    result, sdk = invoke(["get", product])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"]["phase"] == "pending"
    sdk.get_security.assert_called_once_with(product, from_date=None, until_date=None)


def test_get_date_flags():
    result, sdk = invoke(["get", "code_security", "--from", "2026-10-01", "--until", "2026-11-01"])
    assert result.exit_code == 0, result.output
    sdk.get_security.assert_called_once_with("code_security", from_date="2026-10-01", until_date="2026-11-01")


def test_product_choice_refused():
    result, sdk = invoke(["get", "edr"])
    assert result.exit_code != 0
    sdk.get_security.assert_not_called()


@pytest.mark.parametrize("action", ["activate", "stop"])
def test_removed_mutations_are_unknown_commands(action):
    result, sdk = invoke([action, "mail_security"])
    assert result.exit_code != 0
    assert f"No such command '{action}'" in result.output
    sdk.get_security.assert_not_called()
