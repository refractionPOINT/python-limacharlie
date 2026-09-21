import importlib
import ssl
import sys
import uuid

import pytest

import limacharlie
from limacharlie.Manager import _create_ssl_context

# `limacharlie.Manager` resolves to the class, the module has to be looked up.
manager_module = importlib.import_module( 'limacharlie.Manager' )


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


class _FakeResponse:
    def read(self):
        return b'{}'

    def close(self):
        pass

    def getheaders(self):
        return []


class TestSharedSSLContext:
    """Tests for _get_ssl_context(), the context the REST calls actually use."""

    @pytest.fixture(autouse=True)
    def _reset_shared_context(self, monkeypatch):
        monkeypatch.setattr(manager_module, '_ssl_context', None)

    def test_shared_context_is_created_once(self):
        """Verify that every caller gets the same, securely configured context."""
        ctx = manager_module._get_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert manager_module._get_ssl_context() is ctx

    def test_failed_creation_is_not_cached(self, monkeypatch):
        """Verify that a failure to build a context is retried on the next call."""
        with monkeypatch.context() as m:
            m.setattr(manager_module, '_create_ssl_context', lambda: None)
            assert manager_module._get_ssl_context() is None
        assert isinstance(manager_module._get_ssl_context(), ssl.SSLContext)

    def test_rest_calls_reuse_one_context(self, monkeypatch):
        """Verify that REST calls across Manager instances share a single context.

        A context per call loads the CA bundle every time and is only freed by
        the cyclic garbage collector, which grows long-running processes.
        """
        n_created = []
        real_create_default_context = ssl.create_default_context

        def counting_create_default_context(*args, **kwargs):
            n_created.append(1)
            return real_create_default_context(*args, **kwargs)

        contexts_used = []

        def fake_urlopen(request, timeout=None, context=None):
            contexts_used.append(context)
            return _FakeResponse()

        monkeypatch.setattr(ssl, 'create_default_context', counting_create_default_context)
        monkeypatch.setattr(manager_module, 'urlopen', fake_urlopen)

        for _ in range(2):
            man = limacharlie.Manager(oid=str(uuid.uuid4()), jwt='not-a-real-jwt')
            for _ in range(2):
                code, _ = man._restCall('payload/%s' % man._oid, 'GET', {})
                assert code == 200

        assert len(contexts_used) == 4
        assert isinstance(contexts_used[0], ssl.SSLContext)
        assert all(ctx is contexts_used[0] for ctx in contexts_used)
        assert len(n_created) == 1
