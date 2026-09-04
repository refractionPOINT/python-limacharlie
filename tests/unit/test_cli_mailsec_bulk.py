"""Tests for the mailsec CLI's bulk remediation verbs.

Three properties are under test, and they are the three ways this verb can hurt
someone:

- the CONSENT BINDING — the confirmation a preview mints is derived from the
  exact selection, so the list the CLI shows and the list it later executes have
  to be the same list, not two independently-built ones that agree today;
- the SELECTION SHAPE — a member that is not a message id comes back from the
  preview as "NOT IN INDEX", identical to a legitimately expired one, so the
  counts a human consents over would silently be wrong;
- the OUTCOME CONTRACT — stdout carries one document, stderr carries the handle
  and exactly one terminal line, and the exit code says what happened, because a
  runbook chained with `&&` acts on the exit code and nothing else.
"""

import json

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.mailsec import Mailsec

OID = "11111111-2222-3333-4444-555555555555"

# Real msg_uuids. The backend derives them as v5-shaped UUIDs
# (go-mailsec store.MessageUUID), and the CLI now refuses anything else, so a
# fixture of "a"/"b" would be testing an input the verb no longer accepts.
U_A = "0057db2b-3a06-5aab-b3be-c1e6c15dcf10"
U_B = "1157db2b-3a06-5aab-b3be-c1e6c15dcf11"
U_C = "2257db2b-3a06-5aab-b3be-c1e6c15dcf12"

# The gateway's confirmation is 32 hex characters (bulk.Token slices the sha256
# hex to 32); the bulk id is another 32, derived from the token.
TOKEN = "3f31ed7c9b2a4d5e6f8a0b1c2d3e4f50"
BULK_ID = "8f1c2d3e4a5b6c7d8e9f0a1b2c3d4e5f"


def _preview(confirm=TOKEN, messages=None, member_count=2):
    return {
        "preview": True,
        "action": "trash_message",
        "target_state": "trashed",
        "has_target_state": True,
        "member_count": member_count,
        "cap": 500,
        "messages": messages if messages is not None else [
            {"msg_uuid": U_A, "exists": True, "state": "delivered",
             "mailbox": "cfo@corp.example", "provider": "m365",
             "already_in_target_state": False},
            {"msg_uuid": U_B, "exists": False, "state": "", "mailbox": "",
             "provider": "", "already_in_target_state": False},
        ],
        "summary": {
            "total": member_count, "found": 1, "missing": 1,
            "already_in_target_state": 0, "mailbox_count": 1,
            "by_provider": {"m365": 1}, "actionable": 1,
        },
        "confirm": confirm,
    }


def _accepted(bulk_id=BULK_ID, started=True, accepted=True):
    return {
        "accepted": accepted, "bulk_id": bulk_id, "member_count": 2,
        "started": started, "already_running": not started,
        "already_complete": False, "state": "running",
        "counts": {"total": 2, "pending": 2, "ok": 0, "skipped": 0,
                   "failed": 0, "alert_only": 0, "not_found": 0},
    }


def _status(state="complete", stalled=False, ok=2, pending=0, failed=0, skipped=0):
    return {
        "bulk_id": BULK_ID, "state": state, "stalled": stalled,
        "counts": {"total": 2, "pending": pending, "ok": ok, "skipped": skipped,
                   "failed": failed, "alert_only": 0, "not_found": 0},
        "items": [{"msg_uuid": U_A, "result": "ok", "reason": "", "action_id": "act-a"}],
        "items_source": "bulk_record",
    }


