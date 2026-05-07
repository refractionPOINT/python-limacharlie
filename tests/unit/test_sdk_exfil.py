"""Tests for limacharlie.sdk.exfil module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.exfil import Exfil


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    return org


@pytest.fixture
def exfil(mock_org):
    return Exfil(mock_org)


class TestExfilList:
    def test_list_calls_service_request(self, exfil, mock_org):
        mock_org.service_request.return_value = {"rules": {}}
        exfil.list()
        mock_org.service_request.assert_called_once_with("exfil", {"action": "list_rules"})


class TestExfilCreateWatch:
    def test_create_watch_basic(self, exfil, mock_org):
        mock_org.service_request.return_value = {}
        exfil.create_watch("dns-watch", "DNS_REQUEST", "evil.com", "ends with", "event/DOMAIN_NAME")
        mock_org.service_request.assert_called_once_with("exfil", {
            "action": "add_watch",
            "name": "dns-watch",
            "event": "DNS_REQUEST",
            "value": "evil.com",
            "operator": "ends with",
            "path": ["event", "DOMAIN_NAME"],
        })

    def test_create_watch_with_tags_and_platforms(self, exfil, mock_org):
        mock_org.service_request.return_value = {}
        exfil.create_watch("dns-watch", "DNS_REQUEST", "evil.com", "ends with",
                           "event/DOMAIN_NAME", tags=["prod"], platforms=["windows"])
        mock_org.service_request.assert_called_once_with("exfil", {
            "action": "add_watch",
            "name": "dns-watch",
            "event": "DNS_REQUEST",
            "value": "evil.com",
            "operator": "ends with",
            "path": ["event", "DOMAIN_NAME"],
            "tags": ["prod"],
            "platforms": ["windows"],
        })


class TestExfilCreateEvent:
    def test_create_event_basic(self, exfil, mock_org):
        mock_org.service_request.return_value = {}
        exfil.create_event("net-events", ["NEW_TCP4_CONNECTION", "NEW_UDP4_CONNECTION"])
        mock_org.service_request.assert_called_once_with("exfil", {
            "action": "add_event_rule",
            "name": "net-events",
            "events": ["NEW_TCP4_CONNECTION", "NEW_UDP4_CONNECTION"],
        })

    def test_create_event_with_tags_and_platforms(self, exfil, mock_org):
        mock_org.service_request.return_value = {}
        exfil.create_event("net-events", ["NEW_TCP4_CONNECTION"],
                           tags=["servers"], platforms=["linux"])
        mock_org.service_request.assert_called_once_with("exfil", {
            "action": "add_event_rule",
            "name": "net-events",
            "events": ["NEW_TCP4_CONNECTION"],
            "tags": ["servers"],
            "platforms": ["linux"],
        })


class TestExfilDeleteEvent:
    def test_delete_event(self, exfil, mock_org):
        mock_org.service_request.return_value = {}
        exfil.delete_event("net-events")
        mock_org.service_request.assert_called_once_with("exfil", {
            "action": "remove_event_rule",
            "name": "net-events",
        })


class TestExfilDeleteWatch:
    def test_delete_watch(self, exfil, mock_org):
        mock_org.service_request.return_value = {}
        exfil.delete_watch("dns-watch")
        mock_org.service_request.assert_called_once_with("exfil", {
            "action": "remove_watch",
            "name": "dns-watch",
        })
