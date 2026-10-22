"""CLI paging flags and actionable size errors, through the real HTTP transport."""

import json
import sys

import pytest
import yaml
from click.testing import CliRunner

import limacharlie.client as client_mod
from limacharlie.cli import cli, main
from limacharlie.errors import (
    SIZE_LIMITS_DOC_URL,
    ApiError,
    api_error_code,
    error_from_status_code,
    size_limit_suggestion,
)
from limacharlie.sdk.hive import is_listing_too_large
from limacharlie.sdk.organization import Organization
from tests.unit.test_sdk_hive_paging import OID, fill, gateway  # noqa: F401  (gateway is a fixture)

# What the API gateway answers for the refusals the CLI explains.
TOO_LARGE = {
    "error": "lc_error_code:HIVE_LISTING_TOO_LARGE - listing exceeds the limit",
    "retry": False,
    "error_code": "HIVE_LISTING_TOO_LARGE",
}
BAD_CURSOR = {"error": "lc_error_code:INVALID_CURSOR - bad cursor", "retry": False, "error_code": "INVALID_CURSOR"}
INCOMPLETE_503 = {
    "error": "the result is incomplete: the hives [lookup, query] could not be read. Retry, or pass allow_partial=true",
    "error_code": "INCOMPLETE_RESULT",
    "skipped_hives": {"lookup": "BACKEND_ERROR", "query": "BACKEND_ERROR"},
}
INCOMPLETE_413 = {
    "error": "the result is incomplete: the hives [lookup] could not be read. Reduce the number of matching records",
    "error_code": "INCOMPLETE_RESULT",
    "skipped_hives": {"lookup": "HIVE_LISTING_TOO_LARGE"},
}
FP_TOO_LARGE = {
    "error": "lc_error_code:FP_LISTING_TOO_LARGE - the false positive rules are too large",
    "retry": False,
}


@pytest.fixture
def cli_org(gateway, monkeypatch):
    for module in ("limacharlie.commands._hive_shortcut", "limacharlie.commands.dr", "limacharlie.commands.hive"):
        monkeypatch.setattr(f"{module}._get_org", lambda ctx: Organization(gateway.client))
    return gateway


def stub_api_answer(monkeypatch, status, body):
    client = client_mod.Client(oid=OID, jwt="a.b.c")
    monkeypatch.setattr(client, "raw_request", lambda *a, **kw: (status, body))
    monkeypatch.setattr("limacharlie.commands.api_cmd.Client", lambda **kw: client)


def run(*argv):
    return CliRunner(mix_stderr=False).invoke(cli, list(argv))


# --- paging flags -----------------------------------------------------------

def test_limit_prints_one_page_with_next_cursor_in_json(cli_org):
    fill(cli_org, 25)
    result = run("--output", "json", "lookup", "list", "--limit", "10")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert sorted(body) == ["next_cursor", "records"]
    assert sorted(body["records"]) == [f"rec-{i:03d}" for i in range(10)]
    assert body["next_cursor"] == "10"
    assert cli_org.queries == [{"limit": "10"}]


def test_cursor_continues_and_last_page_has_empty_cursor(cli_org):
    fill(cli_org, 25)
    result = run("--output", "json", "lookup", "list", "--limit", "10", "--cursor", "20")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert sorted(body["records"]) == [f"rec-{i:03d}" for i in range(20, 25)]
    assert body["next_cursor"] == ""
    assert cli_org.queries == [{"limit": "10", "cursor": "20"}]


def test_cursor_alone_uses_the_default_page_size(cli_org):
    fill(cli_org, 60)
    result = run("--output", "json", "lookup", "list", "--cursor", "10")
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)["records"]) == 50
    assert cli_org.queries == [{"limit": "50", "cursor": "10"}]


def test_yaml_output_carries_the_cursor(cli_org):
    fill(cli_org, 5)
    result = run("--output", "yaml", "lookup", "list", "--limit", "2")
    assert result.exit_code == 0, result.output
    body = yaml.safe_load(result.stdout)
    assert body["next_cursor"] == "2" and len(body["records"]) == 2


@pytest.mark.parametrize("fmt", ["table", "csv", "jsonl"])
def test_row_formats_keep_records_on_stdout_and_cursor_on_stderr(cli_org, fmt):
    fill(cli_org, 5)
    result = run("--output", fmt, "lookup", "list", "--limit", "2")
    assert result.exit_code == 0, result.output
    assert "next_cursor" not in result.stdout
    assert "rec-000" in result.stdout and "rec-002" not in result.stdout
    assert "next_cursor: 2" in result.stderr
    assert "--cursor=2" in result.stderr


