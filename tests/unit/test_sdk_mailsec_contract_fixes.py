"""Exercise Email Security contracts through the real HTTP client."""

import base64
import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit

import pytest

from limacharlie.client import Client
from limacharlie.errors import ApiError
from limacharlie.sdk.mailsec import Mailsec
from limacharlie.sdk.organization import Organization

OID = "11111111-2222-3333-4444-555555555555"


def mailsec():
    return Mailsec(Organization(Client(oid=OID, jwt="test-jwt")))


def http_response(body):
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode()
    response.getheaders.return_value = []
    return response


def http_failure(body, code=400):
    return HTTPError("https://api.example.test", code, "refused", {}, io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize("envelope", [False, True])
def test_partial_purge_400_recovers_report(envelope):
    report = {"complete": False, "objects_deleted": 12, "objects_failed": 3, "rows_remained": 7}
    body = {"error": "objects could not be deleted", "data": report} if envelope else report
    with patch("limacharlie.client.urlopen", side_effect=http_failure(body)) as transport:
        result = mailsec().purge_tenant("single-use-token")
    assert result["complete"] is False
    assert result["objects_failed"] == 3
    assert result["rows_remained"] == 7
    assert transport.call_count == 1
    request = transport.call_args.args[0]
    assert request.get_method() == "DELETE"
    assert parse_qsl(urlsplit(request.full_url).query) == [("confirmation", "single-use-token")]


@pytest.mark.parametrize("body", [{"error": "active connections"}, {"data": {}}, {"complete": "false"}, {"complete": True}])
def test_purge_400_without_partial_report_stays_an_error(body):
    with patch("limacharlie.client.urlopen", side_effect=http_failure(body)):
        with pytest.raises(ApiError) as error:
            mailsec().purge_tenant("token")
    assert error.value.response_body == body


@pytest.mark.parametrize("method", ["submit_sample", "withdraw_sample"])
def test_sample_failure_preserves_real_http_error_for_sdk_callers(method):
    body = {"error": "sharing disabled", "data": {"action_id": "a-1", "result": "failed", "submission_id": ""}}
    with patch("limacharlie.client.urlopen", side_effect=http_failure(body)) as transport:
        with pytest.raises(ApiError) as error:
            if method == "submit_sample":
                mailsec().submit_sample("msg-1", "other", "Review sample")
            else:
                mailsec().withdraw_sample("msg-1")
    assert error.value.status_code == 400
    assert error.value.response_body == body
    assert transport.call_count == 1


@pytest.mark.parametrize("reason", ["x" * 11, "x" * 1025, "  x  ", "é" * 513])
def test_eml_reason_bounds_prevent_download(reason):
    with patch("limacharlie.client.urlopen") as transport:
        with pytest.raises(ValueError, match="12 to 1024"):
            mailsec().get_message_eml("msg-1", reason)
    transport.assert_not_called()


@pytest.mark.parametrize("reason", ["x" * 12, "x" * 1024, "é" * 6, "é" * 512])
def test_eml_reason_boundaries_are_trimmed_and_forwarded(reason):
    raw = b"From: sender@example.test\r\n\r\nhello"
    body = {"eml_b64": base64.b64encode(raw).decode(), "size": len(raw)}
    with patch("limacharlie.client.urlopen", return_value=http_response(body)) as transport:
        assert mailsec().get_message_eml("msg-1", f"  {reason}  ") == raw
    assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("justification", reason)]


def test_repeated_dispositions_and_legacy_string_reach_query():
    with patch("limacharlie.client.urlopen", return_value=http_response({"messages": [], "next_cursor": ""})) as transport:
        mailsec().list_messages(disposition=["malicious", "none"])
        assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("disposition", "malicious"), ("disposition", "none")]
        mailsec().list_messages(disposition="benign")
        assert parse_qsl(urlsplit(transport.call_args.args[0].full_url).query) == [("disposition", "benign")]


@pytest.mark.parametrize("reason", [None, "  withdrawn in error  ", "x" * 1024])
def test_withdrawal_reason_reaches_delete_query(reason):
    with patch("limacharlie.client.urlopen", return_value=http_response({"withdrawn": True})) as transport:
        assert mailsec().withdraw_submission("s-1", reason=reason)["withdrawn"] is True
    sent = transport.call_args.args[0]
    assert sent.get_method() == "DELETE"
    assert parse_qsl(urlsplit(sent.full_url).query) == ([] if reason is None else [("reason", reason.strip())])


def test_overlong_withdrawal_reason_is_refused_before_http():
    with patch("limacharlie.client.urlopen") as transport:
        with pytest.raises(ValueError, match="1024"):
            mailsec().withdraw_submission("s-1", reason="x" * 1025)
    transport.assert_not_called()


@pytest.mark.parametrize("score", [12.5, True, "12"])
def test_noninteger_revision_score_is_refused_before_http(score):
    with patch("limacharlie.client.urlopen") as transport:
        with pytest.raises(ValueError, match="integer"):
            mailsec().revise_verdict("msg-1", "benign", ["Reviewed"], score=score)
    transport.assert_not_called()


@pytest.mark.parametrize("score", [-1, 12, 101])
def test_revision_integer_score_is_sent_without_invented_range(score):
    with patch("limacharlie.client.urlopen", return_value=http_response({"applied": True})) as transport:
        mailsec().revise_verdict("msg-1", "benign", ["Reviewed"], score=score)
    body = json.loads(transport.call_args.args[0].data)
    assert body["score"] == score
    assert isinstance(body["score"], int)


def test_rationale_clipping_warns_and_leaves_normalization_to_server():
    lines = ["   ", "é" * 281] + [f"reason {i}" for i in range(10)]
    with patch("limacharlie.client.urlopen", return_value=http_response({"applied": True, "revision_seq": 2})) as transport:
        with pytest.warns(UserWarning, match="truncate rationale"):
            assert mailsec().revise_verdict("msg-1", "malicious", lines)["applied"] is True
    assert json.loads(transport.call_args.args[0].data)["rationale"] == lines


@pytest.mark.parametrize("days", [0, 36])
def test_coverage_outside_window_is_refused_before_http(days):
    with patch("limacharlie.client.urlopen") as transport:
        with pytest.raises(ValueError, match="1 to 35"):
            mailsec().get_coverage(window_days=days)
    transport.assert_not_called()
