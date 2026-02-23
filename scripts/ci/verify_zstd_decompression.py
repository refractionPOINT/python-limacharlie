"""Verify zstd decompression works end-to-end (compress then decompress)."""

import json

import zstandard

from limacharlie.transport_compression import decompress_response

original = json.dumps({"events": [{"type": "test"}]}).encode()
compressed = zstandard.ZstdCompressor().compress(original)
result = decompress_response(compressed, "zstd")
assert result == original, "zstd round-trip failed"
print("zstd round-trip OK")
