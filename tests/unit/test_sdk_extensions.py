"""Tests for limacharlie.sdk.extensions module."""

import base64
import gzip
import json
from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.extensions import Extensions


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.client._jwt = "fake-jwt-token"
    return org


@pytest.fixture
def ext(mock_org):
    return Extensions(mock_org)


class TestExtensionsListSubscribed:
    def test_path(self, ext, mock_org):
        mock_org.client.request.return_value = {"subscriptions": []}
        ext.list_subscribed()
        mock_org.client.request.assert_called_once_with("GET", "orgs/test-oid/subscriptions")


class TestExtensionsSubscribe:
    def test_path_and_params(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext.subscribe("ext-zeek")
        mock_org.client.request.assert_called_once_with(
            "POST", "orgs/test-oid/subscription/extension/ext-zeek", params={}
        )


class TestExtensionsUnsubscribe:
    def test_path_and_params(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext.unsubscribe("ext-zeek")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "orgs/test-oid/subscription/extension/ext-zeek", params={}
        )


class TestExtensionsRekey:
    def test_path_and_params(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext.rekey("ext-zeek")
        mock_org.client.request.assert_called_once_with(
            "PATCH", "orgs/test-oid/subscription/extension/ext-zeek", params={}
        )


class TestExtensionsGetAll:
    def test_path(self, ext, mock_org):
        mock_org.client.request.return_value = {"extensions": []}
        ext.get_all()
        mock_org.client.request.assert_called_once_with(
            "GET", "extension/definition", params={}
        )


class TestExtensionsGet:
    def test_path(self, ext, mock_org):
        mock_org.client.request.return_value = {"name": "ext-zeek"}
        ext.get("ext-zeek")
        mock_org.client.request.assert_called_once_with(
            "GET", "extension/definition/ext-zeek"
        )


class TestExtensionsGetSchema:
    def test_path_and_query_params(self, ext, mock_org):
        mock_org.client.request.return_value = {"schema": {}}
        ext.get_schema("ext-zeek")
        mock_org.client.request.assert_called_once_with(
            "GET", "extension/schema/ext-zeek",
            query_params={"oid": "test-oid"},
        )


class TestExtensionsCreate:
    def test_path_and_body(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext_obj = {"name": "my-ext", "description": "test"}
        ext.create(ext_obj)
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "extension/definition")
        assert call_args[1]["params"] == {}
        body = json.loads(call_args[1]["raw_body"])
        assert body == ext_obj
        assert call_args[1]["content_type"] == "application/json"


class TestExtensionsUpdate:
    def test_path_and_body(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext_obj = {"name": "my-ext", "description": "updated"}
        ext.update(ext_obj)
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("PUT", "extension/definition")
        assert call_args[1]["params"] == {}
        body = json.loads(call_args[1]["raw_body"])
        assert body == ext_obj
        assert call_args[1]["content_type"] == "application/json"


class TestExtensionsDelete:
    def test_path(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext.delete("my-ext")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "extension/definition/my-ext"
        )


class TestExtensionsRequest:
    def test_path_and_params(self, ext, mock_org):
        mock_org.client.request.return_value = {"result": {}}
        ext.request("ext-zeek", "get_logs", {"limit": 10})
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "extension/request/ext-zeek")
        params = call_args[1]["params"]
        assert params["oid"] == "test-oid"
        assert params["action"] == "get_logs"
        assert "gzdata" in params
        # Verify gzdata decodes to the original data
        decoded = json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))
        assert decoded == {"limit": 10}

    def test_default_data_is_empty_dict(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext.request("ext-zeek", "ping")
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        decoded = json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))
        assert decoded == {}

    def test_impersonated_includes_jwt(self, ext, mock_org):
        mock_org.client.request.return_value = {}
        ext.request("ext-zeek", "get_logs", {}, is_impersonated=True)
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        assert "impersonator_jwt" in params
        assert params["impersonator_jwt"] == "fake-jwt-token"

    def test_impersonated_refreshes_jwt_if_none(self, ext, mock_org):
        mock_org.client._jwt = None
        mock_org.client.request.return_value = {}
        ext.request("ext-zeek", "get_logs", {}, is_impersonated=True)
        mock_org.client.refresh_jwt.assert_called_once()

    def test_unwrap_default_false_returns_envelope(self, ext, mock_org):
        envelope = {"data": {"x": 1}, "error": "", "retry": False}
        mock_org.client.request.return_value = envelope
        assert ext.request("ext-zeek", "ping") == envelope

    def test_unwrap_true_returns_data_field(self, ext, mock_org):
        mock_org.client.request.return_value = {
            "data": {"x": 1}, "error": "", "retry": False,
        }
        assert ext.request("ext-zeek", "ping", unwrap=True) == {"x": 1}

    def test_unwrap_true_with_no_data_key_returns_envelope(self, ext, mock_org):
        # Defensive: if the API ever returns something that isn't the
        # standard envelope, unwrap=True must not crash — just hand back
        # whatever we got.
        mock_org.client.request.return_value = {"unexpected": "shape"}
        assert ext.request("ext-zeek", "ping", unwrap=True) == {"unexpected": "shape"}
