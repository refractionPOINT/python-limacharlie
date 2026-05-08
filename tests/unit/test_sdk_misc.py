"""Tests for misc SDK modules: ARL, USP, Downloads.

All other test classes have been moved to dedicated per-module test files.
"""

import json
from unittest.mock import MagicMock
import pytest


# Fixtures
@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


# --- USP ---
class TestUSP:
    def test_validate(self, mock_org):
        from limacharlie.sdk.usp import USP
        u = USP(mock_org)
        u.validate("text", mapping={"key": "val"})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "usp/validate/test-oid"
        body = json.loads(call_args[1]["raw_body"])
        assert body["platform"] == "text"
        assert body["mapping"] == {"key": "val"}

    def test_validate_with_json_input(self, mock_org):
        from limacharlie.sdk.usp import USP
        u = USP(mock_org)
        u.validate("json", json_input={"event": "test"}, hostname="myhost")
        call_args = mock_org.client.request.call_args
        body = json.loads(call_args[1]["raw_body"])
        assert body["json_input"] == [{"event": "test"}]
        assert body["hostname"] == "myhost"

    def test_validate_with_text_input(self, mock_org):
        from limacharlie.sdk.usp import USP
        u = USP(mock_org)
        u.validate("syslog", text_input="<14>test message")
        call_args = mock_org.client.request.call_args
        body = json.loads(call_args[1]["raw_body"])
        assert body["text_input"] == "<14>test message"

    def test_validate_with_mappings_list(self, mock_org):
        from limacharlie.sdk.usp import USP
        u = USP(mock_org)
        u.validate("text", mappings=[{"key": "a"}, {"key": "b"}])
        call_args = mock_org.client.request.call_args
        body = json.loads(call_args[1]["raw_body"])
        assert body["mappings"] == [{"key": "a"}, {"key": "b"}]

    def test_validate_with_indexing(self, mock_org):
        from limacharlie.sdk.usp import USP
        u = USP(mock_org)
        u.validate("text", indexing={"type": "custom"})
        call_args = mock_org.client.request.call_args
        body = json.loads(call_args[1]["raw_body"])
        assert body["indexing"] == {"type": "custom"}


# --- ARL ---
class TestARL:
    def test_get(self, mock_org):
        from limacharlie.sdk.arl import ARL
        a = ARL(mock_org)
        mock_org.client.request.return_value = {"data": "resolved"}
        a.get("arl://my-resource")
        mock_org.client.request.assert_called_once_with(
            "GET", "arl/test-oid", query_params={"arl": "arl://my-resource"}
        )


# --- Downloads ---
class TestDownloads:
    def test_list_sensor_targets(self):
        from limacharlie.sdk.downloads import list_sensor_targets, SENSOR_TARGETS
        targets = list_sensor_targets()
        assert len(targets) == len(SENSOR_TARGETS)
        for t in targets:
            assert "platform" in t
            assert "arch" in t
            assert "url" in t
            assert t["url"].startswith("https://downloads.limacharlie.io/")

    def test_list_adapter_targets(self):
        from limacharlie.sdk.downloads import list_adapter_targets, ADAPTER_TARGETS
        targets = list_adapter_targets()
        assert len(targets) == len(ADAPTER_TARGETS)

    def test_download_binary_invalid_target(self):
        from limacharlie.sdk.downloads import download_binary
        with pytest.raises(ValueError, match="Unknown sensor target"):
            download_binary("sensor", "nonexistent", "z80")
