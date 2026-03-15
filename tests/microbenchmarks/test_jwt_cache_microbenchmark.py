"""Microbenchmarks for JWT cache operations.

Measures the performance of the critical hot path: cache lookup, cache write,
config loading, cache key computation, JWT expiry decoding, and atomic writes.

Run with: pytest tests/microbenchmarks/test_jwt_cache_microbenchmark.py -v
"""

import base64
import json
import os
import time

import pytest
import yaml

from limacharlie.file_utils import atomic_write, safe_open_read, secure_file_permissions
from limacharlie.jwt_cache import (
    _compute_cache_key,
    _decode_jwt_exp,
    _get_cache_path,
    _is_cache_disabled,
    _reset_cache_disabled,
    get_cached_jwt,
    invalidate_cached_jwt,
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


@pytest.fixture(autouse=True)
def cache_env(monkeypatch, tmp_path):
    """Isolate all benchmarks to a temp directory."""
    from limacharlie.config import _reset_config_cache
    config_path = str(tmp_path / ".limacharlie")
    monkeypatch.setattr("limacharlie.jwt_cache.CONFIG_FILE_PATH", config_path)
    monkeypatch.setattr("limacharlie.config.CONFIG_FILE_PATH", config_path)
    monkeypatch.delenv("LC_CREDS_FILE", raising=False)
    monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
    monkeypatch.delenv("LC_NO_JWT_CACHE", raising=False)
    _reset_cache_disabled()
    _reset_config_cache()
    yield tmp_path
    _reset_cache_disabled()
    _reset_config_cache()


class TestCacheKeyComputation:
    """Benchmark _compute_cache_key - called on every cache lookup/write."""

    def test_compute_cache_key_api_key(self, benchmark):
        benchmark(_compute_cache_key, "oid-value", "api-key-value", None, None)

    def test_compute_cache_key_api_key_with_uid(self, benchmark):
        benchmark(_compute_cache_key, "oid-value", "api-key-value", None, "uid-value")

    def test_compute_cache_key_oauth(self, benchmark):
        benchmark(
            _compute_cache_key,
            "oid-value",
            None,
            {"refresh_token": "rt-value"},
            None,
        )


class TestJwtExpDecoding:
    """Benchmark _decode_jwt_exp - called on every cache read and write."""

    def test_decode_jwt_exp(self, benchmark):
        jwt = _make_jwt(time.time() + 3600)
        benchmark(_decode_jwt_exp, jwt)

    def test_decode_jwt_exp_long_payload(self, benchmark):
        """JWT with larger payload (more claims)."""
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256"}).encode()
        ).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "exp": time.time() + 3600,
                "oid": "a" * 36,
                "uid": "b" * 36,
                "perms": ["org.get", "sensor.list", "sensor.task"] * 10,
            }).encode()
        ).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        benchmark(_decode_jwt_exp, jwt)


class TestIsCacheDisabled:
    """Benchmark _is_cache_disabled - called on every get/put.

    After first call the result is memoized, so this benchmarks the
    fast path (cached bool check).
    """

    def test_is_cache_disabled_memoized(self, benchmark):
        _is_cache_disabled()  # prime the memoization
        benchmark(_is_cache_disabled)

    def test_is_cache_disabled_cold_env_vars_only(self, benchmark):
        """Cold path when no config file exists (env var check only)."""
        def cold_check():
            _reset_cache_disabled()
            return _is_cache_disabled()
        benchmark(cold_check)

    def test_is_cache_disabled_cold_with_config_file(self, benchmark, tmp_path):
        """Cold path when config file exists (YAML parse required)."""
        config_path = str(tmp_path / ".limacharlie")
        with open(config_path, "w") as f:
            yaml.safe_dump({"oid": "test-oid", "api_key": "test-key"}, f)

        def cold_check():
            _reset_cache_disabled()
            return _is_cache_disabled()
        benchmark(cold_check)


class TestGetCachedJwt:
    """Benchmark get_cached_jwt - the critical hot path on every CLI invocation."""

    def test_cache_hit(self, benchmark):
        """Best case: valid JWT in cache, returned immediately."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)

        benchmark(get_cached_jwt, "oid", "key", None, None)

    def test_cache_miss_empty(self, benchmark):
        """Cache file doesn't exist yet."""
        benchmark(get_cached_jwt, "oid", "key", None, None)

    def test_cache_miss_wrong_key(self, benchmark):
        """Cache file exists but no matching entry."""
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "other-oid", "other-key", None, None)

        benchmark(get_cached_jwt, "oid", "key", None, None)

    def test_cache_hit_with_many_entries(self, benchmark):
        """Cache file has many entries - measures JSON parse overhead."""
        exp = time.time() + 3600
        for i in range(50):
            put_cached_jwt(_make_jwt(exp), f"oid-{i}", f"key-{i}", None, None)
        put_cached_jwt(_make_jwt(exp), "target-oid", "target-key", None, None)

        benchmark(get_cached_jwt, "target-oid", "target-key", None, None)


