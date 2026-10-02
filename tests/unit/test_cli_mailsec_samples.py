"""CLI tests for customer sample submission (message submit-sample /
withdraw-sample and the submission group).

The real SDK runs over a mocked transport, so these cover Click parsing, the
local validation, the request that would be sent and the exit code together.
"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli

OID = "11111111-2222-3333-4444-555555555555"
MSG = "0057db2b-0000-4000-8000-000000000001"
SID = "3f1c9b7e5a2d4c8e9a0b1c2d3e4f5a6b"


def invoke(*args, returns=None):
    org = MagicMock()
    org.oid = OID
    org.client.request.return_value = returns if returns is not None else {}
    with patch("limacharlie.commands.mailsec.Client"), patch(
        "limacharlie.commands.mailsec.Organization", return_value=org
    ):
        result = CliRunner(mix_stderr=False).invoke(
            cli, ["--oid", OID, "--output", "json", "mailsec", *args]
        )
    return result, org.client.request


def sent_body(request):
    return json.loads(request.call_args.kwargs["raw_body"])


class TestSubmitSample:
    def test_sends_category_and_reason_and_says_how_to_withdraw(self):
        result, request = invoke(
            "message", "submit-sample", MSG, "--category", "missed_threat",
            "--reason", "credential phish", returns={"result": "ok", "submission_id": SID},
        )
        assert result.exit_code == 0, result.stderr
        assert request.call_args.args == ("POST", f"mailsec/{OID}/messages/{MSG}/actions")
        assert sent_body(request) == {
            "action": "submit_sample", "category": "missed_threat", "reason": "credential phish",
        }
        assert json.loads(result.stdout)["submission_id"] == SID
        assert "copy of this message was sent to LimaCharlie" in result.stderr
        assert f"mailsec submission withdraw {SID}" in result.stderr

    def test_skipped_says_nothing_new_was_sent(self):
        result, _ = invoke(
            "message", "submit-sample", MSG, "--category", "other", "--reason", "x",
            returns={"result": "skipped", "submission_id": SID},
        )
        assert result.exit_code == 0
        assert "already has an active submission" in result.stderr

    def test_a_refusal_exits_nonzero_with_the_servers_reason(self):
        result, _ = invoke(
            "message", "submit-sample", MSG, "--category", "other", "--reason", "x",
            returns={"result": "failed",
                     "error": "sample submission is not enabled for this organization"},
        )
        assert result.exit_code == 1
        assert "sample submission is not enabled for this organization" in result.stderr
        assert "Not submitted" in result.stderr
        # The response is still printed untouched for a script.
        assert json.loads(result.stdout)["result"] == "failed"

    def test_category_and_reason_are_required(self):
        for args in (["--reason", "x"], ["--category", "other"]):
            result, request = invoke("message", "submit-sample", MSG, *args)
            assert result.exit_code == 2
            request.assert_not_called()

    def test_unknown_category_is_a_usage_error(self):
        result, request = invoke(
            "message", "submit-sample", MSG, "--category", "phish", "--reason", "x",
        )
        assert result.exit_code == 2
        assert "missed_threat" in result.stderr
        request.assert_not_called()

    def test_blank_and_overlong_reasons_are_usage_errors_and_send_nothing(self):
        for reason in ("   ", "x" * 1025):
            result, request = invoke(
                "message", "submit-sample", MSG, "--category", "other", "--reason", reason,
            )
            assert result.exit_code == 2, reason
            assert "--reason" in result.stderr
            request.assert_not_called()

    def test_generic_action_command_refuses_submit_sample(self):
        result, request = invoke("message", "action", MSG, "--action", "submit_sample")
        assert result.exit_code != 0
        request.assert_not_called()

    def test_help_states_the_copy_and_the_way_back(self):
        result, _ = invoke("message", "submit-sample", "--help")
        text = " ".join(result.stdout.split())
        assert "SENDS THE MESSAGE TO LIMACHARLIE" in text
        assert "400 days" in text
        assert "withdraw-sample" in text


class TestWithdrawSample:
    def test_sends_withdraw_action(self):
        result, request = invoke(
            "message", "withdraw-sample", MSG, "--reason", "sent by mistake",
            returns={"result": "ok"},
        )
        assert result.exit_code == 0, result.stderr
        assert sent_body(request) == {"action": "withdraw_sample", "reason": "sent by mistake"}

    def test_reason_is_optional(self):
        result, request = invoke("message", "withdraw-sample", MSG, returns={"result": "ok"})
        assert result.exit_code == 0
        assert sent_body(request) == {"action": "withdraw_sample"}

    def test_a_refusal_exits_nonzero(self):
        result, _ = invoke(
            "message", "withdraw-sample", MSG,
            returns={"result": "failed", "error": "no active submission"},
        )
        assert result.exit_code == 1
        assert "Not withdrawn" in result.stderr


class TestSubmissionGroup:
    def test_list_forwards_filters_and_prints_the_response(self):
        body = {"enabled": True, "available": True, "submissions": [], "next_cursor": "c2"}
        result, request = invoke(
            "submission", "list", "--category", "false_positive", "--since", "2026-09-01T00:00:00Z",
            "--until", "2026-09-30T00:00:00Z", "--limit", "25", "--cursor", "c1", returns=body,
        )
        assert result.exit_code == 0, result.stderr
        assert request.call_args.args == ("GET", f"mailsec/{OID}/submissions")
        assert dict(request.call_args.kwargs["query_params"]) == {
            "category": "false_positive", "since": "2026-09-01T00:00:00Z",
            "until": "2026-09-30T00:00:00Z", "limit": "25", "cursor": "c1",
        }
        assert json.loads(result.stdout) == body
        assert result.stderr == ""

    def test_list_explains_an_org_that_has_not_opted_in(self):
        result, _ = invoke(
            "submission", "list",
            returns={"enabled": False, "available": True, "submissions": [], "next_cursor": ""},
        )
        assert result.exit_code == 0
        assert "not enabled for this organization" in result.stderr

    def test_list_explains_a_datacenter_without_a_store(self):
        result, _ = invoke(
            "submission", "list",
            returns={"enabled": True, "available": False, "submissions": [], "next_cursor": ""},
        )
        assert result.exit_code == 0
        assert "not available in this datacenter" in result.stderr

    def test_list_limit_out_of_range_is_a_usage_error(self):
        for limit in ("0", "201"):
            result, request = invoke("submission", "list", "--limit", limit)
            assert result.exit_code == 2
            request.assert_not_called()

    def test_get_of_an_unknown_id_is_a_note_not_an_error(self):
        result, _ = invoke(
            "submission", "get", SID, returns={"submission": None, "reviews": []},
        )
        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"submission": None, "reviews": []}
        assert "not found" in result.stderr
        assert SID in result.stderr

    def test_get(self):
        result, request = invoke(
            "submission", "get", SID,
            returns={"submission": {"submission_id": SID}, "reviews": [{"ts": "2026-09-30T00:00:00Z"}]},
        )
        assert result.exit_code == 0, result.stderr
        assert request.call_args.args == ("GET", f"mailsec/{OID}/submissions/{SID}")
        assert len(json.loads(result.stdout)["reviews"]) == 1

    def test_withdraw(self):
        result, request = invoke(
            "submission", "withdraw", SID,
            returns={"withdrawn": True, "submission_id": SID, "action_id": "a1"},
        )
        assert result.exit_code == 0, result.stderr
        assert request.call_args.args == ("DELETE", f"mailsec/{OID}/submissions/{SID}")
        assert json.loads(result.stdout)["withdrawn"] is True
        assert result.stderr == ""

    def test_withdraw_of_an_unknown_or_already_withdrawn_id_says_so(self):
        result, _ = invoke(
            "submission", "withdraw", SID,
            returns={"withdrawn": False, "submission_id": SID},
        )
        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"withdrawn": False, "submission_id": SID}
        assert "Nothing was deleted" in result.stderr
        assert "already withdrawn" in result.stderr

    def test_ai_help_is_registered_for_every_command(self):
        for path in (
            ("message", "submit-sample"), ("message", "withdraw-sample"),
            ("submission", "list"), ("submission", "get"), ("submission", "withdraw"),
        ):
            result, _ = invoke(*path, "--ai-help")
            assert result.exit_code == 0, path
            assert "mailsec.act" in result.stdout or "mailsec.get" in result.stdout, path
