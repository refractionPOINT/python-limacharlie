"""Tests for limacharlie.config module."""

import os
import stat
import tempfile

import pytest
import yaml

from limacharlie.config import (
    resolve_credentials,
    get_environment_creds,
    get_config_value,
    load_config,
    save_config,
    write_credentials,
    list_environments,
    is_ephemeral,
    _get_config_path,
)
from limacharlie.errors import ConfigError


@pytest.fixture
def tmp_config_file(monkeypatch, tmp_path):
    """Create a temporary config directory and point paths module to it.

    Sets LC_CONFIG_DIR to a temp directory so all path resolution
    goes through the new layout. The yielded path is the config file
    inside that directory (e.g. <tmp>/config.yaml).
    """
    from limacharlie.config import _reset_config_cache
    from limacharlie.paths import _reset_path_cache

    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.yaml")

    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    monkeypatch.delenv("LC_CREDS_FILE", raising=False)
    monkeypatch.delenv("LC_LEGACY_CONFIG", raising=False)
    monkeypatch.delenv("LC_OID", raising=False)
    monkeypatch.delenv("LC_API_KEY", raising=False)
    monkeypatch.delenv("LC_UID", raising=False)
    monkeypatch.delenv("LC_CURRENT_ENV", raising=False)
    monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
    _reset_path_cache()
    _reset_config_cache()
    yield config_path
    _reset_path_cache()
    _reset_config_cache()


class TestLoadConfig:
    def test_returns_none_when_no_file(self, tmp_config_file):
        assert load_config() is None

    def test_loads_yaml_file(self, tmp_config_file):
        data = {"oid": "test-oid", "api_key": "test-key"}
        with open(tmp_config_file, "w") as f:
            yaml.safe_dump(data, f)
        config = load_config()
        assert config["oid"] == "test-oid"
        assert config["api_key"] == "test-key"

    def test_returns_none_in_ephemeral_mode(self, tmp_config_file, monkeypatch):
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        with open(tmp_config_file, "w") as f:
            yaml.safe_dump({"oid": "test"}, f)
        assert load_config() is None


class TestSaveConfig:
    def test_creates_file_with_secure_permissions(self, tmp_config_file):
        save_config({"oid": "test-oid"})
        assert os.path.isfile(tmp_config_file)
        mode = os.stat(tmp_config_file).st_mode
        assert mode & 0o777 == 0o600

    def test_round_trips_data(self, tmp_config_file):
        data = {"oid": "abc-123", "api_key": "key-456", "env": {"prod": {"oid": "prod-oid"}}}
        save_config(data)
        loaded = load_config()
        assert loaded == data

    def test_raises_in_ephemeral_mode(self, tmp_config_file, monkeypatch):
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        with pytest.raises(ConfigError):
            save_config({"oid": "test"})


class TestGetEnvironmentCreds:
    def test_default_creds(self, tmp_config_file):
        save_config({"oid": "my-oid", "api_key": "my-key", "uid": "my-uid"})
        creds = get_environment_creds("default")
        assert creds["oid"] == "my-oid"
        assert creds["api_key"] == "my-key"
        assert creds["uid"] == "my-uid"

    def test_named_environment(self, tmp_config_file):
        save_config({
            "oid": "default-oid",
            "api_key": "default-key",
            "env": {
                "production": {"oid": "prod-oid", "api_key": "prod-key"},
            },
        })
        creds = get_environment_creds("production")
        assert creds["oid"] == "prod-oid"
        assert creds["api_key"] == "prod-key"

    def test_missing_environment_returns_none(self, tmp_config_file):
        save_config({"oid": "default-oid"})
        creds = get_environment_creds("nonexistent")
        assert creds["oid"] is None
        assert creds["api_key"] is None

    def test_no_file_returns_none(self, tmp_config_file):
        creds = get_environment_creds("default")
        assert creds["oid"] is None


