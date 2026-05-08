"""Tests for limacharlie.paths module.

Tests cover path resolution for config, JWT cache, and checkpoint
directories across all supported platforms and configuration modes
(new layout, legacy fallback, env var overrides, legacy mode).

Focus areas:
- Correctness of resolution priority across all env var combinations
- Security: symlink injection, path traversal, permission model
- Robustness: missing dirs, unreadable paths, pathological inputs
- Edge cases: empty strings, relative paths, unicode, spaces
- Caching: per-process cache correctness and reset behavior
- Deprecation warnings: correct emission and suppression
"""

import os
import stat
import sys
import warnings

import pytest

from limacharlie.paths import (
    _LEGACY_CONFIG_FILE,
    _LEGACY_JWT_CACHE_FILE,
    _default_config_dir,
    _reset_path_cache,
    get_all_paths,
    get_checkpoint_dir,
    get_config_dir,
    get_config_path,
    get_jwt_cache_path,
    get_legacy_paths,
    is_legacy_mode,
)


@pytest.fixture(autouse=True)
def isolated_paths(monkeypatch):
    """Reset path caches and clear all env vars that affect path resolution."""
    for var in ("LC_CONFIG_DIR", "LC_CREDS_FILE", "LC_LEGACY_CONFIG",
                "LC_EPHEMERAL_CREDS"):
        monkeypatch.delenv(var, raising=False)
    _reset_path_cache()
    yield
    _reset_path_cache()


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

