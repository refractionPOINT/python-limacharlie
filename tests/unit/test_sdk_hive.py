"""Tests for limacharlie.sdk.hive module."""

import json
from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.hive import Hive, HiveRecord


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def hive(mock_org):
    return Hive(mock_org, "dr-general")


class TestHiveRecord:
    def test_from_raw(self):
        raw = {
            "data": {"op": "is", "path": "event/FILE_PATH"},
            "usr_mtd": {"expiry": 0, "enabled": True, "tags": ["test"], "comment": "my rule"},
            "sys_mtd": {"etag": "abc123", "created_at": 1234567890, "guid": "g1"},
        }
        rec = HiveRecord.from_raw("my-rule", raw)
        assert rec.name == "my-rule"
        assert rec.data == {"op": "is", "path": "event/FILE_PATH"}
        assert rec.enabled is True
        assert rec.etag == "abc123"
        assert rec.tags == ["test"]
        assert rec.comment == "my rule"

    def test_from_data(self):
        rec = HiveRecord("simple", data={"key": "value"})
        assert rec.name == "simple"
        assert rec.data == {"key": "value"}
        assert rec.etag is None

    def test_to_dict(self):
        rec = HiveRecord("test", data={"a": 1})
        rec.enabled = True
        rec.tags = ["t1"]
        d = rec.to_dict()
        assert d["data"] == {"a": 1}
        assert d["usr_mtd"]["enabled"] is True
        assert d["usr_mtd"]["tags"] == ["t1"]

    def test_json_string_data_parsed(self):
        raw = {"data": '{"nested": true}', "usr_mtd": {}, "sys_mtd": {}}
        rec = HiveRecord.from_raw("r", raw)
        assert rec.data == {"nested": True}


class TestHiveRecordFromRawWithUsrMtd:
    """Test creating HiveRecord with usr_mtd and etag via raw dict format.

    This covers the pattern used by _hive_shortcut.py set_cmd which builds
    a raw dict from user input containing 'data', 'usr_mtd', and 'etag'.
    """
    def test_from_raw_with_usr_mtd_and_etag(self):
        raw = {
            "data": {"key": "value"},
            "usr_mtd": {"enabled": True, "tags": ["prod"]},
            "sys_mtd": {"etag": "my-etag"},
        }
        rec = HiveRecord.from_raw("test-key", raw)
        assert rec.name == "test-key"
        assert rec.data == {"key": "value"}
        assert rec.enabled is True
        assert rec.tags == ["prod"]
        assert rec.etag == "my-etag"

    def test_from_raw_with_empty_sys_mtd(self):
        raw = {
            "data": {"key": "value"},
            "usr_mtd": {"comment": "hello"},
            "sys_mtd": {},
        }
        rec = HiveRecord.from_raw("test-key", raw)
        assert rec.comment == "hello"
        assert rec.etag is None


class TestHiveInit:
    def test_default_partition(self, mock_org):
        h = Hive(mock_org, "secret")
        assert h._partition_key == "test-oid"

    def test_custom_partition(self, mock_org):
        h = Hive(mock_org, "secret", partition_key="custom-key")
        assert h._partition_key == "custom-key"


class TestHiveList:
    def test_list_returns_records(self, hive, mock_org):
        mock_org.client.request.return_value = {
            "rule1": {"data": {"op": "is"}, "usr_mtd": {}, "sys_mtd": {}},
            "rule2": {"data": {"op": "and"}, "usr_mtd": {}, "sys_mtd": {}},
        }
        result = hive.list()
        assert "rule1" in result
        assert isinstance(result["rule1"], HiveRecord)
        mock_org.client.request.assert_called_once_with("GET", "hive/dr-general/test-oid")


class TestHiveGet:
    def test_get_record(self, hive, mock_org):
        mock_org.client.request.return_value = {
            "data": {"value": 42},
            "usr_mtd": {"enabled": True},
            "sys_mtd": {"etag": "e1"},
        }
        rec = hive.get("my-key")
        assert rec.name == "my-key"
        assert rec.data == {"value": 42}
        assert rec.etag == "e1"
        mock_org.client.request.assert_called_once_with(
            "GET", "hive/dr-general/test-oid/my-key/data"
        )

    def test_get_metadata(self, hive, mock_org):
        mock_org.client.request.return_value = {
            "usr_mtd": {"enabled": False},
            "sys_mtd": {"etag": "e2"},
        }
        rec = hive.get_metadata("my-key")
        assert rec.enabled is False
        mock_org.client.request.assert_called_once_with(
            "GET", "hive/dr-general/test-oid/my-key/mtd"
        )

    def test_get_metadata_clears_empty_data_envelope(self, hive, mock_org):
        """The /mtd endpoint returns ``"data": {}`` even though it is a
        metadata-only fetch. ``get_metadata`` must drop that envelope so
        a subsequent ``set()`` stays on the /mtd routing path — otherwise
        typed hives with required fields (ai_skill, ai_agent, ...) reject
        the disable/enable flow on an empty data validator pass."""
        mock_org.client.request.return_value = {
            "data": {},
            "usr_mtd": {"enabled": True},
            "sys_mtd": {"etag": "e3"},
        }
        rec = hive.get_metadata("my-key")
        assert rec.data is None

        # Round-trip: a follow-up set() must target /mtd, not /data.
        mock_org.client.request.reset_mock()
        rec.enabled = False
        hive.set(rec)
        url = mock_org.client.request.call_args[0][1]
        assert url.endswith("/my-key/mtd"), url


