"""Tests for limacharlie.sdk.mailsec module."""

import json

from unittest.mock import MagicMock, patch

import pytest

from limacharlie.sdk.mailsec import BULK_TERMINAL_STATES, Mailsec, normalize_bulk_selection


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

    def test_banner_uses_the_gateway_wire_name(self, ms, mock_org):
        ms.act_on_message("msg-1", "banner_message", banner="<div>external sender</div>")
        _, body = _post_call(mock_org)
        assert body == {
            "action": "banner_message",
            "banner_html": "<div>external sender</div>",
        }

    def test_campaign_action_previews_without_confirm(self, ms, mock_org):
        """confirm is what turns a preview into an execution. Its absence must
        reach the server as an absence, not as an empty string that could be
        read as a confirmation."""
        ms.act_on_campaign("cmp-1", "quarantine_message")
        _, body = _post_call(mock_org)
        assert "confirm" not in body

    def test_campaign_action_confirm_is_forwarded(self, ms, mock_org):
        ms.act_on_campaign("cmp-1", "quarantine_message", confirm="member-bound-token")
        _, body = _post_call(mock_org)
        assert body["confirm"] == "member-bound-token"


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

    def test_reopen_sends_empty_body(self, ms, mock_org):
        ms.reopen_report("rep-1")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/reports/rep-1/reopen"
        assert body == {}


class TestVerdictRevision:
    """A verdict revision is a human triage decision appended to the message's
    verdict history. mode defaults to analyst because the caller is a person;
    the rationale is required and audited, so its bounds are enforced locally
    to fail with a clear message rather than a 400 after the round trip."""

    def test_revise_body_defaults_to_analyst_mode(self, ms, mock_org):
        ms.revise_verdict("msg-1", "malicious", ["confirmed phish"])
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/messages/msg-1/verdict"
        assert body == {
            "verdict": "malicious",
            "mode": "analyst",
            "rationale": ["confirmed phish"],
        }

    def test_revise_forwards_score_and_multiple_rationale(self, ms, mock_org):
        ms.revise_verdict("msg-1", "benign", ["a", "b"], score=12.5)
        _, body = _post_call(mock_org)
        assert body["rationale"] == ["a", "b"]
        assert body["score"] == 12.5

    def test_score_is_omitted_when_absent(self, ms, mock_org):
        ms.revise_verdict("msg-1", "benign", ["a"])
        _, body = _post_call(mock_org)
        assert "score" not in body

    def test_empty_rationale_is_refused(self, ms):
        with pytest.raises(ValueError, match="at least one rationale"):
            ms.revise_verdict("msg-1", "malicious", [])

    def test_blank_rationale_line_is_refused(self, ms):
        with pytest.raises(ValueError, match="non-empty"):
            ms.revise_verdict("msg-1", "malicious", ["   "])

    def test_too_many_rationale_lines_is_refused(self, ms):
        with pytest.raises(ValueError, match="too many rationale"):
            ms.revise_verdict("msg-1", "malicious", [f"line {i}" for i in range(11)])

    def test_ten_rationale_lines_is_allowed(self, ms, mock_org):
        ms.revise_verdict("msg-1", "malicious", [f"line {i}" for i in range(10)])
        _, body = _post_call(mock_org)
        assert len(body["rationale"]) == 10

    def test_overlong_rationale_line_is_refused(self, ms):
        with pytest.raises(ValueError, match="too long"):
            ms.revise_verdict("msg-1", "malicious", ["x" * 281])

    def test_rationale_line_at_the_limit_is_allowed(self, ms, mock_org):
        ms.revise_verdict("msg-1", "malicious", ["x" * 280])
        _, body = _post_call(mock_org)
        assert body["rationale"] == ["x" * 280]

    def test_revisions_reads_oldest_first_history(self, ms, mock_org):
        ms.list_revisions("msg-1")
        url, qp = _get_call(mock_org)
        assert url == f"mailsec/{OID}/messages/msg-1/revisions"
        assert qp is None


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


