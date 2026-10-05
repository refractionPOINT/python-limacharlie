"""Tests for the mailsec CLI's verdict-revision and report-reopen verbs."""

import json

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli

OID = "11111111-2222-3333-4444-555555555555"


def _invoke(*args, sdk_returns=None, mock_sdk=True):
    """Invoke the CLI. When mock_sdk is True the Mailsec class is replaced with
    a MagicMock so the SDK call is asserted directly; when False the real SDK
    runs over a mocked transport, which is how client-side validation is
    exercised end to end without a live call."""
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
    ):
        if mock_sdk:
            with patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls:
                mailsec = MagicMock()
                if sdk_returns is not None:
                    for name, value in sdk_returns.items():
                        getattr(mailsec, name).return_value = value
                mailsec_cls.return_value = mailsec
                result = CliRunner().invoke(cli, ["--oid", OID, "--output", "json", *args])
                return result, mailsec
        result = CliRunner().invoke(cli, ["--oid", OID, "--output", "json", *args])
        return result, None


class TestMessageRevise:
    def test_revise_reaches_the_sdk_with_defaults(self):
        result, mailsec = _invoke(
            "mailsec", "message", "revise", "msg-1",
            "--verdict", "malicious",
            "--rationale", "confirmed phish",
            sdk_returns={"revise_verdict": {"applied": True, "revision_seq": 3}},
        )
        assert result.exit_code == 0, result.output
        mailsec.revise_verdict.assert_called_once_with(
            "msg-1", "malicious", ["confirmed phish"], score=None
        )

    def test_repeated_rationale_and_score_forwarded(self):
        result, mailsec = _invoke(
            "mailsec", "message", "revise", "msg-1",
            "--verdict", "benign",
            "--rationale", "internal send",
            "--rationale", "sender verified",
            "--score", "12",
            sdk_returns={"revise_verdict": {"applied": True}},
        )
        assert result.exit_code == 0, result.output
        mailsec.revise_verdict.assert_called_once_with(
            "msg-1", "benign", ["internal send", "sender verified"], score=12
        )

    def test_applied_false_is_a_non_error(self):
        """A no-op revision is the honest outcome, not a failure: the response
        carries applied:false and the command still exits 0."""
        result, _ = _invoke(
            "mailsec", "message", "revise", "msg-1",
            "--verdict", "malicious",
            "--rationale", "already malicious",
            sdk_returns={"revise_verdict": {"applied": False, "revision_seq": 2}},
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["applied"] is False

    def test_rationale_is_required(self):
        result, _ = _invoke(
            "mailsec", "message", "revise", "msg-1", "--verdict", "malicious",
            sdk_returns={"revise_verdict": {"applied": True}},
        )
        assert result.exit_code != 0
        assert "rationale" in result.output.lower()

    def test_verdict_choice_is_constrained(self):
        result, _ = _invoke(
            "mailsec", "message", "revise", "msg-1",
            "--verdict", "totally-bad",
            "--rationale", "x",
            sdk_returns={"revise_verdict": {"applied": True}},
        )
        assert result.exit_code != 0

    def test_fractional_score_is_refused_before_the_sdk(self):
        result, mailsec = _invoke(
            "mailsec", "message", "revise", "msg-1", "--verdict", "malicious",
            "--rationale", "confirmed phish", "--score", "12.5",
        )
        assert result.exit_code == 2, result.output
        assert "integer" in result.output
        mailsec.revise_verdict.assert_not_called()


class TestMessageRevisions:
    def test_revisions_reaches_the_sdk(self):
        result, mailsec = _invoke(
            "mailsec", "message", "revisions", "msg-1",
            sdk_returns={"list_revisions": {"revisions": []}},
        )
        assert result.exit_code == 0, result.output
        mailsec.list_revisions.assert_called_once_with("msg-1")


class TestReportReopen:
    def test_reopen_reaches_the_sdk(self):
        result, mailsec = _invoke(
            "mailsec", "report", "reopen", "rep-1",
            sdk_returns={"reopen_report": {"report": {"status": "open"}}},
        )
        assert result.exit_code == 0, result.output
        mailsec.reopen_report.assert_called_once_with("rep-1")

class TestDispositionCommands:
    def test_set_clear_release_and_filter_reach_sdk(self):
        result, sdk = _invoke("mailsec", "message", "disposition", "msg-1", "--disposition", "spam", "--note", "reviewed", sdk_returns={"set_disposition": {"applied": True}})
        assert result.exit_code == 0, result.output
        sdk.set_disposition.assert_called_once_with("msg-1", "spam", clear=False, note="reviewed")
        result, sdk = _invoke("mailsec", "message", "disposition", "msg-1", "--clear", sdk_returns={"set_disposition": {"applied": True}})
        assert result.exit_code == 0, result.output
        sdk.set_disposition.assert_called_once_with("msg-1", None, clear=True, note="")
        result, sdk = _invoke("mailsec", "message", "release", "msg-1", "--reason", "reviewed", "--mode", "ai", "--force", sdk_returns={"release_message": {"result": "ok"}})
        assert result.exit_code == 0, result.output
        sdk.release_message.assert_called_once_with("msg-1", reason="reviewed", mode="ai", force=True)

    def test_report_remediation_preview_and_confirmation_forward(self):
        result, sdk = _invoke("mailsec", "report", "resolve", "rep-1", "--disposition", "malicious", "--scope", "message", "--action", "quarantine_message", "--confirm", "token", "--force", sdk_returns={"resolve_report": {"report": {"status": "resolved"}}})
        assert result.exit_code == 0, result.output
        sdk.resolve_report.assert_called_once_with("rep-1", "malicious", remediation={"scope": "message", "action": "quarantine_message", "confirm": "token", "reason": "", "force": True})
        result, _ = _invoke("mailsec", "report", "resolve", "rep-1", "--disposition", "malicious", "--scope", "message")
        assert result.exit_code != 0 and "provided together" in result.output

class TestReportGroupWait:
    def test_wait_reuses_explicit_attempt(self):
        result, sdk = _invoke("mailsec", "report", "resolve", "rep-1", "--disposition", "malicious", "--scope", "group", "--action", "quarantine_message", "--attempt", "11111111-1111-4111-8111-111111111111", "--confirm", "token", "--wait", sdk_returns={"wait_for_report_resolution": {"report": {"status": "resolved"}}})
        assert result.exit_code == 0, result.output
        sdk.wait_for_report_resolution.assert_called_once_with("rep-1", "malicious", timeout=300, remediation={"scope": "group", "action": "quarantine_message", "reason": "", "force": False, "attempt": "11111111-1111-4111-8111-111111111111", "confirm": "token"})

    def test_wait_timeout_is_nonzero(self):
        result, _ = _invoke("mailsec", "report", "resolve", "rep-1", "--disposition", "malicious", "--scope", "group", "--action", "quarantine_message", "--attempt", "11111111-1111-4111-8111-111111111111", "--wait", sdk_returns={"wait_for_report_resolution": {"report": {"status": "open"}, "wait_timed_out": True}})
        assert result.exit_code == 2, result.output
