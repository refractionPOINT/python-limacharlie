import sys
import platform
import ssl
from unittest import mock

import pytest

from limacharlie.Manager import _build_user_agent
from limacharlie.WebhookSender import _build_webhook_user_agent
from limacharlie.user_agent_utils import (
    _get_python_version,
    _get_os_info,
    _get_ssl_version,
    build_user_agent
)


class TestBuildUserAgent:
    """Tests for the _build_user_agent function in Manager.py."""

    def test_user_agent_format(self):
        """
        Test that User-Agent has the correct format with semicolon separators.

        Example User-Agent:
        lc-py-api/4.10.3;python-3.11.2;debian-12;openssl-3.0.0
        """
        result = _build_user_agent()
        assert isinstance(result, str)
        assert ';' in result
        parts = result.split(';')
        # Should have at least 3 parts: library version, python version, OS
        # May have 4 if SSL info is available
        assert len(parts) >= 3

    def test_user_agent_contains_library_version(self):
        """
        Test that User-Agent contains the library version.

        Example component: lc-py-api/4.10.3
        """
        result = _build_user_agent()
        assert 'lc-py-api/' in result
        parts = result.split(';')
        # First part should be the library version
        assert parts[0].startswith('lc-py-api/')

    def test_user_agent_contains_python_version(self):
        """
        Test that User-Agent contains Python version.

        Example component: python-3.11.2
        """
        result = _build_user_agent()
        assert 'python-' in result

        # Verify format matches current Python version
        expected_version = '%d.%d.%d' % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro
        )
        assert 'python-%s' % expected_version in result

    def test_user_agent_contains_os_info(self):
        """
        Test that User-Agent contains OS information.

        Example components:
        - Linux: debian-12, ubuntu-22.04, linux
        - macOS: macos-14.0, darwin
        - Windows: windows-10, windows
        """
        result = _build_user_agent()
        parts = result.split(';')

        # OS info should be the third component
        os_part = parts[2] if len(parts) > 2 else None
        assert os_part is not None

        # Check that it contains some OS identifier
        os_indicators = ['linux', 'debian', 'ubuntu', 'centos', 'rhel',
                        'macos', 'darwin', 'windows']
        assert any(indicator in os_part.lower() for indicator in os_indicators)

    def test_user_agent_contains_ssl_version_if_available(self):
        """
        Test that User-Agent contains SSL version when available.

        Example component: openssl-3.0.0
        """
        result = _build_user_agent()

        # SSL version should be included if available
        if hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            assert 'openssl-' in result
            parts = result.split(';')
            # Should be the 4th component
            ssl_part = next((p for p in parts if p.startswith('openssl-')), None)
            assert ssl_part is not None
            # Verify format: openssl-X.Y.Z
            assert ssl_part.count('.') == 2

    def test_user_agent_consistent_format(self):
        """
        Test that User-Agent format is consistent across multiple calls.

        Ensures the function produces deterministic output.
        """
        result1 = _build_user_agent()
        result2 = _build_user_agent()
        assert result1 == result2