def _invoke(*args, sdk_returns=None, input=None, monotonic=None):
    """Invoke the CLI with the Mailsec class mocked, and return (result, sdk).

    The streams are kept SEPARATE (``mix_stderr=False``, valid because this
    package pins click==8.1.8 and the parameter was removed in click 8.2): the
    verb's contract is that stdout holds one parseable document while progress,
    the job handle and the terminal line go to stderr, and a runner that merged
    them could not tell the two apart.

    ``wait_for_bulk`` is wired to the REAL SDK implementation bound to the mock,
    so the polling loop under test is the shipped one and only the HTTP-facing
    ``bulk_action_status`` is stubbed. Mocking the wait away would leave the
    loop's terminal semantics — which decide the exit code — untested.
    """
    runner = CliRunner(mix_stderr=False)
    patches = [
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.sdk.mailsec.time.sleep"),
    ]
    if monotonic is not None:
        patches.append(patch("limacharlie.sdk.mailsec.time.monotonic", side_effect=monotonic))
    with patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls:
        for p in patches:
            p.start()
        try:
            mailsec = MagicMock()
            for name, value in (sdk_returns or {}).items():
                if isinstance(value, list):
                    getattr(mailsec, name).side_effect = value
                elif isinstance(value, BaseException) or (
                    isinstance(value, type) and issubclass(value, BaseException)
                ):
                    getattr(mailsec, name).side_effect = value
                else:
                    getattr(mailsec, name).return_value = value
            mailsec.wait_for_bulk = lambda *a, **kw: Mailsec.wait_for_bulk(mailsec, *a, **kw)
            mailsec_cls.return_value = mailsec
            result = runner.invoke(
                cli, ["--oid", OID, "--output", "json", *args], input=input or "",
            )
            return result, mailsec
        finally:
            for p in reversed(patches):
                p.stop()


_HAPPY = {
    "bulk_action_preview": _preview(),
    "bulk_action_execute": _accepted(),
    "bulk_action_status": _status(),
}


