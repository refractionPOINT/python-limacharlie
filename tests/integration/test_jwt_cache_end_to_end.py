"""End-to-end integration tests for JWT caching with real files and mock HTTP.

These tests simulate real CLI usage patterns with:
- Real config files written to temp directories via save_config()
- Real JWT cache files on disk
- Real Client() instantiation with full credential resolution
- Mock HTTP server for jwt.limacharlie.io and api.limacharlie.io
- Real file permission checks
- Real atomic write / symlink protection

Each test simulates a multi-command user session as separate process-like
invocations (new Client per "command", caches reset between "processes").

Run with:
    pytest tests/integration/test_jwt_cache_end_to_end.py --oid dummy --key dummy -v
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
from limacharlie.config import (
    save_config,
    load_config,
    _reset_config_cache,
)
from limacharlie.jwt_cache import (
    _get_cache_path,
    _reset_cache_disabled,
    clear_jwt_cache,
    get_cached_jwt,
    put_cached_jwt,
    invalidate_cached_jwt,
)


def _make_jwt(exp: float, extra: dict | None = None) -> str:
    """Create a minimal JWT with a given exp claim."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256"}).encode()
    ).rstrip(b"=")
    payload_data = {"exp": exp}
    if extra:
        payload_data.update(extra)
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_data).encode()
    ).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


class _Handler(BaseHTTPRequestHandler):
    """Mock HTTP handler tracking call counts per-method."""

    jwt_to_return = ""
    api_response = {"ok": True}
    jwt_call_count = 0
    api_call_count = 0
    force_401_once = False
    lock = threading.Lock()

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.jwt_call_count = 0
            cls.api_call_count = 0
            cls.force_401_once = False

    def do_POST(self):
        with self.lock:
            _Handler.jwt_call_count += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"jwt": self.jwt_to_return}).encode())

    def do_GET(self):
        with self.lock:
            _Handler.api_call_count += 1
            if _Handler.force_401_once:
                _Handler.force_401_once = False
                self.send_error(401, "Unauthorized")
                return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.api_response).encode())

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def server():
    """Single mock HTTP server for the module."""
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    """Fully isolated environment per test."""
    config_path = str(tmp_path / ".limacharlie")
    monkeypatch.setattr("limacharlie.jwt_cache.CONFIG_FILE_PATH", config_path)
    monkeypatch.setattr("limacharlie.config.CONFIG_FILE_PATH", config_path)
    for var in ("LC_CREDS_FILE", "LC_EPHEMERAL_CREDS", "LC_NO_JWT_CACHE",
                "LC_OID", "LC_API_KEY", "LC_UID", "LC_CURRENT_ENV"):
        monkeypatch.delenv(var, raising=False)
    _reset_cache_disabled()
    _reset_config_cache()
    _Handler.reset()
    yield tmp_path
    _reset_cache_disabled()
    _reset_config_cache()


def _new_process():
    """Simulate a new CLI process by resetting per-process caches."""
    _reset_config_cache()
    _reset_cache_disabled()


# ---------------------------------------------------------------------------
# Scenario tests: simulate realistic multi-command user sessions
# ---------------------------------------------------------------------------