class TestBuildWebhookUserAgent:
    """Tests for the _build_webhook_user_agent function in WebhookSender.py."""

    def test_webhook_user_agent_format(self):
        """
        Test that webhook User-Agent has the correct format.

        Example User-Agent:
        lc-sdk-webhook/4.10.3;python-3.11.2;debian-12;openssl-3.0.0
        """
        result = _build_webhook_user_agent()
        assert isinstance(result, str)
        assert ';' in result
        parts = result.split(';')
        # Should have at least 3 parts: library version, python version, OS
        # May have 4 if SSL info is available
        assert len(parts) >= 3

    def test_webhook_user_agent_contains_library_version(self):
        """
        Test that webhook User-Agent contains the library version.

        Example component: lc-sdk-webhook/4.10.3
        """
        result = _build_webhook_user_agent()
        assert 'lc-sdk-webhook/' in result
        parts = result.split(';')
        # First part should be the library version
        assert parts[0].startswith('lc-sdk-webhook/')

    def test_webhook_user_agent_contains_python_version(self):
        """
        Test that webhook User-Agent contains Python version.

        Example component: python-3.11.2
        """
        result = _build_webhook_user_agent()
        assert 'python-' in result

        # Verify format matches current Python version
        expected_version = '%d.%d.%d' % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro
        )
        assert 'python-%s' % expected_version in result

    def test_webhook_user_agent_contains_os_info(self):
        """
        Test that webhook User-Agent contains OS information.

        Example components:
        - Linux: debian-12, ubuntu-22.04, linux
        - macOS: macos-14.0, darwin
        - Windows: windows-10, windows
        """
        result = _build_webhook_user_agent()
        parts = result.split(';')

        # OS info should be the third component
        os_part = parts[2] if len(parts) > 2 else None
        assert os_part is not None

        # Check that it contains some OS identifier
        os_indicators = ['linux', 'debian', 'ubuntu', 'centos', 'rhel',
                        'macos', 'darwin', 'windows']
        assert any(indicator in os_part.lower() for indicator in os_indicators)

    def test_webhook_user_agent_contains_ssl_version_if_available(self):
        """
        Test that webhook User-Agent contains SSL version when available.

        Example component: openssl-3.0.0
        """
        result = _build_webhook_user_agent()

        # SSL version should be included if available
        if hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            assert 'openssl-' in result
            parts = result.split(';')
            # Should be the 4th component
            ssl_part = next((p for p in parts if p.startswith('openssl-')), None)
            assert ssl_part is not None
            # Verify format: openssl-X.Y.Z
            assert ssl_part.count('.') == 2


class TestUserAgentComparison:
    """Tests comparing API and webhook User-Agent functions."""

    def test_api_and_webhook_differ_only_in_prefix(self):
        """
        Test that API and webhook User-Agents differ only in the library prefix.

        API starts with: lc-py-api/VERSION
        Webhook starts with: lc-sdk-webhook/VERSION

        The rest of the components (Python version, OS, SSL) should be identical.
        """
        api_ua = _build_user_agent()
        webhook_ua = _build_webhook_user_agent()

        api_parts = api_ua.split(';')
        webhook_parts = webhook_ua.split(';')

        # Should have same number of parts
        assert len(api_parts) == len(webhook_parts)

        # First part should differ (library prefix)
        assert api_parts[0].startswith('lc-py-api/')
        assert webhook_parts[0].startswith('lc-sdk-webhook/')

        # All other parts should be identical (Python version, OS, SSL)
        for i in range(1, len(api_parts)):
            assert api_parts[i] == webhook_parts[i], \
                f"Component {i} differs: API='{api_parts[i]}' vs Webhook='{webhook_parts[i]}'"


class TestUserAgentOSDetection:
    """Tests for OS detection logic in User-Agent functions."""

    def test_linux_with_freedesktop_os_release(self):
        """
        Test User-Agent generation on Linux with freedesktop_os_release.

        Example result: debian-12, ubuntu-22.04
        """
        if not hasattr(platform, 'freedesktop_os_release'):
            pytest.skip("freedesktop_os_release not available on this platform")

        result = _build_user_agent()

        # On Linux systems with freedesktop_os_release, should get distribution info
        if platform.system().lower() == 'linux':
            parts = result.split(';')
            os_part = parts[2]
            # Should contain a hyphen separating OS name and version
            # Examples: debian-12, ubuntu-22.04
            assert '-' in os_part or os_part == 'linux'

    def test_macos_detection(self):
        """
        Test User-Agent generation on macOS.

        Example result: macos-14.0
        """
        if platform.system().lower() != 'darwin':
            pytest.skip("Test only runs on macOS")

        result = _build_user_agent()
        parts = result.split(';')
        os_part = parts[2]

        # Should contain either 'macos' or 'darwin'
        assert 'macos' in os_part.lower() or 'darwin' in os_part.lower()

    def test_windows_detection(self):
        """
        Test User-Agent generation on Windows.

        Example result: windows-10, windows-11
        """
        if platform.system().lower() != 'windows':
            pytest.skip("Test only runs on Windows")

        result = _build_user_agent()
        parts = result.split(';')
        os_part = parts[2]

        # Should contain 'windows'
        assert 'windows' in os_part.lower()

    def test_os_detection_fallback(self):
        """
        Test that OS detection falls back gracefully on errors.

        Should return basic platform.system() value on error.
        """
        with mock.patch('platform.freedesktop_os_release', side_effect=Exception("Mock error")):
            with mock.patch('platform.system', return_value='Linux'):
                result = _build_user_agent()
                parts = result.split(';')
                os_part = parts[2]
                # Should fall back to 'linux'
                assert os_part.lower() == 'linux'


