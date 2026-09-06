"""Tests for `limacharlie mailsec tenant purge`.

The property under test throughout is that the destructive half is
unreachable by accident: the default invocation must call the PREPARE method
and must not call the purge, and the token a human read has to be handed back
explicitly for anything to be destroyed.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from limacharlie.cli import cli


OID = "11111111-2222-3333-4444-555555555555"

PREPARED = {
    "confirmation": "5f1c0de5-0000-4000-8000-abcdefabcdef",
    "expires_in_seconds": 300,
    "warning": "This permanently deletes all Email Security data for this org.",
}

COMPLETE = {
    "complete": True,
    "objects_deleted": 12,
    "objects_failed": 0,
    "tables_purged": ["messages"],
    "subscriptions_stopped": 2,
    "subscriptions_failed": 0,
    "rows_remained": 0,
}


def invoke_purge(*args: str, prepared=None, purged=None):
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.prepare_tenant_purge.return_value = dict(prepared or PREPARED)
        mailsec.purge_tenant.return_value = dict(purged or COMPLETE)
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            ["--oid", OID, "--output", "json", "mailsec", "tenant", "purge", *args],
        )
        return result, mailsec


# ---------------------------------------------------------------------------
# The preview half
# ---------------------------------------------------------------------------

def test_without_confirm_it_prepares_and_destroys_nothing():
    result, mailsec = invoke_purge()
    assert result.exit_code == 0, result.output
    mailsec.prepare_tenant_purge.assert_called_once_with()
    mailsec.purge_tenant.assert_not_called()


def test_the_preview_shows_the_warning_and_the_token():
    result, _ = invoke_purge()
    assert result.exit_code == 0, result.output
    assert PREPARED["warning"] in result.output
    assert PREPARED["confirmation"] in result.output
    assert "Nothing has been deleted" in result.output


def test_the_preview_document_is_still_the_thing_on_stdout():
    """The narration goes to stderr; a script reading the pipe gets the mint."""
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.prepare_tenant_purge.return_value = dict(PREPARED)
        mailsec_cls.return_value = mailsec
        result = CliRunner(mix_stderr=False).invoke(
            cli, ["--oid", OID, "--output", "json", "mailsec", "tenant", "purge"]
        )
    assert result.exit_code == 0, result.stderr
    import json
    assert json.loads(result.stdout)["confirmation"] == PREPARED["confirmation"]


def test_a_reason_without_confirm_says_it_is_not_recorded_yet():
    result, mailsec = invoke_purge("--reason", "offboarding")
    assert result.exit_code == 0, result.output
    mailsec.purge_tenant.assert_not_called()
    assert "only recorded by the executing call" in result.output


# ---------------------------------------------------------------------------
# The destructive half
# ---------------------------------------------------------------------------

def test_confirm_passes_the_token_through_unchanged():
    result, mailsec = invoke_purge("--confirm", PREPARED["confirmation"])
    assert result.exit_code == 0, result.output
    mailsec.purge_tenant.assert_called_once_with(
        PREPARED["confirmation"], reason=None
    )
    mailsec.prepare_tenant_purge.assert_not_called()


def test_confirm_carries_the_audited_reason():
    result, mailsec = invoke_purge(
        "--confirm", "tok", "--reason", "customer offboarded"
    )
    assert result.exit_code == 0, result.output
    mailsec.purge_tenant.assert_called_once_with("tok", reason="customer offboarded")


def test_an_incomplete_purge_exits_non_zero_and_says_to_re_run():
    partial = dict(COMPLETE, complete=False, objects_failed=3, rows_remained=17)
    result, _ = invoke_purge("--confirm", "tok", purged=partial)
    assert result.exit_code == 1, result.output
    assert "PURGE INCOMPLETE" in result.output
    assert "re-runnable" in result.output


def test_a_client_side_refusal_is_a_usage_error_not_a_traceback():
    with (
        patch("limacharlie.commands.mailsec.Client"),
        patch("limacharlie.commands.mailsec.Organization"),
        patch("limacharlie.commands.mailsec.Mailsec") as mailsec_cls,
    ):
        mailsec = MagicMock()
        mailsec.purge_tenant.side_effect = ValueError(
            "reason is 1025 characters; the audit log records at most 1024"
        )
        mailsec_cls.return_value = mailsec
        result = CliRunner().invoke(
            cli,
            ["--oid", OID, "mailsec", "tenant", "purge", "--confirm", "tok",
             "--reason", "x" * 1025],
        )
    assert result.exit_code == 2, result.output
    assert "the audit log records at most 1024" in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

def test_help_states_the_two_step_and_the_irreversibility():
    result = CliRunner().invoke(cli, ["mailsec", "tenant", "purge", "--help"])
    assert result.exit_code == 0, result.output
    assert "IRREVERSIBLE" in result.output
    assert "Previews unless --confirm is given" in result.output


def test_ai_help_states_the_token_lifetime_and_the_owner_permissions():
    result = CliRunner().invoke(cli, ["mailsec", "tenant", "purge", "--ai-help"])
    assert result.exit_code == 0, result.output
    assert "SINGLE USE" in result.output
    assert "5 minutes" in result.output
    for perm in ("mailsec.act", "billing.ctrl", "user.ctrl"):
        assert perm in result.output


def test_ai_help_names_the_automatic_deletion_clocks():
    """A reader must be able to learn they may not need this command at all."""
    result = CliRunner().invoke(cli, ["mailsec", "tenant", "purge", "--ai-help"])
    assert result.exit_code == 0, result.output
    assert "30" in result.output
    assert "unsubscribes" in result.output
