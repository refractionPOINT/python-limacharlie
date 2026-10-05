"""Run CLI contract regressions over the SDK and its HTTP transport."""

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.client import Client

OID = "11111111-2222-3333-4444-555555555555"
MSG = "0057db2b-3a06-5aab-b3be-c1e6c15dcf10"


def invoke(*args, body=None, status=200, stdin=None):
    client = Client(oid=OID, jwt="test-jwt")
    response = MagicMock()
    response.read.return_value = json.dumps(body or {}).encode()
    response.getheaders.return_value = []
    with patch("limacharlie.commands.mailsec.Client", return_value=client), patch("limacharlie.client.urlopen") as transport:
        if status != 200:
            transport.side_effect = HTTPError("https://api.example.test", status, "refused", {}, io.BytesIO(json.dumps(body).encode()))
        else:
            transport.return_value = response
        result = CliRunner(mix_stderr=False).invoke(cli, ["--oid", OID, "--output", "json", "mailsec", *args], input=stdin)
    return result, transport


def test_purge_http_400_prints_counts_and_fresh_token_guidance():
    body = {"complete": False, "objects_deleted": 20, "objects_failed": 4, "rows_remained": 5}
    result, transport = invoke("tenant", "purge", "--confirm", "token", body=body, status=400)
    assert result.exit_code == 1, result.stderr
    assert json.loads(result.stdout) == body
    assert "PURGE INCOMPLETE" in result.stderr
    assert "fresh token" in result.stderr
    assert transport.call_count == 1


@pytest.mark.parametrize("verb", ["submit-sample", "withdraw-sample"])
@pytest.mark.parametrize("envelope", [False, True])
def test_sample_http_400_prints_failure_without_success_guidance(verb, envelope):
    action = {"action_id": "a-1", "result": "failed", "submission_id": ""}
    body = {"error": "sharing disabled", "data": action} if envelope else dict(action, error="sharing disabled")
    extra = ["--category", "other", "--reason", "Review sample"] if verb == "submit-sample" else []
    result, transport = invoke("message", verb, MSG, *extra, status=400, body=body)
    assert result.exit_code == 1, result.stderr
    assert json.loads(result.stdout)["result"] == "failed"
    assert "sharing disabled" in result.stderr
    assert "A copy of this message was sent" not in result.stderr
    assert "Withdraw it at any time" not in result.stderr
    assert transport.call_count == 1


@pytest.mark.parametrize("command", [["tenant", "purge", "--confirm", "token"], ["message", "withdraw-sample", MSG]])
def test_http_400_without_report_remains_error(command):
    result, transport = invoke(*command, body={"error": "operation refused"}, status=400)
    assert result.exit_code != 0
    assert "operation refused" in result.stderr or "operation refused" in str(result.exception)
    assert "PURGE INCOMPLETE" not in result.stderr
    assert not result.stdout
    assert transport.call_count == 1


@pytest.mark.parametrize("reason", ["INC-4471", "x" * 1025, "   "])
def test_eml_invalid_reason_is_usage_error_without_download(reason):
    result, transport = invoke("message", "eml", MSG, "--justification", reason)
    assert result.exit_code == 2
    assert "12 to 1024" in result.stderr
    transport.assert_not_called()


def test_campaign_choice_accepts_open_closed_and_refuses_active():
    result, transport = invoke("campaign", "list", "--state", "open", "--state", "closed", body={"campaigns": []})
    assert result.exit_code == 0, result.stderr
    assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("state", "open"), ("state", "closed")]
    result, transport = invoke("campaign", "list", "--state", "active")
    assert result.exit_code == 2
    transport.assert_not_called()


@pytest.mark.parametrize("option", ["--input-file", "--input"])
def test_bulk_disposition_aliases_accept_stdin(option):
    result, transport = invoke("message", "bulk-disposition", option, "-", "--disposition", "simulation", stdin=MSG + "\n", body={"results": [{"msg_uuid": MSG, "applied": True}]})
    assert result.exit_code == 0, result.stderr
    assert json.loads(transport.call_args.args[0].data) == {"msg_uuids": [MSG], "disposition": "simulation", "note": ""}


def test_submission_reason_and_repeated_disposition_reach_api():
    result, transport = invoke("submission", "withdraw", "s-1", "--reason", "sent in error", body={"withdrawn": True})
    assert result.exit_code == 0, result.stderr
    assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("reason", "sent in error")]
    result, transport = invoke("message", "list", "--disposition", "malicious", "--disposition", "none", body={"messages": []})
    assert result.exit_code == 0, result.stderr
    assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("disposition", "malicious"), ("disposition", "none")]


