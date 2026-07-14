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


@pytest.fixture(autouse=True)
def _isolate_caches(monkeypatch, tmp_path):
    """Isolate JWT cache and config cache for every client test.

    Without this, cached config/JWTs from one test leak into the next.
    """
    import os
    from limacharlie.config import _reset_config_cache
    from limacharlie.jwt_cache import _reset_cache_disabled
    from limacharlie.paths import _reset_path_cache

    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)
    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    monkeypatch.delenv("LC_CREDS_FILE", raising=False)
    monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
    monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
    monkeypatch.delenv("LC_NO_JWT_CACHE", raising=False)
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()
    yield
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


class TestClientInit:
    def test_creates_with_explicit_creds(self):
        client = Client(oid="test-oid", api_key="test-key")
        assert client.oid == "test-oid"
        assert client._api_key == "test-key"

    @patch("limacharlie.client.resolve_credentials", return_value={"oid": "test-oid", "uid": None, "api_key": None, "oauth": None})
    def test_creates_with_jwt(self, mock_creds):
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
    def test_mint_jwt_is_a_pure_mint(self, mock_urlopen):
        # mint_jwt returns a token WITHOUT setting the client's own JWT
        # (request-scoped tokens, e.g. the multi-org fleet token).
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "minted-jwt"}).encode()
        jwt_response.close = MagicMock()
        mock_urlopen.return_value = jwt_response

        client = Client(oid="test-oid", api_key="test-key", uid="test-uid")
        token = client.mint_jwt()

        assert token == "minted-jwt"
        assert client._jwt is None
        # No oid field when omitted (multi-org form for user creds).
        sent_body = mock_urlopen.call_args[0][0].data.decode()
        assert "oid=" not in sent_body
        assert "uid=test-uid" in sent_body

    @patch("limacharlie.client.urlopen")
    def test_mint_jwt_scoped_oid(self, mock_urlopen):
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "minted-jwt"}).encode()
        jwt_response.close = MagicMock()
        mock_urlopen.return_value = jwt_response

        client = Client(oid="test-oid", api_key="test-key", uid="test-uid")
        client.mint_jwt(oid="-")

        sent_body = mock_urlopen.call_args[0][0].data.decode()
        assert "oid=-" in sent_body

    @patch("limacharlie.client.urlopen")
    def test_raw_response_returns_text(self, mock_urlopen):
        # raw_response must return the body as decoded text (CSV exports),
        # not attempt JSON parsing.
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "test-jwt"}).encode()
        jwt_response.close = MagicMock()

        api_response = MagicMock()
        api_response.read.return_value = b"col_a,col_b\n1,2\n"
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [jwt_response, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        result = client.request("GET", "export", raw_response=True)

        assert result == "col_a,col_b\n1,2\n"

    @patch("limacharlie.client.urlopen")
    def test_query_params_sequences_expand_to_repeated_keys(self, mock_urlopen):
        # doseq: a dict-of-lists (or list-of-tuples) must encode as
        # repeated keys, not the Python list repr.
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "test-jwt"}).encode()
        jwt_response.close = MagicMock()

        api_response = MagicMock()
        api_response.read.return_value = json.dumps({}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [jwt_response, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        client.request(
            "GET", "things",
            query_params={"severity": ["HIGH", "LOW"], "q": "prod"},
        )

        sent = mock_urlopen.call_args_list[-1][0][0]
        assert sent.full_url.endswith("?severity=HIGH&severity=LOW&q=prod")

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


class TestJwtCacheIntegration:
    """Tests for JWT disk cache integration in Client."""

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.urlopen")
    def test_cached_jwt_skips_refresh(self, mock_urlopen, mock_get_cached):
        """Client with a valid cached JWT should not call refresh_jwt."""
        mock_get_cached.return_value = "cached-jwt-token"

        # Mock API response (no JWT endpoint call should happen)
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []
        mock_urlopen.return_value = api_response

        client = Client(oid="test-oid", api_key="test-key")
        assert client._jwt == "cached-jwt-token"
        result = client.request("GET", "test")

        assert result == {"ok": True}
        # Only 1 call (the API request), not 2 (JWT + API)
        assert mock_urlopen.call_count == 1

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.urlopen")
    def test_expired_cached_jwt_triggers_refresh(self, mock_urlopen, mock_get_cached):
        """Client with no cached JWT should call refresh_jwt normally."""
        mock_get_cached.return_value = None

        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "fresh-jwt"}).encode()
        jwt_response.close = MagicMock()

        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [jwt_response, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        assert client._jwt is None
        result = client.request("GET", "test")
        assert result == {"ok": True}
        # 2 calls: JWT endpoint + API request
        assert mock_urlopen.call_count == 2

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_writes_to_cache(self, mock_urlopen, mock_get_cached, mock_put):
        """After refresh_jwt(), the new JWT should be written to cache."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "new-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        client.refresh_jwt()

        mock_put.assert_called_once_with("new-jwt", "test-oid", "test-key", None, None)

    @patch("limacharlie.jwt_cache.invalidate_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value="stale-jwt")
    @patch("limacharlie.client.urlopen")
    def test_401_invalidates_cache_before_refresh(self, mock_urlopen, mock_get_cached, mock_invalidate):
        """On 401 retry, the cached JWT should be invalidated before refresh."""
        from urllib.error import HTTPError
        import io

        http_401 = HTTPError(
            "https://api.limacharlie.io/v1/test", 401, "Unauthorized",
            {}, io.BytesIO(b'{"error": "expired"}')
        )
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "refreshed-jwt"}).encode()
        jwt_response.close = MagicMock()
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [http_401, jwt_response, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        result = client.request("GET", "test")

        assert result == {"ok": True}
        mock_invalidate.assert_called_once_with("test-oid", "test-key", None, None)

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    def test_pre_generated_jwt_does_not_consult_cache(self, mock_get_cached):
        """When jwt= param is passed, cache should not be consulted."""
        client = Client(oid="test-oid", jwt="pre-gen-jwt")
        assert client._jwt == "pre-gen-jwt"
        mock_get_cached.assert_not_called()

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_with_expiry_does_not_cache(self, mock_urlopen, mock_get_cached, mock_put):
        """refresh_jwt(expiry=300) should not write to cache."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "short-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        client.refresh_jwt(expiry=300)
        mock_put.assert_not_called()

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.urlopen")
    def test_refresh_jwt_with_oid_override_does_not_cache(self, mock_urlopen, mock_get_cached, mock_put):
        """refresh_jwt(oid_override='-') should not write to cache."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": "override-jwt"}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        client.refresh_jwt(oid_override="-")
        mock_put.assert_not_called()

    @patch("limacharlie.jwt_cache.invalidate_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value="stale-jwt")
    @patch("limacharlie.client.urlopen")
    def test_raw_request_401_invalidates_cache(self, mock_urlopen, mock_get_cached, mock_invalidate):
        """raw_request 401 retry should also invalidate the cache."""
        from urllib.error import HTTPError
        import io

        http_401 = HTTPError(
            "https://api.limacharlie.io/v1/test", 401, "Unauthorized",
            {}, io.BytesIO(b'{"error": "expired"}')
        )
        jwt_response = MagicMock()
        jwt_response.read.return_value = json.dumps({"jwt": "refreshed-jwt"}).encode()
        jwt_response.close = MagicMock()
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []

        mock_urlopen.side_effect = [http_401, jwt_response, api_response]

        client = Client(oid="test-oid", api_key="test-key")
        code, data = client.raw_request("GET", "test")

        assert code == 200
        assert data == {"ok": True}
        mock_invalidate.assert_called_once_with("test-oid", "test-key", None, None)


class TestDualCredsAuthPathSelection:
    """Tests for cache key correctness when both api_key and oauth_creds are set.

    When config has both api_key and oauth credentials, OAuth takes priority
    for auth. The cache lookup/write/invalidation must all use the OAuth
    cache key, not the api_key key.
    """

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.resolve_credentials", return_value={
        "oid": "test-oid", "uid": None,
        "api_key": "test-key",
        "oauth": {"id_token": "id", "refresh_token": "ref"},
    })
    def test_init_uses_oauth_cache_key_when_both_set(self, mock_creds, mock_get_cached):
        """When both api_key and oauth_creds are resolved, init should
        look up cache using OAuth credentials (api_key=None)."""
        mock_get_cached.return_value = None
        Client(oid="test-oid")
        mock_get_cached.assert_called_once_with("test-oid", None,
            {"id_token": "id", "refresh_token": "ref"}, None)

    @patch("limacharlie.jwt_cache.invalidate_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value="stale")
    @patch("limacharlie.client.resolve_credentials", return_value={
        "oid": "test-oid", "uid": None,
        "api_key": "test-key",
        "oauth": {"id_token": "id", "refresh_token": "ref"},
    })
    @patch("limacharlie.client.urlopen")
    def test_401_invalidates_oauth_cache_key_when_both_set(
        self, mock_urlopen, mock_creds, mock_get_cached, mock_invalidate
    ):
        """401 invalidation should use OAuth cache key when both are set."""
        from urllib.error import HTTPError
        import io

        http_401 = HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        jwt_resp = MagicMock()
        jwt_resp.read.return_value = json.dumps({"jwt": "new"}).encode()
        jwt_resp.close = MagicMock()
        api_resp = MagicMock()
        api_resp.read.return_value = json.dumps({"ok": True}).encode()
        api_resp.close = MagicMock()
        api_resp.getheaders.return_value = []

        # Need to mock OAuth manager since oauth path is taken
        with patch("limacharlie.client.Client._refresh_jwt_oauth") as mock_oauth:
            def set_jwt(oid, expiry, oid_override=None):
                # Simulate _refresh_jwt_oauth setting the JWT
                pass
            mock_oauth.side_effect = set_jwt

            mock_urlopen.side_effect = [http_401, api_resp]
            client = Client(oid="test-oid")
            client._jwt = "stale"  # force a value so request proceeds
            try:
                client.request("GET", "test")
            except Exception:
                pass  # may fail since mock_oauth doesn't set jwt

        mock_invalidate.assert_called_once_with(
            "test-oid", None,
            {"id_token": "id", "refresh_token": "ref"}, None
        )


class TestGetJwtCacheReuse:
    """Tests for get_jwt() reusing cached JWTs when TTL is sufficient."""

    @staticmethod
    def _make_jwt(exp):
        """Create a minimal JWT with a given exp for testing."""
        import base64
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        return f"{header.decode()}.{payload.decode()}.{sig.decode()}"

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.urlopen")
    def test_get_jwt_reuses_token_with_sufficient_ttl(self, mock_urlopen, mock_get_cached):
        """If cached JWT has >= requested hours remaining, reuse it."""
        import time
        # Cached JWT expires in 5 hours
        cached_jwt = self._make_jwt(time.time() + 5 * 3600)
        mock_get_cached.return_value = cached_jwt

        client = Client(oid="test-oid", api_key="test-key")
        assert client._jwt == cached_jwt

        # Request 4 hours - cached has 5h remaining, should reuse
        result = client.get_jwt(expiry_hours=4.0)
        assert result == cached_jwt
        # No HTTP call should have been made
        mock_urlopen.assert_not_called()

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.urlopen")
    def test_get_jwt_fetches_new_when_ttl_insufficient(self, mock_urlopen, mock_get_cached):
        """If cached JWT has < requested hours remaining, fetch new one."""
        import time
        # Cached JWT expires in 2 hours
        cached_jwt = self._make_jwt(time.time() + 2 * 3600)
        mock_get_cached.return_value = cached_jwt

        fresh_jwt = self._make_jwt(time.time() + 5 * 3600)
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": fresh_jwt}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        # Request 4 hours - cached has only 2h, must fetch new
        result = client.get_jwt(expiry_hours=4.0)
        assert result == fresh_jwt
        mock_urlopen.assert_called_once()

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.urlopen")
    def test_get_jwt_caches_long_lived_token(self, mock_urlopen, mock_get_cached, mock_put):
        """get_jwt with expiry_hours should cache the resulting long-lived JWT."""
        import time
        fresh_jwt = self._make_jwt(time.time() + 4 * 3600)
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": fresh_jwt}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        client.get_jwt(expiry_hours=4.0)

        # Should have cached the long-lived JWT
        mock_put.assert_called_once_with(
            fresh_jwt, "test-oid", "test-key", None, None
        )

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.urlopen")
    def test_get_jwt_no_expiry_hours_does_not_check_ttl(self, mock_urlopen, mock_get_cached):
        """get_jwt() with no expiry_hours uses default refresh path."""
        import time
        cached_jwt = self._make_jwt(time.time() + 3600)
        mock_get_cached.return_value = cached_jwt

        fresh_jwt = self._make_jwt(time.time() + 3600)
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": fresh_jwt}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        # No expiry_hours - goes through refresh_jwt(expiry=None) which
        # writes to cache via the normal path
        result = client.get_jwt()
        assert result == fresh_jwt
        mock_urlopen.assert_called_once()


class TestGetJwtValidation:
    """Tests for get_jwt() input validation and edge cases."""

    @staticmethod
    def _make_jwt(exp):
        """Create a minimal JWT with a given exp for testing."""
        import base64
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        return f"{header.decode()}.{payload.decode()}.{sig.decode()}"

    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    def test_get_jwt_zero_expiry_raises_validation_error(self, mock_get_cached):
        """get_jwt(expiry_hours=0) should raise ValidationError."""
        from limacharlie.errors import ValidationError

        client = Client(oid="test-oid", api_key="test-key")
        with pytest.raises(ValidationError, match="positive"):
            client.get_jwt(expiry_hours=0)

    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    def test_get_jwt_negative_expiry_raises_validation_error(self, mock_get_cached):
        """get_jwt(expiry_hours=-1) should raise ValidationError."""
        from limacharlie.errors import ValidationError

        client = Client(oid="test-oid", api_key="test-key")
        with pytest.raises(ValidationError, match="positive"):
            client.get_jwt(expiry_hours=-1)

    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.urlopen")
    def test_get_jwt_with_unparseable_cached_jwt_fetches_new(self, mock_urlopen, mock_get_cached):
        """If self._jwt is set to a malformed string (no exp), get_jwt
        should not crash and should fetch a new JWT instead."""
        import time as time_module

        fresh_jwt = self._make_jwt(time_module.time() + 5 * 3600)
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"jwt": fresh_jwt}).encode()
        mock_response.close = MagicMock()
        mock_urlopen.return_value = mock_response

        client = Client(oid="test-oid", api_key="test-key")
        # Set a malformed JWT that has no parseable exp
        client._jwt = "not.a.validjwt"
        result = client.get_jwt(expiry_hours=4.0)
        assert result == fresh_jwt
        mock_urlopen.assert_called_once()


class TestOnRefreshAuthCacheIntegration:
    """Tests for on_refresh_auth callback interaction with JWT cache."""

    @staticmethod
    def _make_jwt(exp):
        """Create a minimal JWT with a given exp for testing."""
        import base64
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        return f"{header.decode()}.{payload.decode()}.{sig.decode()}"

    @patch("limacharlie.jwt_cache.get_cached_jwt")
    @patch("limacharlie.client.urlopen")
    def test_on_refresh_auth_not_called_when_cache_hit(self, mock_urlopen, mock_get_cached):
        """When a valid JWT is loaded from cache, on_refresh_auth should
        NOT be invoked during request() because no JWT refresh is needed."""
        import time as time_module

        cached_jwt = self._make_jwt(time_module.time() + 3600)
        mock_get_cached.return_value = cached_jwt

        callback = MagicMock()

        # Mock API response
        api_response = MagicMock()
        api_response.read.return_value = json.dumps({"ok": True}).encode()
        api_response.close = MagicMock()
        api_response.getheaders.return_value = []
        mock_urlopen.return_value = api_response

        client = Client(oid="test-oid", api_key="test-key", on_refresh_auth=callback)
        assert client._jwt == cached_jwt

        result = client.request("GET", "test")
        assert result == {"ok": True}
        # The callback should NOT have been called since JWT was already set
        callback.assert_not_called()
        # Only 1 HTTP call (the API request), no JWT endpoint call
        assert mock_urlopen.call_count == 1


class TestBuildUserAgent:
    def test_user_agent_format(self):
        ua = _build_user_agent()
        from limacharlie import __version__
        assert ua.startswith(f"lc-cli/{__version__}")
        assert "python-" in ua


class TestCreateSslContext:
    def test_returns_ssl_context(self):
        ctx = _create_ssl_context()
        assert ctx is not None