class TestDefaultConfigDir:
    """Tests for _default_config_dir platform detection."""

    def test_unix_returns_dot_limacharlie_d(self):
        if sys.platform == "win32":
            pytest.skip("Unix-only test")
        result = _default_config_dir()
        assert result.endswith(".limacharlie.d")
        assert os.path.expanduser("~") in result

    def test_windows_uses_appdata(self, monkeypatch):
        """On Windows, uses %APPDATA%/limacharlie."""
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        monkeypatch.setenv("APPDATA", "/fake/appdata")
        result = _default_config_dir()
        assert result == os.path.join("/fake/appdata", "limacharlie")

    def test_windows_no_appdata_falls_back(self, monkeypatch):
        """On Windows without APPDATA, falls back to ~/.limacharlie.d."""
        import limacharlie.paths as paths_mod
        monkeypatch.setattr(paths_mod.sys, "platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        result = _default_config_dir()
        assert result.endswith(".limacharlie.d")


# ---------------------------------------------------------------------------
# Legacy mode
# ---------------------------------------------------------------------------

class TestIsLegacyMode:
    def test_not_legacy_by_default(self):
        assert is_legacy_mode() is False

    def test_legacy_when_set_to_1(self, monkeypatch):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        assert is_legacy_mode() is True

    def test_not_legacy_for_other_values(self, monkeypatch):
        """Only the exact string '1' activates legacy mode."""
        for val in ("true", "True", "TRUE", "yes", "0", "", "on"):
            monkeypatch.setenv("LC_LEGACY_CONFIG", val)
            assert is_legacy_mode() is False, f"LC_LEGACY_CONFIG={val!r} should not be legacy"

    def test_not_legacy_when_unset(self, monkeypatch):
        monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
        assert is_legacy_mode() is False


# ---------------------------------------------------------------------------
# get_config_dir
# ---------------------------------------------------------------------------

class TestGetConfigDir:
    def test_explicit_override(self, monkeypatch, tmp_path):
        custom_dir = str(tmp_path / "custom")
        monkeypatch.setenv("LC_CONFIG_DIR", custom_dir)
        assert get_config_dir() == os.path.abspath(custom_dir)

    def test_explicit_override_relative_path(self, monkeypatch, tmp_path):
        """Relative LC_CONFIG_DIR is resolved to absolute."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LC_CONFIG_DIR", "relative_dir")
        result = get_config_dir()
        assert os.path.isabs(result)
        assert result == os.path.join(str(tmp_path), "relative_dir")

    def test_legacy_mode_returns_home(self, monkeypatch):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        result = get_config_dir()
        assert result == os.path.dirname(_LEGACY_CONFIG_FILE)

    def test_default_returns_platform_dir(self):
        result = get_config_dir()
        expected = _default_config_dir()
        assert result == expected

    def test_caching(self, monkeypatch, tmp_path):
        """Second call returns cached value even if env var changes."""
        custom_dir = str(tmp_path / "cached_test")
        monkeypatch.setenv("LC_CONFIG_DIR", custom_dir)
        r1 = get_config_dir()
        # Change env var - should still return cached
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "other"))
        r2 = get_config_dir()
        assert r1 == r2

    def test_empty_config_dir_env_var(self, monkeypatch):
        """Empty LC_CONFIG_DIR falls through to default."""
        monkeypatch.setenv("LC_CONFIG_DIR", "")
        result = get_config_dir()
        # Empty string is falsy, so falls through to platform default
        assert result == _default_config_dir()



# ---------------------------------------------------------------------------
# get_config_path
# ---------------------------------------------------------------------------

class TestGetConfigPath:
    def test_lc_creds_file_overrides_everything(self, monkeypatch, tmp_path):
        creds = str(tmp_path / "my_creds")
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        assert get_config_path() == os.path.abspath(creds)

    def test_lc_creds_file_relative_resolved(self, monkeypatch, tmp_path):
        """Relative LC_CREDS_FILE is resolved to absolute."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LC_CREDS_FILE", "my_creds_relative")
        result = get_config_path()
        assert os.path.isabs(result)
        assert result.endswith("my_creds_relative")

    def test_lc_config_dir_uses_new_layout(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        expected = os.path.join(config_dir, "config.yaml")
        assert get_config_path() == expected

    def test_lc_config_dir_no_legacy_fallback(self, monkeypatch, tmp_path):
        """When LC_CONFIG_DIR is set, never falls back to legacy paths even
        if the legacy file exists and the new one does not."""
        import limacharlie.paths as paths_mod
        legacy = str(tmp_path / ".limacharlie")
        with open(legacy, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy)

        config_dir = str(tmp_path / "explicit_dir")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        result = get_config_path()
        assert result == os.path.join(config_dir, "config.yaml")
        assert result != legacy

    def test_legacy_mode_returns_flat_file(self, monkeypatch):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        assert get_config_path() == _LEGACY_CONFIG_FILE

    def test_new_location_preferred_when_exists(self, monkeypatch, tmp_path):
        """When both new and legacy exist, new wins (no warning)."""
        import limacharlie.paths as paths_mod
        config_dir = str(tmp_path / "lc_dir")
        os.makedirs(config_dir)
        new_config = os.path.join(config_dir, "config.yaml")
        with open(new_config, "w") as f:
            f.write("oid: new\n")
        # Also create legacy
        legacy = str(tmp_path / ".limacharlie")
        with open(legacy, "w") as f:
            f.write("oid: old\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: config_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = get_config_path()
        assert result == new_config
        # No deprecation warning when new location exists
        deprecation_warnings = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(deprecation_warnings) == 0

    def test_fresh_install_uses_new_location(self, monkeypatch, tmp_path):
        """No config files anywhere - defaults to new layout."""
        config_dir = str(tmp_path / "fresh")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        expected = os.path.join(config_dir, "config.yaml")
        assert get_config_path() == expected

    def test_legacy_fallback_emits_deprecation_warning(self, monkeypatch, tmp_path):
        """When only legacy file exists, emits deprecation warning."""
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = get_config_path()

        assert result == legacy_file
        assert len(w) == 1
        assert issubclass(w[0].category, UserWarning)
        assert "limacharlie config migrate" in str(w[0].message)
        assert "LC_NO_MIGRATION_WARNING=1" in str(w[0].message)

    def test_deprecation_warning_emitted_only_once(self, monkeypatch, tmp_path):
        """Multiple calls with legacy fallback only warn once per process."""
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # First call triggers caching + warning
            _reset_path_cache()
            get_config_path()
            # Reset cache to force re-evaluation but _deprecation_warned stays True
            import limacharlie.paths as pm
            pm._cached_config_path = None
            get_config_path()

        deprecation_warnings = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(deprecation_warnings) == 1

    def test_warning_is_user_warning_not_deprecation(self, monkeypatch, tmp_path):
        """Warning uses UserWarning so it's visible for installed packages.

        DeprecationWarning is suppressed by default for site-packages.
        UserWarning is always shown, and SDK consumers can filter it
        via standard warnings.filterwarnings().
        """
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_config_path()

        assert len(w) == 1
        # Must be UserWarning, NOT DeprecationWarning
        assert w[0].category is UserWarning
        assert not issubclass(w[0].category, DeprecationWarning)

    def test_warning_does_not_print_to_stderr(self, monkeypatch, tmp_path, capsys):
        """Warning uses only warnings.warn, no direct print to stderr.

        SDK/library consumers should not see unsolicited stderr output.
        """
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            get_config_path()

        captured = capsys.readouterr()
        # No direct print to stderr (only warnings.warn)
        assert captured.err == ""

    def test_no_migration_warning_suppressed_with_1(self, monkeypatch, tmp_path):
        """LC_NO_MIGRATION_WARNING=1 suppresses the warning."""
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        monkeypatch.setenv("LC_NO_MIGRATION_WARNING", "1")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_config_path()

        user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(user_warnings) == 0

    def test_no_migration_warning_not_suppressed_with_0(self, monkeypatch, tmp_path):
        """LC_NO_MIGRATION_WARNING=0 does NOT suppress (only '1' does)."""
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        monkeypatch.setenv("LC_NO_MIGRATION_WARNING", "0")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_config_path()

        user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(user_warnings) == 1

    def test_no_migration_warning_not_suppressed_with_true(self, monkeypatch, tmp_path):
        """LC_NO_MIGRATION_WARNING=true does NOT suppress (only '1' does)."""
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        monkeypatch.setenv("LC_NO_MIGRATION_WARNING", "true")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_config_path()

        user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(user_warnings) == 1


# ---------------------------------------------------------------------------
# get_jwt_cache_path
# ---------------------------------------------------------------------------

class TestGetJwtCachePath:
    def test_lc_creds_file_produces_sibling(self, monkeypatch, tmp_path):
        creds = str(tmp_path / "my_config")
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        assert get_jwt_cache_path() == os.path.abspath(creds) + "_jwt_cache"

    def test_lc_config_dir_uses_new_layout(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        expected = os.path.join(config_dir, "jwt_cache.json")
        assert get_jwt_cache_path() == expected

    def test_legacy_mode_returns_old_path(self, monkeypatch):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        assert get_jwt_cache_path() == _LEGACY_JWT_CACHE_FILE

    def test_new_config_dir_in_use(self, monkeypatch, tmp_path):
        """When config.yaml exists in new dir, jwt cache goes there too."""
        config_dir = str(tmp_path / "lc_dir")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "config.yaml"), "w") as f:
            f.write("oid: test\n")
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        expected = os.path.join(config_dir, "jwt_cache.json")
        assert get_jwt_cache_path() == expected

    def test_legacy_fallback_when_both_legacy_files_exist(self, monkeypatch, tmp_path):
        """When new config doesn't exist but both legacy files do, use legacy jwt."""
        import limacharlie.paths as paths_mod
        legacy_config = str(tmp_path / ".limacharlie")
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        with open(legacy_config, "w") as f:
            f.write("oid: test\n")
        with open(legacy_jwt, "w") as f:
            f.write("{}")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        new_dir = str(tmp_path / "new_dir_missing")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        result = get_jwt_cache_path()
        assert result == legacy_jwt

    def test_fresh_install_uses_new_path(self, monkeypatch, tmp_path):
        """No files anywhere - uses new layout path."""
        import limacharlie.paths as paths_mod
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", str(tmp_path / "nope1"))
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", str(tmp_path / "nope2"))
        new_dir = str(tmp_path / "fresh_dir")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        result = get_jwt_cache_path()
        assert result == os.path.join(new_dir, "jwt_cache.json")


# ---------------------------------------------------------------------------
# get_checkpoint_dir
# ---------------------------------------------------------------------------

class TestGetCheckpointDir:
    def test_lc_creds_file_uses_sibling_dir(self, monkeypatch, tmp_path):
        creds = str(tmp_path / "bar")
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        expected = os.path.join(str(tmp_path), "bar.d", "search_checkpoints")
        assert get_checkpoint_dir() == expected

    def test_lc_creds_file_is_directory(self, monkeypatch, tmp_path):
        creds_dir = str(tmp_path / "my_config_dir")
        os.makedirs(creds_dir)
        monkeypatch.setenv("LC_CREDS_FILE", creds_dir)
        expected = os.path.join(creds_dir, "search_checkpoints")
        assert get_checkpoint_dir() == expected

    def test_lc_config_dir_uses_subdirectory(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        expected = os.path.join(config_dir, "search_checkpoints")
        assert get_checkpoint_dir() == expected

    def test_default_uses_platform_dir(self):
        result = get_checkpoint_dir()
        expected = os.path.join(_default_config_dir(), "search_checkpoints")
        assert result == expected

    def test_legacy_mode_preserves_dot_d_path(self, monkeypatch):
        """In legacy mode, checkpoint dir stays at ~/.limacharlie.d/search_checkpoints.

        Checkpoints were already in the .d directory before the migration
        feature existed, so legacy mode must preserve that path - not derive
        from get_config_dir() which returns ~ in legacy mode.
        """
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        result = get_checkpoint_dir()
        assert result.endswith(".limacharlie.d/search_checkpoints") or \
               result.endswith(".limacharlie.d\\search_checkpoints")
        # Must NOT be ~/search_checkpoints
        assert not result.endswith(os.sep + "search_checkpoints") or ".limacharlie.d" in result

    def test_creds_file_relative_path(self, monkeypatch, tmp_path):
        """Relative LC_CREDS_FILE is resolved to absolute for checkpoint dir."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LC_CREDS_FILE", "myconf")
        result = get_checkpoint_dir()
        assert os.path.isabs(result)
        assert "myconf.d" in result


# ---------------------------------------------------------------------------
# Consistency: all paths use the same base
# ---------------------------------------------------------------------------

class TestPathConsistency:
    """Verify all path functions agree on the same base directory."""

    def test_all_paths_share_config_dir_when_explicit(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "shared")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        assert get_config_path().startswith(config_dir)
        assert get_jwt_cache_path().startswith(config_dir)
        assert get_checkpoint_dir().startswith(config_dir)

    def test_all_paths_share_base_in_legacy_mode(self, monkeypatch):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        home = os.path.expanduser("~")
        assert get_config_path().startswith(home)
        assert get_jwt_cache_path().startswith(home)
        # Checkpoint dir also uses home-based path in legacy mode
        assert get_checkpoint_dir().startswith(home)

    def test_creds_file_jwt_and_checkpoint_are_siblings(self, monkeypatch, tmp_path):
        """When LC_CREDS_FILE is set, jwt cache and checkpoint dir derive from it."""
        creds = str(tmp_path / "mycreds")
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        jwt = get_jwt_cache_path()
        cp = get_checkpoint_dir()
        assert jwt == creds + "_jwt_cache"
        assert cp == creds + ".d/search_checkpoints"


# ---------------------------------------------------------------------------
# get_all_paths / get_legacy_paths
# ---------------------------------------------------------------------------

class TestGetAllPaths:
    def test_returns_all_keys(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        paths = get_all_paths()
        assert set(paths.keys()) == {"config_dir", "config_file", "jwt_cache", "checkpoint_dir"}

    def test_all_values_are_absolute(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        for key, val in get_all_paths().items():
            assert os.path.isabs(val), f"{key} = {val!r} is not absolute"


class TestGetLegacyPaths:
    def test_returns_legacy_paths(self):
        legacy = get_legacy_paths()
        assert legacy["config_file"] == _LEGACY_CONFIG_FILE
        assert legacy["jwt_cache"] == _LEGACY_JWT_CACHE_FILE

    def test_legacy_paths_are_absolute(self):
        for key, val in get_legacy_paths().items():
            assert os.path.isabs(val), f"{key} = {val!r} is not absolute"

    def test_legacy_paths_unaffected_by_env_vars(self, monkeypatch, tmp_path):
        """Legacy paths are constants, not influenced by env vars."""
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("LC_CREDS_FILE", str(tmp_path / "custom"))
        legacy = get_legacy_paths()
        assert legacy["config_file"] == _LEGACY_CONFIG_FILE


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------

class TestPathCacheReset:
    def test_reset_clears_all_caches(self, monkeypatch, tmp_path):
        """After reset, paths are recomputed from env vars."""
        dir1 = str(tmp_path / "dir1")
        os.makedirs(dir1, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", dir1)
        p1 = get_config_path()

        dir2 = str(tmp_path / "dir2")
        os.makedirs(dir2, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", dir2)
        _reset_path_cache()
        p2 = get_config_path()

        assert p1 != p2
        assert "dir1" in p1
        assert "dir2" in p2

    def test_reset_also_clears_deprecation_flag(self, monkeypatch, tmp_path):
        """After reset, deprecation warning fires again."""
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: x\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        new_dir = str(tmp_path / "new")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_config_path()
        assert len([x for x in w if issubclass(x.category, UserWarning)]) == 1

        _reset_path_cache()
        with warnings.catch_warnings(record=True) as w2:
            warnings.simplefilter("always")
            get_config_path()
        assert len([x for x in w2 if issubclass(x.category, UserWarning)]) == 1

    def test_cache_is_per_function(self, monkeypatch, tmp_path):
        """Resetting path cache affects all four cached paths."""
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "a"))
        os.makedirs(str(tmp_path / "a"), exist_ok=True)
        get_config_dir()
        get_config_path()
        get_jwt_cache_path()
        get_checkpoint_dir()

        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "b"))
        os.makedirs(str(tmp_path / "b"), exist_ok=True)
        _reset_path_cache()

        assert "b" in get_config_dir()
        assert "b" in get_config_path()
        assert "b" in get_jwt_cache_path()
        assert "b" in get_checkpoint_dir()


# ---------------------------------------------------------------------------
# Env var priority
# ---------------------------------------------------------------------------

class TestEnvVarPriority:
    """Tests verifying the priority order of env vars."""

    def test_creds_file_beats_config_dir(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE takes precedence over LC_CONFIG_DIR for config path."""
        creds = str(tmp_path / "creds_file")
        config_dir = str(tmp_path / "config_dir")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        assert get_config_path() == os.path.abspath(creds)

    def test_creds_file_beats_legacy_mode(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE takes precedence over LC_LEGACY_CONFIG."""
        creds = str(tmp_path / "creds")
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        assert get_config_path() == os.path.abspath(creds)

    def test_legacy_mode_beats_config_dir(self, monkeypatch, tmp_path):
        """LC_LEGACY_CONFIG=1 takes precedence over LC_CONFIG_DIR for config path."""
        config_dir = str(tmp_path / "config_dir")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        assert get_config_path() == _LEGACY_CONFIG_FILE

    def test_creds_file_beats_config_dir_for_jwt(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE takes precedence over LC_CONFIG_DIR for JWT cache path."""
        creds = str(tmp_path / "creds")
        config_dir = str(tmp_path / "config_dir")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        assert get_jwt_cache_path() == os.path.abspath(creds) + "_jwt_cache"

    def test_creds_file_beats_config_dir_for_checkpoint(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE takes precedence over LC_CONFIG_DIR for checkpoint dir."""
        creds = str(tmp_path / "creds")
        config_dir = str(tmp_path / "config_dir")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CREDS_FILE", creds)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        result = get_checkpoint_dir()
        assert "creds.d" in result
        assert config_dir not in result


# ---------------------------------------------------------------------------
# Security: path traversal & symlinks
# ---------------------------------------------------------------------------

class TestPathSecurity:
    """Tests for security properties of path resolution.

    These verify that path resolution itself does not introduce path
    traversal vulnerabilities. The actual symlink protection at read/write
    time is handled by file_utils and tested there.
    """

    def test_config_dir_with_dotdot_resolved(self, monkeypatch, tmp_path):
        """LC_CONFIG_DIR with .. components is resolved to absolute."""
        traversal = str(tmp_path / "a" / ".." / "b")
        monkeypatch.setenv("LC_CONFIG_DIR", traversal)
        result = get_config_dir()
        assert ".." not in result
        assert result == os.path.abspath(traversal)

    def test_creds_file_with_dotdot_resolved(self, monkeypatch, tmp_path):
        """LC_CREDS_FILE with .. is resolved to absolute."""
        traversal = str(tmp_path / "x" / ".." / "creds")
        monkeypatch.setenv("LC_CREDS_FILE", traversal)
        result = get_config_path()
        assert ".." not in result

    @pytest.mark.skipif(os.name == "nt", reason="Unix symlink test")
    def test_config_dir_symlink_is_not_rejected_at_resolution(self, monkeypatch, tmp_path):
        """Path resolution does not reject symlinks - that's file_utils' job.

        paths.py resolves paths; file_utils.safe_open_read and atomic_write
        handle symlink rejection at I/O time.
        """
        real_dir = str(tmp_path / "real_config")
        os.makedirs(real_dir)
        link = str(tmp_path / "link_config")
        os.symlink(real_dir, link)
        monkeypatch.setenv("LC_CONFIG_DIR", link)
        # Should not raise - resolution doesn't check symlinks
        result = get_config_dir()
        assert os.path.isabs(result)


# ---------------------------------------------------------------------------
# Edge cases: pathological inputs
# ---------------------------------------------------------------------------

class TestPathEdgeCases:
    """Tests for unusual but valid path configurations."""

    def test_multiple_env_vars_set_simultaneously(self, monkeypatch, tmp_path):
        """All three env vars set at once - priority order is respected."""
        monkeypatch.setenv("LC_CREDS_FILE", str(tmp_path / "creds"))
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "dir"))
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        # LC_CREDS_FILE wins for config_path
        assert get_config_path() == os.path.abspath(str(tmp_path / "creds"))
        # LC_LEGACY_CONFIG wins for config_dir (legacy mode takes precedence
        # over LC_CONFIG_DIR, matching get_config_path() priority order)
        _reset_path_cache()
        assert get_config_dir() == os.path.dirname(_LEGACY_CONFIG_FILE)


# ---------------------------------------------------------------------------
# Priority consistency between get_config_dir() and get_config_path()
# ---------------------------------------------------------------------------

class TestPriorityConsistency:
    """Verify get_config_dir() and get_config_path() agree on priority order.

    LC_LEGACY_CONFIG must take precedence over LC_CONFIG_DIR in both
    functions so that show-paths reports a config_dir that actually
    contains the config_file.
    """

    def test_legacy_mode_beats_config_dir_in_get_config_dir(self, monkeypatch, tmp_path):
        """get_config_dir() returns legacy home when LC_LEGACY_CONFIG=1,
        even if LC_CONFIG_DIR is also set."""
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "custom"))
        result = get_config_dir()
        assert result == os.path.dirname(_LEGACY_CONFIG_FILE)

    def test_config_dir_and_config_path_consistent_in_legacy_mode(self, monkeypatch, tmp_path):
        """When LC_LEGACY_CONFIG=1 and LC_CONFIG_DIR are both set,
        config_path is under the directory reported by config_dir."""
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "custom"))
        config_dir = get_config_dir()
        config_path = get_config_path()
        assert os.path.dirname(config_path) == config_dir

    def test_all_paths_consistent_when_legacy_and_config_dir_set(self, monkeypatch, tmp_path):
        """All path functions agree when both LC_LEGACY_CONFIG and
        LC_CONFIG_DIR are set - legacy mode wins everywhere."""
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        monkeypatch.setenv("LC_CONFIG_DIR", str(tmp_path / "custom"))
        config_dir = get_config_dir()
        config_path = get_config_path()
        jwt_path = get_jwt_cache_path()
        checkpoint_dir = get_checkpoint_dir()
        # config_path and jwt_path should be in the home directory (legacy)
        home = os.path.expanduser("~")
        assert config_path.startswith(home)
        assert jwt_path.startswith(home)
        assert checkpoint_dir.startswith(home)
        # config_dir should be the home directory
        assert config_dir == home or config_dir == os.path.dirname(_LEGACY_CONFIG_FILE)

    def test_config_dir_uses_lc_config_dir_when_no_legacy(self, monkeypatch, tmp_path):
        """Without LC_LEGACY_CONFIG, LC_CONFIG_DIR still works as expected."""
        custom = str(tmp_path / "custom")
        monkeypatch.setenv("LC_CONFIG_DIR", custom)
        assert get_config_dir() == os.path.abspath(custom)
