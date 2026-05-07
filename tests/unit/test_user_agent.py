import sys
import platform
import ssl
from unittest import mock

import pytest

from limacharlie.user_agent_utils import (
    _get_python_version,
    _get_os_info,
    _get_ssl_version,
    build_user_agent,
)


class TestBuildUserAgent:
    """Tests for the build_user_agent function in user_agent_utils.py."""

    def test_user_agent_format(self):
        result = build_user_agent("lc-py-api", "5.0.0")
        assert isinstance(result, str)
        assert ';' in result
        parts = result.split(';')
        assert len(parts) >= 3

    def test_user_agent_contains_library_version(self):
        result = build_user_agent("lc-py-api", "5.0.0")
        assert 'lc-py-api/' in result
        parts = result.split(';')
        assert parts[0].startswith('lc-py-api/')

    def test_user_agent_contains_python_version(self):
        result = build_user_agent("lc-py-api", "5.0.0")
        assert 'python-' in result
        expected_version = '%d.%d.%d' % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro
        )
        assert 'python-%s' % expected_version in result

    def test_user_agent_contains_os_info(self):
        result = build_user_agent("lc-py-api", "5.0.0")
        parts = result.split(';')
        os_part = parts[2] if len(parts) > 2 else None
        assert os_part is not None
        os_indicators = ['linux', 'debian', 'ubuntu', 'centos', 'rhel',
                        'macos', 'darwin', 'windows']
        assert any(indicator in os_part.lower() for indicator in os_indicators)

    def test_user_agent_contains_ssl_version_if_available(self):
        result = build_user_agent("lc-py-api", "5.0.0")
        if hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            assert 'openssl-' in result
            parts = result.split(';')
            ssl_part = next((p for p in parts if p.startswith('openssl-')), None)
            assert ssl_part is not None
            assert ssl_part.count('.') == 2

    def test_user_agent_consistent_format(self):
        result1 = build_user_agent("lc-py-api", "5.0.0")
        result2 = build_user_agent("lc-py-api", "5.0.0")
        assert result1 == result2


class TestUserAgentOSDetection:
    """Tests for OS detection logic in User-Agent functions."""

    def test_linux_with_freedesktop_os_release(self):
        if not hasattr(platform, 'freedesktop_os_release'):
            pytest.skip("freedesktop_os_release not available on this platform")

        result = build_user_agent("lc-py-api", "5.0.0")
        if platform.system().lower() == 'linux':
            parts = result.split(';')
            os_part = parts[2]
            assert '-' in os_part or os_part == 'linux'

    def test_macos_detection(self):
        if platform.system().lower() != 'darwin':
            pytest.skip("Test only runs on macOS")

        result = build_user_agent("lc-py-api", "5.0.0")
        parts = result.split(';')
        os_part = parts[2]
        assert 'macos' in os_part.lower() or 'darwin' in os_part.lower()

    def test_windows_detection(self):
        if platform.system().lower() != 'windows':
            pytest.skip("Test only runs on Windows")

        result = build_user_agent("lc-py-api", "5.0.0")
        parts = result.split(';')
        os_part = parts[2]
        assert 'windows' in os_part.lower()

    def test_os_detection_fallback(self):
        with mock.patch('platform.freedesktop_os_release', side_effect=Exception("Mock error"), create=True):
            with mock.patch('platform.system', return_value='Linux'):
                result = build_user_agent("lc-py-api", "5.0.0")
                parts = result.split(';')
                os_part = parts[2]
                assert os_part.lower() == 'linux'


class TestUserAgentSSLVersion:
    """Tests for SSL version detection in User-Agent functions."""

    def test_ssl_version_format(self):
        if not hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            pytest.skip("OPENSSL_VERSION_INFO not available")

        result = build_user_agent("lc-py-api", "5.0.0")
        ssl_parts = [p for p in result.split(';') if p.startswith('openssl-')]
        assert len(ssl_parts) == 1

        ssl_part = ssl_parts[0]
        version_str = ssl_part.replace('openssl-', '')
        version_components = version_str.split('.')
        assert len(version_components) == 3
        for component in version_components:
            assert component.isdigit()

    def test_ssl_version_matches_system(self):
        if not hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            pytest.skip("OPENSSL_VERSION_INFO not available")

        result = build_user_agent("lc-py-api", "5.0.0")
        ssl_info = ssl.OPENSSL_VERSION_INFO
        expected_ssl = 'openssl-%d.%d.%d' % (ssl_info[0], ssl_info[1], ssl_info[2])
        assert expected_ssl in result


class TestUserAgentUtilityFunctions:
    """Tests for individual utility functions in user_agent_utils.py."""

    def test_get_python_version_format(self):
        result = _get_python_version()
        assert result.startswith('python-')
        version_part = result.replace('python-', '')
        assert version_part.count('.') == 2

    def test_get_python_version_matches_sys_version(self):
        result = _get_python_version()
        expected = 'python-%d.%d.%d' % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro
        )
        assert result == expected

    def test_get_os_info_returns_string(self):
        result = _get_os_info()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_ssl_version_format(self):
        result = _get_ssl_version()
        if result is not None:
            assert result.startswith('openssl-')
            version_part = result.replace('openssl-', '')
            assert version_part.count('.') == 2

    def test_build_user_agent_custom_prefix(self):
        result = build_user_agent('custom-lib', '1.2.3')
        assert result.startswith('custom-lib/1.2.3;')
        assert 'python-' in result

    def test_build_user_agent_component_order(self):
        result = build_user_agent('test-lib', '0.0.1')
        parts = result.split(';')
        assert parts[0] == 'test-lib/0.0.1'
        assert parts[1].startswith('python-')
        assert len(parts[2]) > 0
        if len(parts) > 3:
            assert parts[3].startswith('openssl-')
