"""Integration tests for JWT disk caching with mock JWT and API servers.

Spins up a local HTTP server that mocks both the JWT endpoint
(jwt.limacharlie.io) and the API endpoint (api.limacharlie.io).
Verifies the full Client lifecycle: cache miss -> JWT fetch -> cache write
-> subsequent Client uses cached JWT -> 401 invalidates cache, etc.

These tests exercise the real code path end-to-end (Client, jwt_cache,
file_utils, config) with only the HTTP endpoints mocked.
"""

import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest

from limacharlie.client import Client
from limacharlie.jwt_cache import (
    _get_cache_path,
    _reset_cache_disabled,
    clear_jwt_cache,
    get_cached_jwt,
)


def _make_jwt(exp: float, oid: str = "test-oid") -> str:
    """Create a minimal JWT with exp claim."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256"}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp, "oid": oid}).encode()
    ).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


class MockHandler(BaseHTTPRequestHandler):
    """HTTP handler that mocks JWT and API endpoints.

    Class-level attributes control behavior:
    - jwt_to_return: JWT string to return from POST /
    - api_response: dict to return from API calls
    - jwt_call_count: number of JWT requests received
    - api_call_count: number of API requests received
    - force_401_once: if True, return 401 on next API call then reset
    """

    jwt_to_return = ""
    api_response = {"ok": True}
    jwt_call_count = 0
    api_call_count = 0
    force_401_once = False
    lock = threading.Lock()

    def do_POST(self):
        """Handle JWT endpoint (POST /)."""
        with self.lock:
            MockHandler.jwt_call_count += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"jwt": self.jwt_to_return}).encode())

    def do_GET(self):
        """Handle API endpoint (GET /v1/...)."""
        with self.lock:
            MockHandler.api_call_count += 1
            if MockHandler.force_401_once:
                MockHandler.force_401_once = False
                self.send_error(401, "Unauthorized")
                return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.api_response).encode())

    def log_message(self, format, *args):
        """Suppress request logging noise in test output."""
        pass


@pytest.fixture
def mock_server():
    """Start a mock HTTP server on a random port."""
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def cache_env(monkeypatch, tmp_path):
    """Set up isolated cache environment with fresh temp paths."""
    import os
    from limacharlie.config import _reset_config_cache
    from limacharlie.paths import _reset_path_cache
    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)
    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    monkeypatch.delenv("LC_CREDS_FILE", raising=False)
    monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
    monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
    monkeypatch.delenv("LC_NO_JWT_CACHE", raising=False)
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()
    yield tmp_path
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()


class TestJwtCacheE2E:
    """End-to-end tests: real Client + real cache + mock HTTP server."""

    def test_first_request_fetches_jwt_second_uses_cache(self, mock_server, cache_env):
        """First Client fetches JWT from server, second reuses from cache."""
        jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_to_return = jwt
        MockHandler.jwt_call_count = 0
        MockHandler.api_call_count = 0

        # First client: no cache, must fetch JWT
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c1 = Client(oid="test-oid", api_key="test-key")
            result = c1.request("GET", "sensors")

        assert result == {"ok": True}
        assert MockHandler.jwt_call_count == 1
        assert MockHandler.api_call_count == 1

        # Second client: should find cached JWT, no JWT endpoint call
        MockHandler.jwt_call_count = 0
        MockHandler.api_call_count = 0

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c2 = Client(oid="test-oid", api_key="test-key")
            assert c2._jwt == jwt  # loaded from cache
            result = c2.request("GET", "sensors")

        assert result == {"ok": True}
        assert MockHandler.jwt_call_count == 0  # no JWT fetch
        assert MockHandler.api_call_count == 1

    def test_expired_cache_triggers_fresh_jwt_fetch(self, mock_server, cache_env):
        """Expired cached JWT is not used; triggers a fresh fetch."""
        expired_jwt = _make_jwt(time.time() + 300)  # 5 min, within 10-min buffer
        fresh_jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_to_return = fresh_jwt
        MockHandler.jwt_call_count = 0

        # Manually write an about-to-expire JWT to cache
        from limacharlie.jwt_cache import put_cached_jwt
        # Need a jwt with enough exp to be writable but not readable
        writable_jwt = _make_jwt(time.time() + 300)
        # Directly write to cache file (bypass put_cached_jwt exp check)
        from limacharlie.jwt_cache import _compute_cache_key, _save_cache
        key = _compute_cache_key("test-oid", "test-key", None, None)
        _save_cache({key: {"jwt": writable_jwt}})

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c = Client(oid="test-oid", api_key="test-key")
            assert c._jwt is None  # cache miss (within expiry buffer)
            c.request("GET", "sensors")

        assert MockHandler.jwt_call_count == 1  # had to fetch fresh

    def test_401_invalidates_cache_and_refetches(self, mock_server, cache_env):
        """On 401, cached JWT is invalidated, fresh one is fetched."""
        stale_jwt = _make_jwt(time.time() + 3600)
        fresh_jwt = _make_jwt(time.time() + 7200)

        # Pre-populate cache with a JWT the server will reject (401)
        MockHandler.jwt_to_return = stale_jwt
        MockHandler.jwt_call_count = 0

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c1 = Client(oid="test-oid", api_key="test-key")
            c1.request("GET", "sensors")

        assert MockHandler.jwt_call_count == 1
        # Cache now has stale_jwt

        # Now make the API return 401 once, then succeed
        MockHandler.force_401_once = True
        MockHandler.jwt_to_return = fresh_jwt
        MockHandler.jwt_call_count = 0
        MockHandler.api_call_count = 0

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c2 = Client(oid="test-oid", api_key="test-key")
            assert c2._jwt == stale_jwt  # from cache
            result = c2.request("GET", "sensors")

        assert result == {"ok": True}
        assert MockHandler.jwt_call_count == 1  # refreshed after 401
        assert MockHandler.api_call_count == 2  # 401 + retry

        # Cache should now have fresh_jwt
        cached = get_cached_jwt("test-oid", "test-key", None, None)
        assert cached == fresh_jwt

    def test_different_credentials_get_separate_cache_entries(self, mock_server, cache_env):
        """Two different API keys produce independent cache entries."""
        jwt_a = _make_jwt(time.time() + 3600, oid="oid-a")
        jwt_b = _make_jwt(time.time() + 3600, oid="oid-b")

        MockHandler.jwt_to_return = jwt_a
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            Client(oid="oid-a", api_key="key-a").request("GET", "test")

        MockHandler.jwt_to_return = jwt_b
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            Client(oid="oid-b", api_key="key-b").request("GET", "test")

        # Both should be cached independently
        assert get_cached_jwt("oid-a", "key-a", None, None) == jwt_a
        assert get_cached_jwt("oid-b", "key-b", None, None) == jwt_b

    def test_clear_cache_forces_refetch(self, mock_server, cache_env):
        """clear_jwt_cache() forces next Client to fetch a fresh JWT."""
        jwt1 = _make_jwt(time.time() + 3600)
        jwt2 = _make_jwt(time.time() + 7200)

        MockHandler.jwt_to_return = jwt1
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            Client(oid="test-oid", api_key="test-key").request("GET", "test")

        clear_jwt_cache()
        assert get_cached_jwt("test-oid", "test-key", None, None) is None

        MockHandler.jwt_to_return = jwt2
        MockHandler.jwt_call_count = 0
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c = Client(oid="test-oid", api_key="test-key")
            assert c._jwt is None  # cache cleared
            c.request("GET", "test")

        assert MockHandler.jwt_call_count == 1

    def test_cache_disabled_via_env_var(self, mock_server, cache_env, monkeypatch):
        """LC_NO_JWT_CACHE prevents caching."""
        monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
        _reset_cache_disabled()

        jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_to_return = jwt
        MockHandler.jwt_call_count = 0

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            Client(oid="test-oid", api_key="test-key").request("GET", "test")

        assert MockHandler.jwt_call_count == 1
        # No cache file should exist
        assert not os.path.isfile(_get_cache_path())

        # Second client must also fetch (no cache)
        MockHandler.jwt_call_count = 0
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            Client(oid="test-oid", api_key="test-key").request("GET", "test")

        assert MockHandler.jwt_call_count == 1

    def test_pre_generated_jwt_bypasses_cache_entirely(self, mock_server, cache_env):
        """Client(jwt=...) uses the provided JWT, no cache interaction."""
        pre_jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_call_count = 0

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c = Client(oid="test-oid", jwt=pre_jwt)
            result = c.request("GET", "test")

        assert result == {"ok": True}
        assert MockHandler.jwt_call_count == 0
        # Nothing should be cached
        assert get_cached_jwt("test-oid", "test-key", None, None) is None

    def test_cache_file_permissions(self, mock_server, cache_env):
        """Cache file should have owner-only permissions after write."""
        jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_to_return = jwt

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            Client(oid="test-oid", api_key="test-key").request("GET", "test")

        cache_path = _get_cache_path()
        assert os.path.isfile(cache_path)
        mode = os.stat(cache_path).st_mode
        assert mode & 0o777 == 0o600

    def test_rapid_sequential_clients_share_cache(self, mock_server, cache_env):
        """Simulate rapid CLI invocations - only the first fetches JWT."""
        jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_to_return = jwt
        MockHandler.jwt_call_count = 0

        for i in range(10):
            with patch("limacharlie.client.JWT_URL", mock_server), \
                 patch("limacharlie.client.ROOT_URL", mock_server):
                Client(oid="test-oid", api_key="test-key").request("GET", "test")

        # Only the first should have fetched a JWT
        assert MockHandler.jwt_call_count == 1

    def test_get_jwt_reuses_cached_token_with_sufficient_ttl(self, mock_server, cache_env):
        """get_jwt(expiry_hours=4) reuses cached JWT if it has >= 4h remaining.

        Simulates the search command flow: first `search run` fetches a 4h JWT,
        second `search run` reuses it instead of generating another.
        """
        # JWT with 5 hours remaining
        long_jwt = _make_jwt(time.time() + 5 * 3600)
        MockHandler.jwt_to_return = long_jwt
        MockHandler.jwt_call_count = 0

        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c1 = Client(oid="test-oid", api_key="test-key")
            # First search: fetches a long-lived JWT
            result1 = c1.get_jwt(expiry_hours=4.0)
            assert result1 == long_jwt

        assert MockHandler.jwt_call_count == 1

        # Second invocation (new Client, simulating separate CLI process)
        MockHandler.jwt_call_count = 0
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c2 = Client(oid="test-oid", api_key="test-key")
            # Cached JWT has ~5h remaining, requesting 4h - should reuse
            result2 = c2.get_jwt(expiry_hours=4.0)
            assert result2 == long_jwt

        # No JWT endpoint call - reused from cache
        assert MockHandler.jwt_call_count == 0

    def test_get_jwt_fetches_new_when_cached_ttl_insufficient(self, mock_server, cache_env):
        """get_jwt(expiry_hours=4) fetches new JWT if cached one has < 4h left."""
        # JWT with only 2 hours remaining
        short_jwt = _make_jwt(time.time() + 2 * 3600)
        long_jwt = _make_jwt(time.time() + 5 * 3600)

        # Prime cache with the short-lived JWT
        MockHandler.jwt_to_return = short_jwt
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c1 = Client(oid="test-oid", api_key="test-key")
            c1.request("GET", "test")  # caches the 2h JWT

        # Now request 4h - cached has only 2h, must fetch new
        MockHandler.jwt_to_return = long_jwt
        MockHandler.jwt_call_count = 0
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c2 = Client(oid="test-oid", api_key="test-key")
            result = c2.get_jwt(expiry_hours=4.0)
            assert result == long_jwt

        # Had to fetch a new JWT
        assert MockHandler.jwt_call_count == 1

        # The new long-lived JWT should now be cached
        cached = get_cached_jwt("test-oid", "test-key", None, None)
        assert cached == long_jwt


class TestOAuthCacheE2E:
    """End-to-end tests for OAuth authentication path caching."""

    def test_oauth_first_request_caches_second_reuses(self, mock_server, cache_env):
        """OAuth path: first Client fetches JWT, second reuses from cache."""
        jwt = _make_jwt(time.time() + 3600)
        MockHandler.jwt_to_return = jwt
        MockHandler.jwt_call_count = 0
        MockHandler.api_call_count = 0

        oauth_creds = {"id_token": "id-tok", "refresh_token": "ref-tok"}

        # First client: OAuth credentials, no cache
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server), \
             patch("limacharlie.client.resolve_credentials", return_value={
                 "oid": "test-oid", "uid": None, "api_key": None, "oauth": oauth_creds,
             }), \
             patch("limacharlie.client.Client._refresh_jwt_oauth") as mock_oauth:
            # Simulate what _refresh_jwt_oauth does: call JWT endpoint, cache result
            def oauth_side_effect(effective_oid, expiry, oid_override=None):
                from limacharlie.jwt_cache import put_cached_jwt
                c1._jwt = jwt
                if expiry is None and oid_override is None:
                    put_cached_jwt(jwt, effective_oid, None, oauth_creds, None)
            mock_oauth.side_effect = oauth_side_effect

            c1 = Client(oid="test-oid")
            assert c1._jwt is None  # cache miss
            c1.refresh_jwt()

        # Second client: should find cached JWT
        with patch("limacharlie.client.resolve_credentials", return_value={
                 "oid": "test-oid", "uid": None, "api_key": None, "oauth": oauth_creds,
             }):
            c2 = Client(oid="test-oid")
            assert c2._jwt == jwt  # cache hit

    def test_oauth_and_api_key_have_separate_cache_entries(self, mock_server, cache_env):
        """OAuth and API key for same OID don't interfere with each other."""
        jwt_api = _make_jwt(time.time() + 3600)
        jwt_oauth = _make_jwt(time.time() + 3601)
        oauth_creds = {"id_token": "id-tok", "refresh_token": "ref-tok"}

        # Cache an API key JWT
        MockHandler.jwt_to_return = jwt_api
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c_api = Client(oid="test-oid", api_key="test-key")
            c_api.request("GET", "test")

        # Cache an OAuth JWT (manually, simulating the OAuth flow)
        from limacharlie.jwt_cache import put_cached_jwt
        put_cached_jwt(jwt_oauth, "test-oid", None, oauth_creds, None)

        # Verify both are independently cached
        assert get_cached_jwt("test-oid", "test-key", None, None) == jwt_api
        assert get_cached_jwt("test-oid", None, oauth_creds, None) == jwt_oauth

        # New API key client gets the API JWT, not the OAuth one
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c_api2 = Client(oid="test-oid", api_key="test-key")
            assert c_api2._jwt == jwt_api

        # New OAuth client gets the OAuth JWT, not the API one
        with patch("limacharlie.client.resolve_credentials", return_value={
                 "oid": "test-oid", "uid": None, "api_key": None, "oauth": oauth_creds,
             }):
            c_oauth2 = Client(oid="test-oid")
            assert c_oauth2._jwt == jwt_oauth
