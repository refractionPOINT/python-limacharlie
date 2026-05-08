"""Tests for SDK wrapper classes that delegate to Organization."""

from unittest.mock import MagicMock, call

import pytest

from limacharlie.sdk.users import Users
from limacharlie.sdk.groups import Groups
from limacharlie.sdk.api_keys import ApiKeys
from limacharlie.sdk.installation_keys import InstallationKeys
from limacharlie.sdk.ingestion_keys import IngestionKeys
from limacharlie.sdk.outputs import Outputs


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


# ---- Users ----

class TestUsers:
    def test_list(self, mock_org):
        u = Users(mock_org)
        mock_org.get_users.return_value = {"users": []}
        result = u.list()
        mock_org.get_users.assert_called_once_with()
        assert result == {"users": []}

    def test_invite(self, mock_org):
        u = Users(mock_org)
        u.invite("alice@example.com")
        mock_org.add_user.assert_called_once_with("alice@example.com")

    def test_remove(self, mock_org):
        u = Users(mock_org)
        u.remove("alice@example.com")
        mock_org.remove_user.assert_called_once_with("alice@example.com")

    def test_list_permissions(self, mock_org):
        u = Users(mock_org)
        mock_org.get_user_permissions.return_value = {"perms": {}}
        result = u.list_permissions()
        mock_org.get_user_permissions.assert_called_once_with()
        assert result == {"perms": {}}

    def test_add_permission(self, mock_org):
        u = Users(mock_org)
        u.add_permission("alice@example.com", "dr.list")
        mock_org.add_user_permission.assert_called_once_with("alice@example.com", "dr.list")

    def test_remove_permission(self, mock_org):
        u = Users(mock_org)
        u.remove_permission("alice@example.com", "dr.list")
        mock_org.remove_user_permission.assert_called_once_with("alice@example.com", "dr.list")

    def test_set_role(self, mock_org):
        u = Users(mock_org)
        u.set_role("alice@example.com", "admin")
        mock_org.set_user_role.assert_called_once_with("alice@example.com", "admin")

    def test_return_values_propagate(self, mock_org):
        u = Users(mock_org)
        sentinel = {"result": "ok"}
        mock_org.add_user.return_value = sentinel
        assert u.invite("bob@example.com") is sentinel


# ---- Groups ----

class TestGroups:
    def test_list(self, mock_org):
        g = Groups(mock_org)
        mock_org.get_groups.return_value = {"groups": []}
        result = g.list()
        mock_org.get_groups.assert_called_once_with()
        assert result == {"groups": []}

    def test_get(self, mock_org):
        g = Groups(mock_org)
        g.get("gid-1")
        mock_org.get_group.assert_called_once_with("gid-1")

    def test_create(self, mock_org):
        g = Groups(mock_org)
        g.create("my-group")
        mock_org.create_group.assert_called_once_with("my-group")

    def test_delete(self, mock_org):
        g = Groups(mock_org)
        g.delete("gid-1")
        mock_org.delete_group.assert_called_once_with("gid-1")

    def test_add_member(self, mock_org):
        g = Groups(mock_org)
        g.add_member("gid-1", "alice@example.com")
        mock_org.add_group_member.assert_called_once_with("gid-1", "alice@example.com")

    def test_remove_member(self, mock_org):
        g = Groups(mock_org)
        g.remove_member("gid-1", "alice@example.com")
        mock_org.remove_group_member.assert_called_once_with("gid-1", "alice@example.com")

    def test_add_owner(self, mock_org):
        g = Groups(mock_org)
        g.add_owner("gid-1", "alice@example.com")
        mock_org.add_group_owner.assert_called_once_with("gid-1", "alice@example.com")

    def test_remove_owner(self, mock_org):
        g = Groups(mock_org)
        g.remove_owner("gid-1", "alice@example.com")
        mock_org.remove_group_owner.assert_called_once_with("gid-1", "alice@example.com")

    def test_set_permissions(self, mock_org):
        g = Groups(mock_org)
        g.set_permissions("gid-1", ["dr.list", "sensor.task"])
        mock_org.set_group_permissions.assert_called_once_with("gid-1", ["dr.list", "sensor.task"])

    def test_get_logs(self, mock_org):
        g = Groups(mock_org)
        g.get_logs("gid-1")
        mock_org.get_group_logs.assert_called_once_with("gid-1")

    def test_add_org(self, mock_org):
        g = Groups(mock_org)
        g.add_org("gid-1", "other-oid")
        mock_org.add_group_org.assert_called_once_with("gid-1", "other-oid")

    def test_remove_org(self, mock_org):
        g = Groups(mock_org)
        g.remove_org("gid-1", "other-oid")
        mock_org.remove_group_org.assert_called_once_with("gid-1", "other-oid")

    def test_return_values_propagate(self, mock_org):
        g = Groups(mock_org)
        sentinel = {"id": "gid-new"}
        mock_org.create_group.return_value = sentinel
        assert g.create("test") is sentinel


# ---- ApiKeys ----

