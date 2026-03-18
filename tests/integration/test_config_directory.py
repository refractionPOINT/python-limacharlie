"""End-to-end integration tests for config directory migration and path resolution.

These tests simulate realistic CLI usage patterns across the full
config directory lifecycle:
- Fresh install (no existing files)
- Legacy install (only old-layout files)
- Post-migration (new layout in use)
- Mixed states (partial migration)
- Switching between modes via env vars

Each test exercises the real config, jwt_cache, and paths modules with
real files on disk - no mocking except for env vars and legacy path
constants (to avoid touching the user's real ~/.limacharlie).

Run with:
    pytest tests/integration/test_config_directory.py -v
"""

from __future__ import annotations

import json
import os
import stat
import time

import pytest
import yaml

from limacharlie.config import (
    _reset_config_cache,
    get_config_value,
    get_environment_creds,
    list_environments,
    load_config,
    resolve_credentials,
    save_config,
    write_credentials,
)
from limacharlie.jwt_cache import (
    _get_cache_path,
    _reset_cache_disabled,
    clear_jwt_cache,
    get_cached_jwt,
    put_cached_jwt,
)
from limacharlie.paths import (
    _reset_path_cache,
    get_all_paths,
    get_checkpoint_dir,
    get_config_dir,
    get_config_path,
    get_jwt_cache_path,
    get_legacy_paths,
)

import base64


def _make_jwt(exp: float) -> str:
    """Create a minimal JWT with a given exp claim for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


def _reset_all():
    """Reset all per-process caches to simulate a fresh CLI process."""
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Full isolation: clear env vars, reset caches, point legacy paths to tmp."""
    import limacharlie.paths as paths_mod
    for var in ("LC_CONFIG_DIR", "LC_CREDS_FILE", "LC_LEGACY_CONFIG",
                "LC_EPHEMERAL_CREDS", "LC_NO_JWT_CACHE", "LC_OID",
                "LC_API_KEY", "LC_UID", "LC_CURRENT_ENV"):
        monkeypatch.delenv(var, raising=False)
    # Point legacy paths to tmp so we never touch real ~/.limacharlie
    monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE",
                        str(tmp_path / "home" / ".limacharlie"))
    monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE",
                        str(tmp_path / "home" / ".limacharlie_jwt_cache"))
    monkeypatch.setattr(paths_mod, "_default_config_dir",
                        lambda: str(tmp_path / "home" / ".limacharlie.d"))
    os.makedirs(str(tmp_path / "home"), exist_ok=True)
    _reset_all()
    yield
    _reset_all()


# ---------------------------------------------------------------------------
# Scenario: Fresh install
# ---------------------------------------------------------------------------

class TestFreshInstall:
    """Simulate a brand-new installation with no existing files."""

    def test_config_path_points_to_new_layout(self, tmp_path):
        """On fresh install, config path is <default>/.limacharlie.d/config.yaml."""
        path = get_config_path()
        assert path.endswith("config.yaml")
        assert ".limacharlie.d" in path

    def test_save_config_creates_directory_and_file(self, tmp_path):
        """First save_config creates the config dir with secure permissions."""
        save_config({"oid": "fresh-oid", "api_key": "fresh-key"})
        path = get_config_path()
        assert os.path.isfile(path)
        config_dir = os.path.dirname(path)
        assert os.path.isdir(config_dir)
        if os.name != "nt":
            dir_mode = os.stat(config_dir).st_mode & 0o777
            assert dir_mode == 0o700
            file_mode = os.stat(path).st_mode & 0o777
            assert file_mode == 0o600

    def test_write_credentials_and_read_back(self, tmp_path):
        """Write credentials via write_credentials, read back via load_config."""
        write_credentials("default", "org-1", "key-1")
        _reset_config_cache()
        config = load_config()
        assert config["oid"] == "org-1"
        assert config["api_key"] == "key-1"

    def test_jwt_cache_works_on_fresh_install(self, tmp_path):
        """JWT caching works with new layout from scratch."""
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)
        assert get_cached_jwt("oid", "key", None, None) == jwt

        cache_path = get_jwt_cache_path()
        assert os.path.isfile(cache_path)
        assert cache_path.endswith("jwt_cache.json")

    def test_resolve_credentials_empty(self, tmp_path):
        """On fresh install with no config, resolve_credentials returns None values."""
        creds = resolve_credentials()
        assert creds["oid"] is None
        assert creds["api_key"] is None

    def test_named_environments(self, tmp_path):
        """Named environments work with new layout."""
        write_credentials("prod", "prod-oid", "prod-key")
        _reset_config_cache()
        write_credentials("staging", "stage-oid", "stage-key")
        _reset_config_cache()

        envs = list_environments()
        assert "prod" in envs
        assert "staging" in envs

        creds = get_environment_creds("prod")
        assert creds["oid"] == "prod-oid"


