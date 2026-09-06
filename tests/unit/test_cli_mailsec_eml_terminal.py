"""`mailsec message eml` writes the SENDER'S bytes, so it must not write them to a TTY."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli

RAW = b"From: a@b.example\r\nSubject: \x1b[2Jgotcha\r\n\r\nbody\r\n"
OID = "11111111-2222-3333-4444-555555555555"


def _invoke(extra_args, isatty):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.get_message_eml.return_value = RAW
        mailsec_cls.return_value = mailsec
        with patch("click.utils.WIN", False), patch(
            "limacharlie.commands.mailsec.click.get_binary_stream"
        ) as get_stream:
            stream = MagicMock()
            stream.isatty.return_value = isatty
            get_stream.return_value = stream
            result = CliRunner().invoke(
                cli,
                ["--oid", OID, "mailsec", "message", "eml", "msg-1",
                 "--justification", "INC-4471"] + extra_args,
            )
            return result, stream


def test_refuses_to_write_a_raw_message_to_a_terminal():
    result, stream = _invoke([], isatty=True)
    assert result.exit_code != 0
    stream.write.assert_not_called()
    assert "--out-file" in result.output


def test_writes_when_stdout_is_not_a_terminal():
    """Piping or redirecting is the normal case and must be unaffected."""
    result, stream = _invoke([], isatty=False)
    assert result.exit_code == 0, result.output
    stream.write.assert_called_once_with(RAW)


def test_to_terminal_is_the_escape_hatch():
    result, stream = _invoke(["--to-terminal"], isatty=True)
    assert result.exit_code == 0, result.output
    stream.write.assert_called_once_with(RAW)
