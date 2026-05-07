"""Tests for ``limacharlie auth login`` argument validation and credential
persistence.

Covers the three login shapes supported by the CLI:

* ``--oid + --api-key``                         -- org-scoped API key
* ``--uid + --api-key`` (with optional --oid)   -- user-scoped API key
* ``--oauth``                                   -- not exercised here

and the error paths when required flags are missing.  Also asserts that a
user-scoped login clears any stale oid persisted from a previous org-scoped
login in the same environment.
"""

import os

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.config import load_config


@pytest.fixture
def tmp_config_file(monkeypatch, tmp_path):
    """Point config resolution at a fresh temp directory.

    Mirrors the fixture in ``test_config.py`` so each test starts with no
    persisted credentials and a clean cache.
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


class TestLoginValidator:
    """The validator should accept any of the three valid flag shapes and
    reject everything else with a clear error and exit code 4."""

    def test_org_scoped_login_succeeds(self, tmp_config_file):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "auth", "login",
            "--oid", "org-1",
            "--api-key", "key-1",
        ])
        assert result.exit_code == 0, result.output
        config = load_config()
        assert config["oid"] == "org-1"
        assert config["api_key"] == "key-1"
        assert "uid" not in config

    def test_user_scoped_login_without_oid_succeeds(self, tmp_config_file):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "auth", "login",
            "--uid", "user-1",
            "--api-key", "key-1",
        ])
        assert result.exit_code == 0, result.output
        config = load_config()
        assert config["api_key"] == "key-1"
        assert config["uid"] == "user-1"
        assert "oid" not in config

    def test_service_account_login_with_all_three_flags(self, tmp_config_file):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "auth", "login",
            "--oid", "org-1",
            "--uid", "user-1",
            "--api-key", "key-1",
        ])
        assert result.exit_code == 0, result.output
        config = load_config()
        assert config["oid"] == "org-1"
        assert config["api_key"] == "key-1"
        assert config["uid"] == "user-1"

    def test_missing_api_key_errors(self, tmp_config_file):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "login", "--oid", "org-1"])
        assert result.exit_code == 4
        assert "--api-key is required" in result.output
        assert load_config() is None

    def test_missing_oid_and_uid_errors(self, tmp_config_file):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "login", "--api-key", "key-1"])
        assert result.exit_code == 4
        # The error should distinguish the two key types so the user can
        # pick the right one from the LC web UI.
        assert "--oid" in result.output
        assert "--uid" in result.output
        assert load_config() is None


class TestLoginNamedEnvironment:
    """Login should write under the correct env block, not the default
    block, when --env is supplied."""

    def test_user_scoped_login_writes_to_named_env(self, tmp_config_file):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "auth", "login",
            "--env", "staging",
            "--uid", "user-1",
            "--api-key", "key-1",
        ])
        assert result.exit_code == 0, result.output
        config = load_config()
        assert config["env"]["staging"]["api_key"] == "key-1"
        assert config["env"]["staging"]["uid"] == "user-1"
        assert "oid" not in config["env"]["staging"]


class TestStaleOidCleanup:
    """Switching to user-scoped credentials must drop any stale oid left
    behind by a previous org-scoped login in the same environment.
    Otherwise subsequent commands would pair the new user-scoped api key
    with the wrong org context."""

    def test_user_scoped_relogin_clears_default_oid(self, tmp_config_file):
        runner = CliRunner()
        # First, an org-scoped login persists oid=org-old.
        first = runner.invoke(cli, [
            "auth", "login",
            "--oid", "org-old",
            "--api-key", "key-old",
        ])
        assert first.exit_code == 0, first.output
        assert load_config()["oid"] == "org-old"

        # Then a user-scoped login on the same env (no --oid) must drop it.
        second = runner.invoke(cli, [
            "auth", "login",
            "--uid", "user-new",
            "--api-key", "key-new",
        ])
        assert second.exit_code == 0, second.output
        config = load_config()
        assert "oid" not in config
        assert config["api_key"] == "key-new"
        assert config["uid"] == "user-new"

    def test_user_scoped_relogin_clears_named_env_oid(self, tmp_config_file):
        runner = CliRunner()
        first = runner.invoke(cli, [
            "auth", "login",
            "--env", "staging",
            "--oid", "org-old",
            "--api-key", "key-old",
        ])
        assert first.exit_code == 0, first.output
        assert load_config()["env"]["staging"]["oid"] == "org-old"

        second = runner.invoke(cli, [
            "auth", "login",
            "--env", "staging",
            "--uid", "user-new",
            "--api-key", "key-new",
        ])
        assert second.exit_code == 0, second.output
        env_block = load_config()["env"]["staging"]
        assert "oid" not in env_block
        assert env_block["api_key"] == "key-new"
        assert env_block["uid"] == "user-new"

    def test_user_scoped_relogin_does_not_touch_other_envs(self, tmp_config_file):
        runner = CliRunner()
        # Persist an oid in 'production' that should be left alone.
        prod_login = runner.invoke(cli, [
            "auth", "login",
            "--env", "production",
            "--oid", "org-prod",
            "--api-key", "key-prod",
        ])
        assert prod_login.exit_code == 0, prod_login.output

        # User-scoped login in 'staging' must not affect 'production'.
        staging_login = runner.invoke(cli, [
            "auth", "login",
            "--env", "staging",
            "--uid", "user-1",
            "--api-key", "key-1",
        ])
        assert staging_login.exit_code == 0, staging_login.output

        config = load_config()
        assert config["env"]["production"]["oid"] == "org-prod"
        assert config["env"]["production"]["api_key"] == "key-prod"
        assert "oid" not in config["env"]["staging"]

    def test_org_scoped_relogin_overwrites_oid(self, tmp_config_file):
        """Sanity check: org-scoped re-login should *update* the oid, not
        leave the old one in place. (This already worked pre-fix; the test
        guards against a regression where the cleanup helper accidentally
        clobbers the new value.)"""
        runner = CliRunner()
        first = runner.invoke(cli, [
            "auth", "login",
            "--oid", "org-old",
            "--api-key", "key-old",
        ])
        assert first.exit_code == 0, first.output

        second = runner.invoke(cli, [
            "auth", "login",
            "--oid", "org-new",
            "--api-key", "key-new",
        ])
        assert second.exit_code == 0, second.output
        config = load_config()
        assert config["oid"] == "org-new"
        assert config["api_key"] == "key-new"


class TestExplainText:
    """The --ai-help text should advertise the user-scoped shape so users
    discovering the CLI know the flag combo is supported."""

    def test_explain_mentions_user_scoped_form(self):
        from limacharlie.commands.auth import _EXPLAIN_LOGIN
        assert "--uid <UID> --api-key <KEY>" in _EXPLAIN_LOGIN
        assert "user-scoped" in _EXPLAIN_LOGIN.lower()
