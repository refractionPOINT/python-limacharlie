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


def invoke(*args, body=None, status=200, stdin=None, output="json"):
    client = Client(oid=OID, jwt="test-jwt")
    response = MagicMock()
    response.read.return_value = json.dumps(body or {}).encode()
    response.getheaders.return_value = []
    with patch("limacharlie.commands.mailsec.Client", return_value=client), patch("limacharlie.client.urlopen") as transport:
        if status != 200:
            transport.side_effect = HTTPError("https://api.example.test", status, "refused", {}, io.BytesIO(json.dumps(body).encode()))
        else:
            transport.return_value = response
        result = CliRunner(mix_stderr=False).invoke(cli, ["--oid", OID, "--output", output, "mailsec", *args], input=stdin)
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


def test_exclude_state_reaches_the_wire_for_messages_and_groups():
    for noun, key in (("message", "messages"), ("group", "groups")):
        result, transport = invoke(noun, "list", "--exclude-state", "spam", "--exclude-state", "trashed", body={key: []})
        assert result.exit_code == 0, result.stderr
        assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("exclude_state", "spam"), ("exclude_state", "trashed")]
        result, transport = invoke(noun, "list", body={key: []})
        assert result.exit_code == 0, result.stderr
        assert "exclude_state" not in transport.call_args.args[0].full_url


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


def test_analyze_org_context_flag_and_preview_fields_survive_output(tmp_path):
    path = tmp_path / "sample.eml"
    path.write_bytes(b"From: sender@example.test\r\n\r\nHello\xff")
    body = {
        "context": "preview", "with_org_context": True, "org_context_read": True, "stored": False,
        "unavailable_evidence": ["attachment_explosion", "link_detonation"],
        "unevaluated_rules": [{"rule_id": "attachment-rule", "unavailable_evidence": ["attachment_explosion"], "matched": False}],
        "mdm": {"verdict": {"top_signals": [{"rule_id": "conditional-rule", "depends_on_missing_context": True, "unavailable_evidence": ["attachment_explosion"]}]}},
    }
    result, transport = invoke("analyze", "--file", str(path), "--direction", "inbound", "--with-org-context", body=body)
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == body
    sent = json.loads(transport.call_args[0][0].data)
    assert sent["with_org_context"] is True
    assert sent["direction"] == "inbound"
    import base64
    assert base64.b64decode(sent["eml_b64"]) == path.read_bytes()
    assert "Unavailable evidence: attachment_explosion, link_detonation" in result.stderr
    assert "current state, not delivery-time state" in result.stderr
    assert "1 unmatched rules" in result.stderr
    assert "attachment-rule: attachment_explosion" in result.stderr
    assert "Signal conditional-rule: depends_on_missing_context=true; unavailable_evidence=attachment_explosion" in result.stderr


def test_analyze_table_reports_nested_rule_and_signal_diagnostics(tmp_path):
    path = tmp_path / "sample.eml"
    path.write_text("From: sender@example.test\n\nHello")
    body = {
        "context": "preview",
        "unavailable_evidence": ["attachment_explosion"],
        "unevaluated_rules": [{"rule_id": "attachment-rule", "unavailable_evidence": ["attachment_explosion"]}],
        "mdm": {"verdict": {"top_signals": [
            {"rule_id": "conditional-rule", "depends_on_missing_context": True, "unavailable_evidence": ["attachment_explosion"]},
            {"rule_id": "auth-rule", "depends_on_missing_context": False, "unavailable_evidence": []},
        ]}},
    }
    result, _ = invoke("analyze", "--file", str(path), body=body, output="table")
    assert result.exit_code == 0, result.stderr
    assert "preview" in result.stdout
    assert "attachment-rule: attachment_explosion" in result.stderr
    assert "Signal conditional-rule: depends_on_missing_context=true; unavailable_evidence=attachment_explosion" in result.stderr
    assert "Signal auth-rule: depends_on_missing_context=false; unavailable_evidence=none" in result.stderr


def test_analyze_diagnostic_rule_ids_escape_terminal_controls(tmp_path):
    path = tmp_path / "sample.eml"
    path.write_text("From: sender@example.test\n\nHello")
    body = {"context": "preview", "unevaluated_rules": [{"rule_id": "rule\x1b[2J", "unavailable_evidence": ["vip"]}],
            "mdm": {"verdict": {"top_signals": [{"rule_id": "signal\x9b2J", "depends_on_missing_context": True, "unavailable_evidence": ["vip"]}]}}}
    result, _ = invoke("analyze", "--file", str(path), body=body)
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == body
    assert "\x1b" not in result.stderr
    assert "\x9b" not in result.stderr


def test_analyze_default_does_not_request_org_context(tmp_path):
    path = tmp_path / "sample.eml"
    path.write_text("From: sender@example.test\n\nHello")
    result, transport = invoke("analyze", "--file", str(path), body={"context": "preview", "unavailable_evidence": ["sender_history"]})
    assert result.exit_code == 0, result.stderr
    assert "with_org_context" not in json.loads(transport.call_args[0][0].data)
    assert "Preview score" in result.stderr


def test_analyze_transport_413_names_limit(tmp_path):
    path = tmp_path / "sample.eml"
    path.write_text("From: sender@example.test\n\nHello")
    result, transport = invoke("analyze", "--file", str(path), body={"error": "request body exceeds the 16777216-byte JSON limit", "request_body_limit_bytes": 16777216}, status=413)
    assert result.exit_code != 0
    assert "16777216" in result.stderr
    assert transport.call_count == 1


def test_analyze_failed_org_context_does_not_claim_current_stamps(tmp_path):
    path = tmp_path / "sample.eml"
    path.write_text("From: sender@example.test\n\nHello")
    body = {"context": "preview", "with_org_context": True, "org_context_read": False, "verdict_available": False, "verdict_note": "Cannot load rules"}
    result, transport = invoke("analyze", "--file", str(path), "--with-org-context", body=body)
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == body
    assert "Organization context could not be read" in result.stderr
    assert "uses current state" not in result.stderr


def test_analyze_org_domains_allow_server_direction_derivation(tmp_path):
    path = tmp_path / "received.eml"
    path.write_text("From: sender@vendor.example\nTo: staff@corp.example\n\nHello")
    body = {"context": "preview", "direction_source": "received_org_domains",
            "mdm": {"direction": "inbound"}, "unavailable_evidence": ["sender_history"]}
    result, transport = invoke("analyze", "--file", str(path), "--org-domain", "corp.example", body=body)
    assert result.exit_code == 0, result.stderr
    sent = json.loads(transport.call_args[0][0].data)
    assert sent["org_domains"] == ["corp.example"]
    assert "direction" not in sent
    assert json.loads(result.stdout) == body
