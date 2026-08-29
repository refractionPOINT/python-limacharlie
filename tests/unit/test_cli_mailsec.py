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


def test_connection_diagnostic_is_read_only_by_default():
    result, mailsec = invoke_connection("workspace")
    assert result.exit_code == 0, result.output
    mailsec.test_connection.assert_called_once_with("workspace", include_watch=False)


def test_include_watch_reaches_the_public_sdk_call():
    result, mailsec = invoke_connection("workspace", "--include-watch")
    assert result.exit_code == 0, result.output
    mailsec.test_connection.assert_called_once_with("workspace", include_watch=True)
