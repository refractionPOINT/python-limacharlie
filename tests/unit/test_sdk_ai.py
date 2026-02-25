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
        assert call_args[1]["params"] == {"query": "detect mimikatz"}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]
        assert "test-oid" not in call_args[0][1]


class TestAIGenerateDetection:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"detect": {}}
        ai.generate_detection("lateral movement")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/detection")
        assert call_args[1]["params"] == {"query": "lateral movement"}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]


class TestAIGenerateResponse:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"respond": {}}
        ai.generate_response("isolate sensor")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/response")
        assert call_args[1]["params"] == {"query": "isolate sensor"}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]


class TestAIGenerateLcql:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"query": ""}
        ai.generate_lcql("find all DNS events")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/lcql")
        assert call_args[1]["params"] == {"query": "find all DNS events"}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]


class TestAIGenerateSensorSelector:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"selector": ""}
        ai.generate_sensor_selector("all windows servers")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/sensor_selector")
        assert call_args[1]["params"] == {"query": "all windows servers"}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]


class TestAIGeneratePlaybook:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"playbook": ""}
        ai.generate_playbook("respond to ransomware")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/playbook/python")
        assert call_args[1]["params"] == {"query": "respond to ransomware"}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]


class TestAISummarizeDetection:
    def test_path_and_body(self, ai, mock_org):
        mock_org.client.request.return_value = {"summary": ""}
        detection = {"cat": "lateral-movement", "detect": {"op": "is"}}
        ai.summarize_detection(detection)
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "ai/det_summary")
        assert call_args[1]["params"] == {"query": json.dumps(detection)}
        assert "raw_body" not in call_args[1]
        assert "content_type" not in call_args[1]
