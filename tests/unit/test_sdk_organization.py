"""Tests for limacharlie.sdk.organization module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.organization import Organization


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.oid = "test-oid-123"
    return client


@pytest.fixture
def org(mock_client):
    return Organization(mock_client)


class TestOrganizationInit:
    def test_stores_client(self, mock_client):
        org = Organization(mock_client)
        assert org.client is mock_client

    def test_oid_from_client(self, org):
        assert org.oid == "test-oid-123"


class TestOrganizationInfo:
    def test_get_info(self, org, mock_client):
        mock_client.request.return_value = {"name": "TestOrg", "sensor_count": 5}
        result = org.get_info()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123")
        assert result["name"] == "TestOrg"

    def test_get_urls(self, org, mock_client):
        mock_client.request.return_value = {"url": {"search": "search.lc.io", "logs": "logs.lc.io"}}
        result = org.get_urls()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/url", is_no_auth=True)
        assert "search" in result
        assert result["logs"] == "logs.lc.io"

    def test_get_stats(self, org, mock_client):
        mock_client.request.return_value = {"quota_used": 100}
        org.get_stats()
        mock_client.request.assert_called_once_with("GET", "usage/test-oid-123")

    def test_get_errors(self, org, mock_client):
        mock_client.request.return_value = {"errors": []}
        org.get_errors()
        mock_client.request.assert_called_once_with("GET", "errors/test-oid-123")

    def test_dismiss_error(self, org, mock_client):
        org.dismiss_error("my-component")
        mock_client.request.assert_called_once_with("DELETE", "errors/test-oid-123/my-component")

    def test_get_mitre_report(self, org, mock_client):
        org.get_mitre_report()
        mock_client.request.assert_called_once_with("GET", "mitre/test-oid-123")


class TestOrganizationConfig:
    def test_get_config(self, org, mock_client):
        mock_client.request.return_value = {"value": "some-key"}
        org.get_config("vt")
        mock_client.request.assert_called_once_with("GET", "configs/test-oid-123/vt")

    def test_set_config(self, org, mock_client):
        org.set_config("vt", "my-api-key")
        mock_client.request.assert_called_once_with("POST", "configs/test-oid-123/vt", params={"value": "my-api-key"})


class TestOrganizationSchemas:
    def test_get_schemas_no_filter(self, org, mock_client):
        org.get_schemas()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/schema", query_params=None)

    def test_get_schemas_with_platform(self, org, mock_client):
        org.get_schemas(platform="windows")
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/schema", query_params={"platform": "windows"})

    def test_get_schema(self, org, mock_client):
        org.get_schema("NEW_PROCESS")
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/schema/NEW_PROCESS")


class TestOrganizationRules:
    def test_get_rules_default_namespace(self, org, mock_client):
        mock_client.request.return_value = {"rule1": {"detect": {}}}
        org.get_rules()
        mock_client.request.assert_called_once_with("GET", "rules/test-oid-123", query_params=None)

    def test_get_rules_managed_namespace(self, org, mock_client):
        org.get_rules(namespace="managed")
        mock_client.request.assert_called_once_with("GET", "rules/test-oid-123", query_params={"namespace": "managed"})

    def test_add_rule(self, org, mock_client):
        org.add_rule("test-rule", {"op": "is"}, [{"action": "report"}])
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert "rules/test-oid-123" in call_args[0][1]

    def test_delete_rule(self, org, mock_client):
        org.delete_rule("test-rule")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "rules/test-oid-123" in call_args[0][1]
        assert call_args[1]["params"]["name"] == "test-rule"


class TestOrganizationOutputs:
    def test_get_outputs(self, org, mock_client):
        org.get_outputs()
        mock_client.request.assert_called_once_with("GET", "outputs/test-oid-123")

    def test_add_output(self, org, mock_client):
        org.add_output("my-output", "syslog", "event", dest_host="1.2.3.4:443")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert "outputs/test-oid-123" in call_args[0][1]

    def test_delete_output(self, org, mock_client):
        org.delete_output("my-output")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "outputs/test-oid-123" in call_args[0][1]
        assert call_args[1]["params"]["name"] == "my-output"


class TestOrganizationSensors:
    def test_get_all_tags(self, org, mock_client):
        org.get_all_tags()
        mock_client.request.assert_called_once_with("GET", "tags/test-oid-123")

    def test_find_sensors_by_tag(self, org, mock_client):
        mock_client.request.return_value = {"sensors": []}
        org.find_sensors_by_tag("server")
        mock_client.request.assert_called_once_with("GET", "tags/test-oid-123/server")

    def test_get_online_sensors(self, org, mock_client):
        mock_client.request.return_value = {"online": []}
        org.get_online_sensors()
        mock_client.request.assert_called_once()

    def test_service_request(self, org, mock_client):
        import base64
        import json
        mock_client.request.return_value = {"result": "ok"}
        org.service_request("yara", {"action": "list_rules"})
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert "service/test-oid-123/yara" in call_args[0][1]
        # Verify request_data is base64-encoded JSON
        params = call_args[1]["params"]
        decoded = json.loads(base64.b64decode(params["request_data"]))
        assert decoded["action"] == "list_rules"


class TestOrganizationFPs:
    def test_get_fps(self, org, mock_client):
        org.get_fps()
        mock_client.request.assert_called_once_with("GET", "fp/test-oid-123")

    def test_add_fp(self, org, mock_client):
        org.add_fp("fp-rule", {"detect": {}})
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"

    def test_delete_fp(self, org, mock_client):
        org.delete_fp("fp-rule")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "fp/test-oid-123" in call_args[0][1]
        assert call_args[1]["params"]["name"] == "fp-rule"