class TestPreviewIsTheDefault:
    """The grammar the sibling remediation verbs use: omit --confirm and you get
    a preview, pass one and it executes. There is no prompt and no --yes, which
    is what makes the verb usable from a script without a flag that means
    "skip the safety"."""

    def test_omitting_confirm_previews_and_changes_nothing(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_A},{U_B}",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        ms.bulk_action_preview.assert_called_once()
        ms.bulk_action_execute.assert_not_called()

    def test_the_token_arrives_on_stdout_so_a_script_can_read_it(self):
        """The whole point of the two-step: step one's answer has to be readable
        by the thing that runs step two."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout)["confirm"] == TOKEN

    def test_the_table_format_does_not_render_the_preview_away(self):
        """MEASURED: format_table flattens a record to one row per key and
        renders nested values as placeholders — for this document `messages`
        becomes "[2 items]" and `summary` becomes "{7 keys}". Those two ARE the
        preview: the per-message placement and the mailbox count are the blast
        radius being approved. Now that the preview is this verb's default
        output, a table would print its substance away, so it falls back to
        JSON. The token comes through whole either way, and this pins that too."""
        runner = CliRunner(mix_stderr=False)
        with (
            patch("limacharlie.commands.mailsec.Client"),
            patch("limacharlie.commands.mailsec.Organization"),
            patch("limacharlie.commands.mailsec.Mailsec") as cls,
        ):
            ms = MagicMock()
            ms.bulk_action_preview.return_value = _preview()
            cls.return_value = ms
            result = runner.invoke(cli, [
                "--oid", OID, "--output", "table", "mailsec", "message", "bulk-action",
                "--action", "trash_message", "--msg-uuids", f"{U_A},{U_B}",
            ])
        assert result.exit_code == 0, result.stderr
        assert "[2 items]" not in result.stdout
        doc = json.loads(result.stdout)
        assert doc["confirm"] == TOKEN
        assert [m["msg_uuid"] for m in doc["messages"]] == [U_A, U_B]

    def test_the_blast_radius_is_narrated_for_a_human(self):
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_A},{U_B}",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        # Every member is listed, including the one that is no longer indexed:
        # a truncated blast radius under-reports the thing being approved.
        assert "cfo@corp.example" in result.stderr
        assert "NOT IN INDEX" in result.stderr
        assert "mailboxes:     1" in result.stderr
        assert f"confirm:       {TOKEN}" in result.stderr

    def test_there_is_no_yes_flag(self):
        """The prompt and its escape hatch are gone. A --yes that still parsed
        would leave scripts carrying a flag that no longer means anything."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--yes",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_preview.assert_not_called()

    def test_there_is_no_preview_only_flag(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--preview-only",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_preview.assert_not_called()

    def test_a_valueless_confirm_is_refused_rather_than_read_as_consent(self):
        """--confirm takes a value here, unlike the boolean --confirm elsewhere
        in the CLI. Click refuses the bare flag, which is the safe direction:
        the failure mode of the other reading would be executing on a token
        nobody supplied."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "requires an argument" in result.stderr
        ms.bulk_action_execute.assert_not_called()


class TestPreviewToExecuteBinding:
    """The confirmation is bound to (action, attempt, member list), so the two
    calls must carry the identical list. Rebuilding it differently between them
    is the mistake that would execute a set nobody approved — and it surfaces as
    a stale-token error rather than as the consent failure it is."""

    def test_the_two_steps_send_a_byte_identical_selection(self):
        """The binding property, asserted where it now lives: across two
        invocations, spelled in two orders, with a duplicate in one of them."""
        _, preview_ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_B},{U_A},{U_B}",
            sdk_returns=_HAPPY,
        )
        _, execute_ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_A},{U_B}", "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        previewed = preview_ms.bulk_action_preview.call_args.args[1]
        executed = execute_ms.bulk_action_execute.call_args.args[1]
        assert previewed == executed == [U_A, U_B]

    def test_the_execute_normalizes_once_and_sends_that_list(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_C},{U_A},{U_A}", "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_execute.call_args.args[1] == [U_A, U_C]

    def test_the_token_given_is_the_token_spent(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_execute.call_args.args[2] == TOKEN

    def test_the_attempt_reaches_whichever_call_runs(self):
        """attempt is hashed into the confirmation, so a preview taken with one
        and an execute sent without it are different selections to the server."""
        _, preview_ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--attempt", "inc-9",
            sdk_returns=_HAPPY,
        )
        _, execute_ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--attempt", "inc-9", "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert preview_ms.bulk_action_preview.call_args.kwargs["attempt"] == "inc-9"
        assert execute_ms.bulk_action_execute.call_args.kwargs["attempt"] == "inc-9"

    def test_a_confirm_skips_the_preview_entirely(self):
        """Re-previewing here would mint a fresh token and quietly discard the
        one the operator reviewed."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_A},{U_B}", "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        ms.bulk_action_preview.assert_not_called()

    def test_the_banner_flag_is_ignored_and_said_so(self):
        """--banner used to carry HTML that was spliced into up to 500 mailboxes
        verbatim. The banner is rendered by the server from the org's `banners`
        policy record now. The flag is accepted and ignored for one release so an
        existing runbook does not start failing on an unknown option — and the
        command SAYS it was ignored, because silently discarding what an operator
        typed is how somebody ends up believing they configured something."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "banner_message",
            "--msg-uuids", U_A, "--confirm", TOKEN, "--banner", "<b>caution</b>",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert "banner" not in ms.bulk_action_execute.call_args.kwargs
        assert "--banner is deprecated and ignored" in result.stderr + result.stdout


class TestSelectionAssembly:
    def test_ids_come_from_the_flag_and_the_file_together(self, tmp_path):
        f = tmp_path / "uuids.txt"
        f.write_text(f"{U_C}\n\n")
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_A},{U_B}", "--input-file", str(f),
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B, U_C]

    def test_repeated_flags_accumulate(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--msg-uuids", f"{U_B},{U_C}",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B, U_C]

    def test_the_flag_splits_on_commas_and_trims_around_them(self):
        """Comma-only, matching every other repeatable-and-comma-separated
        option in this CLI. Whitespace around an item is trimmed; it is not
        itself a separator."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"  {U_A} ,  {U_B}  ",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B]

    def test_a_json_array_file_is_read_as_a_list(self, tmp_path):
        f = tmp_path / "uuids.json"
        f.write_text(json.dumps([U_B, U_A]))
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--input-file", str(f),
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B]

    def test_a_yaml_list_file_is_read_as_a_list(self, tmp_path):
        f = tmp_path / "uuids.yaml"
        f.write_text(f"- {U_A}\n- {U_B}\n")
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--input-file", str(f),
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B]

    def test_a_dash_reads_the_selection_from_stdin(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--input-file", "-",
            input=f"{U_A}\n{U_B}\n",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B]

    def test_a_pipe_with_no_flags_is_read_as_the_selection(self):
        """The hive commands' idiom: nothing named and a pipe attached means the
        pipe is the input. Piping ids in is the advertised way to turn a search
        result into an action."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            input=f"{U_A}\n{U_B}\n",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_preview.call_args.args[1] == [U_A, U_B]

    def test_an_empty_selection_is_a_usage_error_before_any_call(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
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
            "--input-file", str(f),
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_preview.assert_not_called()

    def test_an_oversized_selection_is_sent_whole_for_the_server_to_refuse(self):
        """The cap is the server's and it refuses rather than truncates. A CLI
        that trimmed to 500 would report success over a selection whose tail was
        silently left in inboxes."""
        ids = ",".join(f"{i:08x}-3a06-5aab-b3be-c1e6c15dcf10" for i in range(900))
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", ids,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert len(ms.bulk_action_preview.call_args.args[1]) == 900


class TestSelectionShape:
    """A member that is not a message id is reported by the preview as "NOT IN
    INDEX" — the same answer a legitimately expired id gets — so member_count
    and mailbox_count, which are the numbers consent is given over, would be
    quietly wrong. It is refused by name instead."""

    def test_a_pasted_csv_export_is_refused_naming_its_header(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            input=f"msg_uuid,mailbox\n{U_A},cfo@corp.example\n{U_B},cto@corp.example\n",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "'msg_uuid' does not look like a message id" in result.stderr
        ms.bulk_action_preview.assert_not_called()

    def test_a_headerless_csv_row_is_refused_naming_the_second_column(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", f"{U_A},cfo@corp.example",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "'cfo@corp.example' does not look like a message id" in result.stderr
        ms.bulk_action_preview.assert_not_called()

    def test_a_truncated_id_is_refused_rather_than_reported_as_expired(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", "0057db2b-3a06-5aab",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "does not look like a message id" in result.stderr
        ms.bulk_action_preview.assert_not_called()

    def test_a_non_string_list_entry_is_refused_rather_than_crashing(self, tmp_path):
        """YAML types values, so a list can arrive holding a date or an int.
        Without this the caller gets an AttributeError traceback instead of a
        usage message."""
        f = tmp_path / "uuids.yaml"
        f.write_text(f"- {U_A}\n- 2026-08-01\n")
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--input-file", str(f),
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "expected message ids" in result.stderr
        ms.bulk_action_preview.assert_not_called()

    def test_a_mapping_document_is_refused_with_its_shape(self, tmp_path):
        f = tmp_path / "uuids.yaml"
        f.write_text("msg_uuids:\n  - " + U_A + "\n")
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--input-file", str(f),
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        assert "one id per line" in result.stderr
        ms.bulk_action_preview.assert_not_called()


class TestPollIntervalAndTimeoutBounds:
    """Both bounds are enforced by click, which means BEFORE the execute fires.
    A --poll-interval of 0 previously issued tens of thousands of requests in
    seconds, and a negative one crashed after the provider writes had already
    been ordered — the worst possible moment to learn about a flag typo."""

    def test_a_zero_poll_interval_is_refused(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN, "--poll-interval", "0",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_execute.assert_not_called()

    def test_a_negative_poll_interval_is_refused_before_the_execute(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN, "--poll-interval", "-1",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_execute.assert_not_called()

    def test_a_timeout_under_the_floor_is_refused(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN, "--timeout", "0",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code != 0
        ms.bulk_action_execute.assert_not_called()


class TestTheHandleIsNeverLost:
    def test_the_bulk_id_is_announced_before_the_first_poll(self):
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        lines = [ln for ln in result.stderr.splitlines() if BULK_ID in ln]
        assert lines and lines[0] == f"bulk {BULK_ID} accepted"

    def test_a_failing_first_poll_still_leaves_the_caller_the_handle(self):
        """The measured bug: a 502 on the first poll exited 1 with an empty
        stdout and the bulk_id nowhere, orphaning a job that was running."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_status": RuntimeError("502 Bad Gateway")},
        )
        assert result.exit_code != 0
        assert json.loads(result.stdout)["bulk_id"] == BULK_ID
        assert BULK_ID in result.stderr
        assert f"bulk-status {BULK_ID}" in result.stderr
        ms.bulk_action_execute.assert_called_once()

    def test_the_reason_reaches_the_execute(self):
        """The justification a human typed, on the verb that moves up to 500
        people's mail. It is recorded on the job's audit row and on every
        message's — the same record `message action --reason` produces for one."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN, "--reason", "INC-4471",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_execute.call_args.kwargs["reason"] == "INC-4471"

    def test_a_reason_on_a_preview_is_said_out_loud_not_dropped(self):
        """The preview mints the confirmation and takes no reason by design: one
        that reached it could enter the token, and rewording a justification
        would then invalidate a selection somebody had already approved. So the
        verb SAYS the reason applies to the execute rather than accepting it
        quietly — a justification silently discarded is worse than a refused one,
        because the caller believes it was recorded."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--reason", "INC-4471",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert "--reason applies to the execute" in result.stderr
        # And it really did not travel: the preview call carries no reason.
        assert "reason" not in ms.bulk_action_preview.call_args.kwargs

    def test_adopting_an_existing_job_is_reported_not_hidden(self):
        """started:false is the idempotent path — a re-sent execute adopting the
        job it already created. Saying so is what stops it reading as a second
        batch."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_execute": _accepted(started=False)},
        )
        assert result.exit_code == 0, result.stderr
        assert "already existed" in result.stderr


class TestExitCodesCarryTheOutcome:
    def test_a_completed_job_that_acted_on_something_exits_zero(self):
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert "settled: state=complete" in result.stderr

    def test_per_item_failures_inside_a_successful_batch_are_data_not_an_error(self):
        """counts is the caller's to read. Failing the command because two of
        five messages could not be moved would make the normal partial outcome
        indistinguishable from a batch that did nothing."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_status": _status(ok=3, failed=2)},
        )
        assert result.exit_code == 0, result.stderr

    def test_a_completed_job_that_remediated_nothing_exits_non_zero(self):
        """ok=0 with failures means no mail moved. A runbook chained with && must
        not proceed as though it had."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_status": _status(ok=0, failed=2)},
        )
        assert result.exit_code != 0
        assert "NOTHING WAS REMEDIATED" in result.stderr

    def test_a_batch_of_only_skips_is_still_a_success(self):
        """Every member already where the action would put it is the honest
        answer to a re-run, not a failure."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_status": _status(ok=0, skipped=2)},
        )
        assert result.exit_code == 0, result.stderr

    def test_interrupted_is_terminal_and_non_zero(self):
        """A rolled pod finalizes the job as interrupted with its partial
        outcomes intact. Treating only 'complete' as terminal would poll it
        until the timeout for an answer that already arrived — but it did not
        finish, so it is not a success either."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_status": _status(state="interrupted", ok=1)},
        )
        assert result.exit_code != 0
        assert ms.bulk_action_status.call_count == 1
        assert "INTERRUPTED" in result.stderr

    def test_a_stalled_job_stops_polling_and_states_the_documented_repair(self):
        """There is deliberately no automatic resumption, so a stalled record
        will never move on its own; polling it to the timeout would burn the
        window in which someone could re-drive it."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={
                **_HAPPY,
                "bulk_action_status": _status(state="running", stalled=True, ok=1, pending=1),
            },
        )
        assert result.exit_code != 0
        assert ms.bulk_action_status.call_count == 1
        assert "STALLED" in result.stderr
        assert (
            "Re-send the same execute request with the same confirmation token to finish it"
            in result.stderr
        )

    def test_a_job_still_running_at_the_timeout_exits_non_zero(self):
        """A job that outlives the timeout is not a failure and is not silence:
        the loop stops, says the job is unaffected, and names the command that
        resumes the poll — and the exit code stops a chained runbook."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_status": _status(state="running", ok=0, pending=2)},
            monotonic=[0.0, 10_000.0],
        )
        assert result.exit_code != 0
        assert ms.bulk_action_status.call_count == 1
        assert "still running after 300s" in result.stderr
        assert f"bulk-status {BULK_ID}" in result.stderr
        assert json.loads(result.stdout)["state"] == "running"

    def test_an_unaccepted_execute_exits_non_zero(self):
        """MEASURED: this previously exited 0, silently downgraded to a no-wait,
        and reported an acceptance that had not happened."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_execute": _accepted(accepted=False)},
        )
        assert result.exit_code != 0
        assert "NOT accepted" in result.stderr
        ms.bulk_action_status.assert_not_called()
        assert json.loads(result.stdout)["accepted"] is False

    def test_an_execute_without_a_bulk_id_exits_non_zero(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={**_HAPPY, "bulk_action_execute": _accepted(bulk_id=None)},
        )
        assert result.exit_code != 0
        ms.bulk_action_status.assert_not_called()

    def test_no_wait_reports_the_acceptance_and_exits_zero(self):
        """accepted:true IS the success being reported here; the job's outcome
        is deliberately not being waited for."""
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN, "--no-wait",
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        ms.bulk_action_status.assert_not_called()
        assert json.loads(result.stdout)["bulk_id"] == BULK_ID


