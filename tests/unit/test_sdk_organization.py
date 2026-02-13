"""Tests for limacharlie.sdk.organization module."""

import json
from unittest.mock import MagicMock, patch, call
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
        result = org.get_config("vt")
        mock_client.request.assert_called_once_with("GET", "configs/test-oid-123/vt")
        assert result == "some-key"

    def test_get_config_missing_returns_none(self, org, mock_client):
        mock_client.request.return_value = {}
        result = org.get_config("nonexistent")
        assert result is None

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


class TestOrganizationIngestionKeys:
    def test_get_ingestion_keys_unwraps(self, org, mock_client):
        mock_client.request.return_value = {"keys": {"key1": "val1"}}
        result = org.get_ingestion_keys()
        assert result == {"key1": "val1"}

    def test_get_ingestion_keys_missing_returns_none(self, org, mock_client):
        mock_client.request.return_value = {}
        result = org.get_ingestion_keys()
        assert result is None


class TestOrganizationRename:
    def test_rename_sends_correct_param(self, org, mock_client):
        org.rename("new-org-name")
        mock_client.request.assert_called_once_with(
            "POST", "orgs/test-oid-123/name",
            query_params={"name": "new-org-name"},
        )


class TestOrganizationSubscriptions:
    def test_get_subscriptions_unwraps(self, org, mock_client):
        mock_client.request.return_value = {"resources": ["ext1", "ext2"]}
        result = org.get_subscriptions()
        assert result == ["ext1", "ext2"]

    def test_get_subscriptions_missing_returns_none(self, org, mock_client):
        mock_client.request.return_value = {}
        result = org.get_subscriptions()
        assert result is None

    def test_subscribe_splits_name(self, org, mock_client):
        org.subscribe_to_extension("lookup/my-resource")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["params"]["res_cat"] == "lookup"
        assert call_args[1]["params"]["res_name"] == "my-resource"

    def test_unsubscribe_splits_name(self, org, mock_client):
        org.unsubscribe_from_extension("lookup/my-resource")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert call_args[1]["params"]["res_cat"] == "lookup"
        assert call_args[1]["params"]["res_name"] == "my-resource"


class TestOrganizationTags:
    def test_get_all_tags_returns_list(self, org, mock_client):
        mock_client.request.return_value = {"tags": ["tag1", "tag2"]}
        result = org.get_all_tags()
        assert result == ["tag1", "tag2"]

    def test_get_all_tags_empty_response(self, org, mock_client):
        mock_client.request.return_value = {}
        result = org.get_all_tags()
        assert result == []

    def test_find_sensors_by_hostname(self, org, mock_client):
        mock_client.request.return_value = {"sensors": []}
        org.find_sensors_by_hostname("web-server")
        mock_client.request.assert_called_once_with(
            "GET", "hostnames/test-oid-123",
            query_params={"hostname": "web-server"},
        )


class TestRuntimeMetadata:
    def test_get_runtime_metadata_no_filters(self, org, mock_client):
        mock_client.request.return_value = {"metadata": {}}
        result = org.get_runtime_metadata()
        mock_client.request.assert_called_once_with("GET", "runtime_mtd/test-oid-123", query_params=None)
        assert result == {"metadata": {}}

    def test_get_runtime_metadata_with_entity_type(self, org, mock_client):
        mock_client.request.return_value = {}
        org.get_runtime_metadata(entity_type="sensor")
        mock_client.request.assert_called_once_with(
            "GET", "runtime_mtd/test-oid-123",
            query_params={"entity_type": "sensor"},
        )

    def test_get_runtime_metadata_with_both_filters(self, org, mock_client):
        mock_client.request.return_value = {}
        org.get_runtime_metadata(entity_type="sensor", entity_name="my-sensor")
        mock_client.request.assert_called_once_with(
            "GET", "runtime_mtd/test-oid-123",
            query_params={"entity_type": "sensor", "entity_name": "my-sensor"},
        )