class TestBulkSelectionNormalization:
    """The confirmation token is DERIVED from the normalized member list, so
    this function is the contract and not a tidy-up: if the client's
    normalization disagreed with the server's, a preview a human approved would
    mint a token its own execute could not spend."""

    def test_duplicates_collapse_and_order_is_canonical(self):
        assert normalize_bulk_selection(["b", "a", "b", " a "]) == ["a", "b"]

    def test_reordering_the_input_does_not_change_the_selection(self):
        """The property the token binding rests on: the same SET is the same
        list, whatever order a caller happened to build it in."""
        assert normalize_bulk_selection(["c", "a", "b"]) == normalize_bulk_selection(["b", "c", "a"])

    def test_blank_entries_are_dropped_not_sent(self):
        assert normalize_bulk_selection(["a", "", "   ", "b"]) == ["a", "b"]

    def test_an_empty_selection_is_refused(self):
        with pytest.raises(ValueError, match="at least one msg_uuid"):
            normalize_bulk_selection([])

    def test_a_selection_of_only_blanks_is_refused(self):
        """Empty AFTER normalization is still empty; a caller that passed
        whitespace gets the same refusal as one who passed nothing."""
        with pytest.raises(ValueError, match="at least one msg_uuid"):
            normalize_bulk_selection(["", "  "])

    def test_a_bare_string_is_refused_rather_than_split_into_characters(self):
        with pytest.raises(ValueError, match="not a single string"):
            normalize_bulk_selection("0057db2b-3a06-5aab-b3be-c1e6c15dcf10")

    def test_the_cap_is_not_enforced_client_side(self):
        """500 is the SERVER's policy and it refuses an oversized selection
        rather than truncating it. A client that trimmed to fit would leave the
        remainder in inboxes nobody looks at, and the caller would never learn
        it had happened."""
        assert len(normalize_bulk_selection([f"m{i:04d}" for i in range(900)])) == 900


