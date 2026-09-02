"""Tests for the mailsec CLI's bulk remediation verbs.

The property under test throughout is the CONSENT BINDING: the confirmation a
preview mints is derived from the exact selection, so the list the CLI shows a
human and the list it later executes have to be the same object, not two
independently-built lists that happen to agree today.
"""

import json

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli

OID = "11111111-2222-3333-4444-555555555555"


def _preview(confirm="tok-1", messages=None, member_count=2):
    return {
        "preview": True,
        "action": "trash_message",
        "target_state": "trashed",
        "has_target_state": True,
        "member_count": member_count,
        "cap": 500,
        "messages": messages if messages is not None else [
            {"msg_uuid": "a", "exists": True, "state": "delivered",
             "mailbox": "cfo@corp.example", "provider": "m365",
             "already_in_target_state": False},
            {"msg_uuid": "b", "exists": False, "state": "", "mailbox": "",
             "provider": "", "already_in_target_state": False},
        ],
        "summary": {
            "total": member_count, "found": 1, "missing": 1,
            "already_in_target_state": 0, "mailbox_count": 1,
            "by_provider": {"m365": 1}, "actionable": 1,
        },
        "confirm": confirm,
    }


def _accepted(bulk_id="bulk-1", started=True):
    return {
        "accepted": True, "bulk_id": bulk_id, "member_count": 2,
        "started": started, "already_running": not started,
        "already_complete": False, "state": "running",
        "counts": {"total": 2, "pending": 2, "ok": 0, "skipped": 0,
                   "failed": 0, "alert_only": 0, "not_found": 0},
    }


def _status(state="complete", stalled=False, ok=2, pending=0):
    return {
        "bulk_id": "bulk-1", "state": state, "stalled": stalled,
        "counts": {"total": 2, "pending": pending, "ok": ok, "skipped": 0,
                   "failed": 0, "alert_only": 0, "not_found": 0},
        "items": [{"msg_uuid": "a", "result": "ok", "reason": "", "action_id": "act-a"}],
        "items_source": "bulk_record",
    }


def _invoke(*args, sdk_returns=None, isatty=True, mock_sdk=True):
    """Invoke the CLI with the Mailsec class mocked, and return (result, sdk).

    The streams are kept SEPARATE (``mix_stderr=False``, this repo's idiom): the
    command's contract is that stdout holds one parseable document while progress
    goes to stderr, and a runner that merged them could not tell the two apart.

    ``isatty`` is patched rather than left to the runner because the confirmation
    prompt's whole job is to refuse a stream nobody is reading, and CliRunner's
    stdin is never a TTY.
    """
    runner = CliRunner(mix_stderr=False)
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.sys.stdin.isatty", return_value=isatty),
        patch("limacharlie.commands.mailsec.time.sleep"),
    ):
        if not mock_sdk:
            return runner.invoke(cli, ["--oid", OID, "--output", "json", *args]), None
        with patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls:
            mailsec = MagicMock()
            for name, value in (sdk_returns or {}).items():
                if isinstance(value, list):
                    getattr(mailsec, name).side_effect = value
                else:
                    getattr(mailsec, name).return_value = value
            mailsec_cls.return_value = mailsec
            result = runner.invoke(cli, ["--oid", OID, "--output", "json", *args])
            return result, mailsec


_HAPPY = {
    "bulk_action_preview": _preview(),
    "bulk_action_execute": _accepted(),
    "bulk_action_status": _status(),
}