class TestResolveCredentials:
    def test_explicit_params_highest_priority(self, tmp_config_file):
        save_config({"oid": "file-oid", "api_key": "file-key"})
        creds = resolve_credentials(oid="explicit-oid", api_key="explicit-key")
        assert creds["oid"] == "explicit-oid"
        assert creds["api_key"] == "explicit-key"

    def test_env_vars_override_file(self, tmp_config_file, monkeypatch):
        save_config({"oid": "file-oid", "api_key": "file-key"})
        monkeypatch.setenv("LC_OID", "env-oid")
        monkeypatch.setenv("LC_API_KEY", "env-key")
        creds = resolve_credentials()
        assert creds["oid"] == "env-oid"
        assert creds["api_key"] == "env-key"

    def test_file_used_when_no_env_vars(self, tmp_config_file):
        save_config({"oid": "file-oid", "api_key": "file-key"})
        creds = resolve_credentials()
        assert creds["oid"] == "file-oid"
        assert creds["api_key"] == "file-key"

    def test_named_environment_param(self, tmp_config_file):
        save_config({
            "env": {"staging": {"oid": "stage-oid", "api_key": "stage-key"}},
        })
        creds = resolve_credentials(environment="staging")
        assert creds["oid"] == "stage-oid"
        assert creds["api_key"] == "stage-key"

    def test_lc_current_env_selects_environment(self, tmp_config_file, monkeypatch):
        save_config({
            "env": {"myenv": {"oid": "myenv-oid", "api_key": "myenv-key"}},
        })
        monkeypatch.setenv("LC_CURRENT_ENV", "myenv")
        creds = resolve_credentials()
        assert creds["oid"] == "myenv-oid"
        assert creds["api_key"] == "myenv-key"

    def test_explicit_overrides_everything(self, tmp_config_file, monkeypatch):
        save_config({"oid": "file-oid", "api_key": "file-key"})
        monkeypatch.setenv("LC_OID", "env-oid")
        monkeypatch.setenv("LC_API_KEY", "env-key")
        creds = resolve_credentials(oid="explicit-oid")
        assert creds["oid"] == "explicit-oid"
        assert creds["api_key"] == "env-key"

    def test_uid_from_env(self, tmp_config_file, monkeypatch):
        monkeypatch.setenv("LC_API_KEY", "key")
        monkeypatch.setenv("LC_UID", "myuid")
        creds = resolve_credentials()
        assert creds["uid"] == "myuid"


class TestWriteCredentials:
    def test_write_default(self, tmp_config_file):
        write_credentials("default", "oid1", "key1")
        config = load_config()
        assert config["oid"] == "oid1"
        assert config["api_key"] == "key1"

    def test_write_named_env(self, tmp_config_file):
        write_credentials("staging", "oid2", "key2")
        config = load_config()
        assert config["env"]["staging"]["oid"] == "oid2"
        assert config["env"]["staging"]["api_key"] == "key2"

    def test_write_preserves_existing(self, tmp_config_file):
        write_credentials("default", "oid1", "key1")
        write_credentials("staging", "oid2", "key2")
        config = load_config()
        assert config["oid"] == "oid1"
        assert config["env"]["staging"]["oid"] == "oid2"

    def test_write_with_uid(self, tmp_config_file):
        write_credentials("default", "oid1", "key1", uid="user1")
        config = load_config()
        assert config["uid"] == "user1"

    def test_write_clears_uid(self, tmp_config_file):
        write_credentials("default", "oid1", "key1", uid="user1")
        write_credentials("default", "oid1", "key1", uid="")
        config = load_config()
        assert "uid" not in config

    def test_write_with_oauth(self, tmp_config_file):
        oauth = {"id_token": "tok", "refresh_token": "ref"}
        write_credentials("default", "oid1", None, oauth_creds=oauth)
        config = load_config()
        assert config["oauth"]["id_token"] == "tok"


class TestListEnvironments:
    def test_empty_config(self, tmp_config_file):
        assert list_environments() == []

    def test_default_only(self, tmp_config_file):
        save_config({"oid": "oid1", "api_key": "key1"})
        envs = list_environments()
        assert "default" in envs

    def test_named_envs(self, tmp_config_file):
        save_config({
            "oid": "oid1",
            "api_key": "key1",
            "env": {"staging": {}, "production": {}},
        })
        envs = list_environments()
        assert "default" in envs
        assert "staging" in envs
        assert "production" in envs


