"""Tests for limacharlie.sdk.dr_rules module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.dr_rules import DRRules


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    return org


@pytest.fixture
def rules(mock_org):
    return DRRules(mock_org)


class TestDRRulesList:
    def test_list_default(self, rules, mock_org):
        mock_org.get_rules.return_value = {"r1": {"detect": {}}}
        result = rules.list()
        mock_org.get_rules.assert_called_once_with(namespace=None)
        assert "r1" in result

    def test_list_with_namespace(self, rules, mock_org):
        rules.list(namespace="managed")
        mock_org.get_rules.assert_called_once_with(namespace="managed")


class TestDRRulesGet:
    def test_get_existing(self, rules, mock_org):
        mock_org.get_rules.return_value = {"r1": {"detect": {"op": "is"}}}
        result = rules.get("r1")
        assert result == {"detect": {"op": "is"}}

    def test_get_missing(self, rules, mock_org):
        mock_org.get_rules.return_value = {}
        result = rules.get("nonexistent")
        assert result is None


class TestDRRulesCreate:
    def test_create(self, rules, mock_org):
        rules.create("my-rule", {"op": "is"}, [{"action": "report"}])
        mock_org.add_rule.assert_called_once_with(
            "my-rule", {"op": "is"}, [{"action": "report"}],
            is_replace=False, namespace=None, is_enabled=True, ttl=None,
        )

    def test_create_with_replace(self, rules, mock_org):
        rules.create("my-rule", {}, [], is_replace=True, namespace="managed")
        mock_org.add_rule.assert_called_once_with(
            "my-rule", {}, [],
            is_replace=True, namespace="managed", is_enabled=True, ttl=None,
        )


class TestDRRulesUpdate:
    def test_update_calls_create_with_replace(self, rules, mock_org):
        rules.update("r1", {"op": "and"}, [{"action": "task"}])
        mock_org.add_rule.assert_called_once_with(
            "r1", {"op": "and"}, [{"action": "task"}],
            is_replace=True, namespace=None, is_enabled=True, ttl=None,
        )


class TestDRRulesDelete:
    def test_delete(self, rules, mock_org):
        rules.delete("r1")
        mock_org.delete_rule.assert_called_once_with("r1", namespace=None)

    def test_delete_with_namespace(self, rules, mock_org):
        rules.delete("r1", namespace="replicant")
        mock_org.delete_rule.assert_called_once_with("r1", namespace="replicant")
