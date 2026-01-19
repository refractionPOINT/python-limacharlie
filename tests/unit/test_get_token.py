"""Tests for the get-token CLI command and getJWT Manager method.

These tests verify that:
1. The Manager.getJWT() method correctly generates tokens with custom expiry
2. The CLI get-token command correctly parses arguments and outputs tokens
3. Error handling works correctly for invalid inputs
"""

import json
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from limacharlie import Manager
from limacharlie.__main__ import cli
from limacharlie.utils import LcApiException


class TestManagerGetJWT:
    """Tests for the Manager.getJWT() method."""

    def test_get_jwt_default_expiry(self, monkeypatch):
        """Test getJWT with default expiry (no custom expiry specified)."""
        mock_jwt = "mock-jwt-token-12345"

        # Create a mock manager with mocked _refreshJWT
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._jwt = None
            manager._oid = "test-oid"
            manager._uid = None
            manager._secret_api_key = "test-key"
            manager._oauth_creds = None

            # Mock _refreshJWT to set the JWT
            def mock_refresh_jwt(expiry=None, oid_override=None):
                manager._jwt = mock_jwt

            manager._refreshJWT = mock_refresh_jwt

            # Call getJWT without expiry
            result = manager.getJWT()

            assert result == mock_jwt

    def test_get_jwt_custom_expiry(self, monkeypatch):
        """Test getJWT with a custom expiry timestamp."""
        mock_jwt = "mock-jwt-token-with-expiry"
        captured_expiry = None

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._jwt = None
            manager._oid = "test-oid"
            manager._uid = None
            manager._secret_api_key = "test-key"
            manager._oauth_creds = None

            def mock_refresh_jwt(expiry=None, oid_override=None):
                nonlocal captured_expiry
                captured_expiry = expiry
                manager._jwt = mock_jwt

            manager._refreshJWT = mock_refresh_jwt

            # Call getJWT with 8-hour expiry
            expiry_seconds = int(time.time()) + (8 * 3600)
            result = manager.getJWT(expiry_seconds=expiry_seconds)

            assert result == mock_jwt
            assert captured_expiry == expiry_seconds

    def test_get_jwt_expiry_in_past_raises_error(self):
        """Test that getJWT raises an error when expiry is in the past."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._jwt = None
            manager._oid = "test-oid"
            manager._uid = None
            manager._secret_api_key = "test-key"
            manager._oauth_creds = None

            # Try to get a token with expiry in the past
            past_expiry = int(time.time()) - 3600  # 1 hour ago

            with pytest.raises(LcApiException) as exc_info:
                manager.getJWT(expiry_seconds=past_expiry)

            assert "expiry must be in the future" in str(exc_info.value).lower()

    def test_get_jwt_refresh_failure_raises_error(self):
        """Test that getJWT raises an error when token refresh fails."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._jwt = None
            manager._oid = "test-oid"
            manager._uid = None
            manager._secret_api_key = "test-key"
            manager._oauth_creds = None

            def mock_refresh_jwt_fails(expiry=None, oid_override=None):
                # Simulate failure by leaving _jwt as None
                manager._jwt = None

            manager._refreshJWT = mock_refresh_jwt_fails

            with pytest.raises(LcApiException) as exc_info:
                manager.getJWT()

            assert "failed to generate jwt" in str(exc_info.value).lower()


