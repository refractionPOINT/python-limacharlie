"""Tests for the mailsec CLI's public lifecycle probe."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli


def invoke_connection(*args: str):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.test_connection.return_value = {"ok": True}
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            ["--oid", "11111111-2222-3333-4444-555555555555", "--output", "json", "mailsec", "connection", "test", *args],
        )
        return result, mailsec


def invoke_campaign_action(*args: str):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.act_on_campaign.return_value = {"preview": False, "succeeded": 1}
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            [
                "--oid", "11111111-2222-3333-4444-555555555555",
                "--output", "json",
                "mailsec", "campaign", "action", "campaign-1",
                *args,
            ],
        )
        return result, mailsec


def test_connection_diagnostic_is_read_only_by_default():
    result, mailsec = invoke_connection("workspace")
    assert result.exit_code == 0, result.output
    mailsec.test_connection.assert_called_once_with("workspace", include_watch=False)


def test_include_watch_reaches_the_public_sdk_call():
    result, mailsec = invoke_connection("workspace", "--include-watch")
    assert result.exit_code == 0, result.output
    mailsec.test_connection.assert_called_once_with("workspace", include_watch=True)


def test_campaign_action_help_requires_the_preview_token():
    result = CliRunner().invoke(cli, ["mailsec", "campaign", "action", "--help"])
    assert result.exit_code == 0, result.output
    assert "member-bound token returned by the preview" in result.output
    assert "Pass the campaign id" not in result.output


def test_campaign_action_forwards_the_preview_token_unchanged():
    result, mailsec = invoke_campaign_action(
        "--action", "quarantine_message",
        "--confirm", "member-bound-token",
        "--reason", "reviewed current set",
    )
    assert result.exit_code == 0, result.output
    mailsec.act_on_campaign.assert_called_once_with(
        "campaign-1",
        "quarantine_message",
        confirm="member-bound-token",
        reason="reviewed current set",
    )
