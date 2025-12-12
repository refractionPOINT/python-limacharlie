"""
User-Agent utility functions for building comprehensive User-Agent strings.

Inspired by the Scalyr Agent implementation (Apache 2.0 licensed):
https://github.com/scalyr/scalyr-agent-2/blob/97c7405d4a8a7c2d376826779831e6be2753e2ce/scalyr_agent/scalyr_client.py#L881
"""

import sys
import platform
import ssl


def _get_python_version():
    """
    Get the Python version string.

    Returns:
        str: Python version in format "python-X.Y.Z"

    Example:
        "python-3.11.2"
    """
    python_version = '%d.%d.%d' % (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro
    )
    return 'python-%s' % python_version


def _get_os_info():
    """
    Get the operating system information string.

    Attempts to get detailed OS distribution information on Linux,
    macOS version, or Windows version. Falls back to basic platform
    detection if detailed information is unavailable.

    Returns:
        str: Operating system identifier

    Examples:
        - Linux: "debian-12", "ubuntu-22.04"
        - macOS: "macos-14.0"
        - Windows: "windows-10"
    """
    try:
        # For Python 3.8+, use platform.freedesktop_os_release() for Linux
        if hasattr(platform, 'freedesktop_os_release'):
            os_info = platform.freedesktop_os_release()
            return '%s-%s' % (os_info.get('ID', 'linux'), os_info.get('VERSION_ID', 'unknown'))
        else:
            # Fallback for older Python or non-Linux systems
            os_str = platform.system().lower()
            if os_str == 'darwin':
                # macOS version
                mac_ver = platform.mac_ver()[0]
                if mac_ver:
                    return 'macos-%s' % mac_ver
            elif os_str == 'linux':
                # Try to get distribution info (deprecated in Python 3.8+)
                if hasattr(platform, 'linux_distribution') and platform.linux_distribution()[0]:
                    dist = platform.linux_distribution()
                    return '%s-%s' % (dist[0].lower().replace(' ', '-'), dist[1])
            elif os_str == 'windows':
                # Windows version
                win_ver = platform.win32_ver()[0]
                if win_ver:
                    return 'windows-%s' % win_ver
            return os_str
    except Exception:
        # Fallback to basic platform info if detailed info fails
        return platform.system().lower()


def _get_ssl_version():
    """
    Get the SSL/TLS version string if available.

    Returns:
        str or None: SSL version in format "openssl-X.Y.Z" or None if unavailable

    Example:
        "openssl-3.0.0"
    """
    try:
        if hasattr(ssl, 'OPENSSL_VERSION_INFO'):
            ssl_info = ssl.OPENSSL_VERSION_INFO
            # Format as major.minor.patch
            ssl_version = '%d.%d.%d' % (ssl_info[0], ssl_info[1], ssl_info[2])
            return 'openssl-%s' % ssl_version
    except Exception:
        # SSL version info not available
        pass
    return None


def build_user_agent(library_prefix, library_version):
    """
    Build a comprehensive User-Agent string with environment information.

    Parameters:
        library_prefix (str): The library identifier prefix (e.g., "lc-py-api", "lc-sdk-webhook")
        library_version (str): The library version string

    Returns:
        str: Formatted User-Agent string with semicolon-separated components

    Example User-Agent strings:
        - Linux: "lc-py-api/4.10.3;python-3.11.2;debian-12;openssl-3.0.0"
        - macOS: "lc-py-api/4.10.3;python-3.11.2;macos-14.0;openssl-3.0.0"
        - Windows: "lc-py-api/4.10.3;python-3.11.2;windows-10;openssl-3.0.0"
    """
    parts = []

    # Library version
    parts.append('%s/%s' % (library_prefix, library_version))

    # Python version
    parts.append(_get_python_version())

    # Operating system info
    parts.append(_get_os_info())

    # SSL/TLS version (optional)
    ssl_version = _get_ssl_version()
    if ssl_version:
        parts.append(ssl_version)

    return ';'.join(parts)
