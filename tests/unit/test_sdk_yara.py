"""Tests for limacharlie.sdk.yara module."""

import json
from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.yara import Yara


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    return org


@pytest.fixture
def yara(mock_org):
    return Yara(mock_org)


class TestYaraScan:
    def test_scan_basic(self, yara, mock_org):
        mock_org.service_request.return_value = {"matches": []}
        yara.scan("abc-sid", "rule test { condition: true }")
        mock_org.service_request.assert_called_once_with("yara", {
            "action": "scan",
            "sid": "abc-sid",
            "rule": "rule test { condition: true }",
        })

    def test_scan_with_timeout(self, yara, mock_org):
        mock_org.service_request.return_value = {"matches": []}
        yara.scan("abc-sid", "rule test { condition: true }", timeout=60)
        mock_org.service_request.assert_called_once_with("yara", {
            "action": "scan",
            "sid": "abc-sid",
            "rule": "rule test { condition: true }",
            "timeout": "60",
        })

    def test_scan_sid_converted_to_str(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        yara.scan(12345, "rule x { condition: true }")
        call_params = mock_org.service_request.call_args[0][1]
        assert call_params["sid"] == "12345"
        assert isinstance(call_params["sid"], str)


class TestYaraListRules:
    def test_list_rules(self, yara, mock_org):
        mock_org.service_request.return_value = {"rules": {}}
        yara.list_rules()
        mock_org.service_request.assert_called_once_with("yara", {"action": "list_rules"})


class TestYaraAddRule:
    def test_add_rule_basic(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        yara.add_rule("detect-malware", ["source1", "source2"])
        call_params = mock_org.service_request.call_args[0][1]
        assert call_params["action"] == "add_rule"
        assert call_params["name"] == "detect-malware"
        assert call_params["sources"] == json.dumps(["source1", "source2"])

    def test_add_rule_sources_are_json_serialized(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        sources = ["src-a", "src-b"]
        yara.add_rule("rule1", sources)
        call_params = mock_org.service_request.call_args[0][1]
        assert call_params["sources"] == '["src-a", "src-b"]'
        assert isinstance(call_params["sources"], str)

    def test_add_rule_with_tags_and_platforms_json_serialized(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        yara.add_rule("rule1", ["src"], tags=["servers"], platforms=["windows", "linux"])
        call_params = mock_org.service_request.call_args[0][1]
        assert call_params["tags"] == json.dumps(["servers"])
        assert call_params["platforms"] == json.dumps(["windows", "linux"])
        assert isinstance(call_params["tags"], str)
        assert isinstance(call_params["platforms"], str)


class TestYaraDeleteRule:
    def test_delete_rule(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        yara.delete_rule("detect-malware")
        mock_org.service_request.assert_called_once_with("yara", {
            "action": "remove_rule",
            "name": "detect-malware",
        })


class TestYaraListSources:
    def test_list_sources(self, yara, mock_org):
        mock_org.service_request.return_value = {"sources": {}}
        yara.list_sources()
        mock_org.service_request.assert_called_once_with("yara", {"action": "list_sources"})


class TestYaraGetSource:
    def test_get_source(self, yara, mock_org):
        mock_org.service_request.return_value = {"source": "rule content"}
        yara.get_source("my-source")
        mock_org.service_request.assert_called_once_with("yara", {
            "action": "get_source",
            "name": "my-source",
        })


class TestYaraAddSource:
    def test_add_source(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        yara.add_source("my-source", "rule detect { condition: true }")
        mock_org.service_request.assert_called_once_with("yara", {
            "action": "add_source",
            "name": "my-source",
            "source": "rule detect { condition: true }",
        })


class TestYaraDeleteSource:
    def test_delete_source(self, yara, mock_org):
        mock_org.service_request.return_value = {}
        yara.delete_source("my-source")
        mock_org.service_request.assert_called_once_with("yara", {
            "action": "remove_source",
            "name": "my-source",
        })
