"""Verify transport compression module loads with zstd support."""

from limacharlie.transport_compression import ACCEPT_ENCODING

assert "zstd" in ACCEPT_ENCODING, f"zstd missing from: {ACCEPT_ENCODING}"
print(f"Accept-Encoding: {ACCEPT_ENCODING}")
