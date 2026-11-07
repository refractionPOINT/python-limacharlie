"""Contracts for editing and irreversibly redacting case notes."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli, main
from limacharlie.errors import LimaCharlieError, NotFoundError, PermissionDeniedError
from limacharlie.sdk.cases import Cases


@pytest.fixture
def org():
    org = MagicMock()
    org.oid = "test-oid"
    org.get_urls.return_value = {"cases": "cases-staging.limacharlie.io"}
    return org


@pytest.mark.parametrize("method,verb,suffix,body,response", [
    ("edit_note", "PUT", "content", {"content": "修正\n"}, {"event": {"event_id": "evt-1"}}),
    ("redact_note", "POST", "redact", None,
     {"event": {"redacted": True}, "images_pending_deletion": 2}),
])
def test_sdk_request_and_response(org, method, verb, suffix, body, response):
    org.client.request.return_value = response
    args = (42, "evt-1") + ((body["content"],) if body else ())
    assert getattr(Cases(org), method)(*args) == response
    call_args, kwargs = org.client.request.call_args
    assert call_args == (verb, f"api/v1/cases/42/notes/evt-1/{suffix}")
    assert kwargs["alt_root"] == "https://cases-staging.limacharlie.io"
    assert kwargs["query_params"] == {"oid": "test-oid"}
    if body:
        assert json.loads(kwargs["raw_body"]) == body
        assert kwargs["content_type"] == "application/json"
    else:
        assert "raw_body" not in kwargs


@pytest.mark.parametrize("method", ["edit_note", "redact_note"])
@pytest.mark.parametrize("error", [NotFoundError("Note missing"),
    PermissionDeniedError("Access denied"), LimaCharlieError("Already redacted", code=409)])
def test_sdk_propagates_errors(org, method, error):
    org.client.request.side_effect = error
    args = (42, "evt-1", "text") if method == "edit_note" else (42, "evt-1")
    with pytest.raises(type(error)) as exc:
        getattr(Cases(org), method)(*args)
    assert exc.value is error


@pytest.fixture
def sdk():
    with patch("limacharlie.commands.case_cmd.Client") as client, \
         patch("limacharlie.commands.case_cmd.Organization"), \
         patch("limacharlie.commands.case_cmd.Cases") as cls:
        cls.return_value.edit_note.return_value = {"event": {"event_id": "evt-1"}}
        cls.return_value.add_note.return_value = {"event": {"event_id": "evt-1"}}
        cls.return_value.redact_note.return_value = {
            "event": {"redacted": True}, "images_pending_deletion": 2,
        }
        yield cls.return_value, client


def invoke(command, extra=(), stdin=None, output="json"):
    return CliRunner().invoke(cli, ["--oid", "test-oid", "--output", output,
        "case", command, "--case-number", "42", "--event-id", "evt-1", *extra], input=stdin)


@pytest.mark.parametrize("source", ["content", "file", "stdin", "dash"])
def test_cli_edit_sources(sdk, tmp_path, source):
    text = "  修正\nkeep formatting\n"
    path = tmp_path / "note.txt"
    path.write_text(text, encoding="utf-8")
    extra = {"content": ["--content", text], "file": ["--input-file", str(path)],
             "stdin": [], "dash": ["--input-file", "-"]}[source]
    result = invoke("edit-note", extra, stdin=text)
    assert result.exit_code == 0, result.output
    sdk[0].edit_note.assert_called_once_with(42, "evt-1", text.strip())
    assert json.loads(result.output) == {"event": {"event_id": "evt-1"}}
    assert sdk[1].call_args.kwargs["oid"] == "test-oid"


@pytest.mark.parametrize("text", ["", "  \n", "é" * 4097, "  " + "é" * 4097 + "\n"])
def test_cli_edit_invalid_content_never_calls_sdk(sdk, text):
    result = invoke("edit-note", ["--content", text])
    assert result.exit_code != 0
    assert "empty" in result.output or "8192 UTF-8 bytes" in result.output
    sdk[0].edit_note.assert_not_called()


def test_cli_edit_exact_byte_limit(sdk):
    text = "é" * 4096
    assert invoke("edit-note", ["--content", text]).exit_code == 0
    sdk[0].edit_note.assert_called_once_with(42, "evt-1", text)


def test_cli_edit_conflicting_sources(sdk, tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("file")
    result = invoke("edit-note", ["--content", "text", "--input-file", str(path)])
    assert result.exit_code != 0
    assert "Choose either" in result.output
    sdk[0].edit_note.assert_not_called()


def test_cli_edit_missing_input(sdk):
    result = invoke("edit-note")
    assert result.exit_code != 0
    assert "must not be empty" in result.output
    sdk[0].edit_note.assert_not_called()


def test_cli_redact_requires_confirm(sdk):
    result = invoke("redact-note")
    assert result.exit_code == 4
    assert "requires --confirm" in result.output
    sdk[0].redact_note.assert_not_called()
    sdk[1].assert_not_called()


@pytest.mark.parametrize("pending", [0, 2])
@pytest.mark.parametrize("output", ["json", "table"])
def test_cli_redact_pending_cleanup_output(sdk, pending, output):
    sdk[0].redact_note.return_value["images_pending_deletion"] = pending
    result = invoke("redact-note", ["--confirm"], output=output)
    assert result.exit_code == 0, result.output
    assert "images_pending_deletion" in result.output
    assert str(pending) in result.output
    if output == "json":
        assert json.loads(result.output)["images_pending_deletion"] == pending
    assert "all images deleted" not in result.output.lower()
    sdk[0].redact_note.assert_called_once_with(42, "evt-1")


@pytest.mark.parametrize("command,extra", [("edit-note", ["--content", "text"]),
                                           ("redact-note", ["--confirm"])])
@pytest.mark.parametrize("error", [NotFoundError("Note missing"),
    PermissionDeniedError("Access denied"), LimaCharlieError("Edit limit reached", code=409)])
def test_cli_errors(sdk, command, extra, error):
    getattr(sdk[0], command.replace("-", "_")).side_effect = error
    argv = ["limacharlie", "--oid", "test-oid", "case", command,
            "--case-number", "42", "--event-id", "evt-1", *extra]
    with CliRunner().isolation() as streams, patch("sys.argv", argv):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == error.exit_code
        assert error.raw_message in streams[0].getvalue().decode()


@pytest.mark.parametrize("command", ["edit-note", "redact-note"])
def test_cli_explain_and_discovery(command):
    from limacharlie.discovery import PROFILES
    result = CliRunner().invoke(cli, ["case", command, "--ai-help"])
    assert result.exit_code == 0, result.output
    assert "8192" in result.output if command == "edit-note" else "30 days" in result.output
    assert f"case {command}" in PROFILES["cases"]["commands"]


@pytest.mark.parametrize("method,suffix", [("edit_note", "content"), ("redact_note", "redact")])
def test_sdk_encodes_event_id_as_single_path_segment(org, method, suffix):
    args = (42, "../note/redact?oid=other%#fragment")
    if method == "edit_note":
        args += ("text",)
    getattr(Cases(org), method)(*args)
    assert org.client.request.call_args.args[1] == (
        "api/v1/cases/42/notes/..%2Fnote%2Fredact%3Foid%3Dother%25%23fragment/" + suffix
    )
    assert org.client.request.call_args.kwargs["query_params"] == {"oid": "test-oid"}


@pytest.mark.parametrize("source", ["content", "file", "stdin"])
def test_cli_trims_before_byte_limit_matching_add_note(sdk, tmp_path, source):
    text = "  " + "é" * 4096 + "\n"
    path = tmp_path / "note.txt"
    path.write_text(text, encoding="utf-8")
    extra = {"content": ["--content", text], "file": ["--input-file", str(path)],
             "stdin": []}[source]
    result = invoke("edit-note", extra, stdin=text)
    assert result.exit_code == 0, result.output
    sdk[0].edit_note.assert_called_once_with(42, "evt-1", text.strip())
    added = CliRunner().invoke(cli, ["--oid", "test-oid", "case", "add-note",
        "--case-number", "42", *extra], input=text)
    assert added.exit_code == 0, added.output
    # Both commands submit the same text, so an unchanged file/stdin is a no-op.
    assert sdk[0].add_note.call_args.args == (42, text.strip())


def test_update_note_help_explains_redacted_conflict():
    for flag in ("--help", "--ai-help"):
        result = CliRunner().invoke(cli, ["case", "update-note", flag])
        assert result.exit_code == 0
        assert "409" in result.output
