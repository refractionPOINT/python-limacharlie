"""Tests for the mailsec CLI's public lifecycle probe."""

import re
from unittest.mock import MagicMock, patch

import click
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


def invoke_message_list(*args: str):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.list_messages.return_value = {"messages": [], "next_cursor": ""}
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            [
                "--oid", "11111111-2222-3333-4444-555555555555",
                "--output", "json",
                "mailsec", "message", "list",
                *args,
            ],
        )
        return result, mailsec


def test_connection_diagnostic_is_read_only_by_default():
    result, mailsec = invoke_connection("workspace")
    assert result.exit_code == 0, result.output
    mailsec.test_connection.assert_called_once_with("workspace", include_watch=False)


def test_sender_domain_cli_argument_reaches_the_sdk_unchanged():
    result, mailsec = invoke_message_list("--sender-domain", "evil.example")
    assert result.exit_code == 0, result.output
    _, kwargs = mailsec.list_messages.call_args
    assert kwargs["sender_domain"] == "evil.example"


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
        attempt=None,
    )


def test_campaign_action_forwards_a_deliberate_second_run():
    """--attempt is the only way to ask for a sweep that is recorded BESIDE the
    one it retries. A sweep is idempotent per member by default — the per-member
    key is the campaign itself — so without the flag reaching the SDK an operator
    re-running after a provider outage silently overwrites the rows recording
    what failed, which is the evidence they were retrying because of."""
    result, mailsec = invoke_campaign_action(
        "--action", "quarantine_message",
        "--confirm", "member-bound-token",
        "--reason", "re-running after the provider outage",
        "--attempt", "after-the-outage",
    )
    assert result.exit_code == 0, result.output
    mailsec.act_on_campaign.assert_called_once_with(
        "campaign-1",
        "quarantine_message",
        confirm="member-bound-token",
        reason="re-running after the provider outage",
        attempt="after-the-outage",
    )


def test_campaign_action_sends_no_attempt_when_none_is_asked_for():
    """The control for the test above: omitting the flag must reach the SDK as
    None rather than as a value the CLI chose.

    A default would be stable — the backend composes the campaign with whatever
    it is given, so a double click would still collapse — but it would change
    the identity of every per-member row from the campaign id alone to
    `<campaign>#<default>`, so it would disagree with every row every sweep has
    already written. That is why the backend keys an empty attempt on the bare
    campaign id, and why the CLI must not supply one.

    `test_campaign_action_sends_no_attempt_by_default` in the SDK tests is what
    pins the resulting absence ON THE WIRE; this one only pins the hand-off."""
    result, mailsec = invoke_campaign_action(
        "--action", "quarantine_message",
        "--confirm", "member-bound-token",
    )
    assert result.exit_code == 0, result.output
    _, kwargs = mailsec.act_on_campaign.call_args
    assert kwargs["attempt"] is None


def test_no_mailsec_ai_help_denies_a_flag_the_command_really_has():
    """The defect this pins is help that CONTRADICTS the command it documents.

    `message bulk-action` grew a --reason, and its --ai-help went on telling
    operators "There is no --reason ... use `message action --reason` per
    message when the reason matters" — advice that costs a 500-message
    quarantine its justification, from the one surface an operator is most
    likely to read before acting at that scale. The check is over the whole
    mailsec surface rather than that one string, because the failure mode is
    generic: prose that outlives the code it describes.
    """
    from limacharlie.commands import mailsec as mailsec_cmd
    from limacharlie.discovery import get_explain

    # The phrasings a stale paragraph reaches for. Matched against the flag on
    # the same line, so "there is no --reason" fails and prose that merely
    # mentions the words does not.
    _BEFORE = (r"(?:there is no|there's no|there are no|has no|have no|"
               r"(?:does|do) not (?:take|accept|carry|support|have))")
    _AFTER = (r"(?:is|are) not (?:supported|accepted|carried|available|a thing)"
              r"|(?:does|do) not exist|is ignored")
    # A stale paragraph denies a flag in one of two word orders: the denial
    # before the flag ("there is no --reason") or after it ("--reason is not
    # supported"). Both are matched on ONE line, so ordinary prose that happens
    # to contain the words several sentences apart is not a false positive.
    denials = r"%%s[^\n]{0,60}(?:%s)|%s[^\n]{0,60}%%s" % (_AFTER, _BEFORE)

    def check(cmd, path, checked):
        explain = get_explain(".".join(path))
        if not explain:
            return
        checked.append(" ".join(path))
        for param in cmd.params:
            for opt in getattr(param, "opts", []):
                if not opt.startswith("--"):
                    continue
                m = re.search(denials % (re.escape(opt), re.escape(opt)),
                              explain, re.IGNORECASE)
                assert m is None, (
                    f"`{' '.join(path)}` accepts {opt} but its --ai-help says "
                    f"{m.group(0)!r}"
                )

    def walk(cmd, path, checked):
        # A GROUP'S OWN explain text is checked too, before recursing: nothing
        # registers one today, but a group that grew one would otherwise drop
        # out of coverage silently, which is this test's whole failure mode.
        check(cmd, path, checked)
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                walk(sub, path + [name], checked)

    checked: list[str] = []
    walk(mailsec_cmd.group, ["mailsec"], checked)
    # The walk is only worth anything if it actually reached the explain texts:
    # an empty registry would pass every assertion above by never running one.
    assert "mailsec message bulk-action" in checked
    assert "mailsec campaign action" in checked
