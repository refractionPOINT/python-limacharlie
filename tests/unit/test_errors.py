"""Tests for limacharlie.errors module."""

import pytest
from limacharlie.errors import (
    LimaCharlieError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
    RateLimitError,
    PermissionDeniedError,
    ApiError,
    ConfigError,
    SearchError,
    error_from_status_code,
)


class TestErrorHierarchy:
    def test_base_error_has_exit_code(self):
        err = LimaCharlieError("test")
        assert err.exit_code == 1

    def test_base_error_with_suggestion(self):
        err = LimaCharlieError("failed", suggestion="try again")
        assert "failed" in str(err)
        assert "Suggestion: try again" in str(err)
        assert err.suggestion == "try again"

    def test_base_error_without_suggestion(self):
        err = LimaCharlieError("just failed")
        assert str(err) == "just failed"
        assert err.suggestion is None

    def test_raw_message_strips_suggestion(self):
        err = LimaCharlieError("msg", suggestion="hint")
        assert err.raw_message == "msg"

    def test_auth_error_exit_code(self):
        err = AuthenticationError("bad key")
        assert err.exit_code == 2
        assert err.suggestion is not None  # has default suggestion

    def test_auth_error_custom_suggestion(self):
        err = AuthenticationError("bad key", suggestion="custom")
        assert "custom" in str(err)

    def test_not_found_error_exit_code(self):
        err = NotFoundError("no such rule")
        assert err.exit_code == 3
        assert err.status_code == 404

    def test_validation_error_exit_code(self):
        err = ValidationError("bad input")
        assert err.exit_code == 4

    def test_rate_limit_error_exit_code(self):
        err = RateLimitError()
        assert err.exit_code == 5
        assert err.status_code == 429

    def test_rate_limit_with_retry_after(self):
        err = RateLimitError(retry_after=10)
        assert err.retry_after == 10
        assert "10 seconds" in str(err)

    def test_permission_denied_with_missing_perms(self):
        err = PermissionDeniedError("denied", missing_permissions=["dr.set", "sensor.task"])
        assert err.exit_code == 2
        assert err.missing_permissions == ["dr.set", "sensor.task"]
        assert "dr.set" in str(err)

    def test_api_error_with_response_body(self):
        err = ApiError("server error", status_code=500, response_body={"error": "internal"})
        assert err.response_body == {"error": "internal"}
        assert err.status_code == 500

    def test_config_error(self):
        err = ConfigError("no config file")
        assert err.exit_code == 1
        assert "login" in str(err)  # default suggestion mentions login

    def test_all_errors_inherit_from_base(self):
        for cls in [AuthenticationError, NotFoundError, ValidationError,
                     RateLimitError, PermissionDeniedError, ApiError, ConfigError,
                     SearchError]:
            assert issubclass(cls, LimaCharlieError)
            assert issubclass(cls, Exception)