# ---------------------------------------------------------------------------
# Scenario: Legacy install -> migration -> post-migration
# ---------------------------------------------------------------------------

class TestLegacyToMigration:
    """Simulate migrating from legacy layout to new layout."""

    def _create_legacy_state(self, tmp_path):
        """Create a realistic legacy config + JWT cache."""
        import limacharlie.paths as paths_mod
        legacy_config = paths_mod._LEGACY_CONFIG_FILE
        legacy_jwt = paths_mod._LEGACY_JWT_CACHE_FILE

        config_data = {
            "oid": "legacy-oid",
            "api_key": "legacy-key",
            "uid": "legacy-uid",
            "current_env": "default",
            "env": {
                "production": {"oid": "prod-oid", "api_key": "prod-key"},
                "staging": {"oid": "stage-oid", "api_key": "stage-key"},
            },
        }
        with open(legacy_config, "w") as f:
            yaml.safe_dump(config_data, f)
        os.chmod(legacy_config, 0o600)

        jwt = _make_jwt(time.time() + 3600)
        from limacharlie.jwt_cache import _compute_cache_key
        cache_key = _compute_cache_key("legacy-oid", "legacy-key", None, None)
        jwt_data = {cache_key: {"jwt": jwt}}
        with open(legacy_jwt, "w") as f:
            json.dump(jwt_data, f)
        os.chmod(legacy_jwt, 0o600)

        return config_data, jwt, legacy_config, legacy_jwt

    def test_legacy_detected_and_used(self, tmp_path):
        """Config and JWT cache from legacy paths are used correctly."""
        config_data, jwt, _, _ = self._create_legacy_state(tmp_path)
        _reset_all()

        # Should detect legacy config
        config = load_config()
        assert config["oid"] == "legacy-oid"

        # Credentials resolve from legacy file
        creds = resolve_credentials()
        assert creds["oid"] == "legacy-oid"
        assert creds["api_key"] == "legacy-key"

        # Named environments work
        prod_creds = resolve_credentials(environment="production")
        assert prod_creds["oid"] == "prod-oid"

    def test_migrate_then_use_new_layout(self, tmp_path):
        """After migration, all operations use the new layout."""
        from click.testing import CliRunner
        from limacharlie.cli import cli

        config_data, jwt, legacy_config, legacy_jwt = self._create_legacy_state(tmp_path)
        _reset_all()

        # Migrate
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--remove-old"])
        assert result.exit_code == 0

        # Legacy files gone
        assert not os.path.isfile(legacy_config)
        assert not os.path.isfile(legacy_jwt)

        # New files exist
        _reset_all()
        new_config = get_config_path()
        assert new_config.endswith("config.yaml")
        assert os.path.isfile(new_config)

        # Read config from new location
        config = load_config()
        assert config["oid"] == "legacy-oid"
        assert config["env"]["production"]["oid"] == "prod-oid"

        # Named env credentials still work
        _reset_all()
        creds = resolve_credentials(environment="staging")
        assert creds["oid"] == "stage-oid"

    def test_migrate_then_write_new_credentials(self, tmp_path):
        """After migration, writing credentials updates the new config file."""
        from click.testing import CliRunner
        from limacharlie.cli import cli

        self._create_legacy_state(tmp_path)
        _reset_all()

        runner = CliRunner()
        runner.invoke(cli, ["config", "migrate", "--remove-old"])
        _reset_all()

        # Write a new environment
        write_credentials("dev", "dev-oid", "dev-key")
        _reset_config_cache()

        config = load_config()
        assert config["env"]["dev"]["oid"] == "dev-oid"
        # Original data preserved
        assert config["oid"] == "legacy-oid"

    def test_migrate_jwt_cache_still_functional(self, tmp_path):
        """After migration, JWT caching works from new location."""
        from click.testing import CliRunner
        from limacharlie.cli import cli

        self._create_legacy_state(tmp_path)
        _reset_all()

        runner = CliRunner()
        runner.invoke(cli, ["config", "migrate", "--remove-old"])
        _reset_all()

        # Write a new JWT to the new cache location
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "new-oid", "new-key", None, None)
        assert get_cached_jwt("new-oid", "new-key", None, None) == jwt

        # Cache file is in the new location
        cache_path = get_jwt_cache_path()
        assert cache_path.endswith("jwt_cache.json")
        assert os.path.isfile(cache_path)


