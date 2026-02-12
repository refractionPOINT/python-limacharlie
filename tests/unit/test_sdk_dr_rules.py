"""Tests for limacharlie.sdk.dr_rules module (Hive-backed)."""

from unittest.mock import MagicMock, patch
import pytest

from limacharlie.sdk.dr_rules import DRRules
from limacharlie.sdk.hive import HiveRecord


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def rules(mock_org):
    return DRRules(mock_org)


class TestDRRulesList:
    def test_list_default_calls_hive(self, rules, mock_org):
        mock_org.client.request.return_value = {
            "r1": {"data": {"detect": {}}, "usr_mtd": {}, "sys_mtd": {}},
        }
        result = rules.list()
        mock_org.client.request.assert_called_once_with("GET", "hive/dr-general/test-oid")
        assert "r1" in result

    def test_list_with_namespace(self, rules, mock_org):
        mock_org.client.request.return_value = {}
        rules.list(namespace="managed")
        mock_org.client.request.assert_called_once_with("GET", "hive/dr-managed/test-oid")


class TestDRRulesGet:
    def test_get_existing(self, rules, mock_org):
        mock_org.client.request.return_value = {
            "data": {"detect": {"op": "is"}},
            "usr_mtd": {},
            "sys_mtd": {},
        }
        result = rules.get("r1")
        assert result is not None
        assert result["data"]["detect"]["op"] == "is"

    def test_get_missing_returns_none(self, rules, mock_org):
        mock_org.client.request.side_effect = Exception("not found")
        result = rules.get("nonexistent")
        assert result is None


class TestDRRulesCreate:
    def test_create(self, rules, mock_org):
        mock_org.client.request.return_value = {}
        rules.create("my-rule", {"detect": {"op": "is"}, "respond": [{"action": "report"}]})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "hive/dr-general/test-oid/my-rule/data" in call_args[0][1]

    def test_create_with_namespace(self, rules, mock_org):
        mock_org.client.request.return_value = {}
        rules.create("my-rule", {}, namespace="managed")
        call_args = mock_org.client.request.call_args
        assert "hive/dr-managed/test-oid/my-rule/" in call_args[0][1]


class TestDRRulesUpdate:
    def test_update_calls_create(self, rules, mock_org):
        mock_org.client.request.return_value = {}
        rules.update("r1", {"detect": {"op": "and"}})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "hive/dr-general/test-oid/r1/" in call_args[0][1]


class TestDRRulesDelete:
    def test_delete(self, rules, mock_org):
        mock_org.client.request.return_value = {}
        rules.delete("r1")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "hive/dr-general/test-oid/r1" in call_args[0][1]

    def test_delete_with_namespace(self, rules, mock_org):
        mock_org.client.request.return_value = {}
        rules.delete("r1", namespace="service")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "hive/dr-service/test-oid/r1" in call_args[0][1]
