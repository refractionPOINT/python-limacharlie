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

    @patch("limacharlie.sdk.search.time.sleep")
    def test_execute_polls_until_completed(self, mock_sleep, search, mock_org):
        """Query still processing (completed=False) triggers re-poll."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-789"},
            {"results": [], "completed": False, "nextPollInMs": 500},
            {"results": [{"type": "events", "rows": [{"a": 1}]}], "completed": True},
            {},  # DELETE cleanup
        ]

        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 1
        mock_sleep.assert_called_once_with(0.5)

    @patch("limacharlie.sdk.search.time.sleep")
    def test_execute_pagination_follows_next_token(self, mock_sleep, search, mock_org):
        """When a result has nextToken and completed=True, fetch next page."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-pag"},
            # Page 1: completed with nextToken inside the result
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            # Page 2 subquery not ready yet
            {"results": [], "completed": False, "nextPollInMs": 500},
            # Page 2 ready, no more pages
            {"results": [{"type": "events", "rows": [{"a": 2}]}], "completed": True},
            {},  # DELETE cleanup
        ]

        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 2
        assert results[0]["rows"] == [{"a": 1}]
        assert results[1]["rows"] == [{"a": 2}]

        # Verify the second GET used the pagination token
        get_calls = [c for c in mock_org.client.request.call_args_list if c[0][0] == "GET"]
        assert len(get_calls) == 3  # page1 poll, page2 poll (not ready), page2 poll (ready)
        # First GET: no token
        assert get_calls[0][1].get("query_params") is None
        # Second GET: token from page 1
        assert get_calls[1][1]["query_params"] == {"token": "tok1"}
        # Third GET: same token (re-poll same page)
        assert get_calls[2][1]["query_params"] == {"token": "tok1"}
