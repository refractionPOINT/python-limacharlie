"""Tests for limacharlie.sdk.fp_rules module (Hive-backed)."""

from unittest.mock import MagicMock
import json
import pytest

from limacharlie.sdk.fp_rules import FPRules
from limacharlie.errors import ApiError


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def fp_rules(mock_org):
    return FPRules(mock_org)


class TestFPRulesList:
    def test_list(self, fp_rules, mock_org):
        mock_org.client.request.return_value = {
            "rule-a": {"data": {"op": "is"}, "usr_mtd": {}, "sys_mtd": {}},
            "rule-b": {"data": {"op": "and"}, "usr_mtd": {}, "sys_mtd": {}},
        }
        result = fp_rules.list()
        mock_org.client.request.assert_called_once_with("GET", "hive/fp/test-oid")
        assert "rule-a" in result
        assert "rule-b" in result
        # Each value should be the to_dict() format
        assert "data" in result["rule-a"]
        assert result["rule-a"]["data"]["op"] == "is"

    def test_list_empty(self, fp_rules, mock_org):
        mock_org.client.request.return_value = {}
        result = fp_rules.list()
        assert result == {}


class TestFPRulesGet:
    def test_get_existing(self, fp_rules, mock_org):
        mock_org.client.request.return_value = {
            "data": {"op": "is", "path": "event/FILE_PATH"},
            "usr_mtd": {"enabled": True},
            "sys_mtd": {"etag": "abc"},
        }
        result = fp_rules.get("my-fp-rule")
        mock_org.client.request.assert_called_once_with(
            "GET", "hive/fp/test-oid/my-fp-rule/data",
        )
        assert result is not None
        assert result["data"]["op"] == "is"

    def test_get_returns_none_on_404(self, fp_rules, mock_org):
        mock_org.client.request.side_effect = ApiError("not found", status_code=404)
        result = fp_rules.get("nonexistent")
        assert result is None

    def test_get_raises_on_non_404_error(self, fp_rules, mock_org):
        mock_org.client.request.side_effect = ApiError("server error", status_code=500)
        with pytest.raises(ApiError):
            fp_rules.get("some-rule")


class TestFPRulesCreate:
    def test_create(self, fp_rules, mock_org):
        mock_org.client.request.return_value = {}
        fp_rules.create("new-fp", {"op": "is", "path": "event/FILE_PATH", "value": "test.exe"})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "hive/fp/test-oid/new-fp/data" in call_args[0][1]
        # Verify data is passed as JSON string in params
        params = call_args[1]["params"]
        data = json.loads(params["data"])
        assert data["op"] == "is"
        assert data["path"] == "event/FILE_PATH"


class TestFPRulesDelete:
    def test_delete(self, fp_rules, mock_org):
        mock_org.client.request.return_value = {}
        fp_rules.delete("old-fp")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "hive/fp/test-oid/old-fp",
        )
