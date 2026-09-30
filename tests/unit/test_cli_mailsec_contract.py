"""MailSec CLI arguments must reach the published REST contract unchanged."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.mailsec import Mailsec


OID = "11111111-2222-3333-4444-555555555555"


def invoke(*args):
    org = MagicMock()
    org.oid = OID
    org.client.request.return_value = {"messages": [], "next_cursor": ""}
    # Keep the real Mailsec SDK so this covers Click parsing and serialization,
    # including omission of unset values rather than just a mock method call.
    with patch("limacharlie.commands.mailsec.Client"), patch(
        "limacharlie.commands.mailsec.Organization", return_value=org
    ):
        result = CliRunner().invoke(cli, ["--oid", OID, "--output", "json", "mailsec", *args])
    return result, org.client.request


def query(request, path):
    assert request.call_args.args == ("GET", f"mailsec/{OID}/{path}")
    return request.call_args.kwargs["query_params"]


def test_workspace_onboarding_substitutes_customer_resource_names():
    result, request = invoke(
        "onboarding", "--provider", "gworkspace", "--project-id", "customer-project",
        "--sa-email", "mail@customer-project.iam.gserviceaccount.com",
        "--topic", "mail-topic", "--subscription", "mail-subscription",
    )
    assert result.exit_code == 0, result.output
    assert dict(query(request, "onboarding")) == {
        "provider": "gworkspace", "project_id": "customer-project",
        "sa_email": "mail@customer-project.iam.gserviceaccount.com",
        "topic": "mail-topic", "subscription": "mail-subscription",
    }
    assert json.loads(result.output)["messages"] == []


@pytest.mark.parametrize("lane", ["live", "backfill"])
def test_lane_is_forwarded_with_opaque_cursor_and_existing_filters(lane):
    result, request = invoke(
        "message", "list", "--lane", lane, "--verdict", "malicious", "--verdict", "suspicious",
        "--no-user-reported", "--since", "2026-09-01T00:00:00Z", "--cursor", "opaque+/=",
    )
    assert result.exit_code == 0, result.output
    pairs = query(request, "messages")
    assert ("lane", lane) in pairs
    assert ("cursor", "opaque+/=") in pairs
    assert ("user_reported", "false") in pairs
    assert [value for key, value in pairs if key == "verdict"] == ["malicious", "suspicious"]


def test_coverage_accepts_explicit_range():
    result, request = invoke("coverage", "--since", "1788220800", "--until", "1788307200")
    assert result.exit_code == 0, result.output
    assert dict(query(request, "coverage")) == {"since": "1788220800", "until": "1788307200"}


@pytest.mark.parametrize("bound", ["--since", "--until"])
def test_coverage_rejects_ambiguous_window_before_request(bound):
    result, request = invoke("coverage", "--window-days", "7", bound, "1788220800")
    assert result.exit_code == 2
    assert "cannot be combined" in result.output
    request.assert_not_called()


def test_revision_history_limit_reaches_gateway():
    result, request = invoke("message", "revisions", "message-uuid", "--limit", "1000")
    assert result.exit_code == 0, result.output
    assert query(request, "messages/message-uuid/revisions") == [("limit", "1000")]


@pytest.mark.parametrize("args,path", [
    (("coverage",), "coverage"),
    (("onboarding",), "onboarding"),
    (("message", "list"), "messages"),
    (("message", "revisions", "message-uuid"), "messages/message-uuid/revisions"),
    (("message", "similar", "message-uuid"), "messages/message-uuid/similar"),
])
def test_unset_options_do_not_change_default_reads(args, path):
    result, request = invoke(*args)
    assert result.exit_code == 0, result.output
    assert query(request, path) is None


@pytest.mark.parametrize("option,value", [("--cursor", "previous-page"), ("--limit", "1")])
def test_similar_refuses_unsupported_paging_instead_of_repeating_first_page(option, value):
    result, request = invoke("message", "similar", "message-uuid", option, value)
    assert result.exit_code == 2
    assert "not paginated" in result.output
    request.assert_not_called()


@pytest.mark.parametrize("kwargs", [{"cursor": ""}, {"cursor": "opaque"}, {"limit": 1}])
def test_sdk_similar_refuses_unsupported_paging(kwargs):
    org = MagicMock()
    with pytest.raises(ValueError, match="not paginated"):
        Mailsec(org).list_similar_messages("message-uuid", **kwargs)
    org.client.request.assert_not_called()


@pytest.mark.parametrize("bound", ["since", "until"])
def test_sdk_coverage_rejects_ambiguous_window(bound):
    org = MagicMock()
    with pytest.raises(ValueError, match="cannot be combined"):
        Mailsec(org).get_coverage(window_days=7, **{bound: "1788220800"})
    org.client.request.assert_not_called()
