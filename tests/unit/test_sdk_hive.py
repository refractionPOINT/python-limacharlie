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
        rec = HiveRecord("my-rule", raw=raw)
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
        rec = HiveRecord("r", raw=raw)
        assert rec.data == {"nested": True}


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