class TestWaiting:
    def test_it_polls_until_the_job_leaves_running(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={
                **_HAPPY,
                "bulk_action_status": [
                    _status(state="running", ok=0, pending=2),
                    _status(state="running", ok=1, pending=1),
                    _status(state="complete", ok=2),
                ],
            },
        )
        assert result.exit_code == 0, result.stderr
        assert ms.bulk_action_status.call_count == 3
        assert json.loads(result.stdout)["state"] == "complete"
        assert "settled: state=complete" in result.stderr

    def test_stdout_carries_exactly_one_document(self):
        """Two calls, one answer. Narration goes to stderr so `--output json`
        keeps its promise that stdout is a single parseable document."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns=_HAPPY,
        )
        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout)["bulk_id"] == BULK_ID

    def test_exactly_one_terminal_line_is_written(self):
        """A watcher must never end in silence, and never with two endings it
        has to choose between."""
        result, _ = _invoke(
            "mailsec", "message", "bulk-action", "--action", "trash_message",
            "--msg-uuids", U_A, "--confirm", TOKEN,
            sdk_returns={
                **_HAPPY,
                "bulk_action_status": [
                    _status(state="running", ok=0, pending=2),
                    _status(state="complete", ok=2),
                ],
            },
        )
        assert result.exit_code == 0, result.stderr
        terminal = [ln for ln in result.stderr.splitlines()
                    if "settled" in ln or "STALLED" in ln or "still running after" in ln]
        assert len(terminal) == 1, result.stderr


class TestBulkStatusCommand:
    def test_status_reaches_the_sdk(self):
        result, ms = _invoke(
            "mailsec", "message", "bulk-status", BULK_ID,
            sdk_returns={"bulk_action_status": _status()},
        )
        assert result.exit_code == 0, result.stderr
        ms.bulk_action_status.assert_called_once_with(BULK_ID)
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

    def test_help_states_the_two_step_grammar(self):
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-action", "--help"])
        assert result.exit_code == 0, result.output
        assert "Previews unless --confirm is given" in result.output

    def test_ai_help_explains_what_the_token_binds(self):
        """The server hashes (oid, action, attempt, members). Help that named
        only the selection would leave a caller who previewed with --attempt and
        executed without it staring at a stale-token error about a list they
        never changed."""
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-action", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "DERIVED FROM (action, attempt, the normalized member list)" in result.output
        assert "--action, --msg-uuids and\n--attempt" in result.output
        assert "REFUSED, not truncated" in result.output

    def test_ai_help_documents_the_exit_codes_and_quiet(self):
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-action", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "THE EXIT CODE CARRIES THE OUTCOME" in result.output
        assert "--quiet" in result.output

    def test_ai_help_no_longer_advertises_the_removed_flags(self):
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-action", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "--yes" not in result.output
        assert "--preview-only" not in result.output

    def test_ai_help_for_status_explains_stalled(self):
        result = CliRunner().invoke(cli, ["mailsec", "message", "bulk-status", "--ai-help"])
        assert result.exit_code == 0, result.output
        assert "stalled" in result.output
