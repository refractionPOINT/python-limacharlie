"""Microbenchmarks for config directory path resolution and migration overhead.

Measures the performance of path resolution (the overhead added to every
CLI invocation by the paths module), config loading from both new and
legacy layouts, and migration operations.

Critical hot paths that every CLI invocation pays:
- get_config_path() - called by load_config() on every invocation
- get_jwt_cache_path() - called by get_cached_jwt() on every invocation
- load_config() - called during credential resolution

The paths module uses per-process caching, so the first call does
filesystem stat() calls and env var lookups, while subsequent calls
return cached values. Both hot (cached) and cold (uncached) paths
are benchmarked.

Run with: pytest tests/microbenchmarks/test_paths_microbenchmark.py -v
"""

import json
import os
import time

import pytest
import yaml

from limacharlie.config import (
    _reset_config_cache,
    get_config_value,
    get_environment_creds,
    load_config,
    resolve_credentials,
    save_config,
    write_credentials,
)
from limacharlie.file_utils import atomic_write, safe_open_read
from limacharlie.paths import (
    _reset_path_cache,
    get_all_paths,
    get_checkpoint_dir,
    get_config_dir,
    get_config_path,
    get_jwt_cache_path,
    is_legacy_mode,
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Fully isolated environment for benchmarks."""
    from limacharlie.jwt_cache import _reset_cache_disabled

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
    _reset_config_cache()
    _reset_cache_disabled()
    yield tmp_path
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


# ---------------------------------------------------------------------------
# Path resolution - hot path (cached)
# ---------------------------------------------------------------------------

class TestPathResolutionCached:
    """Benchmark cached path resolution - the per-invocation cost after
    the first call. This is the fast path every CLI command pays.
    """

    def test_get_config_dir_cached(self, benchmark):
        """Cached get_config_dir - pure dict lookup, no I/O."""
        get_config_dir()  # prime cache
        benchmark(get_config_dir)

    def test_get_config_path_cached(self, benchmark):
        """Cached get_config_path - pure dict lookup, no I/O."""
        get_config_path()  # prime cache
        benchmark(get_config_path)

    def test_get_jwt_cache_path_cached(self, benchmark):
        """Cached get_jwt_cache_path - pure dict lookup, no I/O."""
        get_jwt_cache_path()  # prime cache
        benchmark(get_jwt_cache_path)

    def test_get_checkpoint_dir_cached(self, benchmark):
        """Cached get_checkpoint_dir - pure dict lookup, no I/O."""
        get_checkpoint_dir()  # prime cache
        benchmark(get_checkpoint_dir)

    def test_get_all_paths_cached(self, benchmark):
        """Cached get_all_paths - four cached lookups."""
        get_all_paths()  # prime cache
        benchmark(get_all_paths)

    def test_is_legacy_mode_hot(self, benchmark):
        """is_legacy_mode - single env var lookup (no caching, always live)."""
        benchmark(is_legacy_mode)


# ---------------------------------------------------------------------------
# Path resolution - cold path (uncached)
# ---------------------------------------------------------------------------

class TestPathResolutionCold:
    """Benchmark uncached path resolution - what the first call in a process
    pays. Includes env var lookups and filesystem stat() calls.
    """

    def test_get_config_path_cold(self, benchmark):
        """Cold get_config_path - env var lookup + stat."""
        def cold():
            _reset_path_cache()
            return get_config_path()
        benchmark(cold)

    def test_get_jwt_cache_path_cold(self, benchmark):
        """Cold get_jwt_cache_path - env var lookup + stat."""
        def cold():
            _reset_path_cache()
            return get_jwt_cache_path()
        benchmark(cold)

    def test_get_config_dir_cold(self, benchmark):
        """Cold get_config_dir - env var lookup."""
        def cold():
            _reset_path_cache()
            return get_config_dir()
        benchmark(cold)

    def test_get_all_paths_cold(self, benchmark):
        """Cold get_all_paths - four cold resolutions."""
        def cold():
            _reset_path_cache()
            return get_all_paths()
        benchmark(cold)

    def test_cold_path_with_legacy_fallback(self, benchmark, monkeypatch, tmp_path):
        """Cold path resolution when legacy file exists (stat + warning check).

        This is the worst-case cold path - checks new location (miss),
        then falls back to legacy (hit + deprecation warning).
        """
        import limacharlie.paths as paths_mod
        legacy_file = str(tmp_path / ".limacharlie")
        with open(legacy_file, "w") as f:
            f.write("oid: test\n")
        monkeypatch.setattr(paths_mod, "_LEGACY_CONFIG_FILE", legacy_file)
        monkeypatch.delenv("LC_CONFIG_DIR", raising=False)
        new_dir = str(tmp_path / "new_dir_does_not_exist")
        monkeypatch.setattr(paths_mod, "_default_config_dir", lambda: new_dir)

        import warnings
        def cold():
            _reset_path_cache()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return get_config_path()
        benchmark(cold)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:
    """Benchmark config file loading - the main I/O cost per CLI invocation."""

    def test_load_config_cached(self, benchmark, tmp_path):
        """Cached load_config - no I/O, returns in-memory dict."""
        config_dir = str(tmp_path / "lc_config")
        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump({"oid": "test", "api_key": "key"}, f)
        os.chmod(config_path, 0o600)
        load_config()  # prime cache
        benchmark(load_config)

    def test_load_config_cold_small(self, benchmark, tmp_path):
        """Cold load_config with small config file (2 keys)."""
        config_dir = str(tmp_path / "lc_config")
        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump({"oid": "test", "api_key": "key"}, f)
        os.chmod(config_path, 0o600)

        def cold():
            _reset_config_cache()
            return load_config()
        benchmark(cold)

    def test_load_config_cold_realistic(self, benchmark, tmp_path):
        """Cold load_config with realistic config (3 named environments)."""
        config_dir = str(tmp_path / "lc_config")
        config_path = os.path.join(config_dir, "config.yaml")
        data = {
            "oid": "default-oid",
            "api_key": "default-key",
            "uid": "default-uid",
            "current_env": "production",
            "no_warnings": False,
            "no_jwt_cache": False,
            "env": {
                "production": {"oid": "prod-oid", "api_key": "prod-key"},
                "staging": {"oid": "stage-oid", "api_key": "stage-key", "uid": "stage-uid"},
                "dev": {"oid": "dev-oid", "api_key": "dev-key"},
            },
        }
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f)
        os.chmod(config_path, 0o600)

        def cold():
            _reset_config_cache()
            return load_config()
        benchmark(cold)

    def test_load_config_cold_large(self, benchmark, tmp_path):
        """Cold load_config with large config (20 named environments)."""
        config_dir = str(tmp_path / "lc_config")
        config_path = os.path.join(config_dir, "config.yaml")
        data = {
            "oid": "default-oid",
            "api_key": "default-key",
            "env": {},
        }
        for i in range(20):
            data["env"][f"env_{i:03d}"] = {
                "oid": f"oid-{i}",
                "api_key": f"key-{i}-" + "x" * 32,
                "uid": f"uid-{i}",
            }
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f)
        os.chmod(config_path, 0o600)

        def cold():
            _reset_config_cache()
            return load_config()
        benchmark(cold)

    def test_load_config_missing_file(self, benchmark, tmp_path):
        """Cold load_config when config file doesn't exist (stat miss)."""
        def cold():
            _reset_config_cache()
            return load_config()
        benchmark(cold)


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

class TestCredentialResolution:
    """Benchmark credential resolution - the full chain from paths to creds."""

    def test_resolve_credentials_from_config(self, benchmark, tmp_path):
        """Full credential resolution from config file (cached config).

        This is what Client.__init__ calls. Includes load_config (cached)
        + env var checks + environment selection.
        """
        write_credentials("default", "bench-oid", "bench-key")
        _reset_config_cache()
        load_config()  # prime cache
        benchmark(resolve_credentials)

    def test_resolve_credentials_cold(self, benchmark, tmp_path):
        """Full cold credential resolution (config not cached).

        Includes path resolution (cached) + config file I/O + YAML
        parse + env var checks + environment selection.
        """
        write_credentials("default", "bench-oid", "bench-key")

        def cold():
            _reset_config_cache()
            return resolve_credentials()
        benchmark(cold)

    def test_resolve_credentials_named_env(self, benchmark, tmp_path):
        """Credential resolution for a named environment (cached config)."""
        write_credentials("production", "prod-oid", "prod-key")
        _reset_config_cache()
        load_config()  # prime cache
        benchmark(resolve_credentials, environment="production")

    def test_get_config_value_cached(self, benchmark, tmp_path):
        """get_config_value with cached config - dictionary lookup."""
        save_config({"oid": "x", "search_token_expiry_hours": 8})
        _reset_config_cache()
        load_config()  # prime cache
        benchmark(get_config_value, "search_token_expiry_hours", 4.0)

    def test_get_environment_creds_cached(self, benchmark, tmp_path):
        """get_environment_creds with cached config."""
        write_credentials("staging", "s-oid", "s-key")
        _reset_config_cache()
        load_config()  # prime cache
        benchmark(get_environment_creds, "staging")


# ---------------------------------------------------------------------------
# Config writing
# ---------------------------------------------------------------------------

class TestConfigWriting:
    """Benchmark config write operations."""

    def test_save_config_small(self, benchmark, tmp_path):
        """save_config with a small config dict (atomic write + YAML dump)."""
        data = {"oid": "test", "api_key": "key"}
        benchmark(save_config, data)

    def test_save_config_realistic(self, benchmark, tmp_path):
        """save_config with realistic config (3 environments)."""
        data = {
            "oid": "default-oid",
            "api_key": "default-key",
            "env": {
                "production": {"oid": "p", "api_key": "pk"},
                "staging": {"oid": "s", "api_key": "sk"},
                "dev": {"oid": "d", "api_key": "dk"},
            },
        }
        benchmark(save_config, data)

    def test_write_credentials_new_env(self, benchmark, tmp_path):
        """write_credentials adding a new named environment.

        Includes load_config (cached after first call) + dict mutation
        + save_config (YAML dump + atomic write).
        """
        save_config({"oid": "base"})
        counter = [0]

        def write():
            counter[0] += 1
            write_credentials(f"env_{counter[0]}", f"oid-{counter[0]}", f"key-{counter[0]}")
        benchmark(write)


# ---------------------------------------------------------------------------
# Migration overhead
# ---------------------------------------------------------------------------

class TestMigrationOverhead:
    """Benchmark migration-related operations."""

    def test_migrate_config_file(self, benchmark, tmp_path):
        """Migrate a realistic config file (read + atomic_write + verify).

        Measures the per-file cost of `config migrate`.
        """
        source = str(tmp_path / "legacy_config")
        data = {
            "oid": "default-oid",
            "api_key": "default-key",
            "env": {
                "production": {"oid": "p", "api_key": "pk"},
                "staging": {"oid": "s", "api_key": "sk"},
            },
        }
        content = yaml.safe_dump(data).encode()
        with open(source, "wb") as f:
            f.write(content)
        os.chmod(source, 0o600)

        dest = str(tmp_path / "new_config")

        def migrate():
            read_content = safe_open_read(source)
            atomic_write(dest, read_content)
            # Verify
            verify = safe_open_read(dest)
            assert verify == read_content
        benchmark(migrate)

    def test_migrate_jwt_cache(self, benchmark, tmp_path):
        """Migrate a JWT cache file (smaller, JSON)."""
        source = str(tmp_path / "legacy_jwt")
        entries = {}
        for i in range(5):
            entries[f"key_{i}"] = {"jwt": f"jwt_value_{i}_" + "x" * 200}
        content = json.dumps(entries).encode()
        with open(source, "wb") as f:
            f.write(content)
        os.chmod(source, 0o600)

        dest = str(tmp_path / "new_jwt")

        def migrate():
            read_content = safe_open_read(source)
            atomic_write(dest, read_content)
            verify = safe_open_read(dest)
            assert verify == read_content
        benchmark(migrate)


# ---------------------------------------------------------------------------
# End-to-end: simulated CLI startup overhead
# ---------------------------------------------------------------------------

class TestCLIStartupOverhead:
    """Benchmark the total overhead the paths/config system adds to CLI startup.

    Simulates what happens during a typical CLI invocation:
    1. Resolve all paths (cold on first call, cached thereafter)
    2. Load config from disk
    3. Resolve credentials
    """

    def test_first_invocation_cold(self, benchmark, tmp_path):
        """First CLI invocation in a process - everything is cold.

        This is the worst-case startup overhead. Includes path resolution
        (env var lookups + stat), config file I/O + YAML parse, and
        credential resolution.
        """
        write_credentials("default", "bench-oid", "bench-key")

        def first_invocation():
            _reset_path_cache()
            _reset_config_cache()
            # Path resolution (cold)
            get_config_path()
            get_jwt_cache_path()
            # Config load (cold - YAML parse from disk)
            load_config()
            # Credential resolution (config cached from above)
            resolve_credentials()
        benchmark(first_invocation)

    def test_second_invocation_warm(self, benchmark, tmp_path):
        """Second CLI invocation - paths cached, config cached.

        This is the typical cost when paths and config are already cached
        (e.g. second call to resolve_credentials in the same process).
        """
        write_credentials("default", "bench-oid", "bench-key")
        # Prime all caches
        get_config_path()
        get_jwt_cache_path()
        load_config()

        def second_invocation():
            get_config_path()
            get_jwt_cache_path()
            load_config()
            resolve_credentials()
        benchmark(second_invocation)

    def test_startup_with_named_environment(self, benchmark, tmp_path):
        """CLI startup with a named environment (e.g. --env production).

        Slightly more work than default: environment lookup in config dict.
        """
        write_credentials("default", "d-oid", "d-key")
        write_credentials("production", "p-oid", "p-key")
        _reset_config_cache()
        # Prime caches
        get_config_path()
        load_config()

        def startup():
            resolve_credentials(environment="production")
        benchmark(startup)
