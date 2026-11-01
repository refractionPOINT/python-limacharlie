"""Tests for ``limacharlie auth signup``.

The user profile is created server-side by the JWT service on the first
``fb_auth`` token exchange, so signup must go straight from OAuth to org
creation without any separate account-creation HTTP call.
"""

import os
from unittest import mock

import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.config import load_config


@pytest.fixture
def tmp_config_file(monkeypatch, tmp_path):
    from limacharlie.config import _reset_config_cache
    from limacharlie.paths import _reset_path_cache

    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)

    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    for var in ("LC_CREDS_FILE", "LC_LEGACY_CONFIG", "LC_OID", "LC_API_KEY",
                "LC_UID", "LC_CURRENT_ENV", "LC_EPHEMERAL_CREDS"):
        monkeypatch.delenv(var, raising=False)
    _reset_path_cache()
    _reset_config_cache()
    yield
    _reset_path_cache()
    _reset_config_cache()


def _oauth_tokens():
    return {
        "id_token": "id-token",
        "refresh_token": "refresh-token",
        "expires_at": 9999999999,
        "provider": "google.com",
        "uid": "firebase-uid-1",
        "email": "new.user@example.com",
    }


def test_signup_creates_org_without_account_creation_call(tmp_config_file):
    with mock.patch(
        "limacharlie.oauth_firebase_simple.SimpleFirebaseAuth.start_auth_flow",
        return_value=_oauth_tokens(),
    ), mock.patch(
        "limacharlie.commands.auth.Client.refresh_jwt",
    ) as refresh_jwt, mock.patch(
        "limacharlie.commands.auth.Organization.create_org",
        # The real POST /orgs/new response nests the OID under "data".
        return_value={"data": {"oid": "new-oid"}},
    ) as create_org, mock.patch(
        "requests.post", side_effect=AssertionError("unexpected HTTP POST"),
    ), mock.patch(
        "requests.Session.request", side_effect=AssertionError("unexpected HTTP request"),
    ):
        result = CliRunner().invoke(cli, [
            "auth", "signup", "--no-browser", "--org-name", "My Org",
        ])

    assert result.exit_code == 0, result.output
    assert "Organization created: new-oid" in result.output
    assert "Step 1/2" in result.output
    assert "Step 2/2" in result.output
    refresh_jwt.assert_called_once_with(oid_override="-")
    create_org.assert_called_once()
    assert create_org.call_args.kwargs["name"] == "My Org"

    config = load_config()
    assert config["oid"] == "new-oid"
    assert config["oauth"]["id_token"] == "id-token"
    assert "email" not in config["oauth"]


def _run_signup(create_org_response):
    with mock.patch(
        "limacharlie.oauth_firebase_simple.SimpleFirebaseAuth.start_auth_flow",
        return_value=_oauth_tokens(),
    ), mock.patch(
        "limacharlie.commands.auth.Client.refresh_jwt",
    ), mock.patch(
        "limacharlie.commands.auth.Organization.create_org",
        return_value=create_org_response,
    ):
        return CliRunner().invoke(cli, [
            "auth", "signup", "--no-browser", "--org-name", "My Org",
        ])


def test_signup_reads_oid_from_json_string_data(tmp_config_file):
    result = _run_signup({"data": '{"oid": "str-oid"}'})

    assert result.exit_code == 0, result.output
    assert "Organization created: str-oid" in result.output
    assert load_config()["oid"] == "str-oid"


@pytest.mark.parametrize("response", [
    {"oid": "top-level-oid"},
    {"data": {}},
    {"data": "not json"},
    {},
])
def test_signup_without_oid_in_response_fails_with_guidance(tmp_config_file, response):
    result = _run_signup(response)

    assert result.exit_code == 6, result.output
    assert "Organization created" not in result.output
    assert "limacharlie org list" in result.output
    assert "auth use-org" in result.output
    config = load_config()
    # The sign-in is kept so the person can select the org themselves.
    assert config["oauth"]["id_token"] == "id-token"
    assert not config.get("oid")
