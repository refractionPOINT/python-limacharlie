import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from limacharlie.cli import cli


@pytest.mark.parametrize("command,method", [
    ("generate-rule", "generate_dr_rule"),
    ("generate-detection", "generate_detection"),
    ("generate-response", "generate_response"),
    ("generate-query", "generate_lcql"),
])
@pytest.mark.parametrize("flag", ["--prompt", "--description"])
def test_generation_accepts_both_description_flags(command, method, flag):
    with patch("limacharlie.commands.ai._get_org"), patch("limacharlie.commands.ai.AISDK") as sdk:
        getattr(sdk.return_value, method).return_value = {"response": "generated content"}
        result = CliRunner().invoke(cli, ["ai", command, flag, "detect jndi", "--output", "json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["response"] == "generated content"
        getattr(sdk.return_value, method).assert_called_once_with("detect jndi")


@pytest.mark.parametrize("payload", [{}, {"response": None}, {"response": " "}, {"response": {}}, {"response": {"resource_link": "url"}}])
def test_missing_generation_is_cli_failure(payload):
    with patch("limacharlie.commands.ai._get_org"), patch("limacharlie.commands.ai.AISDK") as sdk:
        sdk.return_value.generate_detection.return_value = payload
        result = CliRunner().invoke(cli, ["ai", "generate-detection", "--description", "detect jndi"])
        assert result.exit_code != 0
        assert "do not deploy" in result.output
        assert "Traceback" not in result.output


@pytest.mark.parametrize("payload", [
    {"detect": {"op": "exists"}, "respond": [], "usr_mtd": {"enabled": True}},
    {"data": {"detect": {}, "usr_mtd": {"enabled": True}}},
    {"data": {"detect": {}}, "respond": []},
    [], None,
])
def test_dr_rejects_ambiguous_record_before_writing(payload):
    with patch("limacharlie.commands.dr._get_org") as org, patch("limacharlie.commands.dr.Hive") as hive:
        result = CliRunner().invoke(cli, ["dr", "set", "--key", "test"], input=json.dumps(payload))
        assert result.exit_code != 0, result.output
        hive.assert_not_called()
        org.assert_not_called()


def test_dr_wrapped_metadata_is_preserved():
    with patch("limacharlie.commands.dr._get_org"), patch("limacharlie.commands.dr.Hive") as hive:
        hive.return_value.set.return_value = {"name": "test"}
        payload = {"data": {"detect": {"op": "exists"}, "respond": []}, "usr_mtd": {"enabled": True}}
        result = CliRunner().invoke(cli, ["dr", "set", "--key", "test"], input=json.dumps(payload))
        assert result.exit_code == 0, result.output
        record = hive.return_value.set.call_args.args[0]
        assert record.enabled is True
        assert "usr_mtd" not in record.data
