import ssl
import sys

import pytest

from limacharlie.Manager import _create_ssl_context


class TestSSLContext:
    """Tests for _create_ssl_context() to ensure secure defaults are maintained."""

    @pytest.mark.skipif(sys.version_info < (3, 0), reason="Python 3+ only")
    def test_ssl_context_returns_context(self):
        """Verify that _create_ssl_context() returns an SSLContext object."""
        ctx = _create_ssl_context()
        assert ctx is not None
        assert isinstance(ctx, ssl.SSLContext)

    @pytest.mark.skipif(sys.version_info < (3, 0), reason="Python 3+ only")
    def test_ssl_context_check_hostname_enabled(self):
        """Verify that hostname checking is enabled for security."""
        ctx = _create_ssl_context()
        assert ctx.check_hostname is True, "check_hostname must be enabled for security"

    @pytest.mark.skipif(sys.version_info < (3, 0), reason="Python 3+ only")
    def test_ssl_context_cert_verification_required(self):
        """Verify that certificate verification is required."""
        ctx = _create_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED, "verify_mode must be CERT_REQUIRED for security"

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="OP_IGNORE_UNEXPECTED_EOF requires Python 3.10+")
    def test_ssl_context_has_ignore_unexpected_eof_flag(self):
        """Verify that OP_IGNORE_UNEXPECTED_EOF flag is set on Python 3.10+."""
        ctx = _create_ssl_context()
        assert ctx.options & ssl.OP_IGNORE_UNEXPECTED_EOF, \
            "OP_IGNORE_UNEXPECTED_EOF flag must be set for OpenSSL 3.0+ compatibility"

    @pytest.mark.skipif(sys.version_info < (3, 0), reason="Python 3+ only")
    def test_ssl_context_protocol_security(self):
        """Verify that insecure protocols are not enabled."""
        ctx = _create_ssl_context()
        # OP_NO_SSLv2 and OP_NO_SSLv3 should be set by create_default_context()
        # Note: In modern OpenSSL, OP_NO_SSLv2 may be 0 because SSLv2 is completely removed
        if hasattr(ssl, 'OP_NO_SSLv2') and ssl.OP_NO_SSLv2 != 0:
            assert ctx.options & ssl.OP_NO_SSLv2, "SSLv2 must be disabled"
        if hasattr(ssl, 'OP_NO_SSLv3') and ssl.OP_NO_SSLv3 != 0:
            assert ctx.options & ssl.OP_NO_SSLv3, "SSLv3 must be disabled"

    @pytest.mark.skipif(sys.version_info < (3, 0), reason="Python 3+ only")
    def test_ssl_context_matches_default_context_security(self):
        """Verify that our context has at least the same security as default context."""
        ctx = _create_ssl_context()
        default_ctx = ssl.create_default_context()

        # Our context should have the same or more security options as the default
        assert ctx.check_hostname == default_ctx.check_hostname, \
            "check_hostname should match default context"
        assert ctx.verify_mode == default_ctx.verify_mode, \
            "verify_mode should match default context"
