"""Tests for limacharlie.sdk.host_posture: extension requests and the default pack install."""

import base64
import gzip
import json
from unittest.mock import MagicMock, patch

import pytest

from limacharlie.errors import ApiError, ValidationError
from limacharlie.sdk import host_posture as hp
from limacharlie.sdk.hive import HiveRecord
from limacharlie.sdk.host_posture import (
    DEFAULT_PACK_TAG, PACK_DIGEST_TAG_PREFIX, HostPosture, record_digest,
)


def _decode(call_args):
    params = call_args[1]["params"]
    return params["action"], json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))


def _rec(rule_id, version, extra=None):
    rule = {"apiVersion": "lc-posture/v1", "kind": "Signature", "id": rule_id, "version": version}
    if extra:
        rule.update(extra)
    return {"rule": rule}


def _entry(rule_id, version, extra=None):
    return {"id": rule_id, "version": version, "title": rule_id, "record": _rec(rule_id, version, extra)}


def _not_found():
    return ApiError("nope", status_code=400, response_body={"error": "lc_error_code:RECORD_NOT_FOUND - x"})


def _stored(data, *, enabled=True, tags=None, comment=None, etag="e1", expiry=None):
    return HiveRecord(name=data["rule"]["id"], data=data, enabled=enabled, tags=tags,
                      comment=comment, etag=etag, expiry=expiry)


def _pristine(entry, **kw):
    data = entry["record"]
    tags = [DEFAULT_PACK_TAG, PACK_DIGEST_TAG_PREFIX + record_digest(data)]
    return _stored(data, tags=tags, comment="LimaCharlie default pack 1", **kw)


@pytest.fixture
def org():
    o = MagicMock()
    o.oid = "test-oid"
    return o


class TestRequests:
    @pytest.mark.parametrize("method,args,action,data", [
        ("status", (), "status", {}),
        ("default_pack", (), "default_pack", {}),
        ("query_summary", (), "query_summary", {}),
        ("query_host", ("s1",), "query_host", {"sid": "s1"}),
        ("scan", ("s1",), "scan", {"sid": "s1"}),
        ("query_standards", (), "query_standards", {}),
        ("query_standards", ("cis",), "query_standards", {"framework": "cis"}),
    ])
    def test_action_and_data(self, org, method, args, action, data):
        getattr(HostPosture(org), method)(*args)
        sent_action, sent_data = _decode(org.client.request.call_args)
        assert org.client.request.call_args[0][1] == "extension/request/ext-host-posture"
        assert (sent_action, sent_data) == (action, data)

    def test_sweep_sends_tags_only_when_given(self, org):
        HostPosture(org).sweep()
        assert _decode(org.client.request.call_args)[1] == {}
        HostPosture(org).sweep(["prod", "web"])
        assert _decode(org.client.request.call_args) == ("sweep", {"tags": ["prod", "web"]})

    def test_filters_and_paging_are_sent_to_the_server(self, org):
        HostPosture(org).query_hosts(platform="windows", severity="high", status="fail", search="srv", cursor="c", limit=5)
        assert _decode(org.client.request.call_args) == ("query_hosts", {
            "platform": "windows", "severity": "high", "status": "fail", "search": "srv", "cursor": "c", "limit": 5,
        })
        HostPosture(org).query_rules(severity="low")
        assert _decode(org.client.request.call_args) == ("query_rules", {"severity": "low"})
        HostPosture(org).query_rule_hosts("r1", "fail", limit=3)
        assert _decode(org.client.request.call_args) == ("query_rule_hosts", {"rule_id": "r1", "status": "fail", "limit": 3})

    def test_rule_hosts_refuses_unsupported_status(self, org):
        with pytest.raises(ValidationError):
            HostPosture(org).query_rule_hosts("r1", "unsupported")

    def test_response_is_unwrapped(self, org):
        org.client.request.return_value = {"data": {"job_id": "j"}, "error": ""}
        assert HostPosture(org).sweep() == {"job_id": "j"}


