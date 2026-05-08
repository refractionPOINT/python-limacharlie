"""Tests for limacharlie.sdk.firehose module."""

from unittest.mock import MagicMock, patch
import pytest

from limacharlie.sdk.firehose import Firehose, _VALID_DATA_TYPES
from limacharlie.errors import ValidationError


class TestFirehoseValidation:
    def test_invalid_data_type_raises(self):
        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()
        with pytest.raises(ValidationError, match="Invalid data type"):
            Firehose(org, "0.0.0.0:4444", "invalid_type")

    def test_valid_data_types(self):
        assert "event" in _VALID_DATA_TYPES
        assert "detect" in _VALID_DATA_TYPES
        assert "audit" in _VALID_DATA_TYPES

    def test_ssl_cert_path_validation(self):
        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()
        with pytest.raises(ValidationError, match="No cert file"):
            Firehose(org, "0.0.0.0:4444", "event", ssl_cert="/nonexistent/cert.pem")

    def test_ssl_key_path_validation(self):
        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()
        with pytest.raises(ValidationError, match="No key file"):
            Firehose(org, "0.0.0.0:4444", "event", ssl_key="/nonexistent/key.pem")


class TestFirehoseListenAddressParsing:
    @patch("limacharlie.sdk.firehose.os.system", return_value=0)
    @patch("limacharlie.sdk.firehose.socket.socket")
    @patch("limacharlie.sdk.firehose.ssl.SSLContext")
    @patch("limacharlie.sdk.firehose.tempfile.mkstemp")
    def test_parse_host_and_port(self, mock_mkstemp, mock_ssl, mock_sock, mock_system):
        mock_mkstemp.return_value = (0, "/tmp/test")
        mock_sock_inst = MagicMock()
        mock_sock.return_value = mock_sock_inst

        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()

        fh = Firehose(org, "1.2.3.4:5555", "event")
        try:
            assert fh._listen_host == "1.2.3.4"
            assert fh._listen_port == 5555
        finally:
            fh._keep_running = False

    @patch("limacharlie.sdk.firehose.os.system", return_value=0)
    @patch("limacharlie.sdk.firehose.socket.socket")
    @patch("limacharlie.sdk.firehose.ssl.SSLContext")
    @patch("limacharlie.sdk.firehose.tempfile.mkstemp")
    def test_default_port_443(self, mock_mkstemp, mock_ssl, mock_sock, mock_system):
        mock_mkstemp.return_value = (0, "/tmp/test")
        mock_sock_inst = MagicMock()
        mock_sock.return_value = mock_sock_inst

        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()

        fh = Firehose(org, "0.0.0.0", "detect")
        try:
            assert fh._listen_host == "0.0.0.0"
            assert fh._listen_port == 443
        finally:
            fh._keep_running = False

    @patch("limacharlie.sdk.firehose.os.system", return_value=0)
    @patch("limacharlie.sdk.firehose.socket.socket")
    @patch("limacharlie.sdk.firehose.ssl.SSLContext")
    @patch("limacharlie.sdk.firehose.tempfile.mkstemp")
    def test_empty_host_defaults(self, mock_mkstemp, mock_ssl, mock_sock, mock_system):
        mock_mkstemp.return_value = (0, "/tmp/test")
        mock_sock_inst = MagicMock()
        mock_sock.return_value = mock_sock_inst

        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()

        fh = Firehose(org, ":8080", "audit")
        try:
            assert fh._listen_host == "0.0.0.0"
            assert fh._listen_port == 8080
        finally:
            fh._keep_running = False


class TestFirehoseProperties:
    @patch("limacharlie.sdk.firehose.os.system", return_value=0)
    @patch("limacharlie.sdk.firehose.socket.socket")
    @patch("limacharlie.sdk.firehose.ssl.SSLContext")
    @patch("limacharlie.sdk.firehose.tempfile.mkstemp")
    def test_dropped_counter(self, mock_mkstemp, mock_ssl, mock_sock, mock_system):
        mock_mkstemp.return_value = (0, "/tmp/test")
        mock_sock.return_value = MagicMock()

        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()

        fh = Firehose(org, "0.0.0.0:9999", "event")
        try:
            assert fh.dropped == 0
            fh._dropped = 3
            assert fh.dropped == 3
            fh.reset_dropped()
            assert fh.dropped == 0
        finally:
            fh._keep_running = False

    @patch("limacharlie.sdk.firehose.os.system", return_value=0)
    @patch("limacharlie.sdk.firehose.socket.socket")
    @patch("limacharlie.sdk.firehose.ssl.SSLContext")
    @patch("limacharlie.sdk.firehose.tempfile.mkstemp")
    def test_is_running(self, mock_mkstemp, mock_ssl, mock_sock, mock_system):
        mock_mkstemp.return_value = (0, "/tmp/test")
        mock_sock.return_value = MagicMock()

        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()

        fh = Firehose(org, "0.0.0.0:9998", "event")
        assert fh.is_running is True
        fh.shutdown()
        assert fh.is_running is False

    @patch("limacharlie.sdk.firehose.os.system", return_value=0)
    @patch("limacharlie.sdk.firehose.socket.socket")
    @patch("limacharlie.sdk.firehose.ssl.SSLContext")
    @patch("limacharlie.sdk.firehose.tempfile.mkstemp")
    def test_double_shutdown_safe(self, mock_mkstemp, mock_ssl, mock_sock, mock_system):
        mock_mkstemp.return_value = (0, "/tmp/test")
        mock_sock.return_value = MagicMock()

        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()

        fh = Firehose(org, "0.0.0.0:9997", "event")
        fh.shutdown()
        fh.shutdown()  # Should not raise