class TestHiveSet:
    def test_set_record_with_data(self, hive, mock_org):
        rec = HiveRecord("new-rule", data={"detect": {"op": "is"}})
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "new-rule/data" in call_args[0][1]

    def test_set_with_etag(self, hive, mock_org):
        rec = HiveRecord("rule", data={"a": 1})
        rec.etag = "old-etag"
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        assert call_args[1]["params"]["etag"] == "old-etag"

    def test_set_data_is_json_serialized(self, hive, mock_org):
        rec = HiveRecord("rule", data={"key": "value", "nested": {"a": 1}})
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        parsed = json.loads(params["data"])
        assert parsed == {"key": "value", "nested": {"a": 1}}

    def test_set_with_usr_mtd(self, hive, mock_org):
        rec = HiveRecord("rule", data={"a": 1})
        rec.enabled = True
        rec.tags = ["prod", "critical"]
        rec.comment = "important rule"
        rec.expiry = 9999999
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        assert "usr_mtd" in params
        usr = json.loads(params["usr_mtd"])
        assert usr["enabled"] is True
        assert usr["tags"] == ["prod", "critical"]
        assert usr["comment"] == "important rule"
        assert usr["expiry"] == 9999999

    def test_set_without_data_targets_mtd(self, hive, mock_org):
        rec = HiveRecord("rule")
        rec.enabled = False
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        assert "rule/mtd" in call_args[0][1]
        params = call_args[1]["params"]
        assert "data" not in params

    def test_set_with_arl(self, hive, mock_org):
        rec = HiveRecord("rule", data={"a": 1})
        rec.arl = "arl://lookup/my-data"
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        params = call_args[1]["params"]
        assert params["arl"] == "arl://lookup/my-data"
        # With arl and data, target should be "data"
        assert "rule/data" in call_args[0][1]

    def test_set_url_escapes_record_name(self, hive, mock_org):
        rec = HiveRecord("rule/with/slashes", data={"a": 1})
        hive.set(rec)
        call_args = mock_org.client.request.call_args
        # The name should be URL-escaped
        assert "rule%2Fwith%2Fslashes" in call_args[0][1]


class TestHiveGetSchema:
    def test_get_schema(self, hive, mock_org):
        mock_org.client.request.return_value = {
            "schema": {"$ref": "#/$defs/SecretRecord"},
        }
        result = hive.get_schema()
        assert result == {"schema": {"$ref": "#/$defs/SecretRecord"}}
        mock_org.client.request.assert_called_once_with(
            "GET", "hive/dr-general/schema"
        )

    def test_get_schema_url_escapes_hive_name(self, mock_org):
        h = Hive(mock_org, "weird/name")
        mock_org.client.request.return_value = {"schema": {}}
        h.get_schema()
        call_args = mock_org.client.request.call_args
        assert call_args[0][1] == "hive/weird%2Fname/schema"


class TestHiveDelete:
    def test_delete(self, hive, mock_org):
        hive.delete("old-rule")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "hive/dr-general/test-oid/old-rule"
        )


class TestHiveRename:
    def test_rename(self, hive, mock_org):
        hive.rename("old-name", "new-name")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "rename" in call_args[0][1]
        assert call_args[1]["query_params"]["new_name"] == "new-name"


class TestHiveValidate:
    def test_validate(self, hive, mock_org):
        rec = HiveRecord("test", data={"op": "is"})
        hive.validate(rec)
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "validate" in call_args[0][1]


class TestHiveUpdateTx:
    def test_transaction_success(self, hive, mock_org):
        mock_org.client.request.side_effect = [
            {"data": {"v": 1}, "usr_mtd": {}, "sys_mtd": {"etag": "e1"}},  # get
            {"ok": True},  # set
        ]

        def update_fn(record):
            record.data["v"] = 2

        result = hive.update_tx("my-key", update_fn)
        assert result == {"ok": True}
        # get was called, then set
        assert mock_org.client.request.call_count == 2

    def test_transaction_retries_on_conflict(self, hive, mock_org):
        from limacharlie.errors import ApiError

        mock_org.client.request.side_effect = [
            {"data": {"v": 1}, "usr_mtd": {}, "sys_mtd": {"etag": "e1"}},  # first get
            ApiError("etag mismatch", status_code=409),  # first set fails
            {"data": {"v": 1}, "usr_mtd": {}, "sys_mtd": {"etag": "e2"}},  # second get
            {"ok": True},  # second set succeeds
        ]

        def update_fn(record):
            record.data["v"] = 2

        result = hive.update_tx("my-key", update_fn)
        assert result == {"ok": True}

    def test_transaction_retries_on_etag_mismatch_string(self, hive, mock_org):
        from limacharlie.errors import ApiError

        mock_org.client.request.side_effect = [
            {"data": {"v": 1}, "usr_mtd": {}, "sys_mtd": {"etag": "e1"}},  # first get
            ApiError("ETAG_MISMATCH", status_code=400),  # string match, not 409
            {"data": {"v": 1}, "usr_mtd": {}, "sys_mtd": {"etag": "e2"}},  # second get
            {"ok": True},  # second set succeeds
        ]

        def update_fn(record):
            record.data["v"] = 2

        result = hive.update_tx("my-key", update_fn)
        assert result == {"ok": True}
