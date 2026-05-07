"""Tests for Client.get_jwt, token expiry resolution, and CLI commands.

Tests custom token expiry generation for long-running operations
like search queries. Covers SDK method, resolution logic (CLI flag >
config file > constant default), and CLI commands.
"""

import json
import time
from unittest.mock import MagicMock, patch

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
        """get_jwt(expiry_hours=8) computes correct unix timestamp."""
        mock_resolve.return_value = {
            "oid": "test-oid", "uid": None,
            "api_key": "test-api-key-12345678", "oauth": None,
        }
        client = Client(oid="test-oid")
        client.refresh_jwt = MagicMock()
        client._jwt = "mock-jwt-8h"

        before = int(time.time())
        token = client.get_jwt(expiry_hours=8)
        after = int(time.time())

        client.refresh_jwt.assert_called_once()
        call_kwargs = client.refresh_jwt.call_args
        expiry_ts = call_kwargs[1]["expiry"] if "expiry" in (call_kwargs[1] or {}) else call_kwargs[0][0]
        # Expiry should be ~8 hours from now
        expected_min = before + 8 * 3600
        expected_max = after + 8 * 3600
        assert expected_min <= expiry_ts <= expected_max
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

        before = int(time.time())
        client.get_jwt(expiry_hours=0.5)
        after = int(time.time())

        call_kwargs = client.refresh_jwt.call_args
        expiry_ts = call_kwargs[1]["expiry"] if "expiry" in (call_kwargs[1] or {}) else call_kwargs[0][0]
        expected_min = before + 1800
        expected_max = after + 1800
        assert expected_min <= expiry_ts <= expected_max

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