class TestPreviewToExecuteBinding:
    """The confirmation is bound to the selection, so the two calls must carry
    the identical list. Rebuilding it between them is the mistake that would
    execute a set nobody approved — and it would look like a stale-token bug
    rather than like the consent failure it is."""

    def test_execute_reuses_the_exact_list_the_preview_was_taken_over(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action",
            "--action", "trash_message", "--msg-uuids", "b,a,b", "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        previewed = ms.bulk_action_preview.call_args.args[1]
        executed = ms.bulk_action_execute.call_args.args[1]
        assert previewed == executed == ["a", "b"]
        assert previewed is executed, "the two calls must share one list, not two equal ones"

    def test_the_minted_token_is_what_gets_spent(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action",
            "--action", "trash_message", "--msg-uuids", "a,b", "--yes",
            sdk_returns={**_HAPPY, "bulk_action_preview": _preview(confirm="3f31ed")},
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_execute.call_args.args[2] == "3f31ed"

    def test_the_attempt_reaches_both_calls(self):
        """attempt is hashed into the confirmation, so a preview taken with one
        and an execute sent without it are different selections."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action",
            "--action", "trash_message", "--msg-uuids", "a", "--attempt", "inc-9", "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_preview.call_args.kwargs["attempt"] == "inc-9"
        assert ms.bulk_action_execute.call_args.kwargs["attempt"] == "inc-9"

    def test_a_preview_without_a_token_refuses_to_execute(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action",
            "--action", "trash_message", "--msg-uuids", "a", "--yes",
            sdk_returns={**_HAPPY, "bulk_action_preview": _preview(confirm=None)},
        )
        assert result.exit_code != 0
        ms.bulk_action_execute.assert_not_called()


class TestSelectionAssembly:
    def test_ids_come_from_the_flag_and_the_file_together(self, tmp_path):
        f = tmp_path / "uuids.txt"
        f.write_text("c\nd\n\n")
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--input-file", str(f), "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_preview.call_args.args[1] == ["a", "b", "c", "d"]

    def test_repeated_flags_accumulate(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a", "--msg-uuids", "b,c", "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_preview.call_args.args[1] == ["a", "b", "c"]

    def test_an_empty_selection_is_a_usage_error_before_any_call(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message", "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "at least one msg_uuid" in result.stderr
        ms.bulk_action_preview.assert_not_called()

    def test_a_file_of_only_blanks_is_the_same_refusal(self, tmp_path):
        f = tmp_path / "uuids.txt"
        f.write_text("\n  \n")
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--input-file", str(f), "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_preview.assert_not_called()

    def test_an_oversized_selection_is_sent_whole_for_the_server_to_refuse(self):
        """The cap is the server's and it refuses rather than truncates. A CLI
        that trimmed to 500 would report success over a selection whose tail was
        silently left in inboxes."""
        ids = ",".join(f"m{i:04d}" for i in range(900))
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", ids, "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        assert len(ms.bulk_action_preview.call_args.args[1]) == 900


class TestConsent:
    def test_without_yes_off_a_tty_nothing_is_executed(self):
        """Consent has to come from someone who saw the preview. Off a TTY there
        is nobody, so the refusal names the flag that says 'I already decided'
        instead of prompting a stream that cannot answer."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a", isatty=False,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "--yes" in result.stderr
        ms.bulk_action_execute.assert_not_called()

    def test_quiet_suppresses_the_preview_so_it_also_requires_yes(self):
        """--quiet hides the very thing consent would be given to; prompting
        anyway would be asking a human to approve a blank screen."""
        with (
            patch("limacharlie.commands.mailsec.Client"),
            patch("limacharlie.commands.mailsec.Organization"),
            patch("limacharlie.commands.mailsec.sys.stdin.isatty", return_value=True),
            patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
        ):
            ms = MagicMock()
            ms.bulk_action_preview.return_value = _preview()
            mailsec_cls.return_value = ms
            result = CliRunner().invoke(cli, [
                "--oid", OID, "--quiet", "mailsec", "message", "bulk-action",
                "--action", "trash_message", "--msg-uuids", "a",
            ])
        assert result.exit_code != 0
        ms.bulk_action_execute.assert_not_called()

    def test_declining_the_prompt_executes_nothing(self):
        with (
            patch("limacharlie.commands.mailsec.Client"),
            patch("limacharlie.commands.mailsec.Organization"),
            patch("limacharlie.commands.mailsec.sys.stdin.isatty", return_value=True),
            patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
        ):
            ms = MagicMock()
            ms.bulk_action_preview.return_value = _preview()
            mailsec_cls.return_value = ms
            result = CliRunner().invoke(cli, [
                "--oid", OID, "--output", "json", "mailsec", "message", "bulk-action",
                "--action", "trash_message", "--msg-uuids", "a",
            ], input="n\n")
        assert result.exit_code != 0
        ms.bulk_action_execute.assert_not_called()

    def test_the_preview_is_shown_before_the_prompt(self):
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        # Every member is listed, including the one that is no longer indexed:
        # a truncated blast radius under-reports the thing being approved.
        assert "cfo@corp.example" in result.stderr
        assert "NOT IN INDEX" in result.stderr
        assert "mailboxes:     1" in result.stderr


class TestPreviewOnlyAndTwoStep:
    def test_preview_only_prints_the_token_and_executes_nothing(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--preview-only",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["confirm"] == "tok-1"
        ms.bulk_action_execute.assert_not_called()

    def test_an_explicit_confirm_skips_the_preview_entirely(self):
        """The second half of a hand-driven two-step. Re-previewing here would
        mint a fresh token and quietly discard the one the operator reviewed."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--confirm", "3f31ed",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        ms.bulk_action_preview.assert_not_called()
        assert ms.bulk_action_execute.call_args.args[2] == "3f31ed"

    def test_preview_only_and_confirm_are_mutually_exclusive(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a", "--preview-only", "--confirm", "tok",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_preview.assert_not_called()
        ms.bulk_action_execute.assert_not_called()


class TestWaiting:
    def test_it_polls_until_the_job_leaves_running(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes",
            sdk_returns={
                **_HAPPY,
                "bulk_action_status": [
                    _status(state="running", ok=0, pending=2),
                    _status(state="running", ok=1, pending=1),
                    _status(state="complete", ok=2),
                ],
            },
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_status.call_count == 3
        assert json.loads(result.stdout)["state"] == "complete"
        assert "settled: state=complete" in result.stderr

    def test_interrupted_is_terminal_too(self):
        """A rolled pod finalizes the job as interrupted with its partial
        outcomes intact. Treating only 'complete' as terminal would poll it
        until the timeout for an answer that already arrived."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes",
            sdk_returns={**_HAPPY, "bulk_action_status": _status(state="interrupted", ok=1)},
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_status.call_count == 1
        assert "settled: state=interrupted" in result.stderr

    def test_a_stalled_job_stops_polling_and_states_the_repair(self):
        """There is deliberately no automatic resumption, so a stalled record
        will never move on its own; polling it to the timeout would burn the
        window in which someone could re-drive it."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes",
            sdk_returns={
                **_HAPPY,
                "bulk_action_status": _status(state="running", stalled=True, ok=1, pending=1),
            },
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_status.call_count == 1
        assert "STALLED" in result.stderr
        assert "--confirm" in result.stderr

    def test_the_wait_is_bounded_and_says_so(self):
        """A job that outlives the timeout is not a failure and is not silence:
        the loop stops, says the job is unaffected, and names the command that
        resumes the poll."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes", "--timeout", "0",
            sdk_returns={**_HAPPY, "bulk_action_status": _status(state="running", ok=0, pending=2)},
        )
        assert result.exit_code == 0, result.output
        assert ms.bulk_action_status.call_count == 1
        assert "still running after 0s" in result.stderr
        assert "bulk-status bulk-1" in result.stderr
        assert json.loads(result.stdout)["state"] == "running"

    def test_no_wait_returns_the_acceptance_without_polling(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes", "--no-wait",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        ms.bulk_action_status.assert_not_called()
        assert json.loads(result.stdout)["bulk_id"] == "bulk-1"

    def test_adopting_an_existing_job_is_reported_not_hidden(self):
        """started:false is the idempotent path — a re-sent execute adopting the
        job it already created. Saying so is what stops it reading as a second
        batch."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes",
            sdk_returns={**_HAPPY, "bulk_action_execute": _accepted(started=False)},
        )
        assert result.exit_code == 0, result.output
        assert "already existed" in result.stderr

    def test_stdout_carries_exactly_one_document(self):
        """Three calls, one answer. Narration goes to stderr so `--output json`
        keeps its promise that stdout is a single parseable document."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "a,b", "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["bulk_id"] == "bulk-1"


class TestBulkStatusCommand:
    def test_status_reaches_the_sdk(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-status", "bulk-1",
            sdk_returns={"bulk_action_status": _status()},
        )
        assert result.exit_code == 0, result.output
        ms.bulk_action_status.assert_called_once_with("bulk-1")
        assert json.loads(result.stdout)["counts"]["ok"] == 2


class TestGuidance:
    def test_help_names_the_bulk_vocabulary_including_move_to_spam(self):
        """The bulk vocabulary is not the per-message one: it adds move_to_spam
        and drops submit_to_triage. A caller who cannot see the difference will
        assume they match."""
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-action", "--help"])
        assert result.exit_code == 0, result.output
        assert "move_to_spam" in result.output
        assert "submit_to_triage" not in result.output

    def test_ai_help_explains_the_selection_binding(self):
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-action", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "DERIVED FROM THE EXACT SELECTION" in result.output
        assert "REFUSED, not truncated" in result.output

    def test_ai_help_for_status_explains_stalled(self):
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-status", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "stalled" in result.output
