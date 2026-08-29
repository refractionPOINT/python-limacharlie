"""Tests for limacharlie.sdk.mailsec module."""

import json

from unittest.mock import MagicMock

import pytest

from limacharlie.sdk.mailsec import Mailsec


OID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = OID
    org.client = MagicMock()
    return org


@pytest.fixture
def ms(mock_org):
    return Mailsec(mock_org)


def _get_call(mock_org):
    """Pull (url, query_pairs) out of a mocked GET client.request call."""
    args, kwargs = mock_org.client.request.call_args
    assert args[0] == "GET"
    return args[1], kwargs.get("query_params")


def _post_call(mock_org):
    """Pull (url, decoded_json_body) out of a mocked POST client.request call."""
    args, kwargs = mock_org.client.request.call_args
    assert args[0] == "POST"
    assert kwargs["content_type"] == "application/json"
    return args[1], json.loads(kwargs["raw_body"])


class TestBasics:
    def test_oid_property(self, ms):
        assert ms.oid == OID

    def test_get_omits_empty_query(self, ms, mock_org):
        mock_org.client.request.return_value = {"messages": []}
        ms.list_messages()
        url, qp = _get_call(mock_org)
        assert url == f"mailsec/{OID}/messages"
        assert qp is None


class TestTriStateBooleans:
    """The API is tri-state throughout: absent means unconstrained, which is
    NOT the same as false. Collapsing the two silently narrows every
    unfiltered read, and the narrowing is invisible because a smaller result
    set looks like a correct one."""

    def test_absent_user_reported_sends_nothing(self, ms, mock_org):
        ms.list_messages()
        _, qp = _get_call(mock_org)
        assert qp is None

    def test_false_is_forwarded_not_dropped(self, ms, mock_org):
        ms.list_messages(user_reported=False)
        _, qp = _get_call(mock_org)
        assert ("user_reported", "false") in qp

    def test_true_is_forwarded(self, ms, mock_org):
        ms.list_messages(user_reported=True)
        _, qp = _get_call(mock_org)
        assert ("user_reported", "true") in qp


class TestRepeatableFilters:
    def test_verdict_repeats_one_pair_per_value(self, ms, mock_org):
        ms.list_messages(verdict=["malicious", "suspicious"])
        _, qp = _get_call(mock_org)
        assert ("verdict", "malicious") in qp
        assert ("verdict", "suspicious") in qp

    def test_mixed_filters_all_present(self, ms, mock_org):
        ms.list_messages(
            verdict=["malicious"],
            mailbox="cfo@corp.example",
            link_domain="evil.example",
            limit=50,
        )
        _, qp = _get_call(mock_org)
        assert ("verdict", "malicious") in qp
        assert ("mailbox", "cfo@corp.example") in qp
        assert ("link_domain", "evil.example") in qp
        assert ("limit", "50") in qp


class TestEMLRequiresJustification:
    """The EML download is a separate privilege because it takes a person's
    actual mail out of the building, and the justification is what makes the
    access auditable. Refusing an empty one client-side keeps a caller from
    discovering the requirement as a server error after the fact."""

    def test_missing_justification_refused(self, ms):
        with pytest.raises(ValueError, match="justification"):
            ms.get_message_eml("msg-1", "")

    def test_whitespace_justification_refused(self, ms):
        with pytest.raises(ValueError, match="justification"):
            ms.get_message_eml("msg-1", "   ")

    def test_justification_is_forwarded(self, ms, mock_org):
        mock_org.client.request.return_value = {
            "eml_b64": "RnJvbTogc2VuZGVyQGV4YW1wbGUuY29tDQoNCmhlbGxvDQo=",
            "size": 35,
        }
        raw = ms.get_message_eml("msg-1", "INC-4471")
        url, qp = _get_call(mock_org)
        assert url == f"mailsec/{OID}/messages/msg-1/eml"
        assert ("justification", "INC-4471") in qp
        assert raw == b"From: sender@example.com\r\n\r\nhello\r\n"

    @pytest.mark.parametrize(
        "response, match",
        [
            ({}, "did not contain eml_b64"),
            ({"eml_b64": "***", "size": 0}, "invalid base64"),
            ({"eml_b64": "YWJj", "size": 2}, "size mismatch"),
            ({"eml_b64": "YWJj", "size": True}, "size mismatch"),
        ],
    )
    def test_malformed_download_response_is_refused(self, ms, mock_org, response, match):
        mock_org.client.request.return_value = response
        with pytest.raises(ValueError, match=match):
            ms.get_message_eml("msg-1", "INC-4471")


