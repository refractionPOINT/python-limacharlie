"""Tests for limacharlie.sdk.search module."""

import json
import time
from unittest.mock import MagicMock, patch
import pytest

from limacharlie.sdk.search import Search


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.get_urls.return_value = {"search": "search.lc.io"}
    return org


@pytest.fixture
def search(mock_org):
    return Search(mock_org)


class TestSearchInit:
    def test_init(self, mock_org):
        s = Search(mock_org)
        assert s._search_url is None


class TestSearchValidate:
    def test_validate_basic(self, search, mock_org):
        mock_org.client.request.return_value = {"valid": True}
        result = search.validate("event | limit 10")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "search/validate" in call_args[0][1]
        body = json.loads(call_args[1]["raw_body"])
        assert body["query"] == "event | limit 10"
        assert result["valid"] is True

    def test_validate_with_times(self, search, mock_org):
        search.validate("event", start_time=1000, end_time=2000)
        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["startTime"] == "1000"
        assert body["endTime"] == "2000"
        assert body["oid"] == "test-oid"


class TestSearchExecute:
    def test_execute_paginated(self, search, mock_org):
        # First call: initiate search returns queryId
        # Second call: poll returns results + completed
        mock_org.client.request.side_effect = [
            {"queryId": "q-123"},
            {"results": [{"event_type": "NEW_PROCESS"}, {"event_type": "DNS_REQUEST"}], "completed": True},
            {},  # DELETE cleanup
        ]

        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 2
        assert results[0]["event_type"] == "NEW_PROCESS"

    def test_execute_with_limit(self, search, mock_org):
        mock_org.client.request.side_effect = [
            {"queryId": "q-456"},
            {"results": [{"a": 1}, {"a": 2}, {"a": 3}], "completed": False},
            {},  # DELETE cleanup
        ]

        results = list(search.execute("event", 1000, 2000, limit=2))
        assert len(results) == 2

    def test_execute_no_query_id(self, search, mock_org):
        mock_org.client.request.return_value = {}
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 0

    def test_execute_multi_page(self, search, mock_org):
        mock_org.client.request.side_effect = [
            {"queryId": "q-789"},
            {"results": [{"a": 1}], "completed": False, "nextToken": "tok1"},
            {"results": [{"a": 2}], "completed": True},
            {},  # DELETE cleanup
        ]

        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 2
