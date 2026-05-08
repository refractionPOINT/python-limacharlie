"""Tests for limacharlie.sdk.search module.

Tests cover LCQL query execution, validation, error handling, and
poll retry logic for transient errors.
All search errors should include query_id, region, oid, and query
for troubleshooting when available.
"""

import json
import ssl
import time
from unittest.mock import MagicMock, patch, call
import pytest

from limacharlie.sdk.search import Search, _is_transient_poll_error
from limacharlie.errors import (
    ApiError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SearchError,
    ValidationError,
)


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.get_urls.return_value = {"search": "9157798c50af372c.replay-search.limacharlie.io"}
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
    """Tests for _extract_region helper.

    Real search URLs look like:
        https://9157798c50af372c.replay-search.limacharlie.io/v1/search/
    The region identifier is the hex hash prefix.
    """

    def test_extracts_region_from_standard_url(self, search):
        region = search._extract_region()
        assert region == "9157798c50af372c"

    def test_returns_none_for_non_standard_url(self, search_no_region):
        region = search_no_region._extract_region()
        assert region is None

    def test_extracts_region_from_different_hash(self, mock_org):
        mock_org.get_urls.return_value = {"search": "abc123def456.replay-search.limacharlie.io"}
        s = Search(mock_org)
        assert s._extract_region() == "abc123def456"

    def test_extracts_region_with_https_prefix(self, mock_org):
        mock_org.get_urls.return_value = {"search": "https://deadbeef01234567.replay-search.limacharlie.io"}
        s = Search(mock_org)
        assert s._extract_region() == "deadbeef01234567"

    def test_returns_none_for_empty_url(self, mock_org):
        """Empty or blank URL does not crash - returns None."""
        mock_org.get_urls.return_value = {"search": ""}
        s = Search(mock_org)
        assert s._extract_region() is None

    def test_returns_none_for_ip_based_url(self, mock_org):
        """IP-based URL has no region - returns None gracefully."""
        mock_org.get_urls.return_value = {"search": "http://10.0.0.1:8080"}
        s = Search(mock_org)
        assert s._extract_region() is None


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
    """Tests for SearchError raising with query_id, region, oid, query context."""

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
        assert err.region == "9157798c50af372c"
        assert err.oid == "test-oid"
        assert err.query_id is None  # Not available yet
        assert err.query == "event"

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
        assert err.region == "9157798c50af372c"
        assert err.oid == "test-oid"
        assert err.query_id is None
        assert err.query == "event"

    def test_poll_error_raises_search_error_with_query_id(self, search, mock_org):
        """Error during polling raises SearchError with full context."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-fail-123"},
            {"error": "context canceled"},
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event | limit 50", 1000, 2000))
        err = exc_info.value
        assert "context canceled" in str(err)
        assert err.query_id == "q-fail-123"
        assert err.region == "9157798c50af372c"
        assert err.oid == "test-oid"
        assert err.query == "event | limit 50"

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
        assert err.region == "9157798c50af372c"
        assert err.oid == "test-oid"
        assert err.query == "event"
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
        with region/oid/query context for troubleshooting."""
        mock_org.client.request.side_effect = ConnectionError("network down")
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        err = exc_info.value
        assert "network down" in str(err)
        assert err.region == "9157798c50af372c"
        assert err.oid == "test-oid"
        assert err.query_id is None  # Never got a query_id
        assert err.query == "event"
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
        assert err.region == "9157798c50af372c"
        assert err.oid == "test-oid"

    def test_poll_error_includes_context_in_message(self, search, mock_org):
        """Error message includes bracket-formatted context including query."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-ctx"},
            {"error": "timeout"},
            {},  # DELETE cleanup
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        msg = str(exc_info.value).split("\n")[0]
        assert "query_id=q-ctx" in msg
        assert "region=9157798c50af372c" in msg
        assert "oid=test-oid" in msg
        assert "query=event" in msg

    def test_error_preserves_full_query_string(self, search, mock_org):
        """The full query string is stored on the error object even if long."""
        long_query = "plat == windows | WEL | " + "a" * 200
        mock_org.client.request.side_effect = [
            {"error": "failed"},
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute(long_query, 1000, 2000))
        err = exc_info.value
        assert err.query == long_query
        # Message should have truncated version
        msg = str(err).split("\n")[0]
        assert "..." in msg


class TestIsTransientPollError:
    """Tests for _is_transient_poll_error classification."""

    def test_api_error_500_is_transient(self):
        assert _is_transient_poll_error(ApiError("fail", status_code=500)) is True

    def test_api_error_502_is_transient(self):
        assert _is_transient_poll_error(ApiError("fail", status_code=502)) is True

    def test_api_error_503_is_transient(self):
        assert _is_transient_poll_error(ApiError("fail", status_code=503)) is True

    def test_api_error_504_is_transient(self):
        assert _is_transient_poll_error(ApiError("fail", status_code=504)) is True

    def test_api_error_400_not_transient(self):
        assert _is_transient_poll_error(ApiError("fail", status_code=400)) is False

    def test_connection_error_is_transient(self):
        assert _is_transient_poll_error(ConnectionError("reset")) is True

    def test_timeout_error_is_transient(self):
        assert _is_transient_poll_error(TimeoutError("timed out")) is True

    def test_ssl_error_is_transient(self):
        assert _is_transient_poll_error(ssl.SSLError("handshake")) is True

    def test_os_error_is_transient(self):
        """Generic OSError (e.g. ECONNRESET) is transient."""
        assert _is_transient_poll_error(OSError("connection reset")) is True

    def test_auth_error_not_transient(self):
        assert _is_transient_poll_error(AuthenticationError("401")) is False

    def test_rate_limit_error_not_transient(self):
        assert _is_transient_poll_error(RateLimitError("429")) is False

    def test_not_found_error_not_transient(self):
        assert _is_transient_poll_error(NotFoundError("404")) is False

    def test_validation_error_not_transient(self):
        assert _is_transient_poll_error(ValidationError("bad input")) is False

    def test_permission_denied_not_transient(self):
        assert _is_transient_poll_error(PermissionDeniedError("403")) is False

    def test_file_not_found_not_transient(self):
        """FileNotFoundError is an OSError subclass but not transient."""
        assert _is_transient_poll_error(FileNotFoundError("no such file")) is False

    def test_permission_error_not_transient(self):
        """PermissionError (OS) is an OSError subclass but not transient."""
        assert _is_transient_poll_error(PermissionError("denied")) is False

    def test_generic_exception_not_transient(self):
        assert _is_transient_poll_error(RuntimeError("unknown")) is False

    def test_value_error_not_transient(self):
        assert _is_transient_poll_error(ValueError("bad value")) is False


class TestSearchPollRetry:
    """Tests for poll retry logic in Search.execute()."""

    @patch("limacharlie.sdk.search.time.sleep")
    def test_transient_5xx_retried_and_succeeds(self, mock_sleep, search, mock_org):
        """Transient 5xx error is retried and succeeds on next attempt."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-retry"},
            # First poll: transient 502
            ApiError("bad gateway", status_code=502),
            # Retry succeeds
            {"results": [{"type": "events", "rows": [{"a": 1}]}], "completed": True},
            {},  # DELETE cleanup
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 1
        # Should have slept once for backoff (2^0 = 1 second)
        mock_sleep.assert_called_once_with(1)

    @patch("limacharlie.sdk.search.time.sleep")
    def test_connection_error_retried(self, mock_sleep, search, mock_org):
        """ConnectionError is retried."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-conn"},
            ConnectionError("reset"),
            {"results": [{"a": 1}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 1

    @patch("limacharlie.sdk.search.time.sleep")
    def test_timeout_error_retried(self, mock_sleep, search, mock_org):
        """TimeoutError is retried."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-timeout"},
            TimeoutError("timed out"),
            {"results": [{"x": 1}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 1

    @patch("limacharlie.sdk.search.time.sleep")
    def test_fatal_error_not_retried(self, mock_sleep, search, mock_org):
        """AuthenticationError (401) is NOT retried - raised immediately."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-auth"},
            AuthenticationError("token expired"),
        ]
        with pytest.raises(SearchError) as exc_info:
            list(search.execute("event", 1000, 2000))
        assert "token expired" in str(exc_info.value)
        # No sleep calls - no retry
        mock_sleep.assert_not_called()

    @patch("limacharlie.sdk.search.time.sleep")
    def test_not_found_not_retried(self, mock_sleep, search, mock_org):
        """NotFoundError (404) is NOT retried."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-404"},
            NotFoundError("query not found"),
        ]
        with pytest.raises(SearchError):
            list(search.execute("event", 1000, 2000))
        mock_sleep.assert_not_called()

    @patch("limacharlie.sdk.search.time.sleep")
    def test_validation_error_not_retried(self, mock_sleep, search, mock_org):
        """ValidationError (422) is NOT retried."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-422"},
            ValidationError("bad query"),
        ]
        with pytest.raises(SearchError):
            list(search.execute("event", 1000, 2000))
        mock_sleep.assert_not_called()

    @patch("limacharlie.sdk.search.time.sleep")
    def test_poll_body_error_not_retried(self, mock_sleep, search, mock_org):
        """Poll response with 'error' key is NOT retried (search-engine error)."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-body-err"},
            {"error": "context canceled"},
            {},  # DELETE
        ]
        with pytest.raises(SearchError, match="context canceled"):
            list(search.execute("event", 1000, 2000))
        # No retries for body errors
        mock_sleep.assert_not_called()

    @patch("limacharlie.sdk.search.time.sleep")
    def test_retries_exhausted_raises(self, mock_sleep, search, mock_org):
        """When all retries are exhausted, the original error is raised."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-exhaust"},
            ApiError("502", status_code=502),
            ApiError("502", status_code=502),
            ApiError("502", status_code=502),
            ApiError("502", status_code=502),  # 4th attempt (3 retries + 1 initial)
        ]
        with pytest.raises(SearchError, match="502"):
            list(search.execute("event", 1000, 2000))
        # Should have slept 3 times (exponential: 1, 2, 4)
        assert mock_sleep.call_count == 3

    @patch("limacharlie.sdk.search.time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep, search, mock_org):
        """Verifies exponential backoff delays: 1s, 2s, 4s."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-backoff"},
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),
            {"results": [{"a": 1}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 1
        assert mock_sleep.call_args_list == [call(1), call(2), call(4)]

    @patch("limacharlie.sdk.search.time.sleep")
    def test_poll_max_retries_parameter(self, mock_sleep, search, mock_org):
        """poll_max_retries=1 limits to one retry attempt."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-max1"},
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),  # Second failure -> exhausted
        ]
        with pytest.raises(SearchError):
            list(search.execute("event", 1000, 2000, poll_max_retries=1))
        # Only 1 sleep (1 retry)
        assert mock_sleep.call_count == 1

    @patch("limacharlie.sdk.search.time.sleep")
    def test_poll_max_retries_zero_disables_retry(self, mock_sleep, search, mock_org):
        """poll_max_retries=0 disables retries entirely."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-no-retry"},
            ApiError("503", status_code=503),
        ]
        with pytest.raises(SearchError):
            list(search.execute("event", 1000, 2000, poll_max_retries=0))
        mock_sleep.assert_not_called()

    @patch("limacharlie.sdk.search.time.sleep")
    def test_retry_reports_progress(self, mock_sleep, search, mock_org):
        """Progress function receives retry status messages."""
        progress_msgs = []
        mock_org.client.request.side_effect = [
            {"queryId": "q-prog"},
            ApiError("502", status_code=502),
            {"results": [{"a": 1}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000,
                                      progress_fn=progress_msgs.append))
        assert any("Retrying poll" in msg for msg in progress_msgs)
        assert any("attempt 2/4" in msg for msg in progress_msgs)

    @patch("limacharlie.sdk.search.time.sleep")
    def test_backoff_capped_at_30_seconds(self, mock_sleep, search, mock_org):
        """Backoff delay is capped at 30 seconds even with many retries."""
        # Use max_retries=6 to get 2^5=32 which should be capped to 30.
        mock_org.client.request.side_effect = [
            {"queryId": "q-cap"},
            *[ApiError("503", status_code=503) for _ in range(6)],
            {"results": [{"a": 1}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000, poll_max_retries=6))
        assert len(results) == 1
        # Backoff sequence: 1, 2, 4, 8, 16, 30 (capped)
        assert mock_sleep.call_args_list == [
            call(1), call(2), call(4), call(8), call(16), call(30),
        ]

    @patch("limacharlie.sdk.search.time.sleep")
    def test_retry_on_second_page_poll(self, mock_sleep, search, mock_org):
        """Transient error on a later page poll is retried correctly."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-page2"},
            # Page 1: success with nextToken
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            # Page 2: transient failure then success
            ApiError("502", status_code=502),
            {"results": [{"type": "events", "rows": [{"b": 2}]}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 2
        assert results[0]["rows"] == [{"a": 1}]
        assert results[1]["rows"] == [{"b": 2}]

    @patch("limacharlie.sdk.search.time.sleep")
    def test_multiple_transient_errors_across_different_polls(self, mock_sleep, search, mock_org):
        """Retry counter resets between poll calls - each poll gets fresh retries."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-multi"},
            # Poll 1: 2 transient failures then success
            ApiError("503", status_code=503),
            ApiError("503", status_code=503),
            {"results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}], "completed": True},
            # Poll 2: 1 transient failure then success
            ApiError("502", status_code=502),
            {"results": [{"type": "events", "rows": [{"b": 2}]}], "completed": True},
            {},  # DELETE
        ]
        results = list(search.execute("event", 1000, 2000))
        assert len(results) == 2
        # 2 sleeps for poll 1 (1s, 2s) + 1 sleep for poll 2 (1s)
        assert mock_sleep.call_count == 3


class TestSearchCancellation:
    """Tests for KeyboardInterrupt handling during search execution.

    Verifies that Ctrl+C always:
    1. Cancels the server-side query (DELETE request)
    2. Re-raises KeyboardInterrupt to the caller
    3. Does not interfere with retry logic
    """

    def test_keyboard_interrupt_during_poll_cancels_query(self, search, mock_org):
        """KeyboardInterrupt during poll triggers server-side cancel."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-cancel"},
            KeyboardInterrupt(),
            {},  # DELETE response
        ]
        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000))

        # Verify DELETE was called to cancel the query on server.
        delete_calls = [c for c in mock_org.client.request.call_args_list
                        if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1
        assert "search/q-cancel" in delete_calls[0][0][1]

    def test_keyboard_interrupt_not_retried(self, search, mock_org):
        """KeyboardInterrupt is never retried - it's not a transient error."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-no-retry-ki"}
            elif call_count == 2:
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = side_effect
        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000))

        # Only 3 calls: POST (initiate), GET (interrupted), DELETE (cancel).
        # No retry attempts.
        assert call_count <= 3

    @patch("limacharlie.sdk.search.time.sleep")
    def test_keyboard_interrupt_during_retry_backoff(self, mock_sleep, search, mock_org):
        """KeyboardInterrupt during retry sleep propagates without catching.

        If sleep raises KeyboardInterrupt (user hits Ctrl+C while waiting
        for retry backoff), the interrupt propagates and the query is canceled.
        """
        mock_sleep.side_effect = KeyboardInterrupt()
        mock_org.client.request.side_effect = [
            {"queryId": "q-sleep-ki"},
            ApiError("503", status_code=503),  # Triggers retry + sleep
            {},  # DELETE
        ]
        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000))

        # DELETE should still be called via the finally block.
        delete_calls = [c for c in mock_org.client.request.call_args_list
                        if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1

    def test_keyboard_interrupt_after_partial_results(self, search, mock_org):
        """KeyboardInterrupt after yielding some results still cancels query."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-partial-ki"}
            elif call_count == 2:
                # Page 1: some results
                return {
                    "results": [{"type": "events", "rows": [{"a": 1}], "nextToken": "tok1"}],
                    "completed": True,
                }
            elif call_count == 3:
                # Page 2 poll: user cancels
                raise KeyboardInterrupt()
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = side_effect

        results = []
        with pytest.raises(KeyboardInterrupt):
            for item in search.execute("event", 1000, 2000):
                results.append(item)

        # Should have gotten page 1 results before interrupt.
        assert len(results) == 1
        assert results[0]["rows"] == [{"a": 1}]

        # Server query should still be canceled.
        delete_calls = [c for c in mock_org.client.request.call_args_list
                        if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1

    def test_keyboard_interrupt_cancel_message_with_progress_fn(self, search, mock_org):
        """Progress function receives cancel message on KeyboardInterrupt."""
        messages = []
        mock_org.client.request.side_effect = [
            {"queryId": "q-cancel-msg"},
            KeyboardInterrupt(),
            {},  # DELETE
        ]
        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000, progress_fn=messages.append))

        # Should have "Running search..." and "Canceling search query..." messages.
        assert any("Canceling" in m for m in messages)

    def test_keyboard_interrupt_no_cancel_message_without_progress_fn(self, search, mock_org):
        """No cancel message when progress_fn is None."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-no-msg"},
            KeyboardInterrupt(),
            {},  # DELETE
        ]
        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000, progress_fn=None))

        # DELETE still called - just no message.
        delete_calls = [c for c in mock_org.client.request.call_args_list
                        if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1

    def test_cancel_delete_failure_does_not_mask_interrupt(self, search, mock_org):
        """If DELETE fails during cancel, KeyboardInterrupt still propagates."""
        mock_org.client.request.side_effect = [
            {"queryId": "q-del-fail"},
            KeyboardInterrupt(),
            Exception("DELETE network error"),  # DELETE also fails
        ]
        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000))

    @patch("limacharlie.sdk.search.time.sleep")
    def test_keyboard_interrupt_during_wait_poll(self, mock_sleep, search, mock_org):
        """KeyboardInterrupt during wait-for-results sleep propagates correctly.

        When completed=False and we sleep for nextPollInMs, a Ctrl+C during
        that sleep should cancel the query.
        """
        call_count = 0

        def request_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"queryId": "q-wait-ki"}
            elif call_count == 2:
                # Not completed yet - will trigger sleep
                return {"results": [], "completed": False, "nextPollInMs": 1000}
            else:
                return {}  # DELETE

        mock_org.client.request.side_effect = request_side_effect
        # sleep() raises KeyboardInterrupt (user presses Ctrl+C while waiting)
        mock_sleep.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            list(search.execute("event", 1000, 2000))

        delete_calls = [c for c in mock_org.client.request.call_args_list
                        if c[0][0] == "DELETE"]
        assert len(delete_calls) == 1
