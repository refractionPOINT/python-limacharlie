"""Tests for limacharlie.sdk.ai module."""

import json
from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.ai import AI


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def ai(mock_org):
    return AI(mock_org)


class TestAIGenerateDrRule:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"rule": {}}
        ai.generate_dr_rule("detect mimikatz")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/dr")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "detect mimikatz"
        assert "description" not in body
        assert call_args[1]["content_type"] == "application/json"
        assert "test-oid" not in call_args[0][1]


class TestAIGenerateDetection:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"detect": {}}
        ai.generate_detection("lateral movement")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/detection")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "lateral movement"
        assert "description" not in body
        assert call_args[1]["content_type"] == "application/json"


class TestAIGenerateResponse:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"respond": {}}
        ai.generate_response("isolate sensor")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/response")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "isolate sensor"
        assert call_args[1]["content_type"] == "application/json"


class TestAIGenerateLcql:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"query": ""}
        ai.generate_lcql("find all DNS events")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/lcql")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "find all DNS events"
        assert call_args[1]["content_type"] == "application/json"


class TestAIGenerateSensorSelector:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"selector": ""}
        ai.generate_sensor_selector("all windows servers")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/sensor_selector")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "all windows servers"
        assert call_args[1]["content_type"] == "application/json"


class TestAIGeneratePlaybook:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"playbook": ""}
        ai.generate_playbook("respond to ransomware")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/playbook/python")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "respond to ransomware"
        assert call_args[1]["content_type"] == "application/json"


class TestAISummarizeDetection:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"summary": ""}
        detection = {"cat": "lateral-movement", "detect": {"op": "is"}}
        ai.summarize_detection(detection)
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/det_summary")
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == json.dumps(detection)
        assert call_args[1]["content_type"] == "application/json"