class TestBulkRemediation:
    def test_preview_sends_the_normalized_selection(self, ms, mock_org):
        ms.bulk_action_preview("quarantine_message", ["b", "a", "a"], attempt="inc-1")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/actions/bulk/preview"
        assert body == {
            "action": "quarantine_message",
            "msg_uuids": ["a", "b"],
            "attempt": "inc-1",
        }

    def test_preview_omits_an_absent_attempt(self, ms, mock_org):
        """attempt participates in the token, so an absent one and an empty one
        are different selections. Sending "" for absent would mint a token the
        server derived over a different input."""
        ms.bulk_action_preview("trash_message", ["a"])
        _, body = _post_call(mock_org)
        assert "attempt" not in body

    def test_execute_carries_the_confirmation_and_the_same_list(self, ms, mock_org):
        ms.bulk_action_execute("trash_message", ["b", "a"], "tok-1", attempt="inc-1")
        url, body = _post_call(mock_org)
        assert url == f"mailsec/{OID}/actions/bulk/execute"
        assert body == {
            "action": "trash_message",
            "msg_uuids": ["a", "b"],
            "confirm": "tok-1",
            "attempt": "inc-1",
        }

    def test_preview_and_execute_agree_on_the_wire_selection(self, ms, mock_org):
        """The binding property, asserted where it is actually observable: two
        differently-ordered spellings of one set produce byte-identical
        msg_uuids on both routes, so a token minted by the preview is spendable
        by the execute."""
        ms.bulk_action_preview("trash_message", ["c", "a", "b"])
        _, preview_body = _post_call(mock_org)
        ms.bulk_action_execute("trash_message", ["b", "c", "a"], "tok-1")
        _, execute_body = _post_call(mock_org)
        assert preview_body["msg_uuids"] == execute_body["msg_uuids"] == ["a", "b", "c"]

    def test_banner_is_spelled_banner_on_the_wire(self, ms, mock_org):
        """`banner` is the PUBLIC spelling; the gateway translates it to the
        collector's `banner_html` (mailsecBulkExecuteArgs). Its allow-list
        happens to forward a literal `banner_html` too, so both would in fact
        work — but only `banner` is in the documented body schema, and pinning
        the documented name is what keeps this client on the contract rather
        than on an implementation detail of the forwarder."""
        ms.bulk_action_execute("banner_message", ["a"], "tok", banner="<b>caution</b>")
        _, body = _post_call(mock_org)
        assert body["banner"] == "<b>caution</b>"
        assert "banner_html" not in body

    def test_execute_omits_absent_optionals(self, ms, mock_org):
        ms.bulk_action_execute("trash_message", ["a"], "tok")
        _, body = _post_call(mock_org)
        assert set(body) == {"action", "msg_uuids", "confirm"}

    def test_execute_carries_the_operator_reason(self, ms, mock_org):
        """The justification a human typed, on the route that moves up to 500
        people's mail at once. It reaches the job's audit row and every
        message's, the same way act_on_message's does for one."""
        ms.bulk_action_execute("trash_message", ["a"], "tok", reason="INC-4471")
        _, body = _post_call(mock_org)
        assert body["reason"] == "INC-4471"

    def test_the_preview_takes_no_reason(self, ms, mock_org):
        """The other half, and the reason the execute may carry one at all.

        The preview mints the confirmation, which the backend derives from
        (oid, action, attempt, members) and NOT from the reason. A reason that
        reached the preview could end up in that derivation, which would mean
        rewording a justification invalidated a selection somebody had already
        approved — and minted a second bulk id over the same messages. So it is
        not a parameter here, and the gateway's own preview allow-list refuses
        to forward one."""
        with pytest.raises(TypeError):
            ms.bulk_action_preview("trash_message", ["a"], reason="INC-4471")

    def test_an_empty_selection_never_reaches_the_network(self, ms, mock_org):
        for call in (
            lambda: ms.bulk_action_preview("trash_message", []),
            lambda: ms.bulk_action_execute("trash_message", [], "tok"),
        ):
            mock_org.client.request.reset_mock()
            with pytest.raises(ValueError, match="at least one msg_uuid"):
                call()
            mock_org.client.request.assert_not_called()

    def test_status_reads_the_job_by_id(self, ms, mock_org):
        ms.bulk_action_status("bulk-1")
        url, qp = _get_call(mock_org)
        assert url == f"mailsec/{OID}/actions/bulk/bulk-1"
        assert qp is None

    def test_a_slash_in_a_bulk_id_cannot_change_the_route(self, ms, mock_org):
        ms.bulk_action_status("a/b")
        url, _ = _get_call(mock_org)
        assert url == f"mailsec/{OID}/actions/bulk/a%2Fb"


def _bulk_status(state="running", stalled=False, ok=0):
    return {"bulk_id": "b", "state": state, "stalled": stalled,
            "counts": {"total": 2, "ok": ok, "failed": 0, "pending": 2 - ok}}


