"""Tests for limacharlie.jwt_cache module."""

from __future__ import annotations

import base64
import json
import os
import time

import pytest

from limacharlie.jwt_cache import (
    _compute_cache_key,
    _decode_jwt_exp,
    _get_cache_path,
    _is_cache_disabled,
    _load_cache,
    _reset_cache_disabled,
    _save_cache,
    clear_jwt_cache,
    get_cached_jwt,
    invalidate_cached_jwt,
    put_cached_jwt,
)


def _make_jwt(exp: float | int) -> str:
    """Create a minimal JWT with a given exp claim for testing.

    Not cryptographically valid - just valid base64url structure
    with a parseable payload containing an exp claim.
    """
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
    signature = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{signature.decode()}"


@pytest.fixture(autouse=False)
def tmp_jwt_cache(monkeypatch, tmp_path):
    """Point JWT cache to a temp directory and clear relevant env vars.

    Sets LC_CONFIG_DIR to a temp directory so all path resolution
    goes through the new layout. The yielded path is the JWT cache
    file inside that directory (e.g. <tmp>/lc_config/jwt_cache.json).
    """
    from limacharlie.config import _reset_config_cache
    from limacharlie.paths import _reset_path_cache

    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)
    cache_path = os.path.join(config_dir, "jwt_cache.json")

    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    monkeypatch.delenv("LC_CREDS_FILE", raising=False)
    monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
    monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
    monkeypatch.delenv("LC_NO_JWT_CACHE", raising=False)
    # Reset per-process caches so each test evaluates fresh
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()
    yield cache_path
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()


class TestComputeCacheKey:
    def test_different_oids_produce_different_keys(self):
        k1 = _compute_cache_key("oid1", "key", None, None)
        k2 = _compute_cache_key("oid2", "key", None, None)
        assert k1 != k2

    def test_different_api_keys_produce_different_keys(self):
        k1 = _compute_cache_key("oid", "key1", None, None)
        k2 = _compute_cache_key("oid", "key2", None, None)
        assert k1 != k2

    def test_different_uids_produce_different_keys(self):
        k1 = _compute_cache_key("oid", "key", None, "uid1")
        k2 = _compute_cache_key("oid", "key", None, "uid2")
        assert k1 != k2

    def test_oauth_vs_api_key_produce_different_keys(self):
        k1 = _compute_cache_key("oid", "key", None, None)
        k2 = _compute_cache_key("oid", None, {"refresh_token": "rt"}, None)
        assert k1 != k2

    def test_deterministic(self):
        k1 = _compute_cache_key("oid", "key", None, "uid")
        k2 = _compute_cache_key("oid", "key", None, "uid")
        assert k1 == k2

    def test_none_oid_returns_none(self):
        assert _compute_cache_key(None, "key", None, None) is None

    def test_no_api_key_and_no_oauth_returns_none(self):
        assert _compute_cache_key("oid", None, None, None) is None

    def test_empty_string_oid_is_valid(self):
        k = _compute_cache_key("", "key", None, None)
        assert k is not None

    def test_oauth_with_no_refresh_token_still_produces_key(self):
        k = _compute_cache_key("oid", None, {"id_token": "tok"}, None)
        assert k is not None

    def test_key_is_hex_sha256(self):
        k = _compute_cache_key("oid", "key", None, None)
        assert len(k) == 64
        int(k, 16)  # should not raise


