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
                     RateLimitError, PermissionDeniedError, ApiError, ConfigError]:
            assert issubclass(cls, LimaCharlieError)
            assert issubclass(cls, Exception)


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
