"""On-disk JWT caching for LimaCharlie CLI.

Caches JWTs to disk so that repeated CLI invocations within the same
hour reuse a single JWT instead of requesting a new one each time.
Each invocation is a separate process, so caching must be file-based.

Cache file location:
- Default: ~/.limacharlie.d/jwt_cache.json (new layout)
- Legacy fallback: ~/.limacharlie_jwt_cache
- Respects LC_CREDS_FILE: if config is at /foo/bar, cache goes to /foo/bar_jwt_cache
- Respects LC_CONFIG_DIR: uses <dir>/jwt_cache.json
- Respects LC_EPHEMERAL_CREDS: no disk caching when set
- Respects LC_NO_JWT_CACHE: no disk caching when set
- Respects no_jwt_cache config option: no disk caching when true

Format: JSON dict keyed by SHA-256 hash of credential identity.

Concurrency model: last-write-wins with atomic writes (tempfile + move).
No file locking. Worst case on concurrent access is a redundant JWT request.

Expiry buffer: 10 minutes. A cached JWT is only reused if it has more
than 10 minutes remaining before expiration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

from .config import ENV_EPHEMERAL_CREDS, ENV_NO_JWT_CACHE, load_config
from .file_utils import atomic_write, safe_open_read, secure_makedirs
from .paths import get_jwt_cache_path as _resolve_jwt_cache_path

# Cached JWT must have at least this many seconds remaining to be reused.
_EXPIRY_BUFFER_SECONDS = 600  # 10 minutes

# Per-process cache for the disabled check. Each CLI invocation is a
# separate process, so evaluating once is sufficient - the config file
# and env vars won't change mid-process. Avoids repeated YAML parsing.
_cache_disabled: bool | None = None


def _is_cache_disabled() -> bool:
    """Check if JWT caching is disabled via env var or config file.

    Result is cached for the process lifetime to avoid repeated disk I/O
    and YAML parsing. Each CLI invocation is a fresh process so
    re-evaluation is unnecessary.

    Note: load_config() itself is also per-process cached, so even the
    first call here doesn't cause a redundant YAML parse if
    resolve_credentials() already loaded the config.

    Caching is disabled when any of:
    - LC_NO_JWT_CACHE env var is set (any truthy value)
    - LC_EPHEMERAL_CREDS env var is set
    - no_jwt_cache: true in the config file

    Returns:
        True if caching should be skipped.
    """
    global _cache_disabled
    if _cache_disabled is not None:
        return _cache_disabled

    if os.environ.get(ENV_EPHEMERAL_CREDS):
        _cache_disabled = True
        return True
    if os.environ.get(ENV_NO_JWT_CACHE):
        _cache_disabled = True
        return True
    try:
        config = load_config()
        if config and config.get("no_jwt_cache"):
            _cache_disabled = True
            return True
    except Exception:
        pass
    _cache_disabled = False
    return False


def _reset_cache_disabled() -> None:
    """Reset the cached disabled state. For testing only."""
    global _cache_disabled
    _cache_disabled = None


def _get_cache_path() -> str:
    """Return the JWT cache file path, resolved via paths module.

    Respects LC_CREDS_FILE, LC_CONFIG_DIR, LC_LEGACY_CONFIG, and the
    new-then-legacy fallback logic in paths.py.

    Returns:
        Absolute path to the JWT cache file.
    """
    return _resolve_jwt_cache_path()


def _compute_cache_key(
    oid: str | None,
    api_key: str | None,
    oauth_creds: dict[str, str] | None,
    uid: str | None,
) -> str | None:
    """Compute a SHA-256 cache key from credential identity.

    Returns None if there is insufficient credential information
    to form a meaningful cache key.

    Uses null byte as separator to prevent collisions from values
    containing the delimiter (e.g. oid="a:b" + key="c" vs
    oid="a" + key="b:c" would collide with ":" but not with "\\0").

    Args:
        oid: organization ID.
        api_key: API key (for API key auth path).
        oauth_creds: OAuth credentials dict (for OAuth auth path).
        uid: user ID.

    Returns:
        Hex-encoded SHA-256 hash string, or None.
    """
    if oid is None:
        return None

    # Tag with auth method to prevent collisions between API key and
    # OAuth paths (e.g. if an api_key UUID happens to equal a
    # refresh_token UUID, they must not share a cache entry).
    parts = [oid]
    if api_key is not None:
        parts.append("apikey")
        parts.append(api_key)
        if uid is not None:
            parts.append(uid)
    elif oauth_creds is not None:
        parts.append("oauth")
        refresh_token = oauth_creds.get("refresh_token", "")
        parts.append(refresh_token)
    else:
        return None

    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def _decode_jwt_exp(jwt_str: str) -> float | None:
    """Extract the exp claim from a JWT without signature verification.

    Decodes only the payload (middle segment) via base64url to read
    the expiration timestamp.

    Args:
        jwt_str: the JWT string (header.payload.signature).

    Returns:
        The exp claim as a float, or None if parsing fails.
    """
    try:
        parts = jwt_str.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Add padding if needed for base64url
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        exp = payload.get("exp")
        if exp is None:
            return None
        return float(exp)
    except Exception:
        return None


def _load_cache() -> dict[str, Any]:
    """Load the cache file as a dict.

    Uses safe_open_read to reject symlinks at the cache path,
    preventing symlink attacks that could feed arbitrary data.

    Returns:
        Cache dict, or empty dict on any error (including symlink rejection).
    """
    try:
        path = _get_cache_path()
        if not os.path.isfile(path):
            return {}
        raw = safe_open_read(path)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    """Write the cache dict to disk atomically. Best-effort, never raises.

    Args:
        cache: the full cache dict to persist.
    """
    try:
        path = _get_cache_path()
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            secure_makedirs(parent)
        content = json.dumps(cache).encode()
        atomic_write(path, content)
    except Exception:
        pass


def get_cached_jwt(
    oid: str | None,
    api_key: str | None,
    oauth_creds: dict[str, str] | None,
    uid: str | None,
) -> str | None:
    """Return a cached JWT if one exists and is still valid.

    A JWT is considered valid if it has more than 10 minutes remaining
    before expiration (the _EXPIRY_BUFFER_SECONDS constant).

    Args:
        oid: organization ID.
        api_key: API key.
        oauth_creds: OAuth credentials dict.
        uid: user ID.

    Returns:
        The cached JWT string, or None if no valid cache entry exists.
    """
    if _is_cache_disabled():
        return None

    cache_key = _compute_cache_key(oid, api_key, oauth_creds, uid)
    if cache_key is None:
        return None

    cache = _load_cache()
    entry = cache.get(cache_key)
    if not isinstance(entry, dict):
        return None

    jwt_str = entry.get("jwt")
    if not isinstance(jwt_str, str):
        return None

    exp = _decode_jwt_exp(jwt_str)
    if exp is None:
        return None

    if time.time() + _EXPIRY_BUFFER_SECONDS >= exp:
        return None

    return jwt_str


def put_cached_jwt(
    jwt_str: str,
    oid: str | None,
    api_key: str | None,
    oauth_creds: dict[str, str] | None,
    uid: str | None,
) -> None:
    """Write a JWT to the disk cache.

    No-op when caching is disabled (LC_EPHEMERAL_CREDS, LC_NO_JWT_CACHE,
    or no_jwt_cache config option), when the JWT has no parseable exp
    claim, or when insufficient credential information is available.

    Args:
        jwt_str: the JWT string to cache.
        oid: organization ID.
        api_key: API key.
        oauth_creds: OAuth credentials dict.
        uid: user ID.
    """
    if _is_cache_disabled():
        return

    cache_key = _compute_cache_key(oid, api_key, oauth_creds, uid)
    if cache_key is None:
        return

    exp = _decode_jwt_exp(jwt_str)
    if exp is None:
        return

    cache = _load_cache()
    cache[cache_key] = {"jwt": jwt_str}
    _save_cache(cache)


def invalidate_cached_jwt(
    oid: str | None,
    api_key: str | None,
    oauth_creds: dict[str, str] | None,
    uid: str | None,
) -> None:
    """Remove a specific JWT entry from the cache.

    No-op if the entry does not exist or the cache file is missing.

    Args:
        oid: organization ID.
        api_key: API key.
        oauth_creds: OAuth credentials dict.
        uid: user ID.
    """
    cache_key = _compute_cache_key(oid, api_key, oauth_creds, uid)
    if cache_key is None:
        return

    cache = _load_cache()
    if cache_key in cache:
        del cache[cache_key]
        _save_cache(cache)


def clear_jwt_cache() -> None:
    """Delete the entire JWT cache file.

    No-op if the file does not exist. Used by 'auth logout'.
    """
    try:
        path = _get_cache_path()
        if os.path.isfile(path):
            os.unlink(path)
    except Exception:
        pass
