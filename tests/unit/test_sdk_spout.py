"""Tests for limacharlie.sdk.spout module."""

from unittest.mock import MagicMock, patch
import pytest

from limacharlie.sdk.spout import Spout, _VALID_DATA_TYPES
from limacharlie.errors import ValidationError


class TestSpoutValidation:
    def test_invalid_data_type_raises(self):
        org = MagicMock()
        org.oid = "test-oid"
        org.client = MagicMock()
        org.client._api_key = "key"
        org.client._jwt = None
        org.client._uid = None
        with pytest.raises(ValidationError, match="Invalid data type"):
            with patch("limacharlie.sdk.spout.requests") as mock_requests:
                Spout(org, "invalid_type")

    def test_valid_data_types(self):
        assert "event" in _VALID_DATA_TYPES
        assert "detect" in _VALID_DATA_TYPES
        assert "audit" in _VALID_DATA_TYPES
        assert "deployment" in _VALID_DATA_TYPES
        assert "billing" in _VALID_DATA_TYPES


class TestSpoutInit:
    @patch("limacharlie.sdk.spout.requests")
    def test_creates_with_api_key(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter([])
        mock_requests.post.return_value = mock_response

        org = MagicMock()
        org.oid = "test-oid"
        org.client._api_key = "my-key"
        org.client._jwt = None
        org.client._uid = None

        sp = Spout(org, "event")
        try:
            assert sp._oid == "test-oid"
            assert sp._spout_params["type"] == "event"
            assert sp._spout_params["api_key"] == "my-key"
        finally:
            sp.shutdown()

    @patch("limacharlie.sdk.spout.requests")
    def test_creates_with_filters(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter([])
        mock_requests.post.return_value = mock_response

        org = MagicMock()
        org.oid = "test-oid"
        org.client._api_key = "key"
        org.client._jwt = None
        org.client._uid = None

        sp = Spout(org, "detect", tag="web", cat="lateral", sid="sid-1")
        try:
            assert sp._spout_params["tag"] == "web"
            assert sp._spout_params["cat"] == "lateral"
            assert sp._spout_params["sid"] == "sid-1"
        finally:
            sp.shutdown()


class TestSpoutShutdown:
    @patch("limacharlie.sdk.spout.requests")
    def test_shutdown(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter([])
        mock_requests.post.return_value = mock_response

        org = MagicMock()
        org.oid = "test-oid"
        org.client._api_key = "key"
        org.client._jwt = None
        org.client._uid = None

        sp = Spout(org, "event")
        assert sp.is_running is True
        sp.shutdown()
        assert sp.is_running is False

    @patch("limacharlie.sdk.spout.requests")
    def test_double_shutdown_is_safe(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter([])
        mock_requests.post.return_value = mock_response

        org = MagicMock()
        org.oid = "test-oid"
        org.client._api_key = "key"
        org.client._jwt = None
        org.client._uid = None

        sp = Spout(org, "event")
        sp.shutdown()
        sp.shutdown()  # Should not raise


class TestSpoutDropped:
    @patch("limacharlie.sdk.spout.requests")
    def test_dropped_counter(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter([])
        mock_requests.post.return_value = mock_response

        org = MagicMock()
        org.oid = "test-oid"
        org.client._api_key = "key"
        org.client._jwt = None
        org.client._uid = None

        sp = Spout(org, "event")
        try:
            assert sp.dropped == 0
            sp._dropped = 5
            assert sp.dropped == 5
            sp.reset_dropped()
            assert sp.dropped == 0
        finally:
            sp.shutdown()
