"""Centralized path resolution for all LimaCharlie on-disk files.

All file paths used by the SDK and CLI are resolved through this module.
This ensures consistent behavior across platforms and provides a single
place to manage the legacy-to-new-directory migration.

Path layout (new):
    Unix:    ~/.limacharlie.d/config.yaml
             ~/.limacharlie.d/jwt_cache.json
             ~/.limacharlie.d/search_checkpoints/
    Windows: %APPDATA%/limacharlie/config.yaml
             %APPDATA%/limacharlie/jwt_cache.json
             %APPDATA%/limacharlie/search_checkpoints/

Path layout (legacy):
    All platforms: ~/.limacharlie           (config)
                   ~/.limacharlie_jwt_cache (JWT cache)
                   ~/.limacharlie.d/search_checkpoints/  (checkpoints)

Resolution order for config path:
    1. LC_CREDS_FILE env var (overrides everything, exact file path)
    2. LC_LEGACY_CONFIG=1 (forces old flat-file layout)
    3. LC_CONFIG_DIR env var (overrides base directory, uses new layout within)
    4. New location if it exists
    5. Legacy location if it exists (with deprecation warning)
    6. New location (fresh install default)

Env vars:
    LC_CONFIG_DIR     - Override the base config directory
    LC_CREDS_FILE     - Override the config file path directly (existing)
    LC_LEGACY_CONFIG  - Force legacy flat-file layout (set to "1")
"""

from __future__ import annotations

import os
import sys
import warnings


# Environment variable names
ENV_CONFIG_DIR = "LC_CONFIG_DIR"
ENV_CREDS_FILE = "LC_CREDS_FILE"
ENV_LEGACY_CONFIG = "LC_LEGACY_CONFIG"

# Legacy paths (pre-migration)
_LEGACY_CONFIG_FILE = os.path.expanduser("~/.limacharlie")
_LEGACY_JWT_CACHE_FILE = os.path.expanduser("~/.limacharlie_jwt_cache")

# New layout file names within the config directory
_CONFIG_FILENAME = "config.yaml"
_JWT_CACHE_FILENAME = "jwt_cache.json"
_CHECKPOINT_DIRNAME = "search_checkpoints"

# Per-process caches. Each CLI invocation is a separate process so
# paths won't change mid-execution. Avoids repeated env var lookups
# and filesystem stat calls.
_cached_config_dir: str | None = None
_cached_config_path: str | None = None
_cached_jwt_cache_path: str | None = None
_cached_checkpoint_dir: str | None = None
_deprecation_warned: bool = False


