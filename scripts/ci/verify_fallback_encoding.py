"""Verify Accept-Encoding falls back to gzip/deflate when zstd is unavailable."""

from limacharlie.transport_compression import ACCEPT_ENCODING, _HAS_ZSTD

assert not _HAS_ZSTD, "_HAS_ZSTD should be False"
assert "zstd" not in ACCEPT_ENCODING, f"zstd should not be in: {ACCEPT_ENCODING}"
assert "gzip" in ACCEPT_ENCODING, f"gzip missing from: {ACCEPT_ENCODING}"
print(f"Accept-Encoding (fallback): {ACCEPT_ENCODING}")