def test_row_format_last_page_says_so_on_stderr(cli_org):
    fill(cli_org, 2)
    result = run("--output", "table", "lookup", "list", "--limit", "5")
    assert result.exit_code == 0, result.output
    assert "next_cursor" not in result.stderr
    assert "No more pages" in result.stderr


def test_quiet_silences_everything_in_a_row_format(cli_org):
    fill(cli_org, 5)
    result = run("--quiet", "--output", "csv", "lookup", "list", "--limit", "2")
    assert result.exit_code == 0 and result.stderr == "" and result.stdout == ""


def test_paging_forwards_metadata_only_tag_prefix_and_max_bytes(cli_org):
    fill(cli_org, 3)
    result = run(
        "--output", "json", "hive", "list", "--hive-name", "lookup", "--limit", "5",
        "--metadata-only", "--tag-prefix", "t", "--max-bytes", "4096",
    )
    assert result.exit_code == 0, result.output
    assert cli_org.queries == [{"limit": "5", "mtd_only": "true", "tag_prefix": "t", "max_bytes": "4096"}]
    assert all(r["data"] is None for r in json.loads(result.stdout)["records"].values())


def test_dr_list_pages_too(cli_org):
    fill(cli_org, 4)
    result = run("--output", "json", "dr", "list", "--limit", "3")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["next_cursor"] == "3"


def test_brief_still_applies_inside_the_envelope(cli_org):
    fill(cli_org, 3)
    for rec in cli_org.records.values():
        rec["data"] = {"description": "d", "body": "long"}
    result = run("--output", "json", "sop", "list", "--limit", "2", "--brief")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert all(r["data"] == {"description": "d"} for r in body["records"].values())


def test_tag_prefix_alone_walks_every_page(cli_org):
    fill(cli_org, 3)
    result = run("--output", "json", "lookup", "list", "--tag-prefix", "t")
    assert result.exit_code == 0, result.output
    assert sorted(json.loads(result.stdout)) == ["rec-000", "rec-001", "rec-002"]
    assert cli_org.queries == [{"limit": "500", "tag_prefix": "t"}]


def test_max_bytes_without_paging_is_a_usage_error(cli_org):
    result = run("lookup", "list", "--max-bytes", "100")
    assert result.exit_code == 2
    assert "--max-bytes needs --limit or --cursor" in result.stderr
    assert cli_org.queries == []


def test_limit_must_be_positive(cli_org):
    assert run("lookup", "list", "--limit", "0").exit_code == 2
    assert cli_org.queries == []


@pytest.mark.parametrize("argv", [["lookup", "list"], ["hive", "list", "--hive-name", "lookup"], ["dr", "list"]])
def test_without_paging_flags_the_whole_hive_is_listed_as_before(cli_org, argv):
    fill(cli_org, 3)
    result = run("--output", "json", *argv)
    assert result.exit_code == 0, result.output
    assert sorted(json.loads(result.stdout)) == ["rec-000", "rec-001", "rec-002"]
    assert result.stderr == ""
    assert cli_org.queries == [{}]


def test_without_paging_flags_a_too_large_hive_still_pages_by_itself(cli_org):
    fill(cli_org, 1200)
    cli_org.too_large_at = 100
    result = run("--output", "json", "lookup", "list")
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 1200


@pytest.mark.parametrize("argv", [["lookup", "list"], ["hive", "list"], ["dr", "list"], ["fp", "list"], ["sop", "list"]])
def test_help_and_explain_describe_the_paging_flags(argv):
    help_result = run(*argv, "--help")
    assert help_result.exit_code == 0
    for flag in ("--limit", "--cursor", "--max-bytes", "--tag-prefix"):
        assert flag in help_result.output
    explain = run(*argv, "--ai-help")
    assert explain.exit_code == 0
    assert "next_cursor" in explain.output and SIZE_LIMITS_DOC_URL in explain.output


# --- actionable errors ------------------------------------------------------

def run_main(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["limacharlie", *argv])
    with pytest.raises(SystemExit) as exit_info:
        main()
    captured = capsys.readouterr()
    return exit_info.value.code, captured.out, captured.err


