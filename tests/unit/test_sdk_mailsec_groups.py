import json
from unittest.mock import MagicMock, patch

import pytest

from limacharlie.sdk.mailsec import Mailsec

OID = "11111111-1111-4111-8111-111111111111"
GID = "a" * 64
JOB = "22222222-2222-4222-8222-222222222222"

@pytest.fixture
def client():
    org = MagicMock()
    org.oid = OID
    return Mailsec(org), org.client


def test_groups_preserve_repeated_filters_and_false_report_constraint(client):
    ms, transport = client
    ms.list_groups(severity=["medium", "critical"], disposition=["malicious", "none"], user_reported=False, all_groups=True, cursor="opaque", limit=25)
    args, kwargs = transport.request.call_args
    assert args == ("GET", f"mailsec/{OID}/groups")
    pairs = kwargs["query_params"]
    assert [(k, v) for k, v in pairs if k == "severity"] == [("severity", "medium"), ("severity", "critical")]
    assert ("user_reported", "false") in pairs
    assert ("all", "true") in pairs
    assert ("cursor", "opaque") in pairs
    assert ("disposition", "none") in pairs
    assert ("limit", "25") in pairs


def test_group_exclude_state_forwarded_single_and_repeated(client):
    ms, transport = client
    ms.list_groups(exclude_state=["spam"])
    args, kwargs = transport.request.call_args
    assert args == ("GET", f"mailsec/{OID}/groups")
    assert kwargs["query_params"] == [("exclude_state", "spam")]
    ms.list_groups(state=["delivered"], exclude_state=["spam", "trashed"])
    pairs = transport.request.call_args.kwargs["query_params"]
    assert [(k, v) for k, v in pairs if k == "exclude_state"] == [("exclude_state", "spam"), ("exclude_state", "trashed")]
    assert ("state", "delivered") in pairs


def test_group_absent_exclude_state_sends_nothing(client):
    ms, transport = client
    ms.list_groups(state=["spam"])
    pairs = transport.request.call_args.kwargs["query_params"]
    assert all(key != "exclude_state" for key, _ in pairs)


def test_group_preview_freezes_force_reason_text_and_client_identity(client):
    ms, transport = client
    ms.prepare_group_action(GID, "banner_message", JOB, force=True, reason="Fixture review", text="Review this message")
    args, kwargs = transport.request.call_args
    assert args == ("POST", f"mailsec/{OID}/groups/{GID}/actions/preview")
    body = json.loads(kwargs["raw_body"])
    assert body == {"action": "banner_message", "preview_id": JOB, "force": True, "reason": "Fixture review", "text": "Review this message"}
    ms.confirm_group_action(JOB, "b" * 64)
    args, kwargs = transport.request.call_args
    assert args == ("POST", f"mailsec/{OID}/group-actions/{JOB}/confirm")
    assert json.loads(kwargs["raw_body"]) == {"confirmation": "b" * 64}


@pytest.mark.parametrize("value", ["", "../other", "a" * 63, "A" * 64])
def test_group_identity_refused_before_transport(client, value):
    ms, transport = client
    with pytest.raises(ValueError):
        ms.get_group(value)
    transport.request.assert_not_called()


def test_preview_force_must_be_boolean(client):
    ms, transport = client
    with pytest.raises(TypeError):
        ms.prepare_group_action(GID, "trash_message", JOB, force="true")
    transport.request.assert_not_called()


def test_polling_stops_at_ready_without_executing(client):
    ms, transport = client
    transport.request.side_effect = [{"job": {"phase": "preparing"}}, {"job": {"phase": "ready"}, "confirmation": "b" * 64}]
    with patch("limacharlie.sdk.mailsec.time.sleep"):
        status = ms.wait_for_group_action(JOB, preparing=True, timeout=5, poll_interval=1)
    assert status["job"]["phase"] == "ready"
    assert len(transport.request.call_args_list) == 2
    assert all(call.args[0] == "GET" for call in transport.request.call_args_list)


def test_polling_unknown_phase_is_an_error(client):
    ms, transport = client
    transport.request.return_value = {"job": {"phase": "unknown"}}
    with pytest.raises(RuntimeError):
        ms.wait_for_group_action(JOB)