class TestWaitForBulk:
    """Three things stop the wait, and conflating any two of them costs a real
    operator real time: a finished job, a job nobody is working, and a deadline
    that says nothing about the job at all."""

    def test_it_polls_until_the_job_leaves_running(self, ms):
        ms.bulk_action_status = MagicMock(side_effect=[
            _bulk_status("running"),
            _bulk_status("running", ok=1),
            _bulk_status("complete", ok=2),
        ])
        with patch("limacharlie.sdk.mailsec.time.sleep") as sleep:
            final = ms.wait_for_bulk("b", timeout=300, poll_interval=3)
        assert final["state"] == "complete"
        assert ms.bulk_action_status.call_count == 3
        assert sleep.call_count == 2

    def test_interrupted_is_terminal_too(self, ms):
        """A worker that lost its pod finalizes the record with the outcomes it
        had. The answer has already arrived; polling for a different one would
        burn the whole timeout."""
        ms.bulk_action_status = MagicMock(return_value=_bulk_status("interrupted", ok=1))
        final = ms.wait_for_bulk("b", timeout=300)
        assert final["state"] == "interrupted"
        assert ms.bulk_action_status.call_count == 1

    def test_the_terminal_states_are_the_two_the_gateway_defines(self):
        assert BULK_TERMINAL_STATES == ("complete", "interrupted")

    def test_stalled_stops_the_wait_even_though_the_job_is_running(self, ms):
        """There is deliberately no automatic resumption: the record is not
        being heartbeaten, so no amount of further polling will move it."""
        ms.bulk_action_status = MagicMock(return_value=_bulk_status("running", stalled=True))
        final = ms.wait_for_bulk("b", timeout=300)
        assert final["stalled"] is True
        assert final["state"] == "running"
        assert ms.bulk_action_status.call_count == 1

    def test_the_deadline_returns_the_last_running_document(self, ms):
        """No exception, following Jobs.wait: a document that comes back running
        and not stalled is one the deadline ended, and the caller is the only
        one who knows whether that matters."""
        ms.bulk_action_status = MagicMock(return_value=_bulk_status("running"))
        with patch("limacharlie.sdk.mailsec.time.monotonic", side_effect=[0.0, 10_000.0]):
            final = ms.wait_for_bulk("b", timeout=300)
        assert final["state"] == "running"
        assert final["stalled"] is False
        assert ms.bulk_action_status.call_count == 1

    def test_the_sleep_never_overshoots_the_deadline(self, ms):
        """A 300s poll interval against a 5s timeout must not park the caller
        for five minutes past the deadline it asked for."""
        ms.bulk_action_status = MagicMock(return_value=_bulk_status("running"))
        with (
            patch("limacharlie.sdk.mailsec.time.monotonic", side_effect=[0.0, 2.0, 10.0]),
            patch("limacharlie.sdk.mailsec.time.sleep") as sleep,
        ):
            ms.wait_for_bulk("b", timeout=5, poll_interval=300)
        assert sleep.call_args.args[0] == 3.0

    def test_on_poll_sees_every_status_document(self, ms):
        """The CLI narrates from this; a callback that skipped the terminal poll
        would make a caller reconstruct the ending from the return value."""
        seen = []
        ms.bulk_action_status = MagicMock(side_effect=[
            _bulk_status("running"), _bulk_status("complete", ok=2),
        ])
        with patch("limacharlie.sdk.mailsec.time.sleep"):
            ms.wait_for_bulk("b", on_poll=seen.append)
        assert [s["state"] for s in seen] == ["running", "complete"]

    def test_it_adds_no_route_of_its_own(self, ms, mock_org):
        """It is a loop over an existing route, not a new capability. If this
        ever issued anything else, the route inventory below would be wrong."""
        mock_org.client.request.return_value = _bulk_status("complete", ok=2)
        ms.wait_for_bulk("b")
        for call in mock_org.client.request.call_args_list:
            assert call.args == ("GET", f"mailsec/{OID}/actions/bulk/b")


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
            (lambda: ms.list_revisions("m"), "GET", f"mailsec/{OID}/messages/m/revisions"),
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
            (lambda: ms.revise_verdict("m", "malicious", ["why"]), "POST", f"mailsec/{OID}/messages/m/verdict"),
            (lambda: ms.act_on_campaign("c", "a"), "POST", f"mailsec/{OID}/campaigns/c/actions"),
            (lambda: ms.resolve_report("r", "benign"), "POST", f"mailsec/{OID}/reports/r/resolve"),
            (lambda: ms.reopen_report("r"), "POST", f"mailsec/{OID}/reports/r/reopen"),
            (lambda: ms.create_hunt(lcql="q"), "POST", f"mailsec/{OID}/hunts"),
            (lambda: ms.remediate_hunt("h", "a"), "POST", f"mailsec/{OID}/hunts/h/remediate"),
            (lambda: ms.validate_rule({}), "POST", f"mailsec/{OID}/rules/validate"),
            (lambda: ms.backtest_rule({}), "POST", f"mailsec/{OID}/rules/backtest"),
            (lambda: ms.test_connection("rec"), "POST", f"mailsec/{OID}/connections/rec/test"),
            (lambda: ms.bulk_action_preview("trash_message", ["m"]), "POST",
             f"mailsec/{OID}/actions/bulk/preview"),
            (lambda: ms.bulk_action_execute("trash_message", ["m"], "tok"), "POST",
             f"mailsec/{OID}/actions/bulk/execute"),
            (lambda: ms.bulk_action_status("b"), "GET", f"mailsec/{OID}/actions/bulk/b"),
            (lambda: ms.prepare_tenant_purge(), "GET", f"mailsec/{OID}/tenant"),
            (lambda: ms.purge_tenant("tok"), "DELETE", f"mailsec/{OID}/tenant"),
        ]
        # 30 gateway routes, 30 SDK methods.
        assert len(calls) == 30
        for fn, method, expected_url in calls:
            mock_org.client.request.reset_mock()
            fn()
            args, _ = mock_org.client.request.call_args
            assert args[0] == method, f"{expected_url}: wrong HTTP method"
            assert args[1] == expected_url


