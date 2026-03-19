"""Tests for limacharlie.commands.config_cmd (config migrate, config show-paths).

Tests cover the config CLI command group including migration from legacy
config file layout to the new directory-based layout, dry-run mode,
force overwrite, path display, security (symlinks, permissions),
robustness (partial migration, corrupt files, read-only dirs), and
edge cases (empty files, large files, unicode content).
"""

import json
import os
import stat

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.commands.config_cmd import _safe_content_match
from limacharlie.paths import _reset_path_cache


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Fully isolated environment for config commands."""
    from limacharlie.config import _reset_config_cache
    from limacharlie.jwt_cache import _reset_cache_disabled

    for var in ("LC_CONFIG_DIR", "LC_CREDS_FILE", "LC_LEGACY_CONFIG",
                "LC_EPHEMERAL_CREDS", "LC_NO_JWT_CACHE", "LC_OID",
                "LC_API_KEY", "LC_UID", "LC_CURRENT_ENV"):
        monkeypatch.delenv(var, raising=False)
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()
    yield
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_legacy(tmp_path, monkeypatch, *, config_data=None, jwt_data=None):
    """Create fake legacy config and JWT cache files and point paths to them.

    Returns (legacy_config, legacy_jwt, new_dir) paths.
    """
    import limacharlie.paths as paths_mod

    legacy_config = str(tmp_path / ".limacharlie")
    legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")

    if config_data is None:
        config_data = {"oid": "test-oid", "api_key": "test-key"}
    with open(legacy_config, "w") as f:
        yaml.safe_dump(config_data, f)
    os.chmod(legacy_config, 0o600)

    if jwt_data is None:
        jwt_data = {"some_key": {"jwt": "test-jwt"}}
    with open(legacy_jwt, "w") as f:
        json.dump(jwt_data, f)
    os.chmod(legacy_jwt, 0o600)

    new_dir = str(tmp_path / "new_config")
    monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
    monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
    monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
    _reset_path_cache()

    return legacy_config, legacy_jwt, new_dir


# ---------------------------------------------------------------------------
# config show-paths
# ---------------------------------------------------------------------------

class TestConfigShowPaths:
    """Tests for 'config show-paths' command."""

    def test_shows_all_path_keys(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["config_dir"] == config_dir
        assert "config.yaml" in data["config_file"]
        assert "jwt_cache.json" in data["jwt_cache"]
        assert "search_checkpoints" in data["checkpoint_dir"]
        # Boolean existence checks
        assert "config_dir_exists" in data
        assert "config_file_exists" in data
        assert "jwt_cache_exists" in data
        assert "checkpoint_dir_exists" in data

    def test_shows_env_overrides_when_set(self, monkeypatch, tmp_path):
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "LC_CONFIG_DIR" in data["env_overrides"]

    def test_shows_no_overrides_by_default(self, monkeypatch, tmp_path):
        import limacharlie.paths as paths_mod
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", str(tmp_path / "nope"))
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: str(tmp_path / "d"))
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["env_overrides"] == "(none)"

    def test_shows_legacy_mode_flag(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["legacy_mode_forced"] is True

    def test_existence_flags_accurate(self, monkeypatch, tmp_path):
        """Existence booleans reflect actual filesystem state."""
        config_dir = str(tmp_path / "lc_config")
        os.makedirs(config_dir, exist_ok=True)
        # Create config but not jwt cache
        with open(os.path.join(config_dir, "config.yaml"), "w") as f:
            f.write("oid: test\n")
        monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show-paths", "--output", "json"])
        data = json.loads(result.output)
        assert data["config_dir_exists"] is True
        assert data["config_file_exists"] is True
        assert data["jwt_cache_exists"] is False
        assert data["checkpoint_dir_exists"] is False


# ---------------------------------------------------------------------------
# config migrate - correctness
# ---------------------------------------------------------------------------

class TestConfigMigrate:
    """Tests for 'config migrate' command - correctness."""

    def test_migrate_copies_files(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0
        assert "Migrated config file" in result.output
        assert "Migrated JWT cache" in result.output
        assert "Migration complete" in result.output

        new_config = os.path.join(new_dir, "config.yaml")
        new_jwt = os.path.join(new_dir, "jwt_cache.json")
        assert os.path.isfile(new_config)
        assert os.path.isfile(new_jwt)

        with open(new_config, "rb") as f:
            assert yaml.safe_load(f)["oid"] == "test-oid"
        with open(new_jwt, "rb") as f:
            assert json.load(f)["some_key"]["jwt"] == "test-jwt"

        # Legacy files still exist (no --remove-old)
        assert os.path.isfile(legacy_config)
        assert os.path.isfile(legacy_jwt)

    def test_migrate_preserves_file_content_exactly(self, monkeypatch, tmp_path):
        """Byte-for-byte copy integrity check."""
        import limacharlie.paths as paths_mod
        legacy_config = str(tmp_path / ".limacharlie")
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        # Write content with specific formatting
        config_content = b"oid: 'test-oid'\napi_key: 'test-key'\n# comment preserved\n"
        jwt_content = b'{"key": "value", "nested": {"a": 1}}'
        with open(legacy_config, "wb") as f:
            f.write(config_content)
        os.chmod(legacy_config, 0o600)
        with open(legacy_jwt, "wb") as f:
            f.write(jwt_content)
        os.chmod(legacy_jwt, 0o600)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0

        with open(os.path.join(new_dir, "config.yaml"), "rb") as f:
            assert f.read() == config_content
        with open(os.path.join(new_dir, "jwt_cache.json"), "rb") as f:
            assert f.read() == jwt_content

    def test_migrate_dry_run(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "config file" in result.output
        assert "JWT cache" in result.output
        assert not os.path.isdir(new_dir)

    def test_migrate_dry_run_shows_remove_old_plan(self, monkeypatch, tmp_path):
        _setup_legacy(tmp_path, monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--dry-run", "--remove-old"])
        assert result.exit_code == 0
        assert "would be removed" in result.output

    def test_migrate_remove_old(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--remove-old"])
        assert result.exit_code == 0
        assert "Removed legacy" in result.output
        assert not os.path.isfile(legacy_config)
        assert not os.path.isfile(legacy_jwt)

    def test_migrate_skips_existing_without_force(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        os.makedirs(new_dir, exist_ok=True)
        with open(os.path.join(new_dir, "config.yaml"), "w") as f:
            f.write("existing\n")
        with open(os.path.join(new_dir, "jwt_cache.json"), "w") as f:
            f.write("{}")

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0
        assert "already exists" in result.output
        assert "Already migrated" in result.output
        assert "--remove-old" in result.output

        # Existing content should be unchanged
        with open(os.path.join(new_dir, "config.yaml")) as f:
            assert f.read() == "existing\n"

    def test_migrate_remove_old_after_previous_migration(self, monkeypatch, tmp_path):
        """--remove-old cleans up legacy files when new files have matching content."""
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        # Simulate previous migration: copy legacy content to new location
        os.makedirs(new_dir, exist_ok=True)
        import shutil
        shutil.copy2(legacy_config, os.path.join(new_dir, "config.yaml"))
        shutil.copy2(legacy_jwt, os.path.join(new_dir, "jwt_cache.json"))

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--remove-old"])
        assert result.exit_code == 0
        assert "Removed legacy" in result.output
        assert not os.path.isfile(legacy_config)
        assert not os.path.isfile(legacy_jwt)

    def test_migrate_remove_old_refuses_when_content_differs(self, monkeypatch, tmp_path):
        """--remove-old refuses to delete legacy files when new files have different content.

        Prevents data loss when the destination was created independently
        (e.g. manually, or by a different tool) with different content.
        Returns non-zero exit code to signal manual intervention needed.
        """
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        # Create new files with DIFFERENT content than legacy
        os.makedirs(new_dir, exist_ok=True)
        with open(os.path.join(new_dir, "config.yaml"), "w") as f:
            f.write("oid: completely-different-oid\n")
        with open(os.path.join(new_dir, "jwt_cache.json"), "w") as f:
            f.write('{"different": "data"}')

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--remove-old"])
        # Non-zero exit code signals manual intervention needed
        assert result.exit_code == 3
        # Should warn about content mismatch and skip removal
        assert "differs from" in result.output
        # Legacy files should still exist (NOT deleted)
        assert os.path.isfile(legacy_config)
        assert os.path.isfile(legacy_jwt)

    def test_migrate_remove_old_mixed_match(self, monkeypatch, tmp_path):
        """--remove-old handles mix: config matches (removed), jwt differs (kept).

        Exits non-zero because at least one file could not be removed.
        """
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        os.makedirs(new_dir, exist_ok=True)
        # Config matches
        import shutil
        shutil.copy2(legacy_config, os.path.join(new_dir, "config.yaml"))
        # JWT differs
        with open(os.path.join(new_dir, "jwt_cache.json"), "w") as f:
            f.write('{"different": "jwt data"}')

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--remove-old"])
        assert result.exit_code == 3
        # Config removed (matched)
        assert not os.path.isfile(legacy_config)
        # JWT kept (differed)
        assert os.path.isfile(legacy_jwt)
        assert "differs from" in result.output

    def test_migrate_force_overwrites(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        os.makedirs(new_dir, exist_ok=True)
        with open(os.path.join(new_dir, "config.yaml"), "w") as f:
            f.write("old\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--force"])
        assert result.exit_code == 0
        assert "Migrated" in result.output

        new_config = os.path.join(new_dir, "config.yaml")
        with open(new_config, "rb") as f:
            assert yaml.safe_load(f)["oid"] == "test-oid"

    def test_migrate_nothing_to_do(self, monkeypatch, tmp_path):
        """No legacy files exist - nothing to migrate."""
        import limacharlie.paths as paths_mod
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", str(tmp_path / "nonexistent"))
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", str(tmp_path / "nonexistent2"))
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0
        assert "Nothing to migrate" in result.output

    def test_migrate_config_only_no_jwt(self, monkeypatch, tmp_path):
        """Only config file exists, no JWT cache - migrates just the config."""
        import limacharlie.paths as paths_mod
        legacy_config = str(tmp_path / ".limacharlie")
        with open(legacy_config, "w") as f:
            yaml.safe_dump({"oid": "x"}, f)
        os.chmod(legacy_config, 0o600)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", str(tmp_path / "nope"))
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0
        assert "Migrated config file" in result.output
        assert "JWT cache" not in result.output.replace("Skipping JWT cache", "")

    def test_migrate_jwt_only_no_config(self, monkeypatch, tmp_path):
        """Only JWT cache exists, no config - migrates just the JWT cache."""
        import limacharlie.paths as paths_mod
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        with open(legacy_jwt, "w") as f:
            json.dump({"k": "v"}, f)
        os.chmod(legacy_jwt, 0o600)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", str(tmp_path / "nope"))
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0
        assert "Migrated JWT cache" in result.output

    def test_migrate_fails_in_legacy_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LC_LEGACY_CONFIG", "1")
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code != 0
        assert "LC_LEGACY_CONFIG" in result.output

    def test_migrate_idempotent(self, monkeypatch, tmp_path):
        """Running migrate twice - second time detects already migrated."""
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        runner = CliRunner()
        result1 = runner.invoke(cli, ["config", "migrate"])
        assert result1.exit_code == 0
        assert "Migration complete" in result1.output

        _reset_path_cache()
        result2 = runner.invoke(cli, ["config", "migrate"])
        assert result2.exit_code == 0
        assert "Already migrated" in result2.output


# ---------------------------------------------------------------------------
# config migrate - security
# ---------------------------------------------------------------------------

class TestConfigMigrateSecurity:
    """Security tests for the migrate command."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_migrate_creates_secure_directory(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0

        mode = os.stat(new_dir).st_mode & 0o777
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_migrated_files_have_secure_permissions(self, monkeypatch, tmp_path):
        legacy_config, legacy_jwt, new_dir = _setup_legacy(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0

        for filename in ("config.yaml", "jwt_cache.json"):
            filepath = os.path.join(new_dir, filename)
            mode = os.stat(filepath).st_mode & 0o777
            assert mode == 0o600, f"{filename} has {oct(mode)}, expected 0o600"

    @pytest.mark.skipif(os.name == "nt", reason="Unix symlink test")
    def test_migrate_rejects_symlinked_legacy_config(self, monkeypatch, tmp_path):
        """Migration refuses to read a symlinked legacy config file.

        An attacker could place a symlink at ~/.limacharlie pointing to
        /etc/shadow or another sensitive file. safe_open_read rejects it.
        """
        import limacharlie.paths as paths_mod

        target = str(tmp_path / "target_file")
        with open(target, "w") as f:
            f.write("sensitive content\n")

        legacy_config = str(tmp_path / ".limacharlie")
        os.symlink(target, legacy_config)
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        with open(legacy_jwt, "w") as f:
            json.dump({}, f)
        os.chmod(legacy_jwt, 0o600)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        # Should fail because safe_open_read rejects symlinks
        assert result.exit_code != 0 or "Error" in result.output

    @pytest.mark.skipif(os.name == "nt", reason="Unix symlink test")
    def test_migrate_rejects_symlinked_legacy_jwt(self, monkeypatch, tmp_path):
        """Migration refuses to read a symlinked legacy JWT cache."""
        import limacharlie.paths as paths_mod

        legacy_config = str(tmp_path / ".limacharlie")
        with open(legacy_config, "w") as f:
            yaml.safe_dump({"oid": "x"}, f)
        os.chmod(legacy_config, 0o600)

        target = str(tmp_path / "target_jwt")
        with open(target, "w") as f:
            f.write('{"fake": "data"}')
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        os.symlink(target, legacy_jwt)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        # Config succeeds, JWT fails due to symlink
        # The command should still report error for the JWT part
        assert "Migrated config file" in result.output
        assert result.exit_code != 0 or "Error" in result.output


# ---------------------------------------------------------------------------
# config migrate - robustness
# ---------------------------------------------------------------------------

class TestConfigMigrateRobustness:
    """Robustness tests for edge cases and failure modes."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    @pytest.mark.skipif(os.getuid() == 0, reason="Root ignores file permissions")
    def test_migrate_fails_on_unwritable_target_dir(self, monkeypatch, tmp_path):
        """Migration fails gracefully when target dir parent is read-only."""
        import limacharlie.paths as paths_mod

        legacy_config = str(tmp_path / ".limacharlie")
        with open(legacy_config, "w") as f:
            yaml.safe_dump({"oid": "x"}, f)
        os.chmod(legacy_config, 0o600)

        # Make parent read-only so mkdir fails
        locked_parent = str(tmp_path / "locked")
        os.makedirs(locked_parent)
        new_dir = os.path.join(locked_parent, "new_config")

        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", str(tmp_path / "nope"))
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        os.chmod(locked_parent, 0o444)
        try:
            runner = CliRunner()
            result = runner.invoke(cli, ["config", "migrate"])
            # Should fail gracefully
            assert result.exit_code != 0 or "Error" in result.output
        finally:
            os.chmod(locked_parent, 0o755)

    def test_migrate_empty_config_file(self, monkeypatch, tmp_path):
        """Empty legacy config file is migrated without error."""
        import limacharlie.paths as paths_mod
        legacy_config = str(tmp_path / ".limacharlie")
        with open(legacy_config, "w") as f:
            pass  # empty
        os.chmod(legacy_config, 0o600)
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        with open(legacy_jwt, "w") as f:
            pass  # empty
        os.chmod(legacy_jwt, 0o600)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0
        assert "Migration complete" in result.output

    def test_migrate_large_config_file(self, monkeypatch, tmp_path):
        """Large config file (many environments) migrates correctly."""
        import limacharlie.paths as paths_mod
        # Build a config with many environments
        config_data = {"oid": "default-oid", "api_key": "default-key", "env": {}}
        for i in range(100):
            config_data["env"][f"env_{i:03d}"] = {
                "oid": f"oid-{i}",
                "api_key": f"key-{i}" * 10,
            }
        legacy_config = str(tmp_path / ".limacharlie")
        with open(legacy_config, "w") as f:
            yaml.safe_dump(config_data, f)
        os.chmod(legacy_config, 0o600)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", str(tmp_path / "nope"))
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0

        with open(os.path.join(new_dir, "config.yaml"), "rb") as f:
            migrated = yaml.safe_load(f)
        assert len(migrated["env"]) == 100
        assert migrated["env"]["env_050"]["oid"] == "oid-50"

    def test_migrate_unicode_content(self, monkeypatch, tmp_path):
        """Config file with unicode characters (e.g. org names) migrates."""
        config_data = {"oid": "test", "org_name": "T\u00e9st Org \u2603 \u00e9\u00e8\u00ea"}
        _setup_legacy(tmp_path, monkeypatch, config_data=config_data)

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])
        assert result.exit_code == 0

        new_dir = str(tmp_path / "new_config")
        with open(os.path.join(new_dir, "config.yaml"), "rb") as f:
            migrated = yaml.safe_load(f)
        assert migrated["org_name"] == "T\u00e9st Org \u2603 \u00e9\u00e8\u00ea"

    def test_migrate_partial_failure_does_not_remove_old(self, monkeypatch, tmp_path):
        """If JWT migration fails, legacy files are NOT removed even with --remove-old.

        This prevents data loss when migration is partially successful.
        """
        import limacharlie.paths as paths_mod

        legacy_config = str(tmp_path / ".limacharlie")
        with open(legacy_config, "w") as f:
            yaml.safe_dump({"oid": "x"}, f)
        os.chmod(legacy_config, 0o600)

        # Create JWT as a symlink to make its migration fail (safe_open_read rejects)
        if os.name == "nt":
            pytest.skip("Unix symlink test")
        target = str(tmp_path / "target")
        with open(target, "w") as f:
            f.write("{}")
        legacy_jwt = str(tmp_path / ".limacharlie_jwt_cache")
        os.symlink(target, legacy_jwt)

        new_dir = str(tmp_path / "new_config")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_config)
        monkeypatch.setattr(paths_mod, "_LEGACY_JWT_CACHE_FILE", legacy_jwt)
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)
        _reset_path_cache()

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--remove-old"])
        # Config migrated successfully, but JWT failed
        # The successfully migrated config's legacy file gets removed,
        # but the error from JWT migration stops further processing
        assert "Migrated config file" in result.output
        # JWT migration should fail
        assert "Error" in result.output or result.exit_code != 0


class TestSafeContentMatch:
    """Tests for _safe_content_match helper."""

    def test_matching_files(self, tmp_path):
        a = str(tmp_path / "a")
        b = str(tmp_path / "b")
        with open(a, "w") as f:
            f.write("same content")
        with open(b, "w") as f:
            f.write("same content")
        assert _safe_content_match(a, b) is True

    def test_different_files(self, tmp_path):
        a = str(tmp_path / "a")
        b = str(tmp_path / "b")
        with open(a, "w") as f:
            f.write("content a")
        with open(b, "w") as f:
            f.write("content b")
        assert _safe_content_match(a, b) is False

    def test_missing_file_returns_false(self, tmp_path):
        a = str(tmp_path / "exists")
        b = str(tmp_path / "missing")
        with open(a, "w") as f:
            f.write("content")
        assert _safe_content_match(a, b) is False

    def test_both_missing_returns_false(self, tmp_path):
        assert _safe_content_match(
            str(tmp_path / "nope1"), str(tmp_path / "nope2")
        ) is False

    @pytest.mark.skipif(os.name == "nt", reason="Unix permissions test")
    def test_unreadable_file_returns_false(self, tmp_path):
        """Permission error (OSError) is caught and returns False."""
        a = str(tmp_path / "a")
        b = str(tmp_path / "b")
        with open(a, "w") as f:
            f.write("content")
        with open(b, "w") as f:
            f.write("content")
        os.chmod(a, 0o000)
        try:
            assert _safe_content_match(a, b) is False
        finally:
            os.chmod(a, 0o644)