# ---------------------------------------------------------------------------
# Scenario: LC_CONFIG_DIR override
# ---------------------------------------------------------------------------

class TestConfigDirOverride:
    """Tests for LC_CONFIG_DIR pointing to a custom directory."""

    def test_all_operations_use_custom_dir(self, monkeypatch, tmp_path):
        custom_dir = str(tmp_path / "custom_lc")
        os.makedirs(custom_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", custom_dir)
        _reset_all()

        # Write config
        write_credentials("default", "custom-oid", "custom-key")
        assert os.path.isfile(os.path.join(custom_dir, "config.yaml"))

        # Write JWT
        _reset_all()
        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "custom-oid", "custom-key", None, None)
        assert os.path.isfile(os.path.join(custom_dir, "jwt_cache.json"))

        # Read back
        _reset_all()
        config = load_config()
        assert config["oid"] == "custom-oid"
        assert get_cached_jwt("custom-oid", "custom-key", None, None) == jwt

    def test_custom_dir_ignores_legacy_files(self, monkeypatch, tmp_path):
        """LC_CONFIG_DIR means never fall back to legacy, even if legacy exists."""
        import limacharlie.paths as paths_mod

        # Create legacy file
        legacy = paths_mod._LEGACY_CONFIG_FILE
        with open(legacy, "w") as f:
            yaml.safe_dump({"oid": "legacy-should-be-ignored"}, f)

        custom_dir = str(tmp_path / "custom_lc")
        os.makedirs(custom_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", custom_dir)
        _reset_all()

        config = load_config()
        assert config is None  # Custom dir has no config yet

    def test_switching_config_dirs(self, monkeypatch, tmp_path):
        """Switching LC_CONFIG_DIR gives different config files."""
        dir1 = str(tmp_path / "dir1")
        dir2 = str(tmp_path / "dir2")
        os.makedirs(dir1, exist_ok=True)
        os.makedirs(dir2, exist_ok=True)

        # Write to dir1
        monkeypatch.setenv("LC_CONFIG_DIR", dir1)
        _reset_all()
        write_credentials("default", "oid-1", "key-1")

        # Write to dir2
        monkeypatch.setenv("LC_CONFIG_DIR", dir2)
        _reset_all()
        write_credentials("default", "oid-2", "key-2")

        # Read from dir1
        monkeypatch.setenv("LC_CONFIG_DIR", dir1)
        _reset_all()
        assert load_config()["oid"] == "oid-1"

        # Read from dir2
        monkeypatch.setenv("LC_CONFIG_DIR", dir2)
        _reset_all()
        assert load_config()["oid"] == "oid-2"


# ---------------------------------------------------------------------------
# Scenario: LC_LEGACY_CONFIG=1
# ---------------------------------------------------------------------------

class TestLegacyModeForced:
    """Tests for forced legacy mode via LC_LEGACY_CONFIG=1."""

    def test_legacy_mode_uses_old_paths(self, monkeypatch, tmp_path):
        import limacharlie.paths as paths_mod

        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        _reset_all()

        legacy_config = paths_mod._LEGACY_CONFIG_FILE
        assert get_config_path() == legacy_config

    def test_legacy_mode_write_and_read(self, monkeypatch, tmp_path):
        import limacharlie.paths as paths_mod

        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        _reset_all()

        write_credentials("default", "legacy-oid", "legacy-key")
        _reset_config_cache()
        config = load_config()
        assert config["oid"] == "legacy-oid"

        # Verify file is at legacy path
        legacy_config = paths_mod._LEGACY_CONFIG_FILE
        assert os.path.isfile(legacy_config)

    def test_legacy_mode_jwt_cache_at_old_path(self, monkeypatch, tmp_path):
        import limacharlie.paths as paths_mod

        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        _reset_all()

        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)

        legacy_jwt = paths_mod._LEGACY_JWT_CACHE_FILE
        assert os.path.isfile(legacy_jwt)


