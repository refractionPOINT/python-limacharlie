"""Tests for limacharlie.sdk.logging_rules module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.logging_rules import LoggingRules


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    return org


@pytest.fixture
def logging_rules(mock_org):
    return LoggingRules(mock_org)


class TestLoggingRulesList:
    def test_list_calls_service_request(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {"rules": {}}
        logging_rules.list()
        mock_org.service_request.assert_called_once_with("logging", {"action": "list_rules"})


class TestLoggingRulesGet:
    def test_get_returns_matching_rule(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {
            "my-log-rule": {"patterns": ["*.log"]},
            "other": {"patterns": ["*.txt"]},
        }
        result = logging_rules.get("my-log-rule")
        assert result == {"patterns": ["*.log"]}

    def test_get_returns_none_when_not_found(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {
            "other": {"patterns": ["*.txt"]},
        }
        result = logging_rules.get("nonexistent")
        assert result is None

    def test_get_returns_none_for_non_dict_response(self, logging_rules, mock_org):
        mock_org.service_request.return_value = "unexpected"
        result = logging_rules.get("my-rule")
        assert result is None


class TestLoggingRulesCreate:
    def test_create_basic(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {}
        logging_rules.create("access-logs", ["/var/log/access.log"])
        mock_org.service_request.assert_called_once_with("logging", {
            "action": "add_rule",
            "name": "access-logs",
            "patterns": ["/var/log/access.log"],
        })

    def test_create_with_tags_and_platforms(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {}
        logging_rules.create("access-logs", ["/var/log/*.log"],
                             tags=["web"], platforms=["linux"])
        mock_org.service_request.assert_called_once_with("logging", {
            "action": "add_rule",
            "name": "access-logs",
            "patterns": ["/var/log/*.log"],
            "tags": ["web"],
            "platforms": ["linux"],
        })

    def test_create_retention_days_becomes_string(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {}
        logging_rules.create("logs", ["*.log"], retention_days=30)
        call_args = mock_org.service_request.call_args
        params = call_args[0][1]
        assert params["days_retention"] == "30"
        assert isinstance(params["days_retention"], str)

    def test_create_delete_after_becomes_true_string(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {}
        logging_rules.create("logs", ["*.log"], retention_days=7, delete_after=True)
        call_args = mock_org.service_request.call_args
        params = call_args[0][1]
        assert params["is_delete_after"] == "true"
        assert params["days_retention"] == "7"

    def test_create_delete_after_false_omits_key(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {}
        logging_rules.create("logs", ["*.log"], delete_after=False)
        call_args = mock_org.service_request.call_args
        params = call_args[0][1]
        assert "is_delete_after" not in params


class TestLoggingRulesDelete:
    def test_delete(self, logging_rules, mock_org):
        mock_org.service_request.return_value = {}
        logging_rules.delete("access-logs")
        mock_org.service_request.assert_called_once_with("logging", {
            "action": "remove_rule",
            "name": "access-logs",
        })
