"""Downloads SDK for LimaCharlie v2.

Handles downloading sensor (EDR) installers and adapter binaries
from downloads.limacharlie.io.
"""

from __future__ import annotations

import ssl
from urllib.request import Request as URLRequest
from urllib.request import urlopen
from urllib.error import HTTPError

DOWNLOADS_URL = "https://downloads.limacharlie.io"

# -----------------------------------------------------------------------
# Sensor installer matrix
# -----------------------------------------------------------------------
# Maps (platform, architecture) to the URL path segment.
SENSOR_TARGETS: dict[tuple[str, str], str] = {
    # Windows
    ("windows", "64"): "sensor/windows/64",
    ("windows", "32"): "sensor/windows/32",
    ("windows", "arm64"): "sensor/windows/arm64",
    ("windows", "msi64"): "sensor/windows/msi64",
    ("windows", "msi32"): "sensor/windows/msi32",
    # Linux
    ("linux", "64"): "sensor/linux/64",
    ("linux", "deb64"): "sensor/linux/deb64",
    ("linux", "debarm64"): "sensor/linux/debarm64",
    ("linux", "alpine64"): "sensor/linux/alpine64",
    # macOS
    ("mac", "64"): "sensor/mac/64",
    ("mac", "arm64"): "sensor/mac/arm64",
    # Chrome
    ("chrome", ""): "sensor/chrome",
}

# -----------------------------------------------------------------------
# Adapter binary matrix
# -----------------------------------------------------------------------
ADAPTER_TARGETS: dict[tuple[str, str], str] = {
    # Linux
    ("linux", "64"): "adapter/linux/64",
    ("linux", "arm"): "adapter/linux/arm",
    ("linux", "arm64"): "adapter/linux/arm64",
    # Windows
    ("windows", "64"): "adapter/windows/64",
    # macOS
    ("mac", "64"): "adapter/mac/64",
    ("mac", "arm64"): "adapter/mac/arm64",
    # Other UNIX
    ("aix", "ppc64"): "adapter/aix/ppc64",
    ("freebsd", "64"): "adapter/freebsd/64",
    ("openbsd", "64"): "adapter/openbsd/64",
    ("netbsd", "64"): "adapter/netbsd/64",
    ("solaris", "64"): "adapter/solaris/64",
}


def _create_ssl_context() -> ssl.SSLContext | None:
    try:
        ctx = ssl.create_default_context()
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        return ctx
    except Exception:
        return None


def list_sensor_targets() -> list[dict[str, str]]:
    """Return a list of available sensor (platform, architecture) pairs.

    Returns:
        list[dict]: Each dict has 'platform', 'arch', and 'url' keys.
    """
    results = []
    for (platform, arch), path in sorted(SENSOR_TARGETS.items()):
        results.append({
            "platform": platform,
            "arch": arch,
            "url": f"{DOWNLOADS_URL}/{path}",
        })
    return results


def list_adapter_targets() -> list[dict[str, str]]:
    """Return a list of available adapter (platform, architecture) pairs.

    Returns:
        list[dict]: Each dict has 'platform', 'arch', and 'url' keys.
    """
    results = []
    for (platform, arch), path in sorted(ADAPTER_TARGETS.items()):
        results.append({
            "platform": platform,
            "arch": arch,
            "url": f"{DOWNLOADS_URL}/{path}",
        })
    return results


def download_binary(kind: str, platform: str, arch: str) -> bytes:
    """Download a sensor installer or adapter binary.

    Args:
        kind: 'sensor' or 'adapter'.
        platform: Platform name (e.g. 'windows', 'linux', 'mac').
        arch: Architecture (e.g. '64', 'arm64', 'msi64').

    Returns:
        bytes: Raw binary content.

    Raises:
        ValueError: If the (platform, arch) combination is not valid.
        RuntimeError: If the download fails.
    """
    targets = SENSOR_TARGETS if kind == "sensor" else ADAPTER_TARGETS
    path = targets.get((platform, arch))
    if path is None:
        kind_label = "sensor" if kind == "sensor" else "adapter"
        valid = sorted(targets.keys())
        raise ValueError(
            f"Unknown {kind_label} target: platform={platform!r}, arch={arch!r}. "
            f"Valid combinations: {valid}"
        )

    url = f"{DOWNLOADS_URL}/{path}"
    ssl_context = _create_ssl_context()

    request = URLRequest(url)
    request.add_header("User-Agent", "lc-cli/5.0.0")
    request.get_method = lambda: "GET"

    try:
        if ssl_context is not None:
            resp = urlopen(request, context=ssl_context, timeout=300)
        else:
            resp = urlopen(request, timeout=300)
        try:
            return resp.read()
        finally:
            resp.close()
    except HTTPError as e:
        raise RuntimeError(
            f"Download failed: HTTP {e.code} from {url}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Download failed: {e}") from e