class TestApiKeys:
    def test_list(self, mock_org):
        ak = ApiKeys(mock_org)
        mock_org.get_api_keys.return_value = {"keys": []}
        result = ak.list()
        mock_org.get_api_keys.assert_called_once_with()
        assert result == {"keys": []}

    def test_create_without_ip_range(self, mock_org):
        ak = ApiKeys(mock_org)
        ak.create("my-key", ["dr.list"])
        mock_org.add_api_key.assert_called_once_with("my-key", ["dr.list"], ip_range=None)

    def test_create_with_ip_range(self, mock_org):
        ak = ApiKeys(mock_org)
        ak.create("my-key", ["dr.list"], ip_range="10.0.0.0/8")
        mock_org.add_api_key.assert_called_once_with("my-key", ["dr.list"], ip_range="10.0.0.0/8")

    def test_delete(self, mock_org):
        ak = ApiKeys(mock_org)
        ak.delete("abc123hash")
        mock_org.remove_api_key.assert_called_once_with("abc123hash")

    def test_return_values_propagate(self, mock_org):
        ak = ApiKeys(mock_org)
        sentinel = {"key": "secret"}
        mock_org.add_api_key.return_value = sentinel
        assert ak.create("k", ["perm"]) is sentinel


# ---- InstallationKeys ----

class TestInstallationKeys:
    def test_list(self, mock_org):
        ik = InstallationKeys(mock_org)
        mock_org.get_installation_keys.return_value = {"keys": []}
        result = ik.list()
        mock_org.get_installation_keys.assert_called_once_with()
        assert result == {"keys": []}

    def test_get(self, mock_org):
        ik = InstallationKeys(mock_org)
        ik.get("iid-1")
        mock_org.get_installation_key.assert_called_once_with("iid-1")

    def test_create_defaults(self, mock_org):
        ik = InstallationKeys(mock_org)
        ik.create("my sensor")
        mock_org.create_installation_key.assert_called_once_with(
            "my sensor", tags=None, use_public_ca=False,
        )

    def test_create_with_tags_list(self, mock_org):
        ik = InstallationKeys(mock_org)
        ik.create("my sensor", tags=["web", "prod"])
        mock_org.create_installation_key.assert_called_once_with(
            "my sensor", tags=["web", "prod"], use_public_ca=False,
        )

    def test_create_with_tags_string(self, mock_org):
        ik = InstallationKeys(mock_org)
        ik.create("my sensor", tags="web")
        mock_org.create_installation_key.assert_called_once_with(
            "my sensor", tags="web", use_public_ca=False,
        )

    def test_create_with_public_ca(self, mock_org):
        ik = InstallationKeys(mock_org)
        ik.create("my sensor", use_public_ca=True)
        mock_org.create_installation_key.assert_called_once_with(
            "my sensor", tags=None, use_public_ca=True,
        )

    def test_delete(self, mock_org):
        ik = InstallationKeys(mock_org)
        ik.delete("iid-1")
        mock_org.delete_installation_key.assert_called_once_with("iid-1")

    def test_return_values_propagate(self, mock_org):
        ik = InstallationKeys(mock_org)
        sentinel = {"iid": "new-key"}
        mock_org.create_installation_key.return_value = sentinel
        assert ik.create("desc") is sentinel


# ---- IngestionKeys ----

class TestIngestionKeys:
    def test_list(self, mock_org):
        ik = IngestionKeys(mock_org)
        mock_org.get_ingestion_keys.return_value = {"keys": []}
        result = ik.list()
        mock_org.get_ingestion_keys.assert_called_once_with()
        assert result == {"keys": []}

    def test_create(self, mock_org):
        ik = IngestionKeys(mock_org)
        ik.create("my-ingest")
        mock_org.create_ingestion_key.assert_called_once_with("my-ingest")

    def test_delete(self, mock_org):
        ik = IngestionKeys(mock_org)
        ik.delete("my-ingest")
        mock_org.delete_ingestion_key.assert_called_once_with("my-ingest")

    def test_return_values_propagate(self, mock_org):
        ik = IngestionKeys(mock_org)
        sentinel = {"name": "ingest-1"}
        mock_org.create_ingestion_key.return_value = sentinel
        assert ik.create("ingest-1") is sentinel


# ---- Outputs ----

class TestOutputs:
    def test_list(self, mock_org):
        o = Outputs(mock_org)
        mock_org.get_outputs.return_value = {"outputs": []}
        result = o.list()
        mock_org.get_outputs.assert_called_once_with()
        assert result == {"outputs": []}

    def test_create(self, mock_org):
        o = Outputs(mock_org)
        o.create("my-output", "syslog", "event")
        mock_org.add_output.assert_called_once_with("my-output", "syslog", "event")

    def test_create_with_kwargs(self, mock_org):
        o = Outputs(mock_org)
        o.create("my-output", "s3", "detect", bucket="my-bucket", region="us-east-1")
        mock_org.add_output.assert_called_once_with(
            "my-output", "s3", "detect", bucket="my-bucket", region="us-east-1",
        )

    def test_delete(self, mock_org):
        o = Outputs(mock_org)
        o.delete("my-output")
        mock_org.delete_output.assert_called_once_with("my-output")

    def test_return_values_propagate(self, mock_org):
        o = Outputs(mock_org)
        sentinel = {"status": "created"}
        mock_org.add_output.return_value = sentinel
        assert o.create("out", "syslog", "event") is sentinel