class TestGetTokenCLI:
    """Tests for the CLI get-token command."""

    def test_get_token_raw_format(self, monkeypatch, capsys):
        """Test get-token command with raw output format."""
        mock_jwt = "cli-generated-jwt-token"

        # Mock the Manager class - it's imported as 'from . import Manager' in cli
        mock_manager = MagicMock()
        mock_manager._oid = "test-oid"
        mock_manager.getJWT.return_value = mock_jwt

        with patch('limacharlie.Manager', return_value=mock_manager):
            cli(["limacharlie", "get-token", "--hours", "2"])

        captured = capsys.readouterr()
        assert mock_jwt in captured.out
        # In raw format, only the token should be printed
        assert "expiry" not in captured.out.lower()

    def test_get_token_json_format(self, monkeypatch, capsys):
        """Test get-token command with JSON output format."""
        mock_jwt = "cli-generated-jwt-token-json"

        mock_manager = MagicMock()
        mock_manager._oid = "test-oid-123"
        mock_manager.getJWT.return_value = mock_jwt

        with patch('limacharlie.Manager', return_value=mock_manager):
            cli(["limacharlie", "get-token", "--hours", "4", "--format", "json"])

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["token"] == mock_jwt
        assert output["valid_hours"] == 4.0
        assert output["oid"] == "test-oid-123"
        assert "expiry" in output
        assert "expiry_iso" in output

    def test_get_token_custom_hours(self, monkeypatch, capsys):
        """Test get-token command with custom hours parameter."""
        mock_jwt = "token-8-hours"
        captured_expiry = None

        mock_manager = MagicMock()
        mock_manager._oid = "test-oid"

        def capture_expiry(expiry_seconds=None):
            nonlocal captured_expiry
            captured_expiry = expiry_seconds
            return mock_jwt

        mock_manager.getJWT.side_effect = capture_expiry

        with patch('limacharlie.Manager', return_value=mock_manager):
            cli(["limacharlie", "get-token", "--hours", "8"])

        # Verify that expiry was set to approximately 8 hours from now
        expected_expiry = int(time.time()) + (8 * 3600)
        # Allow 5 second tolerance for test execution time
        assert abs(captured_expiry - expected_expiry) < 5

    def test_get_token_negative_hours_error(self, monkeypatch, capsys):
        """Test get-token command with negative hours parameter."""
        with pytest.raises(SystemExit) as exc_info:
            cli(["limacharlie", "get-token", "--hours", "-1"])

        captured = capsys.readouterr()
        assert "--hours must be a positive number" in captured.err

    def test_get_token_zero_hours_error(self, monkeypatch, capsys):
        """Test get-token command with zero hours parameter."""
        with pytest.raises(SystemExit) as exc_info:
            cli(["limacharlie", "get-token", "--hours", "0"])

        captured = capsys.readouterr()
        assert "--hours must be a positive number" in captured.err

    def test_get_token_long_hours_warning(self, monkeypatch, capsys):
        """Test get-token command warns when hours > 24."""
        mock_jwt = "long-lived-token"

        mock_manager = MagicMock()
        mock_manager._oid = "test-oid"
        mock_manager.getJWT.return_value = mock_jwt

        with patch('limacharlie.Manager', return_value=mock_manager):
            cli(["limacharlie", "get-token", "--hours", "48"])

        captured = capsys.readouterr()
        assert "not recommended for security reasons" in captured.err
        # Token should still be generated
        assert mock_jwt in captured.out

    def test_get_token_fractional_hours(self, monkeypatch, capsys):
        """Test get-token command with fractional hours (e.g., 1.5)."""
        mock_jwt = "fractional-hours-token"
        captured_expiry = None

        mock_manager = MagicMock()
        mock_manager._oid = "test-oid"

        def capture_expiry(expiry_seconds=None):
            nonlocal captured_expiry
            captured_expiry = expiry_seconds
            return mock_jwt

        mock_manager.getJWT.side_effect = capture_expiry

        with patch('limacharlie.Manager', return_value=mock_manager):
            cli(["limacharlie", "get-token", "--hours", "1.5"])

        # Verify that expiry was set to approximately 1.5 hours from now
        expected_expiry = int(time.time()) + int(1.5 * 3600)
        # Allow 5 second tolerance
        assert abs(captured_expiry - expected_expiry) < 5

    def test_get_token_with_environment(self, monkeypatch, capsys):
        """Test get-token command with --environment parameter."""
        mock_jwt = "env-specific-token"

        mock_manager = MagicMock()
        mock_manager._oid = "test-oid"
        mock_manager.getJWT.return_value = mock_jwt

        # Track if Manager was called with environment parameter
        manager_call_kwargs = {}

        def mock_manager_init(**kwargs):
            manager_call_kwargs.update(kwargs)
            return mock_manager

        with patch('limacharlie.Manager', side_effect=mock_manager_init):
            cli(["limacharlie", "get-token", "--environment", "prod"])

        assert manager_call_kwargs.get("environment") == "prod"

    def test_get_token_default_hours(self, monkeypatch, capsys):
        """Test get-token command with default hours (should be 1 hour)."""
        mock_jwt = "default-hours-token"
        captured_expiry = None

        mock_manager = MagicMock()
        mock_manager._oid = "test-oid"

        def capture_expiry(expiry_seconds=None):
            nonlocal captured_expiry
            captured_expiry = expiry_seconds
            return mock_jwt

        mock_manager.getJWT.side_effect = capture_expiry

        with patch('limacharlie.Manager', return_value=mock_manager):
            cli(["limacharlie", "get-token"])

        # Default should be 1 hour
        expected_expiry = int(time.time()) + 3600
        # Allow 5 second tolerance
        assert abs(captured_expiry - expected_expiry) < 5

    def test_get_token_manager_error_handling(self, monkeypatch, capsys):
        """Test get-token command handles Manager errors gracefully."""
        mock_manager = MagicMock()
        mock_manager.getJWT.side_effect = LcApiException("Authentication failed")

        with patch('limacharlie.Manager', return_value=mock_manager):
            with pytest.raises(SystemExit) as exc_info:
                cli(["limacharlie", "get-token"])

        captured = capsys.readouterr()
        assert "Error generating token" in captured.err
        assert exc_info.value.code == 1