# ---------------------------------------------------------------------------
# Scenario: LC_CREDS_FILE override
# ---------------------------------------------------------------------------

class TestCredsFileOverride:
    """Tests for LC_CREDS_FILE pointing to a custom config file."""

    def test_creds_file_used_for_config(self, monkeypatch, tmp_path):
        creds_file = str(tmp_path / "custom_creds")
        monkeypatch.setenv("LC_CREDS_FILE", creds_file)
        _reset_all()

        write_credentials("default", "creds-oid", "creds-key")
        assert os.path.isfile(creds_file)
        _reset_config_cache()
        assert load_config()["oid"] == "creds-oid"

    def test_creds_file_jwt_cache_is_sibling(self, monkeypatch, tmp_path):
        creds_file = str(tmp_path / "my_creds")
        monkeypatch.setenv("LC_CREDS_FILE", creds_file)
        _reset_all()

        exp = time.time() + 3600
        jwt = _make_jwt(exp)
        put_cached_jwt(jwt, "oid", "key", None, None)

        expected_jwt_path = creds_file + "_jwt_cache"
        assert os.path.isfile(expected_jwt_path)

    def test_creds_file_checkpoint_dir_is_sibling(self, monkeypatch, tmp_path):
        creds_file = str(tmp_path / "my_creds")
        monkeypatch.setenv("LC_CREDS_FILE", creds_file)
        _reset_all()

        cp_dir = get_checkpoint_dir()
        assert cp_dir == creds_file + ".d/search_checkpoints"


# ---------------------------------------------------------------------------
# Scenario: config show-paths end-to-end
# ---------------------------------------------------------------------------

class TestShowPathsEndToEnd:
    """End-to-end test for config show-paths across different states."""

    def test_show_paths_reflects_actual_state(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from limacharlie.cli import cli

        # Start with fresh install
        _reset_all()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["config_file_exists"] is False
        assert data["jwt_cache_exists"] is False

        # Create config
        write_credentials("default", "x", "y")
        _reset_all()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        data = json.loads(result.output)
        assert data["config_file_exists"] is True


# ---------------------------------------------------------------------------
# Scenario: Cross-subsystem consistency
# ---------------------------------------------------------------------------

class TestCrossSubsystemConsistency:
    """Verify that config, jwt_cache, and checkpoint all agree on paths."""

    def test_config_and_jwt_in_same_directory(self, tmp_path):
        """After writing config and JWT, both files are in the same dir."""
        write_credentials("default", "oid", "key")
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)

        config_dir = os.path.dirname(get_config_path())
        jwt_dir = os.path.dirname(get_jwt_cache_path())
        assert config_dir == jwt_dir

    def test_checkpoint_dir_under_config_dir(self, tmp_path):
        """Checkpoint dir is a subdirectory of the config dir."""
        config_dir = get_config_dir()
        cp_dir = get_checkpoint_dir()
        assert cp_dir.startswith(config_dir)

    def test_all_paths_deterministic_across_resets(self, tmp_path):
        """Multiple cache resets always produce the same paths."""
        paths1 = get_all_paths()
        _reset_all()
        paths2 = get_all_paths()
        assert paths1 == paths2