class TestTenantPurge:
    """The irreversible one.

    Two properties matter more than the rest: the destructive half is a DELETE
    to its own route and cannot be reached without a token, and the token/reason
    reach the wire as query params rather than a body the gateway would not read.
    """

    def test_prepare_is_a_read_and_mints_nothing_of_its_own(self, ms, mock_org):
        mock_org.client.request.return_value = {
            "confirmation": "tok", "expires_in_seconds": 300, "warning": "..."
        }
        assert ms.prepare_tenant_purge()["confirmation"] == "tok"
        url, qp = _get_call(mock_org)
        assert url == f"mailsec/{OID}/tenant"
        assert qp is None

    def test_purge_is_a_delete_carrying_the_token_as_a_query_param(self, ms, mock_org):
        ms.purge_tenant("tok")
        args, kwargs = mock_org.client.request.call_args
        assert args[0] == "DELETE"
        assert args[1] == f"mailsec/{OID}/tenant"
        assert kwargs["query_params"] == [("confirmation", "tok")]
        # A DELETE with a JSON body would be silently ignored by the gateway.
        assert kwargs.get("raw_body") is None

    def test_the_audited_reason_is_forwarded(self, ms, mock_org):
        ms.purge_tenant("tok", reason="customer offboarded")
        _, kwargs = mock_org.client.request.call_args
        assert kwargs["query_params"] == [
            ("confirmation", "tok"), ("reason", "customer offboarded")
        ]

    def test_an_absent_reason_sends_no_pair(self, ms, mock_org):
        ms.purge_tenant("tok", reason=None)
        _, kwargs = mock_org.client.request.call_args
        assert [k for k, _ in kwargs["query_params"]] == ["confirmation"]

    def test_an_empty_reason_is_still_sent(self, ms, mock_org):
        """`reason=""` is a caller saying "record that I gave none", which is
        not the same as never passing the parameter."""
        ms.purge_tenant("tok", reason="")
        _, kwargs = mock_org.client.request.call_args
        assert ("reason", "") in kwargs["query_params"]

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_a_missing_token_never_reaches_the_network(self, ms, mock_org, bad):
        with pytest.raises(ValueError):
            ms.purge_tenant(bad)
        mock_org.client.request.assert_not_called()

    def test_an_over_long_reason_is_refused_before_the_token_is_spent(self, ms, mock_org):
        """The token is single-use: learning about the bound from the server
        costs a re-mint, so it is checked here."""
        with pytest.raises(ValueError, match="1024"):
            ms.purge_tenant("tok", reason="x" * 1025)
        mock_org.client.request.assert_not_called()

    def test_the_bound_itself_is_accepted(self, ms, mock_org):
        ms.purge_tenant("tok", reason="x" * 1024)
        _, kwargs = mock_org.client.request.call_args
        assert ("reason", "x" * 1024) in kwargs["query_params"]
