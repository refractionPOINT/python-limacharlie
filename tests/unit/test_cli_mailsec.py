"""Tests for the mailsec CLI's public lifecycle probe."""

import json
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


def invoke_campaign_action(*args: str, returns=None):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.act_on_campaign.return_value = (
            returns if returns is not None else {"preview": False, "succeeded": 1}
        )
        mailsec_cls.return_value = mailsec
        result = CliRunner(mix_stderr=False).invoke(
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


def test_message_search_cli_argument_reaches_the_sdk_unchanged():
    result, mailsec = invoke_message_list("--search", "invoice overdue", "--since", "2026-08-01")
    assert result.exit_code == 0, result.output
    _, kwargs = mailsec.list_messages.call_args
    assert kwargs["q"] == "invoice overdue"
    assert kwargs["since"] == "2026-08-01"


def test_message_q_alias_reaches_the_sdk():
    result, mailsec = invoke_message_list("--q", "needle", "--verdict", "suspicious")
    assert result.exit_code == 0, result.output
    _, kwargs = mailsec.list_messages.call_args
    assert kwargs["q"] == "needle"


def test_invalid_message_search_prints_an_actionable_cli_error():
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec_cls.return_value.list_messages.side_effect = ValueError("q requires since")
        result = CliRunner().invoke(
            cli,
            ["--oid", "11111111-2222-3333-4444-555555555555", "mailsec", "message", "list", "--q", "needle"],
        )
    assert result.exit_code == 2
    assert "Invalid value for --search/--q: q requires since" in result.output


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
        force=False,
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
        force=False,
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


ALERT_ONLY_NOTE = "This organization is in alert-only mode, so the action was recorded but not performed."


def invoke_message_action(*args: str, returns=None, output="json"):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.act_on_message.return_value = returns if returns is not None else {"result": "ok"}
        mailsec_cls.return_value = mailsec
        result = CliRunner(mix_stderr=False).invoke(
            cli,
            [
                "--oid", "11111111-2222-3333-4444-555555555555",
                "--output", output,
                "mailsec", "message", "action", "msg-1",
                *args,
            ],
        )
        return result, mailsec


class TestForce:
    """--force overrides an org's alert-only mode for one action. The failure
    modes worth pinning: a flag that never reaches the SDK (the operator believes
    they forced and nothing moved), a force that rides a PREVIEW (the preview
    endpoint does not take it), and an alert_only result that reads like a
    success at a terminal because nothing said it was withheld."""

    def test_message_action_forwards_force(self):
        result, mailsec = invoke_message_action("--action", "quarantine_message", "--force")
        assert result.exit_code == 0, result.output
        assert mailsec.act_on_message.call_args.kwargs["force"] is True

    def test_message_action_does_not_force_by_default(self):
        result, mailsec = invoke_message_action("--action", "quarantine_message")
        assert result.exit_code == 0, result.output
        assert mailsec.act_on_message.call_args.kwargs["force"] is False

    def test_message_action_says_when_force_is_required(self):
        response = {"result": "alert_only", "force_required": True, "action_id": "act-1"}
        result, _ = invoke_message_action("--action", "quarantine_message", returns=response)
        assert result.exit_code == 0, result.output
        assert f"{ALERT_ONLY_NOTE} Re-run with --force to perform it." in result.stderr
        # The document is passed through as the server sent it.
        assert json.loads(result.stdout) == response

    def test_message_action_is_silent_when_force_is_not_required(self):
        response = {"result": "ok", "force_required": False}
        result, _ = invoke_message_action("--action", "quarantine_message", returns=response)
        assert result.exit_code == 0, result.output
        assert "alert-only" not in result.stderr

    def test_the_force_hint_respects_quiet(self):
        response = {"result": "alert_only", "force_required": True}

        def run(*global_flags):
            with (
                patch("limacharlie.commands.mailsec.Client"),
                patch("limacharlie.commands.mailsec.Organization"),
                patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
            ):
                mailsec_cls.return_value.act_on_message.return_value = response
                return CliRunner(mix_stderr=False).invoke(cli, [
                    "--oid", "11111111-2222-3333-4444-555555555555", *global_flags,
                    "mailsec", "message", "action", "msg-1", "--action", "quarantine_message",
                ])

        # The control: the same invocation without --quiet does print it, so an
        # empty stderr below is --quiet's doing and not a hint that never fires.
        loud = run("--output", "json")
        assert loud.exit_code == 0, loud.output
        assert ALERT_ONLY_NOTE in loud.stderr
        quiet = run("--quiet")
        assert quiet.exit_code == 0, quiet.output
        assert quiet.stderr == ""

    def test_a_force_the_server_did_not_apply_is_not_answered_with_use_force(self):
        """A forced action is never withheld, so force_required on a forced
        request means the flag never reached the collector (an API that predates
        it drops the field). "Re-run with --force" would loop the operator."""
        response = {"result": "alert_only", "force_required": True}
        result, _ = invoke_message_action(
            "--action", "quarantine_message", "--force", returns=response,
        )
        assert result.exit_code == 0, result.output
        assert "--force was sent but the server did not apply it" in result.stderr
        assert "Re-run with --force" not in result.stderr

    def test_campaign_execute_forwards_force(self):
        result, mailsec = invoke_campaign_action(
            "--action", "quarantine_message", "--confirm", "member-bound-token", "--force",
        )
        assert result.exit_code == 0, result.output
        assert mailsec.act_on_campaign.call_args.kwargs["force"] is True

    def test_campaign_preview_never_sends_force_and_says_so(self):
        result, mailsec = invoke_campaign_action("--action", "quarantine_message", "--force")
        assert result.exit_code == 0, result.output
        mailsec.act_on_campaign.assert_called_once()
        assert "force" not in mailsec.act_on_campaign.call_args.kwargs
        assert "--force applies to the execute, not the preview" in result.stderr

    def test_campaign_execute_says_when_force_is_required(self):
        response = {"preview": False, "alert_only": 3, "force_required": True}
        result, _ = invoke_campaign_action(
            "--action", "quarantine_message", "--confirm", "member-bound-token",
            returns=response,
        )
        assert result.exit_code == 0, result.output
        assert f"{ALERT_ONLY_NOTE} Re-run with --force to perform it." in result.stderr
        assert json.loads(result.stdout) == response

    def test_a_forced_campaign_the_server_did_not_apply_says_so(self):
        response = {"preview": False, "alert_only": 3, "force_required": True}
        result, _ = invoke_campaign_action(
            "--action", "quarantine_message", "--confirm", "member-bound-token", "--force",
            returns=response,
        )
        assert result.exit_code == 0, result.output
        assert "--force was sent but the server did not apply it" in result.stderr
        assert "Re-run with --force" not in result.stderr

    def test_force_help_uses_the_agreed_wording(self):
        expected = ("Perform the action even if the organization is in alert-only mode (no "
                    "automation in enforce mode). The override is recorded in the audit trail.")
        for path in (["message", "action"], ["message", "bulk-action"], ["campaign", "action"]):
            result = CliRunner().invoke(cli, ["mailsec", *path, "--help"], terminal_width=10000)
            assert result.exit_code == 0, result.output
            assert expected in " ".join(result.output.split()), path