class TestDecodeJwtExp:
    def test_valid_jwt_returns_exp(self):
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        assert _decode_jwt_exp(jwt) == pytest.approx(exp)

    def test_no_exp_claim_returns_none(self):
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"sub": "user"}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        assert _decode_jwt_exp(jwt) is None

    def test_malformed_jwt_not_three_segments(self):
        assert _decode_jwt_exp("only.two") is None
        assert _decode_jwt_exp("one") is None
        assert _decode_jwt_exp("a.b.c.d") is None

    def test_invalid_base64_in_payload(self):
        assert _decode_jwt_exp("a.!!!invalid!!!.c") is None

    def test_non_json_payload(self):
        header = base64.urlsafe_b64encode(b"header").rstrip(b"=")
        payload = base64.urlsafe_b64encode(b"not json").rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        assert _decode_jwt_exp(jwt) is None

    def test_base64url_without_padding(self):
        # Ensure base64url decoding works with payloads that need padding
        exp = 1700000000
        jwt = _make_jwt(exp)
        # Verify no padding in the token
        assert "=" not in jwt
        assert _decode_jwt_exp(jwt) == exp

    def test_integer_exp(self):
        assert _decode_jwt_exp(_make_jwt(1700000000)) == 1700000000.0

    def test_float_exp(self):
        assert _decode_jwt_exp(_make_jwt(1700000000.5)) == 1700000000.5

    def test_very_large_exp(self):
        exp = 9999999999
        assert _decode_jwt_exp(_make_jwt(exp)) == exp

    def test_empty_string(self):
        assert _decode_jwt_exp("") is None

    def test_negative_exp(self):
        """JWT with exp: -1 should return -1.0 (valid float, caller handles it)."""
        assert _decode_jwt_exp(_make_jwt(-1)) == -1.0

    def test_non_numeric_exp(self):
        """JWT with exp: 'not a number' should return None (float() fails)."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"exp": "not a number"}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        assert _decode_jwt_exp(jwt) is None

    def test_exp_is_dict(self):
        """JWT with exp: {'nested': 1} should return None."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"exp": {"nested": 1}}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        assert _decode_jwt_exp(jwt) is None


