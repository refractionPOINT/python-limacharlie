"""End-to-end microbenchmarks for JWT caching with real Client + mock HTTP.

Unlike the component-level microbenchmarks in test_jwt_cache_microbenchmark.py,
these benchmarks exercise the full realistic path that a CLI invocation takes:

1. Real config file on disk (written with save_config)
2. Real Client() instantiation (resolve_credentials + cache lookup)
3. Real HTTP mock server (jwt.limacharlie.io + api.limacharlie.io)
4. Real cache file I/O (put/get/invalidate)
5. Real file permissions and symlink checks

This measures what the user actually experiences, end to end.

Run with: pytest tests/microbenchmarks/test_end_to_end_microbenchmark.py -v --benchmark-only
"""

import base64
import json
import os
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest
import yaml

from limacharlie.client import Client
from limacharlie.config import save_config, load_config, _reset_config_cache
from limacharlie.jwt_cache import (
    _get_cache_path,
    _reset_cache_disabled,
    clear_jwt_cache,
    get_cached_jwt,
    put_cached_jwt,
)


def _make_jwt(exp: float) -> str:
    """Create a minimal JWT with a given exp claim."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256"}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()
    ).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


class _MockHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for JWT + API endpoints."""

    jwt_to_return = ""
    lock = threading.Lock()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"jwt": self.jwt_to_return}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def mock_server():
    """Start a mock HTTP server once for the entire module."""
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Fully isolated environment with real config + cache files."""
    import os
    from limacharlie.paths import _reset_path_cache
    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)
    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    monkeypatch.delenv("LC_CREDS_FILE", raising=False)
    monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
    monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
    monkeypatch.delenv("LC_NO_JWT_CACHE", raising=False)
    monkeypatch.delenv("LC_OID", raising=False)
    monkeypatch.delenv("LC_API_KEY", raising=False)
    monkeypatch.delenv("LC_UID", raising=False)
    monkeypatch.delenv("LC_CURRENT_ENV", raising=False)
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()
    yield tmp_path
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()


class TestClientInitCacheHit:
    """Benchmark Client() construction when cache has a valid JWT.

    This is the hot path for every CLI command after the first.
    Measures: config resolve + cache file read + JSON parse + JWT decode.
    """

    def test_client_init_cache_hit_with_config_file(self, benchmark, mock_server):
        """Real config file + real cache file + Client() construction."""
        save_config({"oid": "bench-oid", "api_key": "bench-key"})
        jwt = _make_jwt(time.time() + 3600)
        put_cached_jwt(jwt, "bench-oid", "bench-key", None, None)

        def create_client():
            _reset_config_cache()
            with patch("limacharlie.client.JWT_URL", mock_server), \
                 patch("limacharlie.client.ROOT_URL", mock_server):
                c = Client()
                assert c._jwt == jwt
        benchmark(create_client)

    def test_client_init_cache_hit_env_vars(self, benchmark, monkeypatch, mock_server):
        """Env var credentials + real cache file + Client() construction.

        Faster than config file path because no YAML parse needed.
        """
        monkeypatch.setenv("LC_OID", "bench-oid")
        monkeypatch.setenv("LC_API_KEY", "bench-key")
        _reset_config_cache()
        jwt = _make_jwt(time.time() + 3600)
        put_cached_jwt(jwt, "bench-oid", "bench-key", None, None)

        def create_client():
            with patch("limacharlie.client.JWT_URL", mock_server), \
                 patch("limacharlie.client.ROOT_URL", mock_server):
                c = Client()
                assert c._jwt == jwt
        benchmark(create_client)


class TestClientInitCacheMiss:
    """Benchmark Client() + first request when cache is empty.

    Measures: config resolve + cache miss + JWT HTTP fetch + cache write.
    """

    def test_client_init_and_request_cold(self, benchmark, mock_server):
        """No cache. Client must fetch JWT from server then cache it."""
        save_config({"oid": "bench-oid", "api_key": "bench-key"})
        jwt = _make_jwt(time.time() + 3600)
        _MockHandler.jwt_to_return = jwt

        def cold_request():
            _reset_config_cache()
            clear_jwt_cache()
            with patch("limacharlie.client.JWT_URL", mock_server), \
                 patch("limacharlie.client.ROOT_URL", mock_server):
                c = Client()
                assert c._jwt is None
                c.request("GET", "test")
                assert c._jwt == jwt
        benchmark(cold_request)


class TestFullRequestCacheHit:
    """Benchmark the full path: Client() + request() with cached JWT.

    The most common real-world scenario: user runs a CLI command,
    JWT is in cache, request goes through directly.
    """

    def test_client_request_with_cached_jwt(self, benchmark, mock_server):
        """Complete CLI command: Client() + one API request, JWT cached."""
        save_config({"oid": "bench-oid", "api_key": "bench-key"})
        jwt = _make_jwt(time.time() + 3600)
        put_cached_jwt(jwt, "bench-oid", "bench-key", None, None)

        def full_request():
            _reset_config_cache()
            with patch("limacharlie.client.JWT_URL", mock_server), \
                 patch("limacharlie.client.ROOT_URL", mock_server):
                c = Client()
                result = c.request("GET", "test")
                assert result == {"ok": True}
        benchmark(full_request)


class TestSearchTokenReuse:
    """Benchmark get_jwt() reuse vs fresh fetch for search commands."""

    def test_get_jwt_reuse_cached_long_lived(self, benchmark, mock_server):
        """get_jwt(4h) when cached JWT has 5h remaining - pure reuse."""
        save_config({"oid": "bench-oid", "api_key": "bench-key"})
        jwt = _make_jwt(time.time() + 5 * 3600)
        _MockHandler.jwt_to_return = jwt

        # Prime the cache with a long-lived JWT
        with patch("limacharlie.client.JWT_URL", mock_server), \
             patch("limacharlie.client.ROOT_URL", mock_server):
            c = Client()
            c.request("GET", "prime")

        def reuse():
            _reset_config_cache()
            with patch("limacharlie.client.JWT_URL", mock_server), \
                 patch("limacharlie.client.ROOT_URL", mock_server):
                c = Client()
                result = c.get_jwt(expiry_hours=4.0)
                assert result == jwt
        benchmark(reuse)


class TestConfigLoadPerformance:
    """Benchmark config file operations in realistic scenarios."""

    def test_save_then_load_config(self, benchmark):
        """Write config then read it back (what 'auth login' does)."""
        data = {"oid": "my-oid", "api_key": "my-key", "uid": "my-uid"}

        def save_and_load():
            _reset_config_cache()
            save_config(data)
            result = load_config()
            assert result["oid"] == "my-oid"
        benchmark(save_and_load)

    def test_load_config_with_environments(self, benchmark):
        """Load a config file with multiple environments."""
        data = {
            "oid": "default-oid",
            "api_key": "default-key",
            "env": {
                f"env-{i}": {"oid": f"oid-{i}", "api_key": f"key-{i}"}
                for i in range(10)
            },
        }
        save_config(data)

        def load():
            _reset_config_cache()
            result = load_config()
            assert len(result["env"]) == 10
        benchmark(load)


class TestCacheFileGrowth:
    """Benchmark cache performance as the cache file grows."""

    def test_cache_hit_with_1_entry(self, benchmark):
        jwt = _make_jwt(time.time() + 3600)
        put_cached_jwt(jwt, "oid-0", "key-0", None, None)

        benchmark(get_cached_jwt, "oid-0", "key-0", None, None)

    def test_cache_hit_with_10_entries(self, benchmark):
        jwt = _make_jwt(time.time() + 3600)
        for i in range(10):
            put_cached_jwt(_make_jwt(time.time() + 3600), f"oid-{i}", f"key-{i}", None, None)
        put_cached_jwt(jwt, "target", "target-key", None, None)

        benchmark(get_cached_jwt, "target", "target-key", None, None)

    def test_cache_hit_with_50_entries(self, benchmark):
        jwt = _make_jwt(time.time() + 3600)
        for i in range(50):
            put_cached_jwt(_make_jwt(time.time() + 3600), f"oid-{i}", f"key-{i}", None, None)
        put_cached_jwt(jwt, "target", "target-key", None, None)

        benchmark(get_cached_jwt, "target", "target-key", None, None)


class TestOAuthPath:
    """Benchmark cache operations for the OAuth authentication path."""

    def test_oauth_cache_hit(self, benchmark):
        jwt = _make_jwt(time.time() + 3600)
        oauth = {"id_token": "id-tok", "refresh_token": "ref-tok"}
        put_cached_jwt(jwt, "oid", None, oauth, None)

        benchmark(get_cached_jwt, "oid", None, oauth, None)

    def test_oauth_cache_put(self, benchmark):
        jwt = _make_jwt(time.time() + 3600)
        oauth = {"id_token": "id-tok", "refresh_token": "ref-tok"}

        def put():
            put_cached_jwt(jwt, "oid", None, oauth, None)
        benchmark(put)
