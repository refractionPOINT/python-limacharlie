import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from limacharlie.cli import cli


@pytest.mark.parametrize("command,method", [
    ("generate-rule", "generate_dr_rule"),
    ("generate-detection", "generate_detection"),
    ("generate-response", "generate_response"),
    ("generate-query", "generate_lcql"),
    ("generate-selector", "generate_sensor_selector"),
    ("generate-playbook", "generate_playbook"),
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


@pytest.mark.parametrize("command", [
    "generate-rule", "generate-query", "generate-detection",
    "generate-response", "generate-selector", "generate-playbook",
])
@pytest.mark.parametrize("help_flag", ["--help", "--ai-help"])
def test_generation_help_exposes_both_aliases_without_auth(command, help_flag):
    with patch("limacharlie.commands.ai._get_org") as org:
        result = CliRunner().invoke(cli, ["ai", command, help_flag])
        assert result.exit_code == 0, result.output
        assert "--prompt" in result.output
        assert "--description" in result.output
        org.assert_not_called()


def test_documented_dr_file_workflow_reaches_sdk_with_correct_values(tmp_path):
    detect = {"event": "NEW_PROCESS", "op": "exists", "path": "event/COMMAND_LINE"}
    respond = [{"action": "report", "name": "test"}]
    rule = {"detect": detect, "respond": respond}
    events = [{"routing": {"event_type": "NEW_PROCESS"}, "event": {"COMMAND_LINE": "example"}}]
    for name, data in (("detect.yaml", detect), ("respond.yaml", respond), ("rule.yaml", rule), ("events.json", events)):
        (tmp_path / name).write_text(json.dumps(data))
    paths = lambda name: str(tmp_path / name)
    with patch("limacharlie.commands.dr._get_org"), patch("limacharlie.commands.dr.Hive") as hive, patch("limacharlie.commands.dr.ReplaySDK") as replay:
        hive.return_value.set.return_value = {"name": "test"}
        replay.return_value.validate_rule.return_value = {"valid": True}
        replay.return_value.scan_events.return_value = {"responses": []}
        runner = CliRunner()
        for args in [
            ["set", "--key", "test", "--detect", paths("detect.yaml"), "--respond", paths("respond.yaml"), "--enabled"],
            ["validate", "--detect", paths("detect.yaml"), "--respond", paths("respond.yaml")],
            ["test", "--input-file", paths("rule.yaml"), "--events", paths("events.json")],
        ]:
            result = runner.invoke(cli, ["dr", *args, "--output", "yaml"])
            assert result.exit_code == 0, result.output
        record = hive.return_value.set.call_args.args[0]
        assert record.data == rule and record.enabled is True
        replay.return_value.validate_rule.assert_called_once_with(rule)
        replay.return_value.scan_events.assert_called_once_with(events, rule_name=None, namespace=None, rule_content=rule, trace=False)


@pytest.mark.parametrize("enabled_flag,expected", [("--enabled", True), ("--disabled", False)])
def test_enabled_flag_overrides_record_metadata(enabled_flag, expected):
    with patch("limacharlie.commands.dr._get_org"), patch("limacharlie.commands.dr.Hive") as hive:
        hive.return_value.set.return_value = {"name": "test"}
        payload = {"data": {"detect": {"op": "exists"}, "respond": []}, "usr_mtd": {"enabled": not expected}}
        result = CliRunner().invoke(cli, ["dr", "set", "--key", "test", enabled_flag], input=json.dumps(payload))
        assert result.exit_code == 0, result.output
        assert hive.return_value.set.call_args.args[0].enabled is expected
