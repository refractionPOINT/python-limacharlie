"""Tests for dataclass conversions in CLI v2."""

from dataclasses import fields, is_dataclass

from limacharlie.cli import LimaCharlieContext
from limacharlie.sdk.hive import HiveRecord


class TestLimaCharlieContext:
    def test_is_dataclass(self):
        assert is_dataclass(LimaCharlieContext)

    def test_default_values(self):
        ctx = LimaCharlieContext()
        assert ctx.oid is None
        assert ctx.output_format is None
        assert ctx.debug is False
        assert ctx.quiet is False
        assert ctx.profile is None
        assert ctx.environment is None

    def test_field_names(self):
        names = [f.name for f in fields(LimaCharlieContext)]
        assert names == ["oid", "output_format", "debug", "quiet", "profile", "environment"]

    def test_custom_values(self):
        ctx = LimaCharlieContext(oid="abc", output_format="json", debug=True, quiet=True)
        assert ctx.oid == "abc"
        assert ctx.output_format == "json"
        assert ctx.debug is True
        assert ctx.quiet is True


class TestHiveRecordDataclass:
    def test_is_dataclass(self):
        assert is_dataclass(HiveRecord)

    def test_field_count(self):
        assert len(fields(HiveRecord)) == 15

    def test_simple_construction(self):
        rec = HiveRecord(name="test", data={"key": "val"})
        assert rec.name == "test"
        assert rec.data == {"key": "val"}
        assert rec.etag is None
        assert rec.enabled is None

    def test_from_raw_basic(self):
        raw = {
            "data": {"detect": {"op": "is"}},
            "usr_mtd": {"enabled": True, "tags": ["prod"]},
            "sys_mtd": {"etag": "e1", "guid": "g1", "created_at": 100},
        }
        rec = HiveRecord.from_raw("rule-1", raw)
        assert rec.name == "rule-1"
        assert rec.data == {"detect": {"op": "is"}}
        assert rec.enabled is True
        assert rec.tags == ["prod"]
        assert rec.etag == "e1"
        assert rec.guid == "g1"
        assert rec.created_at == 100

    def test_from_raw_json_string_data(self):
        import json
        raw = {
            "data": json.dumps({"key": "value"}),
            "usr_mtd": {},
            "sys_mtd": {},
        }
        rec = HiveRecord.from_raw("test", raw)
        assert rec.data == {"key": "value"}

    def test_to_dict_roundtrip(self):
        rec = HiveRecord(
            name="test",
            data={"key": "val"},
            enabled=True,
            tags=["a", "b"],
            comment="hello",
            etag="etag1",
        )
        d = rec.to_dict()
        assert d["data"] == {"key": "val"}
        assert d["usr_mtd"]["enabled"] is True
        assert d["usr_mtd"]["tags"] == ["a", "b"]
        assert d["usr_mtd"]["comment"] == "hello"
        assert d["sys_mtd"]["etag"] == "etag1"

    def test_to_dict_minimal(self):
        rec = HiveRecord(name="minimal", data={"x": 1})
        d = rec.to_dict()
        assert d["data"] == {"x": 1}
        assert d["usr_mtd"] == {}
        assert d["sys_mtd"] == {}
