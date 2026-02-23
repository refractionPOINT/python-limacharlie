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

    def test_has_zstd_flag_true(self):
        """_HAS_ZSTD should be True when zstandard is importable."""
        assert _HAS_ZSTD is True


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

    def test_zstd_passthrough_case_insensitive_when_unavailable(self):
        """Zstd passthrough should work regardless of header casing."""
        import limacharlie.transport_compression as tc_mod

        saved = sys.modules.pop("zstandard", None)
        try:
            with mock.patch.dict(sys.modules, {"zstandard": None}):
                importlib.reload(tc_mod)
                raw = b"compressed-bytes"
                assert tc_mod.decompress_response(raw, "ZSTD") is raw
                assert tc_mod.decompress_response(raw, "Zstd") is raw
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
        assert decompress_response(compressed, "GZIP") == original
        assert decompress_response(compressed, "Gzip") == original

    def test_large_payload(self):
        """Verify gzip works with larger payloads."""
        events = [{"type": "NEW_PROCESS", "id": f"evt-{i}", "data": "x" * 100} for i in range(500)]
        original = json.dumps({"events": events}).encode()
        compressed = gzip.compress(original)
        result = decompress_response(compressed, "gzip")
        assert result == original

    def test_whitespace_around_header(self):
        """Leading/trailing whitespace in Content-Encoding should be stripped."""
        original = b'{"ok": true}'
        compressed = gzip.compress(original)
        result = decompress_response(compressed, "  gzip  ")
        assert result == original


class TestDecompressDeflate:
    def test_zlib_wrapped_deflate(self):
        """zlib.compress produces zlib-wrapped deflate - should decompress."""
        original = b'{"sensors": []}'
        compressed = zlib.compress(original)
        result = decompress_response(compressed, "deflate")
        assert result == original

    def test_raw_deflate(self):
        """Raw deflate (no zlib header) - should decompress via the try branch."""
        original = b'{"sensors": [{"sid": "test-sensor"}]}'
        # Use wbits=-15 to produce raw deflate (no zlib header)
        compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -zlib.MAX_WBITS)
        compressed = compressor.compress(original) + compressor.flush()
        result = decompress_response(compressed, "deflate")
        assert result == original

    def test_case_insensitive(self):
        """Content-Encoding: DEFLATE should work."""
        original = b'{"data": "test"}'
        compressed = zlib.compress(original)
        assert decompress_response(compressed, "DEFLATE") == original
        assert decompress_response(compressed, "Deflate") == original


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

    def test_case_insensitive(self):
        """Content-Encoding: ZSTD should work."""
        original = b'{"data": "test"}'
        cctx = zstandard.ZstdCompressor()
        compressed = cctx.compress(original)
        assert decompress_response(compressed, "ZSTD") == original
        assert decompress_response(compressed, "Zstd") == original

    def test_whitespace_around_header(self):
        """Leading/trailing whitespace in Content-Encoding should be stripped."""
        original = b'{"ok": true}'
        cctx = zstandard.ZstdCompressor()
        compressed = cctx.compress(original)
        result = decompress_response(compressed, "  zstd  ")
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

    def test_empty_data_with_encoding(self):
        """Empty bytes with a Content-Encoding should not crash."""
        # gzip of empty bytes is a valid gzip stream
        compressed_empty = gzip.compress(b"")
        result = decompress_response(compressed_empty, "gzip")
        assert result == b""

    def test_empty_data_no_encoding(self):
        """Empty bytes with no encoding - passthrough."""
        data = b""
        result = decompress_response(data, None)
        assert result is data