def test_revision_oversized_rationale_and_integer_score_are_sent():
    with pytest.warns(UserWarning, match="truncate rationale"):
        result, transport = invoke("message", "revise", MSG, "--verdict", "malicious", "--rationale", "x" * 281, "--score", "101", body={"applied": True})
    assert result.exit_code == 0, result.stderr
    body = json.loads(transport.call_args.args[0].data)
    assert body["rationale"] == ["x" * 281]
    assert body["score"] == 101
    assert isinstance(body["score"], int)


@pytest.mark.parametrize("limit", [501, 1000])
def test_group_limit_above_500_reaches_server(limit):
    result, transport = invoke("group", "list", "--limit", str(limit), body={"groups": []})
    assert result.exit_code == 0, result.stderr
    assert ("limit", str(limit)) in parse_qsl(urlsplit(transport.call_args.args[0].full_url).query)


@pytest.mark.parametrize("args", [["coverage", "--window-days", "0"], ["coverage", "--window-days", "36"]])
def test_bounded_options_refuse_invalid_values_before_http(args):
    result, transport = invoke(*args)
    assert result.exit_code == 2
    transport.assert_not_called()


@pytest.mark.parametrize("command,field", [("rule validate", "rule"), ("rule backtest", "rule"), ("banner preview", "banner")])
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("format", ["json", "yaml"])
def test_candidate_files_accept_body_or_exported_record(tmp_path, command, field, wrapped, format):
    data = {"policy_type": "banners", "title": "Warning"} if field == "banner" else {"phase": "pre_verdict", "detect": {"op": "is", "path": "direction", "value": "inbound"}, "name": "Test rule", "fp_notes": "Internal probes may match", "weight": 10}
    document = {"data": data, "usr_mtd": {"enabled": False, "tags": ["custom"]}} if wrapped else data
    path = tmp_path / f"candidate.{format}"
    path.write_text(json.dumps(document) if format == "json" else yaml.safe_dump(document))
    result, transport = invoke(*command.split(), "--file", str(path), body={"valid": True})
    assert result.exit_code == 0, result.stderr
    sent = json.loads(transport.call_args.args[0].data)
    assert sent[field] == data
    assert "usr_mtd" not in sent[field]


@pytest.mark.parametrize("document", ["[]", "null", "data: []\nusr_mtd: {}", "data: [unterminated"])
def test_invalid_candidate_file_is_usage_error_and_not_sent(tmp_path, document):
    path = tmp_path / "candidate.yaml"
    path.write_text(document)
    result, transport = invoke("rule", "validate", "--file", str(path))
    assert result.exit_code == 2
    transport.assert_not_called()


@pytest.mark.parametrize("direction", ["inbound", "outbound", "internal", "inbnd"])
def test_analyze_direction_choice_uses_a_real_eml_file(tmp_path, direction):
    path = tmp_path / "message.eml"
    path.write_bytes(b"From: sender@example.test\r\n\r\nhello")
    result, transport = invoke("analyze", "--file", str(path), "--direction", direction, body={"verdict": "unknown"})
    if direction == "inbnd":
        assert result.exit_code == 2
        assert "--direction" in result.stderr
        transport.assert_not_called()
    else:
        assert result.exit_code == 0, result.stderr
        assert json.loads(transport.call_args.args[0].data)["direction"] == direction


@pytest.mark.parametrize("option", ["--input-file", "--input"])
def test_bulk_disposition_aliases_accept_a_named_file(tmp_path, option):
    path = tmp_path / "ids.json"
    path.write_text(json.dumps([MSG]))
    result, transport = invoke("message", "bulk-disposition", option, str(path), "--clear", body={"results": [{"msg_uuid": MSG, "applied": True}]})
    assert result.exit_code == 0, result.stderr
    assert json.loads(transport.call_args.args[0].data) == {"msg_uuids": [MSG], "clear": True, "note": ""}


def test_repeated_dispositions_reach_cli_query_independently():
    result, transport = invoke("message", "list", "--disposition", "malicious", "--disposition", "none", body={"messages": []})
    assert result.exit_code == 0, result.stderr
    assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("disposition", "malicious"), ("disposition", "none")]
