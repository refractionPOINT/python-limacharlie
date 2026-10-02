"""Explicit consent and safe product routing for security billing CLI."""
import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest
from limacharlie.cli import cli


def invoke(args):
    with patch("limacharlie.commands.billing._get_org"), \
         patch("limacharlie.commands.billing.BillingSDK") as sdk:
        sdk.return_value.get_security.return_value = {"status": {"phase": "pending"}}
        sdk.return_value.activate_security.return_value = {"status": {"phase": "pending"}}
        sdk.return_value.stop_security.return_value = {"status": {"phase": "pending"}}
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


@pytest.mark.parametrize("action,flag", [("activate", "--accept-pricing"), ("stop", "--confirm")])
def test_explicit_flags_required(action, flag):
    result, sdk = invoke([action, "mail_security"])
    assert result.exit_code != 0
    assert flag in result.output
    getattr(sdk, f"{action}_security").assert_not_called()


def test_activate():
    result, sdk = invoke(["activate", "mail_security", "--accept-pricing"])
    assert result.exit_code == 0, result.output
    sdk.activate_security.assert_called_once_with("mail_security", accept_pricing=True)


def test_stop():
    result, sdk = invoke(["stop", "code_security", "--confirm"])
    assert result.exit_code == 0, result.output
    sdk.stop_security.assert_called_once_with("code_security")


def test_product_choice_refused():
    result, sdk = invoke(["activate", "edr", "--accept-pricing"])
    assert result.exit_code != 0
    sdk.activate_security.assert_not_called()