class TestGetCachedJwt:
    def test_returns_cached_jwt_when_valid(self, tmp_jwt_cache):
        exp = time.time() + 3600  # 1 hour from now
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        result = get_cached_jwt("oid", "key", None, None)
        assert result == jwt

    def test_returns_none_when_cache_empty(self, tmp_jwt_cache):
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_key_doesnt_match(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key1", None, None)
        assert get_cached_jwt("oid", "key2", None, None) is None

    def test_returns_none_within_expiry_buffer(self, tmp_jwt_cache):
        # JWT expires in 5 minutes - within the 10 minute buffer
        exp = time.time() + 300
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_expired(self, tmp_jwt_cache):
        exp = time.time() - 100  # already expired
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_ephemeral(self, tmp_jwt_cache, monkeypatch):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        _reset_cache_disabled()  # env changed, force re-evaluation
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_no_jwt_cache_env(self, tmp_jwt_cache, monkeypatch):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
        _reset_cache_disabled()  # env changed, force re-evaluation
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_no_jwt_cache_config(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        import yaml
        from limacharlie.paths import get_config_path
        config_path = get_config_path()
        with open(config_path, "w") as f:
            yaml.safe_dump({"no_jwt_cache": True}, f)
        _reset_cache_disabled()  # config changed, force re-evaluation
        from limacharlie.config import _reset_config_cache
        _reset_config_cache()
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_cache_file_missing(self, tmp_jwt_cache):
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_on_invalid_json(self, tmp_jwt_cache):
        path = _get_cache_path()
        with open(path, "w") as f:
            f.write("not json{{{")
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_none_when_oid_is_none(self, tmp_jwt_cache):
        assert get_cached_jwt(None, "key", None, None) is None

    def test_returns_none_when_no_creds(self, tmp_jwt_cache):
        assert get_cached_jwt("oid", None, None, None) is None

    def test_returns_none_at_exact_buffer_boundary(self, tmp_jwt_cache):
        """JWT with exp exactly at time.time() + 600 should return None.

        The boundary check is >= (time.time() + 600 >= exp), so a JWT
        expiring exactly at the buffer boundary is considered too close.
        """
        exp = time.time() + 600  # exactly at buffer boundary
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_returns_jwt_one_second_past_buffer(self, tmp_jwt_cache):
        """JWT with exp at time.time() + 601 should be returned.

        One second past the 600-second buffer means the JWT still has
        enough remaining lifetime to be useful.
        """
        exp = time.time() + 601
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) == jwt

    def test_returns_none_when_jwt_in_cache_has_unparseable_exp(self, tmp_jwt_cache):
        """Write a malformed JWT string directly to the cache JSON file,
        then get should return None because the exp cannot be parsed."""
        key = _compute_cache_key("oid", "key", None, None)
        path = _get_cache_path()
        # Write a JWT-like string with an invalid payload that can't be decoded
        malformed_jwt = "header.!!!invalidbase64!!!.signature"
        with open(path, "w") as f:
            json.dump({key: {"jwt": malformed_jwt}}, f)
        os.chmod(path, 0o600)
        assert get_cached_jwt("oid", "key", None, None) is None


class TestPutCachedJwt:
    def test_writes_jwt_to_cache(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        path = _get_cache_path()
        assert os.path.isfile(path)
        with open(path, "r") as f:
            data = json.load(f)
        assert len(data) == 1
        entry = list(data.values())[0]
        assert entry["jwt"] == jwt

    def test_file_has_restricted_permissions(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        path = _get_cache_path()
        mode = os.stat(path).st_mode
        assert mode & 0o777 == 0o600

    def test_preserves_existing_entries(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid1", "key1", None, None)
        put_cached_jwt(_make_jwt(exp), "oid2", "key2", None, None)
        path = _get_cache_path()
        with open(path, "r") as f:
            data = json.load(f)
        assert len(data) == 2

    def test_overwrites_same_cache_key(self, tmp_jwt_cache):
        exp1 = time.time() + 3600
        exp2 = time.time() + 7200
        jwt1 = _make_jwt(exp1)
        jwt2 = _make_jwt(exp2)
        put_cached_jwt(jwt1, "oid", "key", None, None)
        put_cached_jwt(jwt2, "oid", "key", None, None)
        result = get_cached_jwt("oid", "key", None, None)
        assert result == jwt2

    def test_noop_when_ephemeral(self, tmp_jwt_cache, monkeypatch):
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        path = _get_cache_path()
        assert not os.path.isfile(path)

    def test_noop_when_no_jwt_cache_env(self, tmp_jwt_cache, monkeypatch):
        monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        path = _get_cache_path()
        assert not os.path.isfile(path)

    def test_noop_when_no_jwt_cache_config(self, tmp_jwt_cache):
        import yaml
        from limacharlie.paths import get_config_path
        config_path = get_config_path()
        with open(config_path, "w") as f:
            yaml.safe_dump({"no_jwt_cache": True}, f)
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        assert not os.path.isfile(tmp_jwt_cache)

    def test_noop_when_jwt_exp_is_negative(self, tmp_jwt_cache):
        """JWT with exp=-1 should still be written because put_cached_jwt
        only checks that _decode_jwt_exp returns non-None, and -1 is a
        valid float. It does not check whether the JWT is actually expired."""
        jwt = _make_jwt(-1)
        put_cached_jwt(jwt, "oid", "key", None, None)
        path = _get_cache_path()
        assert os.path.isfile(path)
        with open(path, "r") as f:
            data = json.load(f)
        entry = list(data.values())[0]
        assert entry["jwt"] == jwt

    def test_noop_when_jwt_has_no_exp(self, tmp_jwt_cache):
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"sub": "user"}).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        put_cached_jwt(jwt, "oid", "key", None, None)
        path = _get_cache_path()
        assert not os.path.isfile(path)

    def test_noop_when_oid_is_none(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), None, "key", None, None)
        path = _get_cache_path()
        assert not os.path.isfile(path)

    def test_creates_parent_dirs(self, tmp_path, monkeypatch):
        from limacharlie.paths import _reset_path_cache
        nested_config = str(tmp_path / "deep" / "nested" / ".limacharlie")
        monkeypatch.setenv("LC_CREDS_FILE", nested_config)
        monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        _reset_cache_disabled()
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        cache_path = nested_config + "_jwt_cache"
        assert os.path.isfile(cache_path)
        _reset_path_cache()

    def test_handles_unwritable_dir_gracefully(self, tmp_path, monkeypatch):
        from limacharlie.paths import _reset_path_cache
        unwritable = str(tmp_path / "noperm")
        os.makedirs(unwritable)
        os.chmod(unwritable, 0o444)
        monkeypatch.setenv("LC_CREDS_FILE", str(os.path.join(unwritable, "config")))
        monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        _reset_cache_disabled()
        exp = time.time() + 3600
        # Should not raise
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        # Restore permissions for cleanup
        os.chmod(unwritable, 0o755)
        _reset_path_cache()


class TestInvalidateCachedJwt:
    def test_removes_specific_entry(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid1", "key1", None, None)
        put_cached_jwt(_make_jwt(exp), "oid2", "key2", None, None)
        invalidate_cached_jwt("oid1", "key1", None, None)
        assert get_cached_jwt("oid1", "key1", None, None) is None
        assert get_cached_jwt("oid2", "key2", None, None) is not None

    def test_leaves_other_entries_intact(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt2 = _make_jwt(exp)
        put_cached_jwt(_make_jwt(exp), "oid1", "key1", None, None)
        put_cached_jwt(jwt2, "oid2", "key2", None, None)
        invalidate_cached_jwt("oid1", "key1", None, None)
        assert get_cached_jwt("oid2", "key2", None, None) == jwt2

    def test_noop_when_entry_missing(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        invalidate_cached_jwt("other-oid", "other-key", None, None)
        assert get_cached_jwt("oid", "key", None, None) is not None

    def test_noop_when_cache_file_missing(self, tmp_jwt_cache):
        # Should not raise
        invalidate_cached_jwt("oid", "key", None, None)


class TestClearJwtCache:
    def test_deletes_cache_file(self, tmp_jwt_cache):
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        path = _get_cache_path()
        assert os.path.isfile(path)
        clear_jwt_cache()
        assert not os.path.isfile(path)

    def test_noop_when_file_missing(self, tmp_jwt_cache):
        # Should not raise
        clear_jwt_cache()

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_clear_removes_symlink_itself(self, tmp_jwt_cache, tmp_path):
        """clear_jwt_cache() should remove the symlink at the cache path,
        not the target file the symlink points to."""
        target = str(tmp_path / "symlink_target")
        with open(target, "w") as f:
            f.write("target content")
        cache_path = _get_cache_path()
        os.symlink(target, cache_path)
        assert os.path.islink(cache_path)
        clear_jwt_cache()
        # The symlink should be removed
        assert not os.path.islink(cache_path)
        # The target file should still exist
        assert os.path.isfile(target)
        with open(target, "r") as f:
            assert f.read() == "target content"


class TestCacheIntegration:
    def test_full_round_trip(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) == jwt

    def test_near_expiry_jwt_not_returned(self, tmp_jwt_cache):
        exp = time.time() + 300  # 5 minutes, within 10-min buffer
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_multiple_cache_keys_coexist(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt1 = _make_jwt(exp)
        jwt2 = _make_jwt(exp + 1)
        put_cached_jwt(jwt1, "oid1", "key1", None, None)
        put_cached_jwt(jwt2, "oid2", "key2", None, None)
        assert get_cached_jwt("oid1", "key1", None, None) == jwt1
        assert get_cached_jwt("oid2", "key2", None, None) == jwt2

    def test_rapid_sequential_put_get(self, tmp_jwt_cache):
        for i in range(20):
            exp = time.time() + 3600
            jwt = _make_jwt(exp)
            put_cached_jwt(jwt, f"oid-{i}", f"key-{i}", None, None)
            assert get_cached_jwt(f"oid-{i}", f"key-{i}", None, None) == jwt

    def test_concurrent_like_puts_both_retrievable(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt_a = _make_jwt(exp)
        jwt_b = _make_jwt(exp + 1)
        put_cached_jwt(jwt_a, "oidA", "keyA", None, None)
        put_cached_jwt(jwt_b, "oidB", "keyB", None, None)
        assert get_cached_jwt("oidA", "keyA", None, None) == jwt_a
        assert get_cached_jwt("oidB", "keyB", None, None) == jwt_b

    def test_cache_survives_process_boundary(self, tmp_jwt_cache):
        """Simulate a 'process boundary' - write with one function, read back."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)

        # Read the raw cache file directly to prove it's on disk
        path = _get_cache_path()
        with open(path, "r") as f:
            raw = json.load(f)
        assert len(raw) == 1
        entry = list(raw.values())[0]
        assert entry["jwt"] == jwt

        # Read back via the normal API
        result = get_cached_jwt("oid", "key", None, None)
        assert result == jwt


class TestOAuthCacheRoundTrip:
    """Verify caching works correctly for the OAuth authentication path."""

    def test_oauth_put_and_get_round_trip(self, tmp_jwt_cache):
        """OAuth-path put uses api_key=None, oauth_creds dict."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        oauth_creds = {"id_token": "id-tok", "refresh_token": "ref-tok"}
        put_cached_jwt(jwt, "oid", None, oauth_creds, None)
        result = get_cached_jwt("oid", None, oauth_creds, None)
        assert result == jwt

    def test_oauth_and_api_key_coexist_independently(self, tmp_jwt_cache):
        """Same OID but different auth methods get separate cache entries."""
        exp = time.time() + 3600
        jwt_api = _make_jwt(exp)
        jwt_oauth = _make_jwt(exp + 1)  # slightly different to distinguish
        oauth_creds = {"id_token": "id", "refresh_token": "ref"}
        put_cached_jwt(jwt_api, "oid", "api-key", None, None)
        put_cached_jwt(jwt_oauth, "oid", None, oauth_creds, None)
        assert get_cached_jwt("oid", "api-key", None, None) == jwt_api
        assert get_cached_jwt("oid", None, oauth_creds, None) == jwt_oauth

    def test_oauth_invalidate_does_not_affect_api_key(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt_api = _make_jwt(exp)
        jwt_oauth = _make_jwt(exp + 1)
        oauth_creds = {"id_token": "id", "refresh_token": "ref"}
        put_cached_jwt(jwt_api, "oid", "api-key", None, None)
        put_cached_jwt(jwt_oauth, "oid", None, oauth_creds, None)
        invalidate_cached_jwt("oid", None, oauth_creds, None)
        assert get_cached_jwt("oid", "api-key", None, None) == jwt_api
        assert get_cached_jwt("oid", None, oauth_creds, None) is None

    def test_oauth_updated_refresh_token_is_new_cache_key(self, tmp_jwt_cache):
        """When OAuth token refresh changes the refresh_token, the old
        cache entry becomes stale and a new one is written."""
        exp = time.time() + 3600
        jwt_old = _make_jwt(exp)
        jwt_new = _make_jwt(exp + 1)
        old_creds = {"id_token": "id1", "refresh_token": "old-ref"}
        new_creds = {"id_token": "id2", "refresh_token": "new-ref"}
        put_cached_jwt(jwt_old, "oid", None, old_creds, None)
        put_cached_jwt(jwt_new, "oid", None, new_creds, None)
        # New creds get the new JWT
        assert get_cached_jwt("oid", None, new_creds, None) == jwt_new
        # Old creds still see the old JWT (stale but valid until expiry)
        assert get_cached_jwt("oid", None, old_creds, None) == jwt_old

    def test_oauth_with_uid(self, tmp_jwt_cache):
        """OAuth path with uid still caches correctly (uid not in OAuth key)."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        oauth_creds = {"id_token": "id", "refresh_token": "ref"}
        # OAuth path: uid is passed but _compute_cache_key ignores it for OAuth
        put_cached_jwt(jwt, "oid", None, oauth_creds, "some-uid")
        result = get_cached_jwt("oid", None, oauth_creds, "some-uid")
        assert result == jwt


class TestCacheEdgeCases:
    def test_corrupt_cache_file_handled(self, tmp_jwt_cache):
        path = _get_cache_path()
        with open(path, "w") as f:
            f.write('{"partial": ')
        assert get_cached_jwt("oid", "key", None, None) is None
        # Next put should overwrite the corrupt file
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) == jwt

    def test_empty_cache_file(self, tmp_jwt_cache):
        path = _get_cache_path()
        with open(path, "w") as f:
            pass
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_wrong_type_for_entry(self, tmp_jwt_cache):
        """Cache entry is a string instead of a dict."""
        path = _get_cache_path()
        key = _compute_cache_key("oid", "key", None, None)
        with open(path, "w") as f:
            json.dump({key: "not a dict"}, f)
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_very_long_jwt(self, tmp_jwt_cache):
        # Create a JWT with a very large payload
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload_data = {"exp": time.time() + 3600, "data": "x" * 100000}
        payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=")
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=")
        jwt = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) == jwt

    def test_unicode_in_oid(self, tmp_jwt_cache):
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid-\u00e9\u00e8\u00ea", "key", None, None)
        assert get_cached_jwt("oid-\u00e9\u00e8\u00ea", "key", None, None) == jwt

    def test_cache_key_collision_resistance(self):
        """Different credential combos should not collide."""
        keys = set()
        combos = [
            ("oid1", "key1", None, None),
            ("oid1", "key2", None, None),
            ("oid2", "key1", None, None),
            ("oid1", "key1", None, "uid1"),
            ("oid1", "key1", None, "uid2"),
            ("oid1", None, {"refresh_token": "rt1"}, None),
            ("oid1", None, {"refresh_token": "rt2"}, None),
        ]
        for combo in combos:
            k = _compute_cache_key(*combo)
            assert k not in keys, f"Collision for {combo}"
            keys.add(k)

    def test_cache_file_is_json_array(self, tmp_jwt_cache):
        """Cache file contains [1,2,3] instead of a dict.

        _load_cache returns {} for non-dict JSON, so get returns None.
        A subsequent put should overwrite the file with a valid dict.
        """
        path = _get_cache_path()
        with open(path, "w") as f:
            json.dump([1, 2, 3], f)
        os.chmod(path, 0o600)
        assert get_cached_jwt("oid", "key", None, None) is None
        # Now put should overwrite the invalid file
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) == jwt

    def test_cache_file_contains_non_utf8_bytes(self, tmp_jwt_cache):
        """Cache file has raw bytes that are not valid UTF-8.

        get_cached_jwt should return None gracefully without raising.
        """
        path = _get_cache_path()
        with open(path, "wb") as f:
            f.write(b"\x80\x81")
        os.chmod(path, 0o600)
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_api_key_and_oauth_with_same_token_do_not_collide(self):
        """If an API key UUID happens to match an OAuth refresh_token UUID,
        they must produce different cache keys (different auth method)."""
        same_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        k_api = _compute_cache_key("oid", same_uuid, None, None)
        k_oauth = _compute_cache_key("oid", None, {"refresh_token": same_uuid}, None)
        assert k_api != k_oauth


class TestIsCacheDisabled:
    def test_not_disabled_by_default(self, tmp_jwt_cache):
        assert _is_cache_disabled() is False

    def test_disabled_by_ephemeral_creds(self, tmp_jwt_cache, monkeypatch):
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        assert _is_cache_disabled() is True

    def test_disabled_by_no_jwt_cache_env(self, tmp_jwt_cache, monkeypatch):
        monkeypatch.setenv("LC_NO_JWT_CACHE", "1")
        assert _is_cache_disabled() is True

    def test_disabled_by_config_option(self, tmp_jwt_cache):
        import yaml
        from limacharlie.paths import get_config_path
        config_path = get_config_path()
        with open(config_path, "w") as f:
            yaml.safe_dump({"no_jwt_cache": True}, f)
        assert _is_cache_disabled() is True

    def test_not_disabled_when_config_option_false(self, tmp_jwt_cache):
        import yaml
        from limacharlie.paths import get_config_path
        config_path = get_config_path()
        with open(config_path, "w") as f:
            yaml.safe_dump({"no_jwt_cache": False}, f)
        assert _is_cache_disabled() is False

    def test_not_disabled_when_config_option_absent(self, tmp_jwt_cache):
        import yaml
        from limacharlie.paths import get_config_path
        config_path = get_config_path()
        with open(config_path, "w") as f:
            yaml.safe_dump({"oid": "test"}, f)
        assert _is_cache_disabled() is False


class TestSymlinkProtection:
    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_put_refuses_symlinked_cache_file(self, tmp_jwt_cache, tmp_path):
        """Attacker places symlink at cache path - put must not follow it."""
        target = str(tmp_path / "attacker_target")
        with open(target, "w") as f:
            f.write("original")
        # Create symlink at the expected cache path
        cache_path = _get_cache_path()
        os.symlink(target, cache_path)
        exp = time.time() + 3600
        # put_cached_jwt should silently fail (best-effort, no raise)
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        # Verify target file was NOT overwritten
        with open(target, "r") as f:
            assert f.read() == "original"

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_get_refuses_symlinked_cache_file(self, tmp_jwt_cache, tmp_path):
        """Attacker places symlink to feed controlled JWT data."""
        # Write a valid-looking cache file as the "attacker"
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        from limacharlie.jwt_cache import _compute_cache_key
        key = _compute_cache_key("oid", "key", None, None)
        fake_cache = json.dumps({key: {"jwt": jwt}})
        target = str(tmp_path / "attacker_cache")
        with open(target, "w") as f:
            f.write(fake_cache)
        # Place symlink at cache path
        cache_path = _get_cache_path()
        os.symlink(target, cache_path)
        # get should refuse to read through symlink
        assert get_cached_jwt("oid", "key", None, None) is None

    @pytest.mark.skipif(os.name == "nt", reason="Unix-only symlink test")
    def test_invalidate_refuses_symlinked_cache_file(self, tmp_jwt_cache, tmp_path):
        """invalidate should not follow symlinks either."""
        target = str(tmp_path / "target")
        with open(target, "w") as f:
            f.write("{}")
        cache_path = _get_cache_path()
        os.symlink(target, cache_path)
        # Should silently fail, not modify target
        invalidate_cached_jwt("oid", "key", None, None)


class TestCrossplatformPaths:
    def test_cache_path_from_config_dir(self, monkeypatch, tmp_path):
        """JWT cache goes into the config directory as jwt_cache.json."""
        from limacharlie.paths import _reset_path_cache
        config_dir = str(tmp_path / "myconfig")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        monkeypatch.delenv("LC_CREDS_FILE", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        assert _get_cache_path() == os.path.join(config_dir, "jwt_cache.json")
        _reset_path_cache()

    def test_cache_path_from_creds_file_env(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE produces sibling cache path (legacy behavior)."""
        from limacharlie.paths import _reset_path_cache
        custom = str(tmp_path / "custom" / "config")
        monkeypatch.setenv("LC_CREDS_FILE", custom)
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        assert _get_cache_path() == custom + "_jwt_cache"
        _reset_path_cache()

    def test_path_with_spaces(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE with spaces produces correct sibling path."""
        from limacharlie.paths import _reset_path_cache
        spaced = str(tmp_path / "path with spaces" / ".limacharlie")
        monkeypatch.setenv("LC_CREDS_FILE", spaced)
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        _reset_path_cache()
        assert _get_cache_path() == spaced + "_jwt_cache"
        _reset_path_cache()
