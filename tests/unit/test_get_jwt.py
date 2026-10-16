"""Tests for Client.get_jwt, token expiry resolution, and CLI commands.

Tests custom token expiry generation for long-running operations
like search queries. Covers SDK method, resolution logic (CLI flag >
config file > constant default), and CLI commands.
"""

import base64
import json
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

import click
import pytest
from click.testing import CliRunner

from limacharlie.client import Client
from limacharlie.cli import LimaCharlieContext
from limacharlie.commands.search import (
    DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS,
    CONFIG_KEY_SEARCH_TOKEN_EXPIRY,
    _resolve_token_expiry,
)
from limacharlie.errors import ValidationError


def _make_jwt(exp: float | int, iat: float | int | None = None) -> str:
    """Return an unsigned JWT-shaped string whose payload carries ``exp``
    (and ``iat`` when given)."""
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    payload = {"exp": exp} if iat is None else {"exp": exp, "iat": iat}
    return f"{seg({'alg': 'HS256'})}.{seg(payload)}.{seg('sig')}"


def _make_ctx():
    """Create a LimaCharlieContext for CLI test invocation."""
    return LimaCharlieContext()


class TestClientGetJwt:
    """Tests for Client.get_jwt SDK method."""

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_default_expiry(self, mock_resolve):
        """get_jwt with no args uses default expiry (~1 hour)."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")
        client.refresh_jwt = MagicMock()
        client._jwt = "mock-jwt-token"

        token = client.get_jwt()

        client.refresh_jwt.assert_called_once_with(expiry=None)
        assert token == "mock-jwt-token"

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_custom_expiry_hours(self, mock_resolve):
        """get_jwt(expiry_hours=8) requests a lifetime of 8 hours in seconds."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")
        client.refresh_jwt = MagicMock()
        client._jwt = "mock-jwt-8h"

        token = client.get_jwt(expiry_hours=8)

        # A duration, not a timestamp: the JWT endpoint adds it to now.
        client.refresh_jwt.assert_called_once_with(expiry=8 * 3600)
        assert token == "mock-jwt-8h"

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_fractional_hours(self, mock_resolve):
        """get_jwt supports fractional hours (e.g. 0.5 = 30 minutes)."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")
        client.refresh_jwt = MagicMock()
        client._jwt = "mock-jwt-30m"

        client.get_jwt(expiry_hours=0.5)

        client.refresh_jwt.assert_called_once_with(expiry=1800)

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_sub_second_hours_round_up(self, mock_resolve):
        """A lifetime under one second rounds up to 1, never down to 0."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")
        client.refresh_jwt = MagicMock()
        client._jwt = "mock-jwt-tiny"

        client.get_jwt(expiry_hours=0.0001)  # 0.36 seconds

        client.refresh_jwt.assert_called_once_with(expiry=1)

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_zero_hours_raises_validation_error(self, mock_resolve):
        """get_jwt(expiry_hours=0) raises ValidationError."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")

        with pytest.raises(ValidationError, match="positive"):
            client.get_jwt(expiry_hours=0)

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_negative_hours_raises_validation_error(self, mock_resolve):
        """get_jwt(expiry_hours=-1) raises ValidationError."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")

        with pytest.raises(ValidationError, match="positive"):
            client.get_jwt(expiry_hours=-1)

    @patch("limacharlie.client.resolve_credentials")
    def test_get_jwt_none_jwt_raises_auth_error(self, mock_resolve):
        """get_jwt raises AuthenticationError if refresh_jwt doesn't set _jwt."""
        from limacharlie.errors import AuthenticationError
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")
        client.refresh_jwt = MagicMock()  # Does not set _jwt
        client._jwt = None

        with pytest.raises(AuthenticationError, match="Failed to generate"):
            client.get_jwt()