class TestPutCachedJwt:
    """Benchmark put_cached_jwt - called after each fresh JWT fetch."""

    def test_put_new_entry(self, benchmark):
        """Write a new entry to empty cache."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)

        def put():
            put_cached_jwt(jwt, "oid", "key", None, None)
        benchmark(put)

    def test_put_overwrite(self, benchmark):
        """Overwrite existing entry (read-modify-write cycle)."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)

        new_jwt = _make_jwt(exp + 3600)

        def put():
            put_cached_jwt(new_jwt, "oid", "key", None, None)
        benchmark(put)


class TestInvalidateCachedJwt:
    """Benchmark invalidate_cached_jwt - called on 401."""

    def test_invalidate_existing(self, benchmark):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)

        def invalidate():
            # Re-populate so each iteration has something to invalidate
            put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
            invalidate_cached_jwt("oid", "key", None, None)
        benchmark(invalidate)

    def test_invalidate_missing(self, benchmark):
        """Invalidate when entry doesn't exist (no-op path)."""
        benchmark(invalidate_cached_jwt, "oid", "key", None, None)


class TestAtomicWrite:
    """Benchmark atomic_write - underlies all cache writes."""

    def test_small_payload(self, benchmark, tmp_path):
        path = str(tmp_path / "bench_small")
        data = b'{"key": "value"}'
        benchmark(atomic_write, path, data)

    def test_typical_cache_payload(self, benchmark, tmp_path):
        """Typical cache file size (~500 bytes with a few entries)."""
        path = str(tmp_path / "bench_typical")
        entries = {}
        for i in range(5):
            k = _compute_cache_key(f"oid-{i}", f"key-{i}", None, None)
            entries[k] = {"jwt": _make_jwt(time.time() + 3600)}
        data = json.dumps(entries).encode()
        benchmark(atomic_write, path, data)


class TestSafeOpenRead:
    """Benchmark safe_open_read - underlies all cache reads."""

    def test_small_file(self, benchmark, tmp_path):
        path = str(tmp_path / "bench_read")
        with open(path, "wb") as f:
            f.write(b'{"key": "value"}')
        os.chmod(path, 0o600)
        benchmark(safe_open_read, path)

    def test_typical_cache_file(self, benchmark, tmp_path):
        path = str(tmp_path / "bench_read_typical")
        entries = {}
        for i in range(5):
            k = _compute_cache_key(f"oid-{i}", f"key-{i}", None, None)
            entries[k] = {"jwt": _make_jwt(time.time() + 3600)}
        with open(path, "wb") as f:
            f.write(json.dumps(entries).encode())
        os.chmod(path, 0o600)
        benchmark(safe_open_read, path)


class TestSecureFilePermissions:
    """Benchmark secure_file_permissions - called on every atomic write."""

    def test_chmod_existing_file(self, benchmark, tmp_path):
        path = str(tmp_path / "bench_perm")
        with open(path, "w") as f:
            f.write("data")
        benchmark(secure_file_permissions, path)


class TestEndToEnd:
    """Benchmark the full cache lifecycle as experienced by a CLI invocation."""

    def test_full_cache_hit_path(self, benchmark):
        """Simulate the hot path: Client.__init__ cache lookup (cache hit).

        This is what every CLI invocation pays when a valid JWT is cached.
        Includes: _is_cache_disabled check, cache key computation,
        file read, JSON parse, JWT exp decode, expiry comparison.
        """
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)

        def full_hit():
            result = get_cached_jwt("oid", "key", None, None)
            assert result == jwt
        benchmark(full_hit)

    def test_full_cache_miss_then_put(self, benchmark):
        """Simulate cold path: cache miss + JWT fetch + cache write.

        The JWT fetch itself is network I/O (not benchmarked here).
        This measures the cache overhead around it. Uses a unique key
        per iteration to ensure each lookup is a genuine miss.
        """
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        counter = [0]

        def miss_then_put():
            counter[0] += 1
            oid = f"oid-miss-{counter[0]}"
            key = f"key-miss-{counter[0]}"
            result = get_cached_jwt(oid, key, None, None)
            assert result is None
            put_cached_jwt(jwt, oid, key, None, None)
        benchmark(miss_then_put)