class TestActions:
    def test_message_action_body(self, ms, mock_org):
        ms.act_on_message("msg-1", "quarantine_message", reason="phish")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/messages/msg-1/actions"
        assert body == {"action": "quarantine_message", "reason": "phish"}

    def test_campaign_action_previews_without_confirm(self, ms, mock_org):
        """confirm is what turns a preview into an execution. Its absence must
        reach the server as an absence, not as an empty string that could be
        read as a confirmation."""
        ms.act_on_campaign("cmp-1", "quarantine_message")
        _, body = _post_call(mock_org)
        assert "confirm" not in body

    def test_campaign_action_confirm_is_forwarded(self, ms, mock_org):
        ms.act_on_campaign("cmp-1", "quarantine_message", confirm="cmp-1")
        _, body = _post_call(mock_org)
        assert body["confirm"] == "cmp-1"


class TestConnectionDiagnostics:
    def test_watch_probe_is_absent_by_default(self, ms, mock_org):
        ms.test_connection("workspace")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/connections/workspace/test"
        assert body == {}

    def test_watch_probe_requires_explicit_opt_in(self, ms, mock_org):
        ms.test_connection("workspace", include_watch=True)
        _, body = _post_call(mock_org)
        assert body == {"include_watch": True}


class TestAnalyze:
    def test_analyze_needs_content(self, ms):
        with pytest.raises(ValueError, match="eml"):
            ms.analyze()

    def test_analyze_forwards_b64_and_domains(self, ms, mock_org):
        ms.analyze(eml_b64="QUJD", org_domains=["corp.example"])
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/analyze"
        assert body["eml_b64"] == "QUJD"
        assert body["org_domains"] == ["corp.example"]


class TestReports:
    def test_oldest_first_is_the_sla_ordering(self, ms, mock_org):
        ms.list_reports(oldest_first=True)
        _, qp = _get_call(mock_org)
        assert ("oldest_first", "true") in qp

    def test_status_repeats(self, ms, mock_org):
        ms.list_reports(status=["open", "triaging"])
        _, qp = _get_call(mock_org)
        assert ("status", "open") in qp
        assert ("status", "triaging") in qp

    def test_resolve_sends_disposition(self, ms, mock_org):
        ms.resolve_report("rep-1", "true_positive")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/reports/rep-1/resolve"
        assert body == {"disposition": "true_positive"}


class TestRules:
    def test_validate_body(self, ms, mock_org):
        ms.validate_rule({"phase": "pre_verdict"}, rule_id="custom-x")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/rules/validate"
        assert body == {"rule": {"phase": "pre_verdict"}, "rule_id": "custom-x"}

    def test_backtest_window_forwarded(self, ms, mock_org):
        ms.backtest_rule({"phase": "pre_verdict"}, since="2026-08-01")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/rules/backtest"
        assert body["since"] == "2026-08-01"


