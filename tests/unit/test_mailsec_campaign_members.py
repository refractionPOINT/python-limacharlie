"""Campaign membership pagination through the SDK and CLI."""
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.mailsec import Mailsec


def test_member_page_preserves_missing_message_and_opaque_cursor():
    org = MagicMock()
    org.oid = "11111111-2222-3333-4444-555555555555"
    response = {"members": [{"msg_uuid": "expired", "message": None}], "next_cursor": "opaque"}
    org.client.request.return_value = response
    result = Mailsec(org).list_campaign_members("campaign/one", limit=200, cursor="opaque+/=")
    assert result == response
    args, kwargs = org.client.request.call_args
    assert args == ("GET", f"mailsec/{org.oid}/campaigns/campaign%2Fone/members")
    assert kwargs["query_params"] == [("cursor", "opaque+/="), ("limit", "200")]
    Mailsec(org).list_campaign_members("campaign")
    assert org.client.request.call_args.kwargs["query_params"] is None


@pytest.mark.parametrize("limit", [0, -1, 201, True, "50", 1.5])
def test_invalid_member_page_size_is_refused_before_request(limit):
    org = MagicMock()
    with pytest.raises(ValueError):
        Mailsec(org).list_campaign_members("campaign", limit=limit)
    org.client.request.assert_not_called()


@pytest.mark.parametrize("cursor", ["x" * 513, "é" * 257, ["a", "b"]])
def test_invalid_member_cursor_is_refused_before_request(cursor):
    org = MagicMock()
    with pytest.raises(ValueError):
        Mailsec(org).list_campaign_members("campaign", cursor=cursor)
    org.client.request.assert_not_called()


def test_member_cli_forwards_page_and_preserves_response():
    with patch("limacharlie.commands.mailsec.Client"), patch("limacharlie.commands.mailsec.Organization"), patch("limacharlie.commands.mailsec.Mailsec") as cls:
        response = {"members": [{"msg_uuid": "expired", "message": None}], "next_cursor": None}
        cls.return_value.list_campaign_members.return_value = response
        result = CliRunner().invoke(cli, ["--oid", "11111111-2222-3333-4444-555555555555", "--output", "json", "mailsec", "campaign", "members", "campaign", "--limit", "1", "--cursor", "opaque"])
        assert result.exit_code == 0, result.output
        cls.return_value.list_campaign_members.assert_called_once_with("campaign", cursor="opaque", limit=1)
        assert json.loads(result.output) == response


def test_member_cli_enforces_limit_and_documents_expiration():
    result = CliRunner().invoke(cli, ["mailsec", "campaign", "members", "campaign", "--limit", "201"])
    assert result.exit_code != 0
    help_result = CliRunner().invoke(cli, ["mailsec", "campaign", "members", "--help"])
    assert help_result.exit_code == 0
    assert "message=null" in help_result.output
