"""Tests for limacharlie.sdk.payloads module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.payloads import Payloads


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def payloads(mock_org):
    return Payloads(mock_org)


class TestPayloadsList:
    def test_list(self, payloads, mock_org):
        mock_org.client.request.return_value = {"payloads": {"p1": {"name": "p1"}}}
        result = payloads.list()
        mock_org.client.request.assert_called_once_with("GET", "payload/test-oid")
        assert result == {"p1": {"name": "p1"}}

    def test_list_unwraps_payloads_key(self, payloads, mock_org):
        """The API returns {payloads: {...}, replicants: [...]} — list() extracts just payloads."""
        mock_org.client.request.return_value = {"payloads": {"a": {}}, "replicants": ["svc"]}
        result = payloads.list()
        assert result == {"a": {}}

    def test_list_fallback_when_no_payloads_key(self, payloads, mock_org):
        """If the response lacks a 'payloads' key, return as-is."""
        mock_org.client.request.return_value = {"unexpected": "data"}
        result = payloads.list()
        assert result == {"unexpected": "data"}


class TestPayloadsDelete:
    def test_delete(self, payloads, mock_org):
        mock_org.client.request.return_value = {}
        payloads.delete("my-payload")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "payload/test-oid/my-payload",
        )


class TestPayloadsUpload:
    def test_upload_step1_gets_signed_url(self, payloads, mock_org):
        """Test that upload POSTs to payload/{oid}/{name} to get a signed URL."""
        mock_org.client.request.return_value = {"put_url": "https://storage.example.com/signed"}
        # We pass payload_content to avoid file I/O; the urlopen will fail
        # but we only care about the first client.request call.
        try:
            payloads.upload("my-payload", payload_content=b"data")
        except Exception:
            pass  # urlopen will fail in unit test
        first_call = mock_org.client.request.call_args_list[0]
        assert first_call[0] == ("POST", "payload/test-oid/my-payload")

    def test_upload_returns_none_when_no_put_url(self, payloads, mock_org):
        mock_org.client.request.return_value = {}
        result = payloads.upload("missing", payload_content=b"data")
        assert result is None

    def test_upload_requires_file_or_content(self, payloads):
        with pytest.raises(ValueError, match="Either file_path or payload_content"):
            payloads.upload("name")


class TestPayloadsDownload:
    def test_download_step1_gets_signed_url(self, payloads, mock_org):
        """Test that download GETs payload/{oid}/{name} to retrieve a signed URL."""
        mock_org.client.request.return_value = {"get_url": "https://storage.example.com/signed"}
        try:
            payloads.download("my-payload")
        except Exception:
            pass  # urlopen will fail in unit test
        mock_org.client.request.assert_called_once_with(
            "GET", "payload/test-oid/my-payload",
        )

    def test_download_returns_none_when_no_get_url(self, payloads, mock_org):
        mock_org.client.request.return_value = {}
        result = payloads.download("missing")
        assert result is None