@pytest.mark.parametrize("timeout, interval", [(float("inf"), 3), (True, 3), (3601, 3), (5, 0), (5, 61)])
def test_polling_bounds_refused_before_transport(client, timeout, interval):
    ms, transport = client
    with pytest.raises(ValueError):
        ms.wait_for_group_action(JOB, timeout=timeout, poll_interval=interval)
    transport.request.assert_not_called()


def test_deadline_returns_last_running_job_and_never_reconfirms(client):
    ms, transport = client
    transport.request.return_value = {"job": {"phase": "running", "job_id": JOB}}
    with patch("limacharlie.sdk.mailsec.time.monotonic", side_effect=[0, 10]):
        result = ms.wait_for_group_action(JOB, timeout=1)
    assert result["job"]["phase"] == "running"
    assert transport.request.call_count == 1
    assert transport.request.call_args.args[0] == "GET"


def test_message_group_and_severity_filters_forward_and_narrow_search(client):
    ms, transport = client
    ms.list_messages(group_id=GID, severity=["high", "critical"], q="fixture")
    pairs = transport.request.call_args.kwargs["query_params"]
    assert ("group_id", GID) in pairs
    assert [(key, value) for key, value in pairs if key == "severity"] == [("severity", "high"), ("severity", "critical")]
    ms.list_messages(severity=["critical"], q="fixture")
    with pytest.raises(ValueError):
        ms.list_messages(severity=["high", "critical"], q="fixture")


@pytest.mark.parametrize("disposition", ["malicious", "spam", "graymail", "benign", "simulation"])
def test_group_disposition_uses_the_same_durable_preview(client, disposition):
    ms, transport = client
    ms.prepare_group_action(GID, "set_disposition", JOB, disposition=disposition, note="Reviewed synthetic copies")
    assert json.loads(transport.request.call_args.kwargs["raw_body"]) == {"action": "set_disposition", "preview_id": JOB, "disposition": disposition, "note": "Reviewed synthetic copies"}
    ms.prepare_group_action(GID, "set_disposition", JOB, clear=True)
    assert json.loads(transport.request.call_args.kwargs["raw_body"]) == {"action": "set_disposition", "preview_id": JOB, "clear": True}


@pytest.mark.parametrize("action, params", [
    ("set_disposition", {}),
    ("set_disposition", {"disposition": "true_positive"}),
    ("set_disposition", {"disposition": "benign", "clear": True}),
    ("set_disposition", {"disposition": "benign", "force": True}),
    ("set_disposition", {"disposition": "benign", "reason": "provider override"}),
    ("set_disposition", {"disposition": "benign", "note": "x" * 1025}),
    ("set_disposition", {"disposition": "benign", "note": "\ud800"}),
    ("trash_message", {"disposition": "benign"}),
])
def test_invalid_group_disposition_refused_before_transport(client, action, params):
    ms, transport = client
    with pytest.raises(ValueError):
        ms.prepare_group_action(GID, action, JOB, **params)
    transport.request.assert_not_called()


def test_group_and_message_filter_wire_parity(client):
    ms, transport = client
    filters = dict(verdict=["malicious", "suspicious"], severity=["high", "critical"],
                   group_id=GID, mailbox="copy@example.invalid", sender_email="sender@example.invalid",
                   sender_domain="example.invalid", campaign_id=JOB, state=["delivered", "quarantined"], exclude_state=["spam", "trashed"],
                   direction=["inbound", "internal"], lane="live", user_reported=False, min_score=70,
                   link_domain="linked.invalid", attachment_sha256="b" * 64, q="  literal 50%  ",
                   since="2026-10-01T00:00:00Z", until="2026-10-02T00:00:00Z", cursor="opaque", limit=5)
    ms.list_messages(**filters)
    message_pairs = transport.request.call_args.kwargs["query_params"]
    ms.list_groups(**filters, disposition=["malicious", "none"], all_groups=True)
    group_pairs = transport.request.call_args.kwargs["query_params"]
    assert [(k, v) for k, v in group_pairs if k not in ("disposition", "all")] == message_pairs
    assert ("disposition", "none") in group_pairs
    assert ("q", "literal 50%") in group_pairs


@pytest.mark.parametrize("q,kwargs", [("x" * 513, {"since": "2026-10-01"}), ("needle", {}),
                                     ("needle", {"until": "2026-10-02"})])
def test_group_search_refuses_unbounded_or_oversized_input(client, q, kwargs):
    ms, transport = client
    with pytest.raises(ValueError):
        ms.list_groups(q=q, **kwargs)
    transport.request.assert_not_called()
