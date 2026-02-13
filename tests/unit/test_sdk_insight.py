"""Tests for limacharlie.sdk.insight module."""

import json
from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.insight import Insight


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def insight(mock_org):
    return Insight(mock_org)


class TestInsightIsEnabled:
    def test_enabled_when_bucket_present(self, insight, mock_org):
        mock_org.client.request.return_value = {"insight_bucket": "my-bucket"}
        assert insight.is_enabled() is True
        mock_org.client.request.assert_called_once_with("GET", "insight/test-oid")

    def test_disabled_when_bucket_missing(self, insight, mock_org):
        mock_org.client.request.return_value = {}
        assert insight.is_enabled() is False

    def test_disabled_when_bucket_empty(self, insight, mock_org):
        mock_org.client.request.return_value = {"insight_bucket": ""}
        assert insight.is_enabled() is False


class TestInsightSearchIoc:
    def test_path_and_query_params(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("domain", "evil.com")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("GET", "insight/test-oid/objects/domain")
        qp = call_args[1]["query_params"]
        assert qp["name"] == "evil.com"
        assert qp["info"] == "summary"
        assert qp["case_sensitive"] == "true"
        assert qp["with_wildcards"] == "false"
        assert qp["per_object"] == "false"

    def test_wildcards_enables_per_object_for_summary(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("domain", "%.evil.com", wildcards=True)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["with_wildcards"] == "true"
        assert qp["per_object"] == "true"

    def test_wildcards_with_locations_does_not_auto_enable_per_object(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("domain", "%.evil.com", info="locations", wildcards=True)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["per_object"] == "false"

    def test_explicit_per_object_overrides_default(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("domain", "evil.com", per_object=True)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["per_object"] == "true"

    def test_case_insensitive(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("domain", "Evil.Com", case_sensitive=False)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["case_sensitive"] == "false"

    def test_limit_included_when_set(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("ip", "1.2.3.4", limit=50)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["limit"] == "50"

    def test_limit_excluded_when_none(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("ip", "1.2.3.4")
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert "limit" not in qp

    def test_url_escapes_obj_type(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.search_ioc("file_hash", "abc123")
        call_args = mock_org.client.request.call_args
        assert call_args[0][1] == "insight/test-oid/objects/file_hash"


class TestInsightBatchSearch:
    def test_path_and_params(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": {}}
        objects = {"domain": ["evil.com", "bad.org"], "ip": ["1.2.3.4"]}
        insight.batch_search(objects)
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "insight/test-oid/objects")
        params = call_args[1]["params"]
        decoded = json.loads(params["objects"])
        assert decoded == objects
        assert params["case_sensitive"] == "true"

    def test_case_insensitive(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": {}}
        insight.batch_search({"domain": ["evil.com"]}, case_sensitive=False)
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        assert params["case_sensitive"] == "false"


class TestInsightGetObjectInformation:
    def test_delegates_to_search_ioc(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.get_object_information("domain", "evil.com")
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("GET", "insight/test-oid/objects/domain")
        qp = call_args[1]["query_params"]
        assert qp["name"] == "evil.com"
        assert qp["info"] == "summary"

    def test_passes_through_parameters(self, insight, mock_org):
        mock_org.client.request.return_value = {"results": []}
        insight.get_object_information("ip", "1.2.3.4", info="locations",
                                       case_sensitive=False, wildcards=True, limit=10)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["name"] == "1.2.3.4"
        assert qp["info"] == "locations"
        assert qp["case_sensitive"] == "false"
        assert qp["with_wildcards"] == "true"
        assert qp["limit"] == "10"