class TestJwtExpirySentToEndpoint:
    """The expiry the SDK puts on the wire to the JWT endpoint.

    The endpoint reads ``expiry`` as a lifetime in seconds and adds it to
    the time of the request, so these tests drive get_jwt through the real
    refresh path and read the form body that reaches ``urlopen``.
    """

    @staticmethod
    def _respond_with(mock_urlopen, jwt):
        response = MagicMock()
        response.read.return_value = json.dumps({"jwt": jwt}).encode()
        mock_urlopen.return_value = response

    @staticmethod
    def _sent_form(mock_urlopen):
        request = mock_urlopen.call_args[0][0]
        return parse_qs(request.data.decode())

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_api_key_path_sends_lifetime_in_seconds(self, mock_urlopen, mock_resolve, _get, _put):
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        jwt = _make_jwt(time.time() + 4 * 3600)
        self._respond_with(mock_urlopen, jwt)
        client = Client(oid="test-oid")

        assert client.get_jwt(expiry_hours=4) == jwt

        form = self._sent_form(mock_urlopen)
        assert form["expiry"] == ["14400"]
        assert form["oid"] == ["test-oid"]

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_oauth_path_sends_lifetime_in_seconds(self, mock_urlopen, mock_resolve, _get, _put):
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None, "api_key": None,
            "oauth": {"id_token": "id", "refresh_token": "ref"},
        }
        jwt = _make_jwt(time.time() + 8 * 3600)
        self._respond_with(mock_urlopen, jwt)
        client = Client(oid="test-oid")

        with patch.object(Client, "_refreshed_oauth_id_token", return_value="id-token"):
            assert client.get_jwt(expiry_hours=8) == jwt

        form = self._sent_form(mock_urlopen)
        assert form["fb_auth"] == ["id-token"]
        assert form["expiry"] == ["28800"]

    @patch("limacharlie.jwt_cache.put_cached_jwt")
    @patch("limacharlie.jwt_cache.get_cached_jwt", return_value=None)
    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_default_sends_no_expiry(self, mock_urlopen, mock_resolve, _get, _put):
        """Without expiry_hours the endpoint's own default applies."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        self._respond_with(mock_urlopen, _make_jwt(time.time() + 3600))
        client = Client(oid="test-oid")
        client._jwt = None

        client.get_jwt()

        assert "expiry" not in self._sent_form(mock_urlopen)

class TestResolveTokenExpiry:
    """Tests for _resolve_token_expiry resolution logic.

    Priority: CLI flag > config file > DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS.
    """

    def test_cli_value_takes_highest_priority(self):
        """Explicit CLI value overrides config and default."""
        with patch("limacharlie.commands.search.get_config_value", return_value=10.0):
            assert _resolve_token_expiry(8.0) == 8.0

    def test_config_value_overrides_default(self):
        """Config file value overrides the constant default."""
        with patch("limacharlie.commands.search.get_config_value", return_value=6.0):
            assert _resolve_token_expiry(None) == 6.0

    def test_config_value_as_string(self):
        """Config values are often loaded as strings from YAML - should coerce."""
        with patch("limacharlie.commands.search.get_config_value", return_value="12"):
            assert _resolve_token_expiry(None) == 12.0

    def test_config_value_as_int(self):
        """Config values may be int from YAML - should coerce to float."""
        with patch("limacharlie.commands.search.get_config_value", return_value=8):
            assert _resolve_token_expiry(None) == 8.0

    def test_default_when_no_cli_no_config(self):
        """Falls back to constant when neither CLI nor config is set."""
        with patch("limacharlie.commands.search.get_config_value", return_value=None):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_default_when_config_is_zero(self):
        """Zero config value is ignored (not positive) - falls back to default."""
        with patch("limacharlie.commands.search.get_config_value", return_value=0):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_default_when_config_is_negative(self):
        """Negative config value is ignored - falls back to default."""
        with patch("limacharlie.commands.search.get_config_value", return_value=-5):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_default_when_config_is_non_numeric(self):
        """Non-numeric config value is ignored - falls back to default."""
        with patch("limacharlie.commands.search.get_config_value", return_value="not-a-number"):
            assert _resolve_token_expiry(None) == DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS

    def test_cli_zero_passes_through(self):
        """CLI value of 0 passes through (validation happens later in get_jwt)."""
        with patch("limacharlie.commands.search.get_config_value", return_value=None):
            assert _resolve_token_expiry(0.0) == 0.0

    def test_environment_passed_to_config_lookup(self):
        """Environment name is forwarded to get_config_value."""
        with patch("limacharlie.commands.search.get_config_value") as mock_gcv:
            mock_gcv.return_value = None
            _resolve_token_expiry(None, environment="staging")
            mock_gcv.assert_called_once_with(
                CONFIG_KEY_SEARCH_TOKEN_EXPIRY,
                default=None,
                environment="staging",
            )


class TestSearchRunTokenExpiry:
    """Tests for --token-expiry option in search run CLI command."""

    def test_run_with_explicit_token_expiry(self):
        """--token-expiry triggers get_jwt with the specified value."""
        from limacharlie.commands.search import run

        runner = CliRunner()
        with patch("limacharlie.commands.search._get_org") as mock_get_org:
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="custom-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}
            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            result = runner.invoke(run, [
                "--query", "event", "--start", "1000", "--end", "2000",
                "--token-expiry", "8",
            ], obj=_make_ctx(), catch_exceptions=False)

            mock_org.client.get_jwt.assert_called_once_with(expiry_hours=8.0)

    def test_run_without_token_expiry_uses_default(self):
        """Without --token-expiry, get_jwt is called with the default expiry."""
        from limacharlie.commands.search import run

        runner = CliRunner()
        with patch("limacharlie.commands.search._get_org") as mock_get_org, \
             patch("limacharlie.commands.search.get_config_value", return_value=None):
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="default-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}
            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            result = runner.invoke(run, [
                "--query", "event", "--start", "1000", "--end", "2000",
            ], obj=_make_ctx(), catch_exceptions=False)

            mock_org.client.get_jwt.assert_called_once_with(
                expiry_hours=DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS,
            )

    def test_run_uses_config_file_expiry(self):
        """Config file search_token_expiry_hours is used when no CLI flag."""
        from limacharlie.commands.search import run

        runner = CliRunner()
        with patch("limacharlie.commands.search._get_org") as mock_get_org, \
             patch("limacharlie.commands.search.get_config_value", return_value=6.0):
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="config-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}
            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            result = runner.invoke(run, [
                "--query", "event", "--start", "1000", "--end", "2000",
            ], obj=_make_ctx(), catch_exceptions=False)

            mock_org.client.get_jwt.assert_called_once_with(expiry_hours=6.0)

    def test_run_cli_flag_overrides_config(self):
        """--token-expiry CLI flag takes priority over config file value."""
        from limacharlie.commands.search import run

        runner = CliRunner()
        with patch("limacharlie.commands.search._get_org") as mock_get_org, \
             patch("limacharlie.commands.search.get_config_value", return_value=6.0):
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="override-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}
            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            result = runner.invoke(run, [
                "--query", "event", "--start", "1000", "--end", "2000",
                "--token-expiry", "12",
            ], obj=_make_ctx(), catch_exceptions=False)

            mock_org.client.get_jwt.assert_called_once_with(expiry_hours=12.0)

    def test_run_with_large_token_expiry_shows_warning(self):
        """--token-expiry > 24 shows security warning on stderr."""
        from limacharlie.commands.search import run

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.search._get_org") as mock_get_org:
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="custom-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}
            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            result = runner.invoke(run, [
                "--query", "event", "--start", "1000", "--end", "2000",
                "--token-expiry", "48",
            ], obj=_make_ctx(), catch_exceptions=False)

            # Warning goes to stderr since click.echo(..., err=True)
            assert "Warning" in result.stderr or "security" in result.stderr.lower()


class TestSavedRunTokenExpiry:
    """Tests for --token-expiry option in search saved-run CLI command."""

    def test_saved_run_with_token_expiry_calls_get_jwt(self):
        """--token-expiry triggers get_jwt before executing saved query."""
        from limacharlie.commands.search import saved_run

        runner = CliRunner()
        with patch("limacharlie.commands.search._get_org") as mock_get_org:
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="custom-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}

            # Mock hive.get to return a saved query
            mock_hive_record = MagicMock()
            mock_hive_record.data = {
                "query": "event | limit 10",
                "start": 1000,
                "end": 2000,
                "stream": "event",
            }

            mock_hive = MagicMock()
            mock_hive.get.return_value = mock_hive_record

            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            with patch("limacharlie.commands.search.Hive", return_value=mock_hive):
                result = runner.invoke(saved_run, [
                    "--name", "my-query",
                    "--token-expiry", "4",
                ], obj=_make_ctx(), catch_exceptions=False)

            mock_org.client.get_jwt.assert_called_once_with(expiry_hours=4.0)

    def test_saved_run_without_token_expiry_uses_default(self):
        """Without --token-expiry, saved-run uses the default token expiry."""
        from limacharlie.commands.search import saved_run

        runner = CliRunner()
        with patch("limacharlie.commands.search._get_org") as mock_get_org, \
             patch("limacharlie.commands.search.get_config_value", return_value=None):
            mock_org = MagicMock()
            mock_org.client = MagicMock()
            mock_org.client.get_jwt = MagicMock(return_value="default-jwt")
            mock_org.oid = "test-oid"
            mock_org.get_urls.return_value = {"search": "search.lc.io"}

            mock_hive_record = MagicMock()
            mock_hive_record.data = {
                "query": "event | limit 10",
                "start": 1000,
                "end": 2000,
                "stream": "event",
            }
            mock_hive = MagicMock()
            mock_hive.get.return_value = mock_hive_record

            mock_org.client.request.side_effect = [
                {"queryId": "q-1"},
                {"results": [], "completed": True},
                {},  # DELETE
            ]
            mock_get_org.return_value = mock_org

            with patch("limacharlie.commands.search.Hive", return_value=mock_hive):
                result = runner.invoke(saved_run, [
                    "--name", "my-query",
                ], obj=_make_ctx(), catch_exceptions=False)

            mock_org.client.get_jwt.assert_called_once_with(
                expiry_hours=DEFAULT_SEARCH_TOKEN_EXPIRY_HOURS,
            )


class TestGetTokenCommand:
    """Tests for auth get-token CLI command."""

    def test_get_token_raw_format(self):
        """get-token outputs raw token by default."""
        from limacharlie.commands.auth import get_token

        runner = CliRunner()
        with patch("limacharlie.commands.auth._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_jwt.return_value = "raw-jwt-token-here"
            mock_client.oid = "test-oid"
            mock_get_client.return_value = mock_client

            result = runner.invoke(get_token, ["--hours", "8"], catch_exceptions=False)

            assert result.exit_code == 0
            assert "raw-jwt-token-here" in result.output
            mock_client.get_jwt.assert_called_once_with(expiry_hours=8.0)

    def test_get_token_json_format(self):
        """get-token --format json outputs JSON with metadata."""
        from limacharlie.commands.auth import get_token

        runner = CliRunner()
        with patch("limacharlie.commands.auth._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_jwt.return_value = "json-jwt-token"
            mock_client.oid = "test-oid"
            mock_get_client.return_value = mock_client

            result = runner.invoke(get_token, [
                "--hours", "4", "--format", "json",
            ], catch_exceptions=False)

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["token"] == "json-jwt-token"
            assert data["valid_hours"] == 4.0
            assert data["oid"] == "test-oid"
            assert "expiry" in data
            assert "expiry_iso" in data

    def test_get_token_json_reports_the_tokens_own_expiry(self):
        """The reported expiry is the token's exp claim, not the requested one.

        get_jwt may hand back a cached token whose lifetime differs from
        the request, so only the claim says when the token stops working.
        """
        from limacharlie.commands.auth import get_token

        exp = int(time.time()) + 30 * 24 * 3600
        runner = CliRunner()
        with patch("limacharlie.commands.auth._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_jwt.return_value = _make_jwt(exp)
            mock_client.oid = "test-oid"
            mock_get_client.return_value = mock_client

            result = runner.invoke(get_token, [
                "--hours", "4", "--format", "json",
            ], catch_exceptions=False)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["expiry"] == exp
        assert data["valid_hours"] == 4.0

    def test_get_token_json_falls_back_to_requested_expiry(self):
        """A token without a readable exp claim reports the requested expiry."""
        from limacharlie.commands.auth import get_token

        runner = CliRunner()
        with patch("limacharlie.commands.auth._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_jwt.return_value = "not-a-jwt"
            mock_client.oid = "test-oid"
            mock_get_client.return_value = mock_client

            before = int(time.time())
            result = runner.invoke(get_token, [
                "--hours", "2", "--format", "json",
            ], catch_exceptions=False)
            after = int(time.time())

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert before + 7200 <= data["expiry"] <= after + 7200

    def test_get_token_default_1_hour(self):
        """get-token without --hours uses 1 hour default."""
        from limacharlie.commands.auth import get_token

        runner = CliRunner()
        with patch("limacharlie.commands.auth._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_jwt.return_value = "default-jwt"
            mock_client.oid = "test-oid"
            mock_get_client.return_value = mock_client

            result = runner.invoke(get_token, [], catch_exceptions=False)

            assert result.exit_code == 0
            mock_client.get_jwt.assert_called_once_with(expiry_hours=1.0)

    def test_get_token_large_expiry_warns(self):
        """get-token --hours 48 shows security warning on stderr."""
        from limacharlie.commands.auth import get_token

        runner = CliRunner(mix_stderr=False)
        with patch("limacharlie.commands.auth._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_jwt.return_value = "long-jwt"
            mock_client.oid = "test-oid"
            mock_get_client.return_value = mock_client

            result = runner.invoke(get_token, ["--hours", "48"], catch_exceptions=False)

            assert result.exit_code == 0
            # Warning goes to stderr
            assert "Warning" in result.stderr or "security" in result.stderr.lower()


@pytest.fixture
def tmp_jwt_cache(monkeypatch, tmp_path):
    """Point the JWT cache at a temp directory, so tests never read or
    write the real one."""
    from limacharlie.config import _reset_config_cache
    from limacharlie.jwt_cache import _reset_cache_disabled
    from limacharlie.paths import _reset_path_cache

    config_dir = tmp_path / "lc_config"
    config_dir.mkdir()
    monkeypatch.setenv("LC_CONFIG_DIR", str(config_dir))
    for var in ("LC_CREDS_FILE", "LC_LEGACY_CONFIG", "LC_EPHEMERAL_CREDS", "LC_NO_JWT_CACHE"):
        monkeypatch.delenv(var, raising=False)
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()
    yield
    _reset_path_cache()
    _reset_cache_disabled()
    _reset_config_cache()


class TestGetJwtCappedLifetime:
    """get_jwt when the server grants less than the requested lifetime.

    The server caps every token's lifetime. A request above the cap can
    never be covered by any token, so the cache must not mint a new token
    on every command: it records the granted lifetime and reuses a token
    that still has at least 90% of it. Each test builds a new Client per
    step, the way separate CLI invocations do, with only ``urlopen``
    mocked and the cache in a temp directory.
    """

    CAP = 48 * 3600
    CREDS = {"oid": "test-oid", "uid": None, "api_key": "test-api-key-12345678", "oauth": None}

    @staticmethod
    def _serve(mock_urlopen, lifetime):
        """Make the mocked endpoint mint tokens of ``lifetime`` seconds."""
        def respond(request, *a, **k):
            now = int(time.time())
            response = MagicMock()
            response.read.return_value = json.dumps(
                {"jwt": _make_jwt(now + lifetime, iat=now)}
            ).encode()
            return response
        mock_urlopen.side_effect = respond

    def _cache_entry(self):
        from limacharlie.jwt_cache import _compute_cache_key, _load_cache
        return _load_cache()[_compute_cache_key("test-oid", self.CREDS["api_key"], None, None)]

    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_capped_grant_is_recorded_and_reused_by_the_next_command(self, mock_urlopen, mock_resolve, tmp_jwt_cache):
        mock_resolve.return_value = dict(self.CREDS)
        self._serve(mock_urlopen, self.CAP)

        first = Client(oid="test-oid").get_jwt(expiry_hours=72)
        assert mock_urlopen.call_count == 1
        assert self._cache_entry()["max_lifetime"] == self.CAP

        # The next command asks for 72h again. No token can cover it, and the
        # cached one has (almost) the whole cap left, so it is reused.
        second = Client(oid="test-oid").get_jwt(expiry_hours=72)
        assert second == first
        assert mock_urlopen.call_count == 1

    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_capped_token_below_90_percent_of_the_cap_is_replaced(self, mock_urlopen, mock_resolve, tmp_jwt_cache):
        from limacharlie.jwt_cache import put_cached_jwt, set_cached_max_lifetime

        mock_resolve.return_value = dict(self.CREDS)
        now = int(time.time())
        # 40h left of a 48h cap: under the 43.2h reuse threshold.
        stale = _make_jwt(now + 40 * 3600, iat=now - 8 * 3600)
        put_cached_jwt(stale, "test-oid", self.CREDS["api_key"], None, None)
        set_cached_max_lifetime(self.CAP, "test-oid", self.CREDS["api_key"], None, None)
        self._serve(mock_urlopen, self.CAP)

        fresh = Client(oid="test-oid").get_jwt(expiry_hours=72)

        assert fresh != stale
        assert mock_urlopen.call_count == 1

    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_request_within_the_cap_still_needs_the_full_request(self, mock_urlopen, mock_resolve, tmp_jwt_cache):
        """The 90% rule only applies to requests the cap cannot cover."""
        from limacharlie.jwt_cache import put_cached_jwt, set_cached_max_lifetime

        mock_resolve.return_value = dict(self.CREDS)
        now = int(time.time())
        cached = _make_jwt(now + 3 * 3600, iat=now - 45 * 3600)
        put_cached_jwt(cached, "test-oid", self.CREDS["api_key"], None, None)
        set_cached_max_lifetime(self.CAP, "test-oid", self.CREDS["api_key"], None, None)
        self._serve(mock_urlopen, 4 * 3600)

        Client(oid="test-oid").get_jwt(expiry_hours=4)

        assert mock_urlopen.call_count == 1

    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_full_grant_clears_a_recorded_cap(self, mock_urlopen, mock_resolve, tmp_jwt_cache):
        """When the server grants the full request again (the cap was raised
        or removed), the old cap stops lowering the reuse threshold.

        A raised cap is only seen at the next mint, which happens once the
        cached token drops below 90% of the old cap.
        """
        from limacharlie.jwt_cache import put_cached_jwt, set_cached_max_lifetime

        mock_resolve.return_value = dict(self.CREDS)
        now = int(time.time())
        put_cached_jwt(_make_jwt(now + 40 * 3600, iat=now - 8 * 3600), "test-oid", self.CREDS["api_key"], None, None)
        set_cached_max_lifetime(self.CAP, "test-oid", self.CREDS["api_key"], None, None)
        self._serve(mock_urlopen, 72 * 3600)

        Client(oid="test-oid").get_jwt(expiry_hours=72)

        assert mock_urlopen.call_count == 1
        assert "max_lifetime" not in self._cache_entry()

    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_full_grant_records_nothing(self, mock_urlopen, mock_resolve, tmp_jwt_cache):
        mock_resolve.return_value = dict(self.CREDS)
        self._serve(mock_urlopen, 4 * 3600)

        Client(oid="test-oid").get_jwt(expiry_hours=4)

        assert "max_lifetime" not in self._cache_entry()

    @patch("limacharlie.client.resolve_credentials")
    @patch("limacharlie.client.urlopen")
    def test_default_token_refresh_keeps_the_recorded_cap(self, mock_urlopen, mock_resolve, tmp_jwt_cache):
        """A default (1h) refresh rewrites the cached token; the recorded
        cap is a property of the server and must survive it."""
        mock_resolve.return_value = dict(self.CREDS)
        self._serve(mock_urlopen, self.CAP)
        Client(oid="test-oid").get_jwt(expiry_hours=72)

        self._serve(mock_urlopen, 3600)
        client = Client(oid="test-oid")
        client._jwt = None
        client.refresh_jwt()

        assert self._cache_entry()["max_lifetime"] == self.CAP
