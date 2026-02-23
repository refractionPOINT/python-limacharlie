"""Tests for limacharlie.transport_compression module."""

import gzip
import importlib
import json
import sys
import zlib
from unittest import mock

import pytest
import zstandard

from limacharlie.transport_compression import (
    ACCEPT_ENCODING,
    _HAS_ZSTD,
    decompress_response,
)


class TestAcceptEncoding:
    def test_includes_all_algorithms(self):
        """Accept-Encoding should advertise zstd, gzip, and deflate."""
        assert "zstd" in ACCEPT_ENCODING
        assert "gzip" in ACCEPT_ENCODING
        assert "deflate" in ACCEPT_ENCODING

    def test_zstd_preferred(self):
        """zstd should be listed first (highest priority)."""
        assert ACCEPT_ENCODING.startswith("zstd")


class TestAcceptEncodingWithoutZstd:
    def test_fallback_without_zstandard(self):
        """When zstandard is not importable, fall back to gzip/deflate only."""
        import limacharlie.transport_compression as tc_mod

        # Temporarily make zstandard unimportable by removing it from
        # sys.modules and patching the import machinery.
        saved = sys.modules.pop("zstandard", None)
        try:
            with mock.patch.dict(sys.modules, {"zstandard": None}):
                importlib.reload(tc_mod)
                assert tc_mod._HAS_ZSTD is False
                assert "zstd" not in tc_mod.ACCEPT_ENCODING
                assert "gzip" in tc_mod.ACCEPT_ENCODING
                assert "deflate" in tc_mod.ACCEPT_ENCODING
        finally:
            # Restore original module state
            if saved is not None:
                sys.modules["zstandard"] = saved
            importlib.reload(tc_mod)

    def test_zstd_passthrough_when_unavailable(self):
        """If server sends zstd but lib is missing, return raw bytes."""
        import limacharlie.transport_compression as tc_mod

        saved = sys.modules.pop("zstandard", None)
        try:
            with mock.patch.dict(sys.modules, {"zstandard": None}):
                importlib.reload(tc_mod)
                raw = b"some-zstd-compressed-bytes"
                # Should passthrough without crashing
                result = tc_mod.decompress_response(raw, "zstd")
                assert result is raw
        finally:
            if saved is not None:
                sys.modules["zstandard"] = saved
            importlib.reload(tc_mod)


class TestDecompressGzip:
    def test_round_trip(self):
        """Compress with gzip, decompress with our function."""
        original = b'{"events": [{"type": "NEW_PROCESS"}]}'
        compressed = gzip.compress(original)
        result = decompress_response(compressed, "gzip")
        assert result == original

    def test_x_gzip_alias(self):
        """x-gzip is a legacy alias for gzip."""
        original = b'{"ok": true}'
        compressed = gzip.compress(original)
        result = decompress_response(compressed, "x-gzip")
        assert result == original

    def test_case_insensitive(self):
        """Content-Encoding values should be case-insensitive."""
        original = b'{"data": "test"}'
        compressed = gzip.compress(original)
        result = decompress_response(compressed, "GZIP")
        assert result == original


class TestDecompressDeflate:
    def test_raw_deflate_round_trip(self):
        """Compress with raw deflate, decompress with our function."""
        original = b'{"sensors": []}'
        # zlib.compress produces zlib-wrapped deflate, test that path
        compressed = zlib.compress(original)
        result = decompress_response(compressed, "deflate")
        assert result == original


class TestDecompressZstd:
    def test_round_trip(self):
        """Compress with zstandard, decompress with our function."""
        original = b'{"detects": [{"id": "d-1", "title": "suspicious"}]}'
        cctx = zstandard.ZstdCompressor()
        compressed = cctx.compress(original)
        result = decompress_response(compressed, "zstd")
        assert result == original

    def test_large_payload(self):
        """Verify zstd works with larger payloads (realistic JSON response)."""
        events = [{"type": "NEW_PROCESS", "id": f"evt-{i}", "data": "x" * 100} for i in range(500)]
        original = json.dumps({"events": events}).encode()
        cctx = zstandard.ZstdCompressor()
        compressed = cctx.compress(original)
        result = decompress_response(compressed, "zstd")
        assert result == original


class TestPassthrough:
    def test_none_encoding(self):
        """None content_encoding means no compression - passthrough."""
        data = b'{"events": []}'
        result = decompress_response(data, None)
        assert result is data  # Same object, not just equal

    def test_empty_encoding(self):
        """Empty string content_encoding - passthrough."""
        data = b'{"events": []}'
        result = decompress_response(data, "")
        assert result is data

    def test_unknown_encoding(self):
        """Unknown encoding - passthrough without crashing."""
        data = b'{"events": []}'
        result = decompress_response(data, "br")  # brotli, not supported
        assert result is data

    def test_whitespace_encoding(self):
        """Whitespace-only encoding string - passthrough."""
        data = b'{"events": []}'
        result = decompress_response(data, "   ")
        assert result is data