class TestUserSessionApiKey:
    """Simulate a user session using API key credentials across multiple
    CLI commands, each as a separate 'process'."""

    def test_login_then_three_commands(self, server):
        """auth login -> sensors list -> rules list -> search run.

        First command fetches JWT and caches it.
        Second and third commands reuse cached JWT (zero HTTP to jwt endpoint).
        """
        # Step 1: User logs in (writes config file)
        save_config({"oid": "my-org", "api_key": "my-key-123"})

        jwt = _make_jwt(time.time() + 3600)
        _Handler.jwt_to_return = jwt

        # Step 2: First command (e.g. sensors list) - cache miss
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c1 = Client()
            assert c1._jwt is None  # no cache yet
            result = c1.request("GET", "sensors")
            assert result == {"ok": True}
        assert _Handler.jwt_call_count == 1
        assert _Handler.api_call_count == 1

        # Step 3: Second command (e.g. rules list) - cache hit
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c2 = Client()
            assert c2._jwt == jwt  # from cache
            result = c2.request("GET", "rules")
            assert result == {"ok": True}
        assert _Handler.jwt_call_count == 0  # no JWT fetch
        assert _Handler.api_call_count == 1

        # Step 4: Third command - still cache hit
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c3 = Client()
            assert c3._jwt == jwt
            result = c3.request("GET", "search")
            assert result == {"ok": True}
        assert _Handler.jwt_call_count == 0
        assert _Handler.api_call_count == 1

    def test_stale_cached_jwt_401_recovery(self, server):
        """Cached JWT is valid locally but server rejects it (401).

        Must invalidate cache, fetch fresh JWT, cache it, and succeed.
        """
        save_config({"oid": "my-org", "api_key": "my-key-123"})

        stale_jwt = _make_jwt(time.time() + 3600)
        fresh_jwt = _make_jwt(time.time() + 7200, extra={"v": 2})
        _Handler.jwt_to_return = stale_jwt

        # Prime cache
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        # Simulate server revoking the token
        _new_process()
        _Handler.reset()
        _Handler.jwt_to_return = fresh_jwt
        _Handler.force_401_once = True

        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c = Client()
            assert c._jwt == stale_jwt  # from cache
            result = c.request("GET", "test")
            assert result == {"ok": True}
            assert c._jwt == fresh_jwt  # refreshed

        assert _Handler.jwt_call_count == 1  # fetched fresh
        assert _Handler.api_call_count == 2  # 401 + retry

        # Next command should use the fresh JWT from cache
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c2 = Client()
            assert c2._jwt == fresh_jwt

    def test_logout_clears_cache(self, server):
        """auth logout clears the cache, next command must re-authenticate."""
        save_config({"oid": "my-org", "api_key": "my-key-123"})

        jwt1 = _make_jwt(time.time() + 3600)
        jwt2 = _make_jwt(time.time() + 7200)
        _Handler.jwt_to_return = jwt1

        # Login + first command
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        # Logout (clear cache)
        clear_jwt_cache()
        assert not os.path.isfile(_get_cache_path())

        # Next command: must fetch fresh JWT
        _new_process()
        _Handler.reset()
        _Handler.jwt_to_return = jwt2
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c = Client()
            assert c._jwt is None  # cache cleared
            c.request("GET", "test")
        assert _Handler.jwt_call_count == 1

    def test_multiple_environments(self, server):
        """Different environments get separate cache entries."""
        save_config({
            "oid": "default-org",
            "api_key": "default-key",
            "env": {
                "staging": {"oid": "staging-org", "api_key": "staging-key"},
            },
        })

        jwt_default = _make_jwt(time.time() + 3600, extra={"env": "default"})
        jwt_staging = _make_jwt(time.time() + 3600, extra={"env": "staging"})

        # Command in default environment
        _Handler.jwt_to_return = jwt_default
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        # Command in staging environment
        _new_process()
        _Handler.jwt_to_return = jwt_staging
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client(environment="staging").request("GET", "test")

        # Both cached independently
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c_default = Client()
            assert c_default._jwt == jwt_default
            c_staging = Client(environment="staging")
            assert c_staging._jwt == jwt_staging
        assert _Handler.jwt_call_count == 0  # both from cache


class TestUserSessionEnvVars:
    """Simulate a user session using environment variable credentials."""

    def test_env_var_credentials_cached(self, server, monkeypatch):
        """LC_OID + LC_API_KEY flow uses cache correctly."""
        monkeypatch.setenv("LC_OID", "env-org")
        monkeypatch.setenv("LC_API_KEY", "env-key")

        jwt = _make_jwt(time.time() + 3600)
        _Handler.jwt_to_return = jwt

        # First command: cache miss
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c1 = Client()
            c1.request("GET", "test")
        assert _Handler.jwt_call_count == 1

        # Second command: cache hit
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c2 = Client()
            assert c2._jwt == jwt
            c2.request("GET", "test")
        assert _Handler.jwt_call_count == 0