class TestSetQuota:
    def test_set_quota(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        result = org.set_quota(500)
        mock_client.request.assert_called_once_with("POST", "orgs/test-oid-123/quota", params={"quota": 500})
        assert result["success"] is True


class TestOntologyAndEventTypes:
    def test_get_ontology(self, org, mock_client):
        mock_client.request.return_value = {"events": {}}
        result = org.get_ontology()
        mock_client.request.assert_called_once_with("GET", "ontology")
        assert result == {"events": {}}

    def test_get_event_types(self, org, mock_client):
        mock_client.request.return_value = {"NEW_PROCESS": "new process event"}
        result = org.get_event_types()
        mock_client.request.assert_called_once_with("GET", "events")
        assert "NEW_PROCESS" in result


class TestWhoAmI:
    def test_who_am_i(self, org, mock_client):
        mock_client.request.return_value = {"oid": "test-oid-123", "perms": ["dr.set"]}
        result = org.who_am_i()
        mock_client.request.assert_called_once_with("GET", "who")
        assert result["oid"] == "test-oid-123"


class TestTestAuth:
    def test_auth_success_no_permissions(self, org, mock_client):
        result = org.test_auth()
        mock_client.refresh_jwt.assert_called_once()
        assert result is True

    def test_auth_failure_refresh_raises(self, org, mock_client):
        mock_client.refresh_jwt.side_effect = Exception("auth failed")
        result = org.test_auth()
        assert result is False

    def test_auth_with_permissions_user_perms_present(self, org, mock_client):
        mock_client.request.return_value = {
            "user_perms": {"test-oid-123": ["dr.set", "output.set"]},
        }
        result = org.test_auth(permissions=["dr.set"])
        assert result is True

    def test_auth_with_permissions_missing_perm(self, org, mock_client):
        mock_client.request.return_value = {
            "user_perms": {"test-oid-123": ["dr.set"]},
        }
        result = org.test_auth(permissions=["dr.set", "sensor.set"])
        assert result is False

    def test_auth_with_permissions_api_key_path(self, org, mock_client):
        mock_client.request.return_value = {
            "orgs": ["test-oid-123"],
            "perms": ["dr.set", "output.set"],
        }
        result = org.test_auth(permissions=["dr.set"])
        assert result is True

    def test_auth_with_permissions_api_key_wrong_org(self, org, mock_client):
        mock_client.request.return_value = {
            "orgs": ["other-oid"],
            "perms": ["dr.set"],
        }
        result = org.test_auth(permissions=["dr.set"])
        assert result is False


class TestListAccessibleOrgs:
    def test_list_accessible_orgs_basic(self, org, mock_client):
        mock_client.request.return_value = {
            "orgs": [
                {"oid": "oid-1", "name": "Org One"},
                {"oid": "oid-2", "name": "Org Two"},
            ]
        }
        result = org.list_accessible_orgs()
        mock_client.refresh_jwt.assert_called_once_with(oid_override="-")
        mock_client.request.assert_called_once_with("GET", "user/orgs", query_params=None)
        assert result["orgs"] == ["oid-1", "oid-2"]
        assert result["names"]["oid-1"] == "Org One"

    def test_list_accessible_orgs_with_pagination(self, org, mock_client):
        mock_client.request.return_value = {"orgs": []}
        org.list_accessible_orgs(offset=10, limit=5, filter_text="test")
        mock_client.request.assert_called_once_with(
            "GET", "user/orgs",
            query_params={"offset": "10", "limit": "5", "filter": "test"},
        )

    def test_list_accessible_orgs_restores_jwt(self, org, mock_client):
        original_jwt = "original-jwt-token"
        mock_client._jwt = original_jwt
        mock_client.request.return_value = {"orgs": []}
        org.list_accessible_orgs()
        assert mock_client._jwt == original_jwt


class TestCreateOrg:
    def test_create_org_minimal(self, mock_client):
        mock_client.request.return_value = {"oid": "new-oid"}
        result = Organization.create_org(mock_client, "My Org")
        mock_client.request.assert_called_once_with("POST", "orgs/new", params={"name": "My Org"})
        assert result["oid"] == "new-oid"

    def test_create_org_with_location_and_template(self, mock_client):
        mock_client.request.return_value = {"oid": "new-oid"}
        Organization.create_org(mock_client, "My Org", location="us-east", template="basic")
        mock_client.request.assert_called_once_with(
            "POST", "orgs/new",
            params={"name": "My Org", "loc": "us-east", "template": "basic"},
        )


class TestCheckName:
    def test_check_name(self, mock_client):
        mock_client.request.return_value = {"available": True}
        result = Organization.check_name(mock_client, "unique-name")
        mock_client.request.assert_called_once_with("GET", "orgs/new", query_params={"name": "unique-name"})
        assert result["available"] is True


class TestDeleteOrg:
    def test_delete_org_without_token(self, org, mock_client):
        mock_client.request.return_value = {"confirmation": "abc-token"}
        result = org.delete_org()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/delete")
        assert result["confirmation"] == "abc-token"

    def test_delete_org_with_token(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        result = org.delete_org(confirm_token="abc-token")
        mock_client.request.assert_called_once_with(
            "DELETE", "orgs/test-oid-123/delete",
            params={"confirmation": "abc-token"},
        )
        assert result["success"] is True


class TestUsers:
    def test_get_users(self, org, mock_client):
        mock_client.request.return_value = {"users": []}
        result = org.get_users()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/users")

    def test_add_user(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.add_user("user@example.com")
        mock_client.request.assert_called_once_with(
            "POST", "orgs/test-oid-123/users",
            params={"email": "user@example.com"},
        )

    def test_remove_user(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.remove_user("user@example.com")
        mock_client.request.assert_called_once_with(
            "DELETE", "orgs/test-oid-123/users",
            params={"email": "user@example.com"},
        )


class TestUserPermissions:
    def test_get_user_permissions(self, org, mock_client):
        mock_client.request.return_value = {"permissions": {}}
        org.get_user_permissions()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/users/permissions")

    def test_add_user_permission_uses_perm_not_permission(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.add_user_permission("user@example.com", "dr.set")
        mock_client.request.assert_called_once_with(
            "POST", "orgs/test-oid-123/users/permissions",
            params={"email": "user@example.com", "perm": "dr.set"},
        )

    def test_remove_user_permission_uses_perm_not_permission(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.remove_user_permission("user@example.com", "dr.set")
        mock_client.request.assert_called_once_with(
            "DELETE", "orgs/test-oid-123/users/permissions",
            params={"email": "user@example.com", "perm": "dr.set"},
        )


class TestSetUserRole:
    def test_set_user_role_uses_put_with_json_body(self, org, mock_client):
        mock_client.request.return_value = {"success": True, "role": "Administrator"}
        result = org.set_user_role("user@example.com", "Administrator")
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "PUT"
        assert call_args[0][1] == "orgs/test-oid-123/users/role"
        body = json.loads(call_args[1]["raw_body"])
        assert body["email"] == "user@example.com"
        assert body["role"] == "Administrator"
        assert call_args[1]["content_type"] == "application/json"


class TestApiKeys:
    def test_get_api_keys(self, org, mock_client):
        mock_client.request.return_value = {"keys": []}
        org.get_api_keys()
        mock_client.request.assert_called_once_with("GET", "orgs/test-oid-123/keys")

    def test_add_api_key_uses_key_name_and_comma_joined_perms(self, org, mock_client):
        mock_client.request.return_value = {"key": "secret"}
        org.add_api_key("my-key", ["dr.set", "output.set"])
        mock_client.request.assert_called_once_with(
            "POST", "orgs/test-oid-123/keys",
            params={"key_name": "my-key", "perms": "dr.set,output.set"},
        )

    def test_add_api_key_with_ip_range(self, org, mock_client):
        mock_client.request.return_value = {"key": "secret"}
        org.add_api_key("my-key", ["dr.set"], ip_range="10.0.0.0/8")
        mock_client.request.assert_called_once_with(
            "POST", "orgs/test-oid-123/keys",
            params={"key_name": "my-key", "perms": "dr.set", "allowed_ip_range": "10.0.0.0/8"},
        )

    def test_remove_api_key(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.remove_api_key("abc123hash")
        mock_client.request.assert_called_once_with(
            "DELETE", "orgs/test-oid-123/keys",
            params={"key_hash": "abc123hash"},
        )


class TestInstallationKeys:
    def test_get_installation_keys(self, org, mock_client):
        mock_client.request.return_value = {"keys": []}
        org.get_installation_keys()
        mock_client.request.assert_called_once_with("GET", "installationkeys/test-oid-123")

    def test_get_installation_key(self, org, mock_client):
        mock_client.request.return_value = {"key": "details"}
        org.get_installation_key("iid-abc")
        mock_client.request.assert_called_once_with("GET", "installationkeys/test-oid-123/iid-abc")

    def test_create_installation_key_minimal(self, org, mock_client):
        mock_client.request.return_value = {"iid": "new-iid"}
        org.create_installation_key("Test key")
        mock_client.request.assert_called_once_with(
            "POST", "installationkeys/test-oid-123",
            params={"desc": "Test key", "use_public_root_ca": "false"},
        )

    def test_create_installation_key_with_tags_and_public_ca(self, org, mock_client):
        mock_client.request.return_value = {"iid": "new-iid"}
        org.create_installation_key("Test key", tags=["vip", "prod"], use_public_ca=True)
        mock_client.request.assert_called_once_with(
            "POST", "installationkeys/test-oid-123",
            params={"desc": "Test key", "use_public_root_ca": "true", "tags": "vip,prod"},
        )

    def test_create_installation_key_with_string_tags(self, org, mock_client):
        mock_client.request.return_value = {"iid": "new-iid"}
        org.create_installation_key("Test key", tags="vip,prod")
        mock_client.request.assert_called_once_with(
            "POST", "installationkeys/test-oid-123",
            params={"desc": "Test key", "use_public_root_ca": "false", "tags": "vip,prod"},
        )

    def test_delete_installation_key(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.delete_installation_key("iid-abc")
        mock_client.request.assert_called_once_with(
            "DELETE", "installationkeys/test-oid-123",
            params={"iid": "iid-abc"},
        )


class TestIngestionKeysCRUD:
    def test_create_ingestion_key(self, org, mock_client):
        mock_client.request.return_value = {"key": "new-key"}
        result = org.create_ingestion_key("my-ingest-key")
        mock_client.request.assert_called_once_with(
            "POST", "insight/test-oid-123/ingestion_keys",
            params={"name": "my-ingest-key"},
        )

    def test_delete_ingestion_key(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.delete_ingestion_key("my-ingest-key")
        mock_client.request.assert_called_once_with(
            "DELETE", "insight/test-oid-123/ingestion_keys",
            query_params={"name": "my-ingest-key"},
        )


class TestMassTagUntag:
    def test_mass_tag(self, org, mock_client):
        with patch.object(org, "list_sensors") as mock_ls:
            mock_ls.return_value = iter([{"sid": "sid-1"}, {"sid": "sid-2"}])
            with patch("limacharlie.sdk.sensor.Sensor") as MockSensor:
                sensor_instances = [MagicMock(), MagicMock()]
                MockSensor.side_effect = sensor_instances

                result = org.mass_tag("plat == windows", "vip", ttl=3600)

                assert result == {"tagged": 2, "tag": "vip", "selector": "plat == windows"}
                sensor_instances[0].add_tag.assert_called_once_with("vip", ttl=3600)
                sensor_instances[1].add_tag.assert_called_once_with("vip", ttl=3600)

    def test_mass_untag(self, org, mock_client):
        with patch.object(org, "list_sensors") as mock_ls:
            mock_ls.return_value = iter([{"sid": "sid-1"}, {"sid": "sid-2"}])
            with patch("limacharlie.sdk.sensor.Sensor") as MockSensor:
                sensor_instances = [MagicMock(), MagicMock()]
                MockSensor.side_effect = sensor_instances

                result = org.mass_untag("plat == windows", "vip")

                assert result == {"untagged": 2, "tag": "vip", "selector": "plat == windows"}
                sensor_instances[0].remove_tag.assert_called_once_with("vip")
                sensor_instances[1].remove_tag.assert_called_once_with("vip")

    def test_mass_tag_skips_entries_without_sid(self, org, mock_client):
        with patch.object(org, "list_sensors") as mock_ls:
            mock_ls.return_value = iter([{"sid": "sid-1"}, {"hostname": "no-sid"}])
            with patch("limacharlie.sdk.sensor.Sensor") as MockSensor:
                sensor_inst = MagicMock()
                MockSensor.return_value = sensor_inst

                result = org.mass_tag("plat == windows", "vip")

                assert result["tagged"] == 1
                assert MockSensor.call_count == 1


class TestListSensors:
    def test_list_sensors_single_page(self, org, mock_client):
        mock_client.request.return_value = {
            "sensors": [{"sid": "s1"}, {"sid": "s2"}],
        }
        result = list(org.list_sensors())
        mock_client.request.assert_called_once_with("GET", "sensors/test-oid-123", query_params=None)
        assert len(result) == 2

    def test_list_sensors_pagination(self, org, mock_client):
        mock_client.request.side_effect = [
            {"sensors": [{"sid": "s1"}], "continuation_token": "page2"},
            {"sensors": [{"sid": "s2"}]},
        ]
        result = list(org.list_sensors())
        assert len(result) == 2
        assert mock_client.request.call_count == 2
        second_call_qp = mock_client.request.call_args_list[1][1]["query_params"]
        assert second_call_qp["continuation_token"] == "page2"

    def test_list_sensors_with_filters(self, org, mock_client):
        mock_client.request.return_value = {"sensors": []}
        list(org.list_sensors(selector="plat == windows", limit=10, with_ip="1.2.3.4", with_hostname_prefix="web"))
        mock_client.request.assert_called_once_with(
            "GET", "sensors/test-oid-123",
            query_params={
                "selector": "plat == windows",
                "limit": "10",
                "with_ip": "1.2.3.4",
                "with_hostname_prefix": "web",
            },
        )


class TestExportSensors:
    def test_export_sensors(self, org, mock_client):
        mock_client.request.return_value = {"export": "data"}
        result = org.export_sensors()
        mock_client.request.assert_called_once_with("POST", "export/test-oid-123/sensors")
        assert result["export"] == "data"


class TestSetSensorVersion:
    def test_set_sensor_version_no_options(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.set_sensor_version()
        mock_client.request.assert_called_once_with("POST", "modules/test-oid-123", query_params=None)

    def test_set_sensor_version_with_version(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.set_sensor_version(version="4.28.0")
        mock_client.request.assert_called_once_with(
            "POST", "modules/test-oid-123",
            query_params={"specific_version": "4.28.0"},
        )

    def test_set_sensor_version_fallback_and_sleep(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.set_sensor_version(is_fallback=True, is_sleep=True)
        mock_client.request.assert_called_once_with(
            "POST", "modules/test-oid-123",
            query_params={"is_fallback": "true", "is_sleep": "true"},
        )


class TestAvailableServices:
    def test_get_available_services_unwraps_replicants(self, org, mock_client):
        mock_client.request.return_value = {"replicants": ["yara", "responder"]}
        result = org.get_available_services()
        mock_client.request.assert_called_once_with("GET", "service/test-oid-123")
        assert result == ["yara", "responder"]

    def test_get_available_services_no_replicants_key(self, org, mock_client):
        mock_client.request.return_value = {"other": "data"}
        result = org.get_available_services()
        assert result == {"other": "data"}


class TestGroups:
    def test_get_groups(self, org, mock_client):
        mock_client.request.return_value = {"groups": []}
        org.get_groups()
        mock_client.request.assert_called_once_with("GET", "groups")

    def test_create_group(self, org, mock_client):
        mock_client.request.return_value = {"gid": "g-1"}
        org.create_group("My Group")
        mock_client.request.assert_called_once_with("POST", "groups", params={"name": "My Group"})

    def test_get_group(self, org, mock_client):
        mock_client.request.return_value = {"gid": "g-1", "name": "My Group"}
        org.get_group("g-1")
        mock_client.request.assert_called_once_with("GET", "groups/g-1")

    def test_delete_group(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.delete_group("g-1")
        mock_client.request.assert_called_once_with("DELETE", "groups/g-1")


class TestGroupOwners:
    def test_add_group_owner_uses_member_email(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.add_group_owner("g-1", "owner@example.com")
        mock_client.request.assert_called_once_with(
            "POST", "groups/g-1/owners",
            params={"member_email": "owner@example.com"},
        )

    def test_remove_group_owner_uses_member_email(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.remove_group_owner("g-1", "owner@example.com")
        mock_client.request.assert_called_once_with(
            "DELETE", "groups/g-1/owners",
            params={"member_email": "owner@example.com"},
        )


class TestGroupMembers:
    def test_add_group_member_uses_member_email(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.add_group_member("g-1", "user@example.com")
        mock_client.request.assert_called_once_with(
            "POST", "groups/g-1/users",
            params={"member_email": "user@example.com"},
        )

    def test_remove_group_member_uses_member_email(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.remove_group_member("g-1", "user@example.com")
        mock_client.request.assert_called_once_with(
            "DELETE", "groups/g-1/users",
            params={"member_email": "user@example.com"},
        )


class TestGroupPermissions:
    def test_set_group_permissions_uses_perm_as_list(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.set_group_permissions("g-1", ["dr.set", "output.set"])
        mock_client.request.assert_called_once_with(
            "POST", "groups/g-1/permissions",
            params={"perm": ["dr.set", "output.set"]},
        )


class TestGroupLogs:
    def test_get_group_logs(self, org, mock_client):
        mock_client.request.return_value = {"logs": []}
        org.get_group_logs("g-1")
        mock_client.request.assert_called_once_with("GET", "groups/g-1/logs")


class TestGroupOrgs:
    def test_add_group_org(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.add_group_org("g-1", "oid-abc")
        mock_client.request.assert_called_once_with(
            "POST", "groups/g-1/orgs",
            params={"oid": "oid-abc"},
        )

    def test_remove_group_org(self, org, mock_client):
        mock_client.request.return_value = {"success": True}
        org.remove_group_org("g-1", "oid-abc")
        mock_client.request.assert_called_once_with(
            "DELETE", "groups/g-1/orgs",
            params={"oid": "oid-abc"},
        )


class TestDetections:
    def test_get_detections_single_page(self, org, mock_client):
        mock_client.request.return_value = {"detects": "", "next_cursor": None}
        mock_client.unwrap.return_value = [{"detect_id": "d1"}]
        result = list(org.get_detections(1000, 2000))
        mock_client.request.assert_called_once_with(
            "GET", "insight/test-oid-123/detections",
            query_params={"start": "1000", "end": "2000", "cursor": "-", "is_compressed": "true"},
        )
        assert result == [{"detect_id": "d1"}]

    def test_get_detections_with_limit_and_category(self, org, mock_client):
        mock_client.request.return_value = {"detects": "", "next_cursor": None}
        mock_client.unwrap.return_value = [{"detect_id": "d1"}]
        result = list(org.get_detections(1000, 2000, limit=5, category="lateral"))
        qp = mock_client.request.call_args[1]["query_params"]
        assert qp["limit"] == "5"
        assert qp["cat"] == "lateral"

    def test_get_detections_pagination(self, org, mock_client):
        mock_client.request.side_effect = [
            {"detects": "compressed1", "next_cursor": "cursor2"},
            {"detects": "compressed2", "next_cursor": None},
        ]
        mock_client.unwrap.side_effect = [
            [{"detect_id": "d1"}],
            [{"detect_id": "d2"}],
        ]
        result = list(org.get_detections(1000, 2000))
        assert len(result) == 2
        assert mock_client.request.call_count == 2

    def test_get_detections_limit_stops_iteration(self, org, mock_client):
        mock_client.request.return_value = {"detects": "", "next_cursor": "more"}
        mock_client.unwrap.return_value = [{"detect_id": "d1"}, {"detect_id": "d2"}]
        result = list(org.get_detections(1000, 2000, limit=1))
        assert len(result) == 1

    def test_get_detection_by_id(self, org, mock_client):
        mock_client.request.return_value = {"detect_id": "d-123", "title": "suspicious"}
        result = org.get_detection_by_id("d-123")
        mock_client.request.assert_called_once_with("GET", "insight/test-oid-123/detections/d-123")
        assert result["detect_id"] == "d-123"


class TestAuditLogs:
    def test_get_audit_logs_single_page(self, org, mock_client):
        mock_client.request.return_value = {"events": "", "next_cursor": None}
        mock_client.unwrap.return_value = [{"event": "login"}]
        result = list(org.get_audit_logs(1000, 2000))
        mock_client.request.assert_called_once_with(
            "GET", "insight/test-oid-123/audit",
            query_params={"start": "1000", "end": "2000", "cursor": "-", "is_compressed": "true"},
        )
        assert result == [{"event": "login"}]

    def test_get_audit_logs_with_filters(self, org, mock_client):
        mock_client.request.return_value = {"events": "", "next_cursor": None}
        mock_client.unwrap.return_value = []
        list(org.get_audit_logs(1000, 2000, limit=10, event_type="auth", sid="sid-1"))
        qp = mock_client.request.call_args[1]["query_params"]
        assert qp["limit"] == "10"
        assert qp["event_type"] == "auth"
        assert qp["sid"] == "sid-1"

    def test_get_audit_logs_pagination(self, org, mock_client):
        mock_client.request.side_effect = [
            {"events": "c1", "next_cursor": "cursor2"},
            {"events": "c2", "next_cursor": None},
        ]
        mock_client.unwrap.side_effect = [
            [{"event": "e1"}],
            [{"event": "e2"}],
        ]
        result = list(org.get_audit_logs(1000, 2000))
        assert len(result) == 2

    def test_get_audit_logs_limit_stops_iteration(self, org, mock_client):
        mock_client.request.return_value = {"events": "", "next_cursor": "more"}
        mock_client.unwrap.return_value = [{"event": "e1"}, {"event": "e2"}]
        result = list(org.get_audit_logs(1000, 2000, limit=1))
        assert len(result) == 1


class TestJobs:
    def test_get_jobs_with_explicit_times(self, org, mock_client):
        mock_client.request.return_value = {"jobs": {"j1": {"name": "scan"}, "j2": {"name": "resp"}}}
        mock_client.unwrap.return_value = {"j1": {"name": "scan"}, "j2": {"name": "resp"}}
        result = org.get_jobs(start_time=1000, end_time=2000)
        qp = mock_client.request.call_args[1]["query_params"]
        assert qp["start"] == "1000"
        assert qp["end"] == "2000"
        assert qp["is_compressed"] == "true"
        assert qp["with_data"] == "false"
        assert len(result) == 2

    def test_get_jobs_empty(self, org, mock_client):
        mock_client.request.return_value = {"jobs": ""}
        result = org.get_jobs(start_time=1000, end_time=2000)
        assert result == []

    def test_get_jobs_with_limit_and_sid(self, org, mock_client):
        mock_client.request.return_value = {"jobs": ""}
        org.get_jobs(start_time=1000, end_time=2000, limit=5, sid="sid-1")
        qp = mock_client.request.call_args[1]["query_params"]
        assert qp["limit"] == "5"
        assert qp["sid"] == "sid-1"