class TestInstallDefaultPack:
    @pytest.fixture
    def env(self, org):
        hp_ = HostPosture(org)
        hive = MagicMock()
        pack = {"pack_version": "1", "rules": [_entry("lc.a", 2), _entry("lc.b", 1)]}
        with patch.object(HostPosture, "default_pack", return_value=pack), \
             patch.object(HostPosture, "_rules", return_value=hive):
            hive.get.side_effect = _not_found()
            yield hp_, hive, pack

    def test_creates_missing_rules_create_only_and_enabled(self, env):
        hp_, hive, _ = env
        result = hp_.install_default_pack()
        assert [c["id"] for c in result["created"]] == ["lc.a", "lc.b"]
        assert not (result["updated"] or result["skipped"] or result["failed"])
        record = hive.set.call_args_list[0][0][0]
        assert record.etag == hp._CREATE_ONLY_ETAG
        assert record.enabled is True
        assert record.name == "lc.a" and record.data == _rec("lc.a", 2)
        assert DEFAULT_PACK_TAG in record.tags
        assert PACK_DIGEST_TAG_PREFIX + record_digest(record.data) in record.tags
        assert record.comment == "LimaCharlie default pack 1"

    def test_disabled_and_id_filter(self, env):
        hp_, hive, _ = env
        result = hp_.install_default_pack(["lc.b"], enabled=False)
        assert [c["id"] for c in result["created"]] == ["lc.b"]
        assert hive.set.call_args[0][0].enabled is False

    def test_unknown_id_is_refused_before_any_write(self, env):
        hp_, hive, _ = env
        with pytest.raises(ValidationError, match="lc.zzz"):
            hp_.install_default_pack(["lc.zzz"])
        hive.set.assert_not_called()

    def test_empty_pack_is_refused(self, org):
        with patch.object(HostPosture, "default_pack", return_value={"rules": []}):
            with pytest.raises(ValidationError):
                HostPosture(org).install_default_pack()

    def test_dry_run_writes_nothing(self, env):
        hp_, hive, _ = env
        result = hp_.install_default_pack(dry_run=True)
        assert len(result["created"]) == 2 and result["dry_run"] is True
        hive.set.assert_not_called()

    def test_existing_rule_is_skipped_with_update_available(self, env):
        hp_, hive, _ = env
        hive.get.side_effect = lambda name: _stored(_rec(name, 1))
        result = hp_.install_default_pack(["lc.a"])
        assert result["skipped"][0]["update_available"] is True
        assert result["skipped"][0]["installed_version"] == 1
        hive.set.assert_not_called()

    def test_identical_rule_is_up_to_date(self, env):
        hp_, hive, _ = env
        hive.get.side_effect = lambda name: _stored(_rec(name, 2) if name == "lc.a" else _rec(name, 1))
        result = hp_.install_default_pack(update=True)
        assert {s["reason"] for s in result["skipped"]} == {"already up to date"}
        hive.set.assert_not_called()

    def test_update_replaces_unedited_older_rule_keeping_org_state(self, env):
        hp_, hive, pack = env
        old = _entry("lc.a", 1)
        stored = _pristine(old, enabled=False, expiry=123)
        stored.tags.append("org-tag")
        hive.get.side_effect = None
        hive.get.return_value = stored
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert result["updated"] == [{"id": "lc.a", "from_version": 1, "to_version": 2}]
        record = hive.set.call_args[0][0]
        assert record.etag == "e1"  # conditional on what was read
        assert record.data == _rec("lc.a", 2)
        assert record.enabled is False and record.expiry == 123
        assert "org-tag" in record.tags
        digests = [t for t in record.tags if t.startswith(PACK_DIGEST_TAG_PREFIX)]
        assert digests == [PACK_DIGEST_TAG_PREFIX + record_digest(_rec("lc.a", 2))]

    def test_update_keeps_the_orgs_own_comment(self, env):
        hp_, hive, _ = env
        stored = _pristine(_entry("lc.a", 1))
        stored.comment = "we tuned the scope"
        hive.get.side_effect = None
        hive.get.return_value = stored
        hp_.install_default_pack(["lc.a"], update=True)
        assert hive.set.call_args[0][0].comment == "we tuned the scope"

    def test_update_never_overwrites_an_edited_rule(self, env):
        hp_, hive, _ = env
        stored = _pristine(_entry("lc.a", 1))
        stored.data = _rec("lc.a", 1, {"severity": "low"})  # edited after install
        hive.get.side_effect = None
        hive.get.return_value = stored
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "edited" in result["skipped"][0]["reason"]
        hive.set.assert_not_called()

    def test_update_never_overwrites_a_record_the_pack_did_not_write(self, env):
        hp_, hive, _ = env
        hive.get.side_effect = None
        hive.get.return_value = _stored(_rec("lc.a", 1), tags=[])
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "not installed from the pack" in result["skipped"][0]["reason"]
        hive.set.assert_not_called()

    def test_update_skips_a_rule_that_is_not_older(self, env):
        hp_, hive, _ = env
        newer = _entry("lc.a", 5)
        hive.get.side_effect = None
        hive.get.return_value = _pristine(newer)
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "not older" in result["skipped"][0]["reason"]
        hive.set.assert_not_called()

    def test_force_replaces_an_edited_rule(self, env):
        hp_, hive, _ = env
        hive.get.side_effect = None
        hive.get.return_value = _stored(_rec("lc.a", 9, {"severity": "low"}), enabled=True, tags=["x"])
        result = hp_.install_default_pack(["lc.a"], force=True)
        assert result["updated"][0]["to_version"] == 2
        record = hive.set.call_args[0][0]
        assert record.data == _rec("lc.a", 2) and record.etag == "e1"
        assert "x" in record.tags and DEFAULT_PACK_TAG in record.tags

    def test_etag_conflict_on_update_is_skipped_not_failed(self, env):
        hp_, hive, _ = env
        hive.get.side_effect = None
        hive.get.return_value = _pristine(_entry("lc.a", 1))
        hive.set.side_effect = ApiError("etag", status_code=409)
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "changed while updating" in result["skipped"][0]["reason"]
        assert not result["failed"]

    def test_record_created_concurrently_is_skipped(self, env):
        hp_, hive, _ = env
        hive.set.side_effect = ApiError("ETAG_MISMATCH", status_code=400)
        result = hp_.install_default_pack(["lc.a"])
        assert "created while installing" in result["skipped"][0]["reason"]

    def test_failure_is_reported_and_the_rest_continues(self, env):
        hp_, hive, _ = env
        hive.set.side_effect = [ApiError("bad rule: probes.x", status_code=400), {}]
        result = hp_.install_default_pack()
        assert result["failed"][0]["id"] == "lc.a" and "probes.x" in result["failed"][0]["error"]
        assert [c["id"] for c in result["created"]] == ["lc.b"]

    def test_a_read_failure_other_than_not_found_is_a_failure(self, env):
        hp_, hive, _ = env
        hive.get.side_effect = ApiError("denied", status_code=403)
        result = hp_.install_default_pack(["lc.a"])
        assert result["failed"][0]["id"] == "lc.a"
        hive.set.assert_not_called()


def test_digest_is_stable_across_key_order():
    assert record_digest({"a": 1, "b": {"c": 2}}) == record_digest({"b": {"c": 2}, "a": 1})
    assert record_digest({"a": 1}) != record_digest({"a": 2})