class TestPathSegmentsAreEscaped:
    """A caller-supplied id must not be able to change which route is addressed.

    Most of these are server-minted UUIDs, but the sender key is an address or
    domain a person types and the connection record is a hive record name. An
    unescaped slash in either silently addresses a DIFFERENT route rather than
    failing — a typo becoming a request nobody intended.
    """

    def test_a_slash_in_a_sender_key_cannot_change_the_route(self, ms, mock_org):
        ms.get_sender_profile("evil/../../admin")
        url, _ = _get_call(mock_org)
        assert url == f"mailsec/{OID}/senders/evil%2F..%2F..%2Fadmin"
        assert url.count("/") == 3, f"the key escaped its segment: {url}"

    def test_a_slash_in_a_connection_record_cannot_change_the_route(self, ms, mock_org):
        ms.test_connection("a/b")
        url, _ = _post_call(mock_org)
        assert url == f"mailsec/{OID}/connections/a%2Fb/test"

    def test_ordinary_ids_are_unharmed(self, ms, mock_org):
        ms.get_message("0057db2b-3a06-5aab-b3be-c1e6c15dcf10")
        url, _ = _get_call(mock_org)
        assert url == f"mailsec/{OID}/messages/0057db2b-3a06-5aab-b3be-c1e6c15dcf10"

    def test_an_email_sender_key_survives_readably(self, ms, mock_org):
        """@ and . are escaped but the request still resolves; the point is that
        the segment cannot BREAK OUT, not that it stays pretty."""
        ms.get_sender_profile("cfo@corp.example")
        url, _ = _get_call(mock_org)
        assert url.startswith(f"mailsec/{OID}/senders/")
        assert "/" not in url[len(f"mailsec/{OID}/senders/"):]


class TestRouteCoverage:
    """Every gateway route has an SDK method.

    The gateway is the contract; a route with no SDK method is a capability
    the CLI silently does not have, and nobody notices until someone needs it.
    """

    def test_every_route_has_a_method(self, ms, mock_org):
        # Most methods do not inspect the mocked response. The EML route does,
        # because its SDK contract is the decoded byte stream.
        mock_org.client.request.return_value = {"eml_b64": "", "size": 0}
        calls = [
            (lambda: ms.get_coverage(), "GET", f"mailsec/{OID}/coverage"),
            (lambda: ms.list_messages(), "GET", f"mailsec/{OID}/messages"),
            (lambda: ms.get_message("m"), "GET", f"mailsec/{OID}/messages/m"),
            (lambda: ms.get_message_eml("m", "why"), "GET", f"mailsec/{OID}/messages/m/eml"),
            (lambda: ms.list_similar_messages("m"), "GET", f"mailsec/{OID}/messages/m/similar"),
            (lambda: ms.list_campaigns(), "GET", f"mailsec/{OID}/campaigns"),
            (lambda: ms.get_campaign("c"), "GET", f"mailsec/{OID}/campaigns/c"),
            (lambda: ms.get_sender_profile("s"), "GET", f"mailsec/{OID}/senders/s"),
            (lambda: ms.get_action("a"), "GET", f"mailsec/{OID}/actions/a"),
            (lambda: ms.list_reports(), "GET", f"mailsec/{OID}/reports"),
            (lambda: ms.get_report("r"), "GET", f"mailsec/{OID}/reports/r"),
            (lambda: ms.get_hunt("h"), "GET", f"mailsec/{OID}/hunts/h"),
            (lambda: ms.get_onboarding(), "GET", f"mailsec/{OID}/onboarding"),
            (lambda: ms.analyze(eml="x"), "POST", f"mailsec/{OID}/analyze"),
            (lambda: ms.act_on_message("m", "a"), "POST", f"mailsec/{OID}/messages/m/actions"),
            (lambda: ms.act_on_campaign("c", "a"), "POST", f"mailsec/{OID}/campaigns/c/actions"),
            (lambda: ms.resolve_report("r", "benign"), "POST", f"mailsec/{OID}/reports/r/resolve"),
            (lambda: ms.create_hunt(lcql="q"), "POST", f"mailsec/{OID}/hunts"),
            (lambda: ms.remediate_hunt("h", "a"), "POST", f"mailsec/{OID}/hunts/h/remediate"),
            (lambda: ms.validate_rule({}), "POST", f"mailsec/{OID}/rules/validate"),
            (lambda: ms.backtest_rule({}), "POST", f"mailsec/{OID}/rules/backtest"),
            (lambda: ms.test_connection("rec"), "POST", f"mailsec/{OID}/connections/rec/test"),
        ]
        # 22 gateway routes, 22 SDK methods.
        assert len(calls) == 22
        for fn, method, expected_url in calls:
            mock_org.client.request.reset_mock()
            fn()
            args, _ = mock_org.client.request.call_args
            assert args[0] == method, f"{expected_url}: wrong HTTP method"
            assert args[1] == expected_url