def _default_config_dir() -> str:
    """Return the platform-specific default config directory.

    Unix (Linux/macOS): ~/.limacharlie.d
    Windows: %APPDATA%/limacharlie (falls back to ~/.limacharlie.d
        if APPDATA is not set)

    Returns:
        Absolute path to the default config directory.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "limacharlie")
    return os.path.expanduser("~/.limacharlie.d")


def is_legacy_mode() -> bool:
    """Return True if legacy config layout is forced via LC_LEGACY_CONFIG=1."""
    return os.environ.get(ENV_LEGACY_CONFIG) == "1"


def _warn_legacy_path(old_path: str, new_path: str) -> None:
    """Emit a deprecation warning for legacy config path usage.

    Uses Python's warnings module which deduplicates by default
    (one warning per unique message+location per process).

    Args:
        old_path: The legacy path currently in use.
        new_path: The new path the user should migrate to.
    """
    global _deprecation_warned
    if _deprecation_warned:
        return
    _deprecation_warned = True
    # Write directly to stderr for CLI visibility. Python's warnings module
    # respects filters that may suppress DeprecationWarning in some contexts
    # (e.g. when running under -W ignore), so we also emit via warnings for
    # programmatic consumers.
    msg = (
        f"Using legacy config location '{old_path}'. "
        f"Run 'limacharlie config migrate' to move to '{new_path}'. "
        f"Set LC_LEGACY_CONFIG=1 to suppress this warning."
    )
    warnings.warn(msg, DeprecationWarning, stacklevel=3)


def get_config_dir() -> str:
    """Return the base config directory path.

    Resolution order:
        1. LC_CONFIG_DIR env var
        2. LC_LEGACY_CONFIG=1 - parent directory of legacy config file
        3. Platform-specific default

    The returned directory may not exist yet. Callers that need to write
    files should create it via file_utils.secure_makedirs().

    Returns:
        Absolute path to the config directory.
    """
    global _cached_config_dir
    if _cached_config_dir is not None:
        return _cached_config_dir

    # 1. Explicit override
    env_dir = os.environ.get(ENV_CONFIG_DIR)
    if env_dir:
        _cached_config_dir = os.path.abspath(env_dir)
        return _cached_config_dir

    # 2. Legacy mode forced
    if is_legacy_mode():
        # In legacy mode, the "config dir" is the parent of the flat file.
        # This means JWT cache and checkpoints derive from the home directory.
        _cached_config_dir = os.path.dirname(_LEGACY_CONFIG_FILE)
        return _cached_config_dir

    # 3. Platform default
    _cached_config_dir = _default_config_dir()
    return _cached_config_dir


def get_config_path() -> str:
    """Return the path to the YAML config file.

    Resolution order:
        1. LC_CREDS_FILE env var (overrides everything)
        2. LC_LEGACY_CONFIG=1 - legacy ~/.limacharlie
        3. New location <config_dir>/config.yaml if it exists
        4. Legacy ~/.limacharlie if it exists (with deprecation warning)
        5. New location (fresh install default)

    Returns:
        Absolute path to the config file.
    """
    global _cached_config_path
    if _cached_config_path is not None:
        return _cached_config_path

    # 1. Explicit file override
    creds_file = os.environ.get(ENV_CREDS_FILE)
    if creds_file:
        _cached_config_path = os.path.abspath(creds_file)
        return _cached_config_path

    # 2. Legacy mode forced
    if is_legacy_mode():
        _cached_config_path = _LEGACY_CONFIG_FILE
        return _cached_config_path

    # 3. If LC_CONFIG_DIR is explicitly set, always use new layout within it
    # (no legacy fallback - the user has explicitly chosen a directory).
    env_dir = os.environ.get(ENV_CONFIG_DIR)
    if env_dir:
        _cached_config_path = os.path.join(get_config_dir(), _CONFIG_FILENAME)
        return _cached_config_path

    # 4. Check new location
    new_path = os.path.join(get_config_dir(), _CONFIG_FILENAME)
    if os.path.exists(new_path):
        _cached_config_path = new_path
        return _cached_config_path

    # 5. Check legacy location (with deprecation warning)
    if os.path.exists(_LEGACY_CONFIG_FILE):
        _warn_legacy_path(_LEGACY_CONFIG_FILE, new_path)
        _cached_config_path = _LEGACY_CONFIG_FILE
        return _cached_config_path

    # 6. Fresh install - use new location
    _cached_config_path = new_path
    return _cached_config_path


def get_jwt_cache_path() -> str:
    """Return the path to the JWT cache file.

    When LC_CREDS_FILE is set, the JWT cache is a sibling file with
    '_jwt_cache' appended (preserving existing behavior). Otherwise
    the cache lives in the config directory.

    When LC_LEGACY_CONFIG=1, uses the legacy sibling path.

    For non-override cases, follows the same new-then-legacy-fallback
    pattern as get_config_path().

    Returns:
        Absolute path to the JWT cache file.
    """
    global _cached_jwt_cache_path
    if _cached_jwt_cache_path is not None:
        return _cached_jwt_cache_path

    # When LC_CREDS_FILE is set, JWT cache is a sibling file (existing behavior)
    creds_file = os.environ.get(ENV_CREDS_FILE)
    if creds_file:
        _cached_jwt_cache_path = os.path.abspath(creds_file) + "_jwt_cache"
        return _cached_jwt_cache_path

    # Legacy mode forced
    if is_legacy_mode():
        _cached_jwt_cache_path = _LEGACY_JWT_CACHE_FILE
        return _cached_jwt_cache_path

    # If LC_CONFIG_DIR is explicitly set, always use new layout
    env_dir = os.environ.get(ENV_CONFIG_DIR)
    if env_dir:
        _cached_jwt_cache_path = os.path.join(get_config_dir(), _JWT_CACHE_FILENAME)
        return _cached_jwt_cache_path

    # New location
    new_path = os.path.join(get_config_dir(), _JWT_CACHE_FILENAME)

    # If new config dir is in use (config.yaml exists there), use new jwt path
    new_config = os.path.join(get_config_dir(), _CONFIG_FILENAME)
    if os.path.exists(new_config):
        _cached_jwt_cache_path = new_path
        return _cached_jwt_cache_path

    # If legacy jwt cache exists and legacy config is in use, use legacy path
    if os.path.exists(_LEGACY_JWT_CACHE_FILE) and os.path.exists(_LEGACY_CONFIG_FILE):
        _cached_jwt_cache_path = _LEGACY_JWT_CACHE_FILE
        return _cached_jwt_cache_path

    # Fresh install or already migrated config but no jwt cache yet
    _cached_jwt_cache_path = new_path
    return _cached_jwt_cache_path


def get_checkpoint_dir() -> str:
    """Return the path to the search checkpoints directory.

    When LC_CREDS_FILE is set, checkpoints go into a .d sibling directory
    (preserving existing behavior). Otherwise they live in the config dir.

    Returns:
        Absolute path to the checkpoints directory.
    """
    global _cached_checkpoint_dir
    if _cached_checkpoint_dir is not None:
        return _cached_checkpoint_dir

    # When LC_CREDS_FILE is set, use the existing sibling-dir convention
    creds_file = os.environ.get(ENV_CREDS_FILE)
    if creds_file:
        config_path = os.path.abspath(creds_file)
        config_dir = os.path.dirname(config_path)
        config_base = os.path.basename(config_path)
        if os.path.isdir(config_path):
            _cached_checkpoint_dir = os.path.join(config_path, _CHECKPOINT_DIRNAME)
        else:
            _cached_checkpoint_dir = os.path.join(
                config_dir, config_base + ".d", _CHECKPOINT_DIRNAME
            )
        return _cached_checkpoint_dir

    # Standard resolution: config_dir/search_checkpoints/
    _cached_checkpoint_dir = os.path.join(get_config_dir(), _CHECKPOINT_DIRNAME)
    return _cached_checkpoint_dir


def get_all_paths() -> dict[str, str]:
    """Return a dict of all resolved paths for diagnostic display.

    Returns:
        Dict with keys: config_dir, config_file, jwt_cache, checkpoint_dir.
    """
    return {
        "config_dir": get_config_dir(),
        "config_file": get_config_path(),
        "jwt_cache": get_jwt_cache_path(),
        "checkpoint_dir": get_checkpoint_dir(),
    }


def get_legacy_paths() -> dict[str, str]:
    """Return a dict of legacy file paths for migration purposes.

    Returns:
        Dict with keys: config_file, jwt_cache. Values are the
        legacy paths regardless of current resolution.
    """
    return {
        "config_file": _LEGACY_CONFIG_FILE,
        "jwt_cache": _LEGACY_JWT_CACHE_FILE,
    }


def _reset_path_cache() -> None:
    """Reset all per-process path caches. For testing only."""
    global _cached_config_dir, _cached_config_path
    global _cached_jwt_cache_path, _cached_checkpoint_dir
    global _deprecation_warned
    _cached_config_dir = None
    _cached_config_path = None
    _cached_jwt_cache_path = None
    _cached_checkpoint_dir = None
    _deprecation_warned = False