class TestUserAgentSSLVersion:
    """Tests for SSL version detection in User-Agent functions."""

    def test_ssl_version_format(self):
        """
        Test that SSL version has the correct format when available.

        Example: openssl-3.0.0
        """
        if not hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            pytest.skip("OPENSSL_VERSION_INFO not available")

        result = _build_user_agent()

        ssl_parts = [p for p in result.split(';') if p.startswith('openssl-')]
        assert len(ssl_parts) == 1

        ssl_part = ssl_parts[0]
        # Format should be openssl-X.Y.Z
        version_str = ssl_part.replace('openssl-', '')
        version_components = version_str.split('.')
        assert len(version_components) == 3
        # Each component should be a number
        for component in version_components:
            assert component.isdigit()

    def test_ssl_version_matches_system(self):
        """
        Test that SSL version in User-Agent matches system SSL info.

        Verifies the extracted version matches ssl.OPENSSL_VERSION_INFO.
        """
        if not hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            pytest.skip("OPENSSL_VERSION_INFO not available")

        result = _build_user_agent()
        ssl_info = ssl.OPENSSL_VERSION_INFO

        expected_ssl = 'openssl-%d.%d.%d' % (ssl_info[0], ssl_info[1], ssl_info[2])
        assert expected_ssl in result


class TestUserAgentUtilityFunctions:
    """Tests for individual utility functions in user_agent_utils.py."""

    def test_get_python_version_format(self):
        """
        Test that _get_python_version returns correctly formatted version.

        Format should be: python-X.Y.Z
        """
        result = _get_python_version()
        assert result.startswith('python-')
        version_part = result.replace('python-', '')
        assert version_part.count('.') == 2

    def test_get_python_version_matches_sys_version(self):
        """
        Test that _get_python_version matches current Python version.

        Verifies the version matches sys.version_info.
        """
        result = _get_python_version()
        expected = 'python-%d.%d.%d' % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro
        )
        assert result == expected

    def test_get_os_info_returns_string(self):
        """
        Test that _get_os_info returns a non-empty string.

        Should return some OS identifier.
        """
        result = _get_os_info()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_ssl_version_format(self):
        """
        Test that _get_ssl_version returns correct format when available.

        Format should be: openssl-X.Y.Z or None
        """
        result = _get_ssl_version()
        if result is not None:
            assert result.startswith('openssl-')
            version_part = result.replace('openssl-', '')
            assert version_part.count('.') == 2

    def test_build_user_agent_custom_prefix(self):
        """
        Test that build_user_agent accepts custom prefix and version.

        Verifies the function can build User-Agent with any prefix.
        """
        result = build_user_agent('custom-lib', '1.2.3')
        assert result.startswith('custom-lib/1.2.3;')
        # Should still contain python version and OS
        assert 'python-' in result

    def test_build_user_agent_component_order(self):
        """
        Test that build_user_agent returns components in correct order.

        Order should be: library, python, os, ssl (optional)
        """
        result = build_user_agent('test-lib', '0.0.1')
        parts = result.split(';')

        # First part should be library version
        assert parts[0] == 'test-lib/0.0.1'

        # Second part should be Python version
        assert parts[1].startswith('python-')

        # Third part should be OS (any string)
        assert len(parts[2]) > 0

        # Fourth part (if exists) should be SSL
        if len(parts) > 3:
            assert parts[3].startswith('openssl-')