class TestSearchError:
    """Tests for SearchError with query_id, region, and oid context."""

    def test_all_context_fields(self):
        """All context fields are included in the error message."""
        err = SearchError(
            "search failed",
            query_id="q-abc-123",
            region="9157798c50af372c",
            oid="oid-xyz",
            query="event | limit 10",
        )
        msg = str(err)
        assert "search failed" in msg
        assert "query_id=q-abc-123" in msg
        assert "region=9157798c50af372c" in msg
        assert "oid=oid-xyz" in msg
        assert "query=event | limit 10" in msg
        assert err.query_id == "q-abc-123"
        assert err.region == "9157798c50af372c"
        assert err.oid == "oid-xyz"
        assert err.query == "event | limit 10"

    def test_no_context_fields(self):
        """Works gracefully when no context fields are provided."""
        err = SearchError("search failed")
        msg = str(err)
        assert msg.startswith("search failed")
        # No brackets should appear when there's no context
        assert "[" not in msg.split("\n")[0] or "Suggestion" in msg
        assert err.query_id is None
        assert err.region is None
        assert err.oid is None
        assert err.query is None

    def test_partial_context_only_query_id(self):
        """Only query_id provided."""
        err = SearchError("failed", query_id="q-123")
        msg = str(err)
        assert "query_id=q-123" in msg
        assert "region=" not in msg
        assert "oid=" not in msg

    def test_partial_context_only_region(self):
        """Only region provided."""
        err = SearchError("failed", region="9157798c50af372c")
        msg = str(err)
        assert "region=9157798c50af372c" in msg
        assert "query_id=" not in msg

    def test_partial_context_only_oid(self):
        """Only oid provided."""
        err = SearchError("failed", oid="oid-abc")
        msg = str(err)
        assert "oid=oid-abc" in msg
        assert "query_id=" not in msg
        assert "region=" not in msg

    def test_partial_context_region_and_oid_no_query_id(self):
        """Region and oid but no query_id - typical initiation failure."""
        err = SearchError("initiation failed", region="9157798c50af372c", oid="oid-abc")
        msg = str(err)
        assert "region=9157798c50af372c" in msg
        assert "oid=oid-abc" in msg
        assert "query_id=" not in msg

    def test_query_string_included(self):
        """Query string is included in context when provided."""
        err = SearchError("failed", query="event | limit 10")
        msg = str(err).split("\n")[0]
        assert "query=event | limit 10" in msg
        assert err.query == "event | limit 10"

    def test_long_query_truncated(self):
        """Queries longer than 120 chars are truncated in the message."""
        long_query = "event | " + "a" * 200
        err = SearchError("failed", query=long_query)
        msg = str(err).split("\n")[0]
        # The display version should be truncated with "..."
        assert "..." in msg
        # But the stored query attribute is the full string
        assert err.query == long_query
        assert len(long_query) > 120

    def test_exit_code(self):
        err = SearchError("failed")
        assert err.exit_code == 1

    def test_default_suggestion(self):
        """Default suggestion mentions query_id for troubleshooting."""
        err = SearchError("failed", query_id="q-123")
        assert err.suggestion is not None
        assert "query_id" in err.suggestion

    def test_token_expiry_suggestion_on_401(self):
        """401-related errors get a token expiry suggestion."""
        err = SearchError("authentication failed: HTTP 401")
        assert "--token-expiry" in err.suggestion
        assert "search_token_expiry_hours" in err.suggestion

    def test_token_expiry_suggestion_on_unauthorized(self):
        """Unauthorized keyword triggers token expiry suggestion."""
        err = SearchError("search failed: unauthorized access")
        assert "--token-expiry" in err.suggestion

    def test_token_expiry_suggestion_on_jwt_expired(self):
        """JWT expired keyword triggers token expiry suggestion."""
        err = SearchError("search failed: JWT expired during execution")
        assert "--token-expiry" in err.suggestion

    def test_token_expiry_suggestion_on_server_401_message(self):
        """Server-side 401 message triggers helpful client-side suggestion."""
        err = SearchError(
            "authentication failed: your API token expired during query execution (HTTP 401). "
            "Use a longer-lived token for large time range queries."
        )
        assert "--token-expiry" in err.suggestion
        assert "search_token_expiry_hours" in err.suggestion

    def test_custom_suggestion(self):
        """Custom suggestion overrides automatic detection."""
        err = SearchError("HTTP 401 unauthorized", suggestion="try again later")
        assert err.suggestion == "try again later"

    def test_inherits_from_base(self):
        err = SearchError("failed")
        assert isinstance(err, LimaCharlieError)
        assert isinstance(err, Exception)

    def test_can_be_caught_as_base(self):
        """SearchError can be caught as LimaCharlieError."""
        with pytest.raises(LimaCharlieError):
            raise SearchError("failed", query_id="q-1")

    def test_context_bracket_format(self):
        """Context is enclosed in square brackets after the message."""
        err = SearchError("msg", query_id="q-1", region="r", oid="o", query="event")
        msg = str(err).split("\n")[0]  # First line only (before suggestion)
        assert msg == "msg [query_id=q-1, region=r, oid=o, query=event]"

    def test_empty_string_fields_not_included(self):
        """Empty strings for context fields are treated as falsy."""
        err = SearchError("failed", query_id="", region="", oid="", query="")
        msg = str(err).split("\n")[0]
        assert "[" not in msg


class TestErrorFromStatusCode:
    def test_401_returns_auth_error(self):
        err = error_from_status_code(401, "unauthorized")
        assert isinstance(err, AuthenticationError)

    def test_403_returns_permission_error(self):
        err = error_from_status_code(403, "forbidden")
        assert isinstance(err, PermissionDeniedError)

    def test_404_returns_not_found(self):
        err = error_from_status_code(404, "not found")
        assert isinstance(err, NotFoundError)

    def test_422_returns_validation_error(self):
        err = error_from_status_code(422, "bad request")
        assert isinstance(err, ValidationError)

    def test_429_returns_rate_limit(self):
        err = error_from_status_code(429, "too many requests")
        assert isinstance(err, RateLimitError)

    def test_500_returns_api_error(self):
        err = error_from_status_code(500, "internal error")
        assert isinstance(err, ApiError)

    def test_unknown_code_returns_api_error(self):
        err = error_from_status_code(502, "bad gateway")
        assert isinstance(err, ApiError)
