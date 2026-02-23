"""Transport-level HTTP compression support.

Handles Accept-Encoding negotiation and Content-Encoding decompression
for HTTP responses. Supports zstd, gzip, and deflate.

zstd is preferred because it offers better compression ratios and faster
decompression than gzip. The zstandard package is a hard dependency but
the runtime gracefully falls back to gzip/deflate if it's unavailable
(e.g., exotic platform where the wheel couldn't be installed).
"""

from __future__ import annotations

import zlib

# zstandard is a hard dependency (listed in pyproject.toml) with pre-built
# wheels for all major platforms. However, we guard the import so the SDK
# still works if someone is on an exotic platform where the wheel isn't
# available and there's no C compiler to build from source.
try:
    import zstandard as _zstd

    _HAS_ZSTD = True
except ImportError:
    _zstd = None  # type: ignore[assignment]
    _HAS_ZSTD = False

# Header value sent on every request. Prefer zstd when available.
ACCEPT_ENCODING: str = "zstd, gzip, deflate" if _HAS_ZSTD else "gzip, deflate"


def decompress_response(data: bytes, content_encoding: str | None) -> bytes:
    """Decompress an HTTP response body based on Content-Encoding.

    If the encoding is unrecognized or absent, the data is returned as-is
    (passthrough). This matches standard HTTP client behavior - servers may
    return uncompressed responses even when Accept-Encoding was sent.

    Parameters:
        data: Raw response body bytes.
        content_encoding: Value of the Content-Encoding response header,
            or None if the header was absent.

    Returns:
        Decompressed bytes, or the original bytes if no decompression needed.
    """
    if not content_encoding:
        return data

    encoding = content_encoding.strip().lower()

    if encoding == "zstd":
        if not _HAS_ZSTD:
            # Server sent zstd but we can't decompress - return as-is.
            # JSON parsing will fail with a clear error downstream.
            return data
        return _zstd.ZstdDecompressor().decompress(data)

    if encoding in ("gzip", "x-gzip"):
        # 16 + MAX_WBITS tells zlib to auto-detect gzip vs raw deflate
        return zlib.decompress(data, 16 + zlib.MAX_WBITS)

    if encoding == "deflate":
        # Try raw deflate first, fall back to zlib-wrapped deflate
        try:
            return zlib.decompress(data, -zlib.MAX_WBITS)
        except zlib.error:
            return zlib.decompress(data)

    # Unknown encoding - return data as-is rather than crashing.
    # The caller will attempt JSON parsing which will fail with a clear
    # error if the data is actually compressed.
    return data
