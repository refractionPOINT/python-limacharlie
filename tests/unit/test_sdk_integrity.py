"""Tests for limacharlie.sdk.integrity module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.integrity import Integrity


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    return org


@pytest.fixture
def integrity(mock_org):
    return Integrity(mock_org)


class TestIntegrityList:
    def test_list_calls_service_request(self, integrity, mock_org):
        mock_org.service_request.return_value = {"rules": {}}
        integrity.list()
        mock_org.service_request.assert_called_once_with("integrity", {"action": "list_rules"})


class TestIntegrityGet:
    def test_get_returns_matching_rule(self, integrity, mock_org):
        mock_org.service_request.return_value = {
            "my-rule": {"patterns": ["/etc/*"]},
            "other-rule": {"patterns": ["/var/*"]},
        }
        result = integrity.get("my-rule")
        assert result == {"patterns": ["/etc/*"]}

    def test_get_returns_none_when_not_found(self, integrity, mock_org):
        mock_org.service_request.return_value = {
            "other-rule": {"patterns": ["/var/*"]},
        }
        result = integrity.get("nonexistent")
        assert result is None

    def test_get_returns_none_for_non_dict_response(self, integrity, mock_org):
        mock_org.service_request.return_value = []
        result = integrity.get("my-rule")
        assert result is None


class TestIntegrityCreate:
    def test_create_basic(self, integrity, mock_org):
        mock_org.service_request.return_value = {}
        integrity.create("my-rule", ["/etc/passwd", "/etc/shadow"])
        mock_org.service_request.assert_called_once_with("integrity", {
            "action": "add_rule",
            "name": "my-rule",
            "patterns": ["/etc/passwd", "/etc/shadow"],
        })

    def test_create_with_tags_and_platforms(self, integrity, mock_org):
        mock_org.service_request.return_value = {}
        integrity.create("my-rule", ["/etc/*"], tags=["server"], platforms=["linux"])
        mock_org.service_request.assert_called_once_with("integrity", {
            "action": "add_rule",
            "name": "my-rule",
            "patterns": ["/etc/*"],
            "tags": ["server"],
            "platforms": ["linux"],
        })


class TestIntegrityDelete:
    def test_delete(self, integrity, mock_org):
        mock_org.service_request.return_value = {}
        integrity.delete("my-rule")
        mock_org.service_request.assert_called_once_with("integrity", {
            "action": "remove_rule",
            "name": "my-rule",
        })
