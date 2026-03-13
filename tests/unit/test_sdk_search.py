"""Tests for limacharlie.sdk.search module.

Tests cover LCQL query execution, validation, and error handling.
All search errors should include query_id, region, and oid for
troubleshooting when available.
"""

import json
import time
from unittest.mock import MagicMock, patch
import pytest

from limacharlie.sdk.search import Search
from limacharlie.errors import SearchError


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.get_urls.return_value = {"search": "search-prod-usa.limacharlie.io"}
    return org


@pytest.fixture
def mock_org_no_region():
    """Org with a search URL that has no extractable region."""
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.get_urls.return_value = {"search": "custom-search.example.com"}
    return org


@pytest.fixture
def search(mock_org):
    return Search(mock_org)


@pytest.fixture
def search_no_region(mock_org_no_region):
    return Search(mock_org_no_region)


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


class TestRegionExtraction:
    """Tests for _extract_region helper."""

    def test_extracts_region_from_standard_url(self, search):
        region = search._extract_region()
        assert region == "prod-usa"

    def test_returns_none_for_non_standard_url(self, search_no_region):
        region = search_no_region._extract_region()
        assert region is None

    def test_extracts_region_from_europe_url(self, mock_org):
        mock_org.get_urls.return_value = {"search": "search-prod-europe.limacharlie.io"}
        s = Search(mock_org)
        assert s._extract_region() == "prod-europe"

    def test_extracts_region_from_dev_url(self, mock_org):
        mock_org.get_urls.return_value = {"search": "search-dev-1.limacharlie.io"}
        s = Search(mock_org)
        assert s._extract_region() == "dev-1"


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


class TestSearchExecuteErrors:
    """Tests for SearchError raising with query_id, region, oid context."""

    def test_no_query_id_raises_search_error(self, search, mock_org):
        """Missing queryId in initiation response raises SearchError."""
        mock_org.client.request.side_effect = [
            {},  # No queryId in response
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "missing queryId" in str(err)
        assert err.region == "prod-usa"
        assert err.oid == "test-oid"
        assert err.query_id is None  # Not available yet

    def test_initiation_error_raises_search_error(self, search, mock_org):
        """Error in initiation response raises SearchError with region and oid."""
        mock_org.client.request.side_effect = [
            {"error": "quota exceeded"},
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "quota exceeded" in str(err)
        assert err.region == "prod-usa"
        assert err.oid == "test-oid"
        assert err.query_id is None

    def test_poll_error_raises_search_error_with_query_id(self, search, mock_org):
        """Error during polling raises SearchError with full context."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-fail-123"},
            {"error": "context canceled"},
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "context canceled" in str(err)
        assert err.query_id == "q-fail-123"
        assert err.region == "prod-usa"
        assert err.oid == "test-oid"

    def test_unexpected_exception_wrapped_in_search_error(self, search, mock_org):
        """Generic exceptions during polling are wrapped in SearchError."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-exc-456"},
            RuntimeError("connection reset"),
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "connection reset" in str(err)
        assert err.query_id == "q-exc-456"
        assert err.region == "prod-usa"
        assert err.oid == "test-oid"
        # Original exception is chained
        assert isinstance(err.__cause__, RuntimeError)

    def test_error_without_extractable_region(self, search_no_region, mock_org_no_region):
        """SearchError gracefully handles non-extractable region."""
        mock_org_no_region.client.request.side_effect = [
            {"error": "something broke"},
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search_no_region.execute("event", 1000, 2000))
        err = exc_info.value
        assert err.region is None
        assert err.oid == "test-oid"
        assert "region=" not in str(err).split("\n")[0]

    def test_query_id_response_key_fallback(self, search, mock_org):
        """Supports both 'queryId' and 'query_id' response keys."""
        mock_org.client.request.side_effect = [
            {"query_id": "q-snake-case"},
            {"results": [{"a": 1}], "completed": True},
            {},  # DELETE cleanup
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 1

    def test_cleanup_called_on_error(self, search, mock_org):
        """DELETE cleanup is attempted even when search fails."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-cleanup"},
            {"error": "something failed"},
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError):
            list(search.execute("event", 1000, 2000))

        # Verify DELETE was called for cleanup
        delete_calls = [c for c in mock_org.client.request.call_args_list if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1
        assert "search/q-cleanup" in delete_calls[0][0][1]

    def test_cleanup_failure_does_not_mask_original_error(self, search, mock_org):
        """If DELETE cleanup itself fails, the original SearchError is raised."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-cleanup-fail"},
            {"error": "original error"},
            Exception("cleanup failed"),  # DELETE fails
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        assert "original error" in str(exc_info.value)

    def test_initiation_transport_exception_wrapped_in_search_error(self, search, mock_org):
        """Transport exceptions during initiation are wrapped in SearchError
        with region/oid context for troubleshooting."""
        mock_org.client.request.side_effect = ConnectionError("network down")
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "network down" in str(err)
        assert err.region == "prod-usa"
        assert err.oid == "test-oid"
        assert err.query_id is None  # Never got a query_id
        assert isinstance(err.__cause__, ConnectionError)
        # Only one request (the failed POST), no DELETE
        assert mock_org.client.request.call_count == 1

    def test_initiation_auth_error_wrapped_in_search_error(self, search, mock_org):
        """AuthenticationError during initiation is wrapped with context."""
        from limacharlie.errors import AuthenticationError
        mock_org.client.request.side_effect = AuthenticationError("JWT expired")
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "JWT expired" in str(err)
        assert err.region == "prod-usa"
        assert err.oid == "test-oid"

    def test_poll_error_includes_context_in_message(self, search, mock_org):
        """Error message includes bracket-formatted context."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-ctx"},
            {"error": "timeout"},
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        msg = str(exc_info.value).split("\n")[0]
        assert "[query_id=q-ctx, region=prod-usa, oid=test-oid]" in msg
