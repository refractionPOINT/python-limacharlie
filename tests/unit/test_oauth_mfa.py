"""
Unit tests for OAuth MFA support.
"""

import pytest
from limacharlie.oauth_mfa import MFAHandler, FirebaseMFAError


class TestMFAHandler:
    """Test MFA handler functionality."""

    def test_display_mfa_factors_with_totp(self, capsys):
        """Test displaying TOTP factor."""
        mfa_info = [{
            'mfaEnrollmentId': 'test-enrollment-id',
            'displayName': 'My Authenticator',
            'totpInfo': {}
        }]

        factor = MFAHandler.display_mfa_factors(mfa_info)

        captured = capsys.readouterr()
        assert "Multi-Factor Authentication Required" in captured.out
        assert "My Authenticator" in captured.out
        assert "Authenticator app (TOTP)" in captured.out
        assert factor['mfaEnrollmentId'] == 'test-enrollment-id'

    def test_display_mfa_factors_with_sms(self, capsys):
        """Test displaying SMS factor."""
        mfa_info = [{
            'mfaEnrollmentId': 'test-sms-id',
            'displayName': 'My Phone',
            'phoneInfo': '+1234567890'
        }]

        factor = MFAHandler.display_mfa_factors(mfa_info)

        captured = capsys.readouterr()
        assert "Multi-Factor Authentication Required" in captured.out
        assert "My Phone" in captured.out
        assert "SMS to +1234567890" in captured.out
        assert factor['mfaEnrollmentId'] == 'test-sms-id'

    def test_display_mfa_factors_empty_list(self):
        """Test that empty factor list raises error."""
        with pytest.raises(FirebaseMFAError) as exc_info:
            MFAHandler.display_mfa_factors([])

        assert "No MFA factors found" in str(exc_info.value)

    def test_prompt_verification_code_valid_input(self, monkeypatch):
        """Test valid verification code input."""
        monkeypatch.setattr('builtins.input', lambda _: '123456')

        factor = {
            'mfaEnrollmentId': 'test-id',
            'displayName': 'My Auth',
            'totpInfo': {}
        }

        code = MFAHandler.prompt_verification_code(factor)
        assert code == '123456'

    def test_prompt_verification_code_invalid_then_valid(self, monkeypatch):
        """Test invalid code followed by valid code."""
        inputs = iter(['', 'abc', '123456'])  # Only 3 inputs: 2 invalid + 1 valid
        monkeypatch.setattr('builtins.input', lambda _: next(inputs))

        factor = {
            'mfaEnrollmentId': 'test-id',
            'displayName': 'My Auth',
            'totpInfo': {}
        }

        code = MFAHandler.prompt_verification_code(factor, max_attempts=3)
        assert code == '123456'

    def test_prompt_verification_code_max_attempts_exceeded(self, monkeypatch):
        """Test that max attempts raises error."""
        monkeypatch.setattr('builtins.input', lambda _: 'invalid')

        factor = {
            'mfaEnrollmentId': 'test-id',
            'displayName': 'My Auth',
            'totpInfo': {}
        }

        with pytest.raises(FirebaseMFAError) as exc_info:
            MFAHandler.prompt_verification_code(factor, max_attempts=3)

        assert "Maximum attempts" in str(exc_info.value)

    def test_prompt_verification_code_keyboard_interrupt(self, monkeypatch):
        """Test that keyboard interrupt is handled."""
        def raise_interrupt(_):
            raise KeyboardInterrupt()

        monkeypatch.setattr('builtins.input', raise_interrupt)

        factor = {
            'mfaEnrollmentId': 'test-id',
            'displayName': 'My Auth',
            'totpInfo': {}
        }

        with pytest.raises(FirebaseMFAError) as exc_info:
            MFAHandler.prompt_verification_code(factor)

        assert "cancelled by user" in str(exc_info.value)
