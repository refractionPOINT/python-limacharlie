import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli

OID = "11111111-1111-4111-8111-111111111111"
GID = "a" * 64
JOB = "22222222-2222-4222-8222-222222222222"


def invoke(*args, phase="ready", withheld=0):
    with (patch("limacharlie.commands.mailsec.Client"), patch("limacharlie.commands.mailsec.Organization"), patch("limacharlie.commands.mailsec.Mailsec") as factory):
        ms = MagicMock()
        factory.return_value = ms
        status = {"job": {"job_id": JOB, "phase": phase, "withheld": withheld, "failed": 0}, "confirmation": "b" * 64}
        ms.prepare_group_action.return_value = status
        ms.confirm_group_action.return_value = status
        ms.wait_for_group_action.return_value = status
        ms.list_groups.return_value = {"groups": [], "next_cursor": "opaque"}
        result = CliRunner(mix_stderr=False).invoke(cli, ["--oid", OID, "--output", "json", "mailsec", "group", *args])
        return result, ms


def test_preview_never_executes_and_freezes_fields():
    result, ms = invoke("preview", GID, "--action", "banner_message", "--preview-id", JOB, "--text", "Review", "--reason", "Fixture", "--force")
    assert result.exit_code == 0, result.output
    ms.prepare_group_action.assert_called_once_with(GID, "banner_message", JOB, force=True, reason="Fixture", text="Review")
    ms.confirm_group_action.assert_not_called()
    assert json.loads(result.stdout)["job"]["phase"] == "ready"
    assert JOB in result.stderr


def test_confirmation_has_no_action_force_or_text_surface():
    result, ms = invoke("confirm", JOB, "--confirmation", "b" * 64, "--no-wait", phase="running")
    assert result.exit_code == 0, result.output
    ms.confirm_group_action.assert_called_once_with(JOB, "b" * 64)
    ms.prepare_group_action.assert_not_called()
    ms.wait_for_group_action.assert_not_called()


def test_done_with_withheld_copies_exits_nonzero_but_preserves_job():
    result, ms = invoke("confirm", JOB, "--confirmation", "b" * 64, phase="done", withheld=7)
    assert result.exit_code == 1
    assert json.loads(result.stdout)["job"]["withheld"] == 7
    assert "withheld" in result.stderr


def test_preview_timeout_returns_handle_without_confirmation():
    result, ms = invoke("preview", GID, "--action", "trash_message", "--preview-id", JOB, phase="preparing")
    assert result.exit_code == 1
    assert json.loads(result.stdout)["job"]["job_id"] == JOB
    ms.confirm_group_action.assert_not_called()


def test_group_filters_and_severity_choices():
    result, ms = invoke("list", "--severity", "critical", "--disposition", "none", "--user-reported", "false", "--all")
    assert result.exit_code == 0, result.output
    assert ms.list_groups.call_args.kwargs["severity"] == ["critical"]
    assert ms.list_groups.call_args.kwargs["user_reported"] is False
    assert ms.list_groups.call_args.kwargs["all_groups"] is True
    result, ms = invoke("list", "--severity", "urgent")
    assert result.exit_code != 0
    ms.list_groups.assert_not_called()
