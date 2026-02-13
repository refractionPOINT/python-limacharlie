"""Tests for limacharlie.sdk.investigations module."""

import json
from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.investigations import Investigations


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def inv(mock_org):
    return Investigations(mock_org)


class TestInvestigationsList:
    def test_delegates_to_hive_list(self, inv, mock_org):
        mock_org.client.request.return_value = {
            "inv-1": {"data": {"status": "open"}, "usr_mtd": {}, "sys_mtd": {}},
        }
        result = inv.list()
        mock_org.client.request.assert_called_once_with(
            "GET", "hive/investigation/test-oid"
        )
        assert "inv-1" in result


class TestInvestigationsGet:
    def test_delegates_to_hive_get(self, inv, mock_org):
        mock_org.client.request.return_value = {
            "data": {"status": "open"},
            "usr_mtd": {},
            "sys_mtd": {"etag": "e1"},
        }
        rec = inv.get("inv-1")
        mock_org.client.request.assert_called_once_with(
            "GET", "hive/investigation/test-oid/inv-1/data"
        )
        assert rec.name == "inv-1"
        assert rec.data == {"status": "open"}


class TestInvestigationsCreate:
    def test_delegates_to_hive_set(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.create("new-inv", {"status": "open", "priority": "high"})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "hive/investigation/test-oid/new-inv/data" in call_args[0][1]
        params = call_args[1]["params"]
        data = json.loads(params["data"])
        assert data == {"status": "open", "priority": "high"}


class TestInvestigationsUpdate:
    def test_delegates_to_hive_set(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.update("inv-1", {"status": "closed"})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "hive/investigation/test-oid/inv-1/data" in call_args[0][1]

    def test_passes_etag(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.update("inv-1", {"status": "closed"}, etag="e1")
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        assert params["etag"] == "e1"


class TestInvestigationsDelete:
    def test_delegates_to_hive_delete(self, inv, mock_org):
        mock_org.client.request.return_value = {}
        inv.delete("inv-1")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "hive/investigation/test-oid/inv-1"
        )


class TestInvestigationsExpand:
    def test_expand_by_name(self, inv, mock_org):
        mock_org.client.request.return_value = {"events": {}, "detections": {}}
        inv.expand(investigation_name="inv-1")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "orgs/test-oid/investigation/expand")
        body = json.loads(call_args[1]["raw_body"])
        assert body == {"investigation_name": "inv-1"}
        assert call_args[1]["content_type"] == "application/json"

    def test_expand_by_object(self, inv, mock_org):
        mock_org.client.request.return_value = {"events": {}, "detections": {}}
        inv_obj = {"name": "inline", "data": {"events": ["e1"]}}
        inv.expand(investigation=inv_obj)
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "orgs/test-oid/investigation/expand")
        body = json.loads(call_args[1]["raw_body"])
        assert body == {"investigation": inv_obj}
        assert "investigation_name" not in body