class TestGetConfigValue:
    """Tests for get_config_value - reads arbitrary config keys."""

    def test_reads_top_level_key(self, tmp_config_file):
        save_config({"oid": "oid1", "search_token_expiry_hours": 8})
        assert get_config_value("search_token_expiry_hours") == 8

    def test_returns_default_when_key_missing(self, tmp_config_file):
        save_config({"oid": "oid1"})
        assert get_config_value("search_token_expiry_hours", default=4.0) == 4.0

    def test_returns_default_when_no_config_file(self, tmp_config_file):
        assert get_config_value("anything", default="fallback") == "fallback"

    def test_returns_none_default_when_key_missing(self, tmp_config_file):
        save_config({"oid": "oid1"})
        assert get_config_value("nonexistent") is None

    def test_reads_from_named_environment(self, tmp_config_file):
        save_config({
            "search_token_expiry_hours": 4,
            "env": {"production": {"search_token_expiry_hours": 12}},
        })
        assert get_config_value("search_token_expiry_hours", environment="production") == 12

    def test_named_env_falls_back_to_default_if_key_missing(self, tmp_config_file):
        """Named env without the key returns default, not the top-level value."""
        save_config({
            "search_token_expiry_hours": 4,
            "env": {"production": {"oid": "prod-oid"}},
        })
        # The key is not in the 'production' env section, so returns default
        assert get_config_value("search_token_expiry_hours", default=99, environment="production") == 99

    def test_respects_lc_current_env(self, tmp_config_file, monkeypatch):
        save_config({
            "search_token_expiry_hours": 4,
            "env": {"staging": {"search_token_expiry_hours": 6}},
        })
        monkeypatch.setenv("LC_CURRENT_ENV", "staging")
        assert get_config_value("search_token_expiry_hours") == 6

    def test_respects_current_env_in_config(self, tmp_config_file):
        save_config({
            "current_env": "staging",
            "search_token_expiry_hours": 4,
            "env": {"staging": {"search_token_expiry_hours": 10}},
        })
        assert get_config_value("search_token_expiry_hours") == 10

    def test_returns_default_in_ephemeral_mode(self, tmp_config_file, monkeypatch):
        save_config({"search_token_expiry_hours": 8})
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        assert get_config_value("search_token_expiry_hours", default=4.0) == 4.0

    def test_reads_string_value(self, tmp_config_file):
        """Config values can be any YAML type."""
        save_config({"my_key": "hello"})
        assert get_config_value("my_key") == "hello"


class TestConfigCaching:
    """Tests for the per-process config caching behavior."""

    def test_load_config_returns_cached_on_second_call(self, tmp_config_file, monkeypatch):
        """Call load_config() twice, verify the file is only read once.

        Uses monkeypatch to track calls to safe_open_read. The second
        call should return the cached result without re-reading the file.
        """
        data = {"oid": "cached-test"}
        with open(tmp_config_file, "w") as f:
            yaml.safe_dump(data, f)

        call_count = {"n": 0}
        original_safe_open_read = None
        import limacharlie.config as config_mod
        original_safe_open_read = config_mod.safe_open_read

        def tracking_open_read(path):
            call_count["n"] += 1
            return original_safe_open_read(path)

        monkeypatch.setattr("limacharlie.config.safe_open_read", tracking_open_read)

        result1 = load_config()
        result2 = load_config()
        assert result1 == {"oid": "cached-test"}
        assert result2 == {"oid": "cached-test"}
        assert call_count["n"] == 1, "safe_open_read should be called exactly once"

    def test_save_config_updates_cache(self, tmp_config_file):
        """Call save_config({'oid': 'x'}) then load_config() without resetting.

        load_config() should return {'oid': 'x'} from the in-process
        cache without needing to read the file again.
        """
        save_config({"oid": "x"})
        result = load_config()
        assert result == {"oid": "x"}

    def test_write_credentials_does_not_corrupt_cache_on_failure(self, tmp_config_file, monkeypatch):
        """Set ephemeral mode AFTER writing initial config.

        write_credentials should raise ConfigError (from save_config).
        After unsetting ephemeral and resetting the cache, load_config()
        should still return the original data. This verifies that
        write_credentials uses deepcopy to avoid corrupting the cached
        config dict when save_config fails.
        """
        from limacharlie.config import _reset_config_cache

        # Write initial config
        save_config({"oid": "original", "api_key": "key1"})
        # Verify it loads
        assert load_config() == {"oid": "original", "api_key": "key1"}

        # Now set ephemeral mode so save_config will raise
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        with pytest.raises(ConfigError):
            write_credentials("default", "corrupted-oid", "corrupted-key")

        # Unset ephemeral and reset cache to force re-read from disk
        monkeypatch.delenv("LC_EPHEMERAL_CREDS")
        _reset_config_cache()
        result = load_config()
        assert result["oid"] == "original"
        assert result["api_key"] == "key1"


class TestIsEphemeral:
    def test_not_ephemeral_by_default(self, monkeypatch):
        monkeypatch.delenv("LC_EPHEMERAL_CREDS", raising=False)
        assert is_ephemeral() is False

    def test_ephemeral_when_set(self, monkeypatch):
        monkeypatch.setenv("LC_EPHEMERAL_CREDS", "1")
        assert is_ephemeral() is True