@pytest.mark.parametrize("status,body,fixes,anchor", [
    (413, TOO_LARGE, ["--limit 100", "--cursor <next_cursor>", "--metadata-only", "Hive.iter_pages()", "mtd_only=true"], "#hive_listing_too_large"),
    (400, BAD_CURSOR, ["next_cursor", "--cursor"], "#invalid_cursor"),
])
def test_cli_prints_what_to_do_for_a_refused_page(cli_org, monkeypatch, capsys, status, body, fixes, anchor):
    cli_org.answer = lambda query: (status, body)
    code, out, err = run_main(monkeypatch, capsys, "lookup", "list", "--limit", "10")
    assert code == 1
    assert out == ""
    # The machine-readable error is still in the message.
    assert f"API error ({status})" in err
    assert body["error_code"] in err
    suggestion = err.split("Suggestion: ", 1)[1]
    for fix in fixes:
        assert fix in suggestion
    assert f"{SIZE_LIMITS_DOC_URL}{anchor}" in suggestion


def test_invalid_cursor_from_the_real_gateway_answer(cli_org, monkeypatch, capsys):
    code, _, err = run_main(monkeypatch, capsys, "lookup", "list", "--cursor", "bad")
    assert code == 1
    assert "lc_error_code:INVALID_CURSOR" in err
    assert "Pass the 'next_cursor' of the previous page unchanged" in err
    assert f"{SIZE_LIMITS_DOC_URL}#invalid_cursor" in err


@pytest.mark.parametrize("status,body,expect", [
    (503, INCOMPLETE_503, ["Retry in a moment", "allow_partial=true", "lookup, query", "#incomplete_result"]),
    (413, INCOMPLETE_413, ["Retrying will not help", "allow_partial=true", "hives not read: lookup", "#incomplete_result"]),
    (400, FP_TOO_LARGE, ["fp list --limit 100", "/v1/hive/fp/{oid}?limit=100", "#fp_listing_too_large"]),
])
def test_api_command_hints_on_stderr_and_leaves_the_body_alone(monkeypatch, status, body, expect):
    stub_api_answer(monkeypatch, status, body)
    result = run("--output", "json", "api", "orgs/{oid}/stories")
    assert result.exit_code == (4 if status < 500 else 5)
    assert json.loads(result.stdout) == body
    assert result.stderr.startswith("Hint: ")
    for text in expect:
        assert text in result.stderr
    assert SIZE_LIMITS_DOC_URL in result.stderr


def test_api_command_stays_silent_on_other_errors(monkeypatch):
    stub_api_answer(monkeypatch, 404, {"error": "nope"})
    result = run("--output", "json", "api", "orgs/{oid}/stories")
    assert result.stderr == ""


# --- SDK exceptions -----------------------------------------------------------

def test_sdk_exception_names_the_fix_and_keeps_the_code(gateway):
    gateway.answer = lambda query: (413, TOO_LARGE)
    with pytest.raises(ApiError) as exc_info:
        gateway.hive.list_page(limit=10)
    err = exc_info.value
    assert err.status_code == 413
    assert err.error_code == "HIVE_LISTING_TOO_LARGE"
    assert "iter_pages()" in err.suggestion and SIZE_LIMITS_DOC_URL in err.suggestion
    assert err.response_body == TOO_LARGE


def test_sdk_exception_exposes_skipped_hives():
    err = error_from_status_code(503, INCOMPLETE_503)
    assert err.error_code == "INCOMPLETE_RESULT"
    assert err.skipped_hives == {"lookup": "BACKEND_ERROR", "query": "BACKEND_ERROR"}
    assert error_from_status_code(500, "boom").skipped_hives == {}


@pytest.mark.parametrize("body,code", [
    ({"error_code": "X", "error": "lc_error_code:Y - z"}, "X"),
    ({"error": "lc_error_code:INVALID_CURSOR - bad"}, "INVALID_CURSOR"),
    ({"error": "something else"}, None),
    ("HIVE_LISTING_TOO_LARGE", None),
    (None, None),
])
def test_api_error_code(body, code):
    assert api_error_code(body) == code


def test_other_errors_keep_their_generic_suggestion():
    for status, body in ((500, "boom"), (503, {"error": "overloaded"}), (413, {"error": "too big"})):
        err = error_from_status_code(status, body)
        assert size_limit_suggestion(status, body) is None
        assert "status.limacharlie.io" in err.suggestion


def test_an_incomplete_result_413_is_not_a_too_large_hive_listing():
    assert not is_listing_too_large(error_from_status_code(413, INCOMPLETE_413))
    assert is_listing_too_large(error_from_status_code(413, TOO_LARGE))
    assert is_listing_too_large(error_from_status_code(413, {"error": "HIVE_LISTING_TOO_LARGE"}))
