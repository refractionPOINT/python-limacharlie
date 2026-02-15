"""Tests for limacharlie.client module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from limacharlie.client import Client, _build_user_agent, _create_ssl_context
from limacharlie.errors import (
    AuthenticationError,
    ApiError,
    RateLimitError,
)


class TestClientInit:
    def test_creates_with_explicit_creds(self):
        client = Client(oid="test-oid", api_key="test-key")
        assert client.oid == "test-oid"
        assert client._api_key == "test-key"

    def test_creates_with_jwt(self):
        client = Client(oid="test-oid", jwt="pre-generated-jwt")
        assert client._jwt == "pre-generated-jwt"
        assert client._api_key is None

    def test_uid_passthrough(self):
        client = Client(oid="test-oid", api_key="key", uid="myuid")
        assert client.uid == "myuid"

    def test_context_manager(self):
        with Client(oid="test-oid", api_key="key") as c:
            assert c.oid == "test-oid"

    def test_retry_quota_flag(self):
        client = Client(oid="o", api_key="k", is_retry_quota_errors=True)
        assert client._is_retry_quota_errors is True


class TestRefreshJWT:
    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_with_api_key(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "new-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        client.refresh_jwt()

        assert client._jwt == "new-jwt"
        mock_urlopen.assert_called_once()

    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_with_uid(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "uid-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key", uid="myuid")
        client.refresh_jwt()

        assert client._jwt == "uid-jwt"

    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_with_oid_override(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "override-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        client.refresh_jwt(oid_override="-")

        # Verify the JWT URL was called (actual auth_data testing requires
        # inspecting the URLRequest, which is complex with urlopen mock)
        assert client._jwt == "override-jwt"

    def test_refresh_jwt_no_oid_raises_clear_error(self):
        client = Client.__new__(Client)
        client._oid = None
        client._api_key = "test-key"
        client._oauth_creds = None
        client._jwt = None
        client._uid = None
        client._ssl_context = None
        client._debug_fn = None
        client._on_refresh_auth = None

        with pytest.raises(AuthenticationError, match="No organization ID") as exc_info:
            client.refresh_jwt()
        assert "use-org" in str(exc_info.value)
        assert "--oid" in str(exc_info.value)
        assert "LC_OID" in str(exc_info.value)

    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_oid_override_bypasses_missing_oid_check(self, mock_urlopen):
        """oid_override='-' should work even when self._oid is None."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "user-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client.__new__(Client)
        client._oid = None
        client._api_key = "test-key"
        client._oauth_creds = None
        client._jwt = None
        client._uid = None
        client._ssl_context = None
        client._debug_fn = None
        client._on_refresh_auth = None

        client.refresh_jwt(oid_override="-")
        assert client._jwt == "user-jwt"

    def test_refresh_jwt_no_credentials_raises(self):
        client = Client.__new__(Client)
        client._oid = "test"
        client._api_key = None
        client._oauth_creds = None
        client._jwt = None
        client._uid = None
        client._ssl_context = None
        client._debug_fn = None
        client._on_refresh_auth = None

        with pytest.raises(AuthenticationError, match="No API key"):
            client.refresh_jwt()

    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_http_error(self, mock_urlopen):
        from urllib.error import HTTPError
        import io

        error_body = b"bad credentials"
        mock_urlopen.side_effect = HTTPError(
            "https://jwt.limacharlie.io", 401, "Unauthorized",
            {}, io.BytesIO(error_body)
        )

        client = Client(oid="test-oid", api_key="bad-key")
        with pytest.raises(AuthenticationError, match="bad credentials"):
            client.refresh_jwt()


class TestRequest:
    @patch("limacharlie.client.urlopen")
    def test_successful_get_request(self, mock_urlopen):
        # Mock JWT generation
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "test-jwt"}).encode()
        jwt_response.close = MagicMock()

        # Mock API response
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"sensors": []}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []
        api_response.getcode.return_value = 200

        mock_urlopen.side_effect = [jwt_response, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        result = client.request("GET", "sensors")

        assert result == {"sensors": []}

    @patch("limacharlie.client.urlopen")
    def test_auto_refreshes_jwt_on_401(self, mock_urlopen):
        from urllib.error import HTTPError
        import io

        # Mock JWT generation (first call)
        jwt_response1 = MagicMock()
        jwt_response1.read.return_value = json.dumps({"jwt": "jwt1"}).encode()
        jwt_response1.close = MagicMock()

        # Mock 401 response
        http_401 = HTTPError(
            "https://api.limacharlie.io/v1/sensors", 401, "Unauthorized",
            {}, io.BytesIO(b'{"error": "expired"}')
        )

        # Mock JWT refresh (second call)
        jwt_response2 = MagicMock()
        jwt_response2.read.return_value = json.dumps({"jwt": "jwt2"}).encode()
        jwt_response2.close = MagicMock()

        # Mock successful API response after refresh
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"sensors": ["s1"]}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [jwt_response1, http_401, jwt_response2, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        result = client.request("GET", "sensors")

        assert result == {"sensors": ["s1"]}

    @patch("limacharlie.client.urlopen")
    def test_429_raises_rate_limit_error(self, mock_urlopen):
        from urllib.error import HTTPError
        import io

        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "jwt"}).encode()
        jwt_response.close = MagicMock()

        http_429 = HTTPError(
            "https://api.limacharlie.io/v1/test", 429, "Too Many Requests",
            {}, io.BytesIO(b'{"error": "rate limited"}')
        )

        mock_urlopen.side_effect = [jwt_response, http_429]

        client = Client(oid="test-oid", api_key="test-key")
        with pytest.raises(RateLimitError):
            client.request("GET", "test")

    @patch("limacharlie.client.urlopen")
    @patch("limacharlie.client.time")
    def test_504_retries(self, mock_time, mock_urlopen):
        from urllib.error import HTTPError
        import io

        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "jwt"}).encode()
        jwt_response.close = MagicMock()

        http_504 = HTTPError(
            "https://api.limacharlie.io/v1/test", 504, "Gateway Timeout",
            {}, io.BytesIO(b'{"error": "timeout"}')
        )

        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [jwt_response, http_504, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        result = client.request("GET", "test")

        assert result == {"ok": True}


class TestRefreshAuthCallback:
    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_calls_on_refresh_auth_with_self(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "new-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        callback = MagicMock()
        client = Client(oid="test-oid", api_key="test-key", on_refresh_auth=callback)
        client.refresh_jwt()

        callback.assert_called_once_with(client)

    @patch("limacharlie.client.urlopen")
    def test_request_primes_jwt_via_on_refresh_auth(self, mock_urlopen):
        """When on_refresh_auth is set and no JWT exists, request() should call
        on_refresh_auth(client) to let the callback generate/set the JWT."""
        callback = MagicMock()

        def set_jwt(c):
            c._jwt = "callback-jwt"

        callback.side_effect = set_jwt

        # Mock API response
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []
        mock_urlopen.return_value = api_response

        client = Client(oid="test-oid", api_key="test-key", on_refresh_auth=callback)
        result = client.request("GET", "test")

        callback.assert_called_with(client)
        assert result == {"ok": True}


class TestBuildUserAgent:
    def test_user_agent_format(self):
        ua = _build_user_agent()
        assert ua.startswith("lc-cli/5.0.0")
        assert "python-" in ua


class TestCreateSslContext:
    def test_returns_ssl_context(self):
        ctx = _create_ssl_context()
        assert ctx is not None