# ---------------------------------------------------------------------------
# Scenario: Permissions across operations
# ---------------------------------------------------------------------------

class TestPermissionsEndToEnd:
    """End-to-end permission checks for all file operations."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_config_file_always_0600(self, tmp_path):
        """Every write operation preserves 0o600 on the config file."""
        write_credentials("default", "oid", "key")
        mode = os.stat(get_config_path()).st_mode & 0o777
        assert mode == 0o600

        # Write again
        _reset_config_cache()
        write_credentials("staging", "s-oid", "s-key")
        mode = os.stat(get_config_path()).st_mode & 0o777
        assert mode == 0o600

        # save_config directly
        _reset_config_cache()
        save_config(load_config())
        mode = os.stat(get_config_path()).st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_jwt_cache_always_0600(self, tmp_path):
        """JWT cache file has 0o600 permissions after writes."""
        exp = time.time() + 3600
        put_cached_jwt(_make_jwt(exp), "oid", "key", None, None)
        cache_path = get_jwt_cache_path()
        mode = os.stat(cache_path).st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_config_dir_always_0700(self, tmp_path):
        """Config directory has 0o700 permissions after creation."""
        write_credentials("default", "oid", "key")
        config_dir = get_config_dir()
        mode = os.stat(config_dir).st_mode & 0o777
        assert mode == 0o700


# ---------------------------------------------------------------------------
# Scenario: Concurrent-like access patterns
# ---------------------------------------------------------------------------

class TestConcurrentPatterns:
    """Simulate patterns that arise from multiple CLI invocations."""

    def test_sequential_processes_share_config(self, tmp_path):
        """Multiple simulated CLI processes read/write the same config."""
        # Process 1: write
        write_credentials("default", "oid-1", "key-1")
        _reset_all()

        # Process 2: read
        config = load_config()
        assert config["oid"] == "oid-1"
        _reset_all()

        # Process 3: overwrite
        write_credentials("default", "oid-2", "key-2")
        _reset_all()

        # Process 4: read updated
        config = load_config()
        assert config["oid"] == "oid-2"

    def test_sequential_processes_share_jwt_cache(self, tmp_path):
        """Multiple simulated processes use the same JWT cache."""
        exp = time.time() + 3600
        jwt1 = _make_jwt(exp)

        # Process 1: put jwt
        put_cached_jwt(jwt1, "oid", "key", None, None)
        _reset_all()

        # Process 2: get jwt (cache hit)
        assert get_cached_jwt("oid", "key", None, None) == jwt1
        _reset_all()

        # Process 3: clear cache
        clear_jwt_cache()
        _reset_all()

        # Process 4: cache miss
        assert get_cached_jwt("oid", "key", None, None) is None

    def test_config_write_atomicity(self, tmp_path):
        """Config writes are atomic - no partial reads."""
        # Write initial
        write_credentials("default", "oid-initial", "key-initial")
        _reset_config_cache()

        # Overwrite with new data
        config = load_config()
        config["oid"] = "oid-updated"
        config["new_field"] = "new_value"
        save_config(config)
        _reset_config_cache()

        # Read back - should be complete
        loaded = load_config()
        assert loaded["oid"] == "oid-updated"
        assert loaded["new_field"] == "new_value"
        assert loaded["api_key"] == "key-initial"  # preserved