class TestCacheDisabling:
    """Verify all cache disabling mechanisms work end-to-end."""

    def test_lc_no_jwt_cache_env_var(self, server, monkeypatch):
        """LC_NO_JWT_CACHE=1 prevents any cache file from being created."""
        monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
        _reset_cache_disabled()
        save_config({"oid": "my-org", "api_key": "my-key"})
        _Handler.jwt_to_return = _make_jwt(time.time() + 3600)

        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        assert not os.path.isfile(_get_cache_path())

    def test_no_jwt_cache_config_option(self, server):
        """no_jwt_cache: true in config prevents caching."""
        save_config({"oid": "my-org", "api_key": "my-key", "no_jwt_cache": True})
        _Handler.jwt_to_return = _make_jwt(time.time() + 3600)

        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        assert not os.path.isfile(_get_cache_path())

    def test_lc_ephemeral_creds(self, server, monkeypatch):
        """LC_EPHEMERAL_CREDS prevents caching (and config loading)."""
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        monkeypatch.setenv("LC_OID", "eph-org")
        monkeypatch.setenv("LC_API_KEY", "eph-key")
        _reset_cache_disabled()
        _Handler.jwt_to_return = _make_jwt(time.time() + 3600)

        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        assert not os.path.isfile(_get_cache_path())


class TestSearchTokenReuse:
    """End-to-end tests for the search command token reuse optimization."""

    def test_two_search_runs_reuse_long_lived_jwt(self, server):
        """First search run generates 4h JWT, second reuses it."""
        save_config({"oid": "my-org", "api_key": "my-key"})
        long_jwt = _make_jwt(time.time() + 5 * 3600)
        _Handler.jwt_to_return = long_jwt

        # First search run: get_jwt(4h) - must fetch
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c1 = Client()
            result1 = c1.get_jwt(expiry_hours=4.0)
            assert result1 == long_jwt
        assert _Handler.jwt_call_count == 1

        # Second search run (new process): get_jwt(4h) - should reuse
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c2 = Client()
            result2 = c2.get_jwt(expiry_hours=4.0)
            assert result2 == long_jwt
        assert _Handler.jwt_call_count == 0  # reused from cache

    def test_search_after_regular_command_fetches_longer_jwt(self, server):
        """Regular command caches 1h JWT, search needs 4h so fetches new one."""
        save_config({"oid": "my-org", "api_key": "my-key"})
        short_jwt = _make_jwt(time.time() + 3600)  # 1h
        long_jwt = _make_jwt(time.time() + 5 * 3600)  # 5h

        # Regular command: caches 1h JWT
        _Handler.jwt_to_return = short_jwt
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "sensors")

        # Search run: needs 4h, cached has only 1h, must fetch new
        _new_process()
        _Handler.reset()
        _Handler.jwt_to_return = long_jwt
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c = Client()
            assert c._jwt == short_jwt  # loaded from cache
            result = c.get_jwt(expiry_hours=4.0)
            assert result == long_jwt  # fetched new
        assert _Handler.jwt_call_count == 1

        # Subsequent regular command uses the long-lived JWT from cache
        _new_process()
        _Handler.reset()
        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            c2 = Client()
            assert c2._jwt == long_jwt
        assert _Handler.jwt_call_count == 0


class TestFileSecurityE2E:
    """Verify file security properties in realistic usage."""

    def test_cache_file_permissions_after_request(self, server):
        save_config({"oid": "my-org", "api_key": "my-key"})
        _Handler.jwt_to_return = _make_jwt(time.time() + 3600)

        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        path = _get_cache_path()
        assert os.path.isfile(path)
        mode = os.stat(path).st_mode
        assert mode & 0o777 == 0o600

    def test_config_file_permissions_after_save(self):
        save_config({"oid": "test"})
        from limacharlie.config import _get_config_path
        mode = os.stat(_get_config_path()).st_mode
        assert mode & 0o777 == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_symlink_at_cache_path_rejected(self, server, tmp_path):
        """Attacker places symlink at cache path. Write must not follow it."""
        save_config({"oid": "my-org", "api_key": "my-key"})
        _Handler.jwt_to_return = _make_jwt(time.time() + 3600)

        target = str(tmp_path / "attacker_target")
        with open(target, "w") as f:
            f.write("original")

        cache_path = _get_cache_path()
        os.symlink(target, cache_path)

        with patch("limacharlie.client.JWT_URL", server), \
             patch("limacharlie.client.ROOT_URL", server):
            Client().request("GET", "test")

        # Target file must NOT have been overwritten
        with open(target, "r") as f:
            assert f.read() == "original"
