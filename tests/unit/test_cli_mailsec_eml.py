"""Regression coverage for public mailsec EML downloads."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli


def test_eml_out_file_contains_original_bytes():
    raw = b"From: marker@example.com\r\nSubject: test\r\n\r\nmarker body\r\n"
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
        CliRunner().isolated_filesystem(),
    ):
        mailsec = MagicMock()
        mailsec.get_message_eml.return_value = raw
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            [
                "--oid",
                "11111111-2222-3333-4444-555555555555",
                "mailsec",
                "message",
                "eml",
                "msg-1",
                "--justification",
                "P0 marker-only acceptance evidence",
                "--out-file",
                "message.eml",
            ],
        )

        assert result.exit_code == 0, result.output
        assert Path("message.eml").read_bytes() == raw
        mailsec.get_message_eml.assert_called_once_with(
            "msg-1", "P0 marker-only acceptance evidence"
        )


def test_eml_stdout_contains_original_bytes():
    raw = b"From: marker@example.com\r\n\r\nmarker body\r\n"
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.get_message_eml.return_value = raw
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            [
                "--oid",
                "11111111-2222-3333-4444-555555555555",
                "mailsec",
                "message",
                "eml",
                "msg-1",
                "--justification",
                "P0 marker-only acceptance evidence",
            ],
        )

        assert result.exit_code == 0, result.output
        assert result.stdout_bytes == raw
