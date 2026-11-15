"""Tests for limacharlie.sdk.host_posture: extension requests and the default pack install."""

import base64
import gzip
import json
from unittest.mock import MagicMock, patch

import pytest

from limacharlie.errors import ApiError, ValidationError
from limacharlie.sdk import host_posture as hp
from limacharlie.sdk.hive import HiveRecord
from limacharlie.sdk.host_posture import DEFAULT_PACK_TAG, PACK_DIGEST_TAG_PREFIX, HostPosture


def _decode(call_args):
    params = call_args[1]["params"]
    return params["action"], json.loads(gzip.decompress(base64.b64decode(params["gzdata"])))


def _rec(rule_id, version, extra=None):
    rule = {"apiVersion": "lc-posture/v1", "kind": "Signature", "id": rule_id, "version": version}
    if extra:
        rule.update(extra)
    return {"rule": rule}


def _entry(rule_id, version, extra=None):
    return {"id": rule_id, "version": version, "title": rule_id, "digest": f"digest-{rule_id}-{version}",
            "record": _rec(rule_id, version, extra)}


def _not_found():
    return ApiError("nope", status_code=400, response_body={"error": "lc_error_code:RECORD_NOT_FOUND - x"})


def _stored(data, *, enabled=True, tags=None, comment=None, etag="e1", expiry=None):
    return HiveRecord(name=data["rule"]["id"], data=data, enabled=enabled, tags=tags,
                      comment=comment, etag=etag, expiry=expiry)


def _status(rule_id, state, installed=None, pack=2):
    return {"id": rule_id, "pack_version_of_rule": pack, "installed_version": installed, "state": state}


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
        statuses = {"rules": [_status("lc.a", "new", None, 2), _status("lc.b", "new", None, 1)]}
        with patch.object(HostPosture, "default_pack", return_value=pack), \
             patch.object(HostPosture, "pack_status", return_value=statuses) as ps, \
             patch.object(HostPosture, "_rules", return_value=hive):
            hive.get.return_value = _stored(_rec("lc.a", 1), tags=["org-tag"], comment="our note",
                                            enabled=False, expiry=123)
            hive.get.return_value.ui_actions = [{"name": "x"}]
            yield hp_, hive, statuses, ps

    def _states(self, statuses, state, installed=1):
        statuses["rules"] = [_status("lc.a", state, installed), _status("lc.b", state, installed, 1)]

    def test_creates_new_rules_create_only_enabled_with_the_extensions_digest(self, env):
        hp_, hive, _, _ = env
        result = hp_.install_default_pack()
        assert [c["id"] for c in result["created"]] == ["lc.a", "lc.b"]
        assert not (result["updated"] or result["skipped"] or result["failed"])
        record = hive.set.call_args_list[0][0][0]
        assert record.etag == hp._CREATE_ONLY_ETAG
        assert record.enabled is True
        assert record.name == "lc.a" and record.data == _rec("lc.a", 2)
        # the digest is written exactly as the extension returned it
        assert record.tags == [DEFAULT_PACK_TAG, PACK_DIGEST_TAG_PREFIX + "digest-lc.a-2"]
        assert record.comment == "LimaCharlie default pack 1"
        hive.get.assert_not_called()

    def test_no_digest_is_computed_here(self):
        assert not hasattr(hp, "record_digest")

    def test_disabled_and_id_filter(self, env):
        hp_, hive, _, _ = env
        result = hp_.install_default_pack(["lc.b"], enabled=False)
        assert [c["id"] for c in result["created"]] == ["lc.b"]
        assert hive.set.call_args[0][0].enabled is False

    def test_unknown_id_is_refused_before_any_write(self, env):
        hp_, hive, _, ps = env
        with pytest.raises(ValidationError, match="lc.zzz"):
            hp_.install_default_pack(["lc.zzz"])
        hive.set.assert_not_called()

    def test_empty_pack_is_refused(self, org):
        with patch.object(HostPosture, "default_pack", return_value={"rules": []}):
            with pytest.raises(ValidationError):
                HostPosture(org).install_default_pack()

    def test_dry_run_writes_nothing(self, env):
        hp_, hive, _, _ = env
        result = hp_.install_default_pack(dry_run=True)
        assert len(result["created"]) == 2 and result["dry_run"] is True
        hive.set.assert_not_called()

    def test_current_is_up_to_date(self, env):
        hp_, hive, st, _ = env
        self._states(st, "current", 2)
        result = hp_.install_default_pack(update=True, force=True)
        assert {s["reason"] for s in result["skipped"]} == {"already up to date"}
        hive.set.assert_not_called()

    def test_update_available_is_skipped_without_update(self, env):
        hp_, hive, st, _ = env
        self._states(st, "update_available")
        result = hp_.install_default_pack(["lc.a"])
        assert result["skipped"][0]["update_available"] is True
        assert result["skipped"][0]["installed_version"] == 1
        hive.set.assert_not_called()

    def test_update_replaces_keeping_org_state(self, env):
        hp_, hive, st, _ = env
        self._states(st, "update_available")
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert result["updated"] == [{"id": "lc.a", "state": "update_available", "from_version": 1, "to_version": 2}]
        record = hive.set.call_args[0][0]
        assert record.etag == "e1"  # conditional on what was read
        assert record.data == _rec("lc.a", 2)
        assert record.enabled is False and record.expiry == 123
        assert record.comment == "our note"
        assert record.ui_actions == [{"name": "x"}]
        assert "org-tag" in record.tags
        digests = [t for t in record.tags if t.startswith(PACK_DIGEST_TAG_PREFIX)]
        assert digests == [PACK_DIGEST_TAG_PREFIX + "digest-lc.a-2"]

    def test_update_replaces_a_pack_comment_with_the_new_one(self, env):
        hp_, hive, st, _ = env
        self._states(st, "update_available")
        hive.get.return_value.comment = "LimaCharlie default pack 0"
        hp_.install_default_pack(["lc.a"], update=True)
        assert hive.set.call_args[0][0].comment == "LimaCharlie default pack 1"

    @pytest.mark.parametrize("state", ["edited", "org_newer"])
    def test_edited_and_org_newer_need_force(self, env, state):
        hp_, hive, st, _ = env
        self._states(st, state)
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "--force" in result["skipped"][0]["reason"]
        hive.set.assert_not_called()
        result = hp_.install_default_pack(["lc.a"], force=True)
        assert result["updated"][0]["state"] == state
        assert hive.set.call_args[0][0].etag == "e1"

    def test_force_does_not_recreate_or_touch_current(self, env):
        hp_, hive, st, _ = env
        self._states(st, "current", 2)
        hp_.install_default_pack(force=True)
        hive.set.assert_not_called()

    def test_etag_conflict_on_update_is_skipped_not_failed(self, env):
        hp_, hive, st, _ = env
        self._states(st, "update_available")
        hive.set.side_effect = ApiError("etag", status_code=409)
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "changed while updating" in result["skipped"][0]["reason"]
        assert "state_now" in result["skipped"][0]
        assert not result["failed"]

    def test_edit_between_pack_status_and_the_read_is_not_overwritten(self, env):
        hp_, hive, st, ps = env
        self._states(st, "update_available")
        edited = {"rules": [_status("lc.a", "edited", 1)]}
        ps.side_effect = [dict(st), edited]  # initial read, then the check after hive.get
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert result["skipped"][0]["state_now"] == "edited"
        assert "changed while installing" in result["skipped"][0]["reason"]
        assert not result["updated"]
        hive.set.assert_not_called()

    def test_state_that_cannot_be_rechecked_blocks_the_write(self, env):
        hp_, hive, st, ps = env
        self._states(st, "update_available")
        ps.side_effect = [dict(st), ApiError("down", status_code=500)]
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert result["skipped"][0]["state_now"] is None
        hive.set.assert_not_called()

    def test_force_also_rechecks(self, env):
        hp_, hive, st, ps = env
        self._states(st, "edited")
        ps.side_effect = [dict(st), {"rules": [_status("lc.a", "current", 2)]}]
        result = hp_.install_default_pack(["lc.a"], force=True)
        assert result["skipped"][0]["state_now"] == "current"
        hive.set.assert_not_called()

    def test_record_deleted_between_status_and_update_is_skipped(self, env):
        hp_, hive, st, _ = env
        self._states(st, "update_available")
        hive.get.side_effect = _not_found()
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert "deleted while installing" in result["skipped"][0]["reason"]
        hive.set.assert_not_called()

    def test_record_created_concurrently_is_skipped_and_the_new_state_reported(self, env):
        hp_, hive, st, ps = env
        hive.set.side_effect = ApiError("ETAG_MISMATCH", status_code=400)
        ps.side_effect = [dict(st), {"rules": [_status("lc.a", "edited", 3)]}]
        result = hp_.install_default_pack(["lc.a"])
        assert "created while installing" in result["skipped"][0]["reason"]
        assert result["skipped"][0]["state_now"] == "edited"
        assert ps.call_count == 2
        assert not result["created"] and not result["failed"]

    def test_state_now_is_none_when_pack_status_cannot_be_read(self, env):
        hp_, hive, st, ps = env
        hive.set.side_effect = ApiError("ETAG_MISMATCH", status_code=400)
        ps.side_effect = [dict(st), ApiError("down", status_code=500)]
        result = hp_.install_default_pack(["lc.a"])
        assert result["skipped"][0]["state_now"] is None

    def test_failure_is_reported_and_the_rest_continues(self, env):
        hp_, hive, _, _ = env
        hive.set.side_effect = [ApiError("bad rule: probes.x", status_code=400), {}]
        result = hp_.install_default_pack()
        assert result["failed"][0]["id"] == "lc.a" and "probes.x" in result["failed"][0]["error"]
        assert [c["id"] for c in result["created"]] == ["lc.b"]

    def test_a_read_failure_other_than_not_found_is_a_failure(self, env):
        hp_, hive, st, _ = env
        self._states(st, "update_available")
        hive.get.side_effect = ApiError("denied", status_code=403)
        result = hp_.install_default_pack(["lc.a"], update=True)
        assert result["failed"][0]["id"] == "lc.a"
        hive.set.assert_not_called()

    def test_entry_without_digest_fails_that_rule_only(self, env):
        hp_, hive, _, _ = env
        pack = {"pack_version": "1", "rules": [{**_entry("lc.a", 2), "digest": ""}, _entry("lc.b", 1)]}
        with patch.object(HostPosture, "default_pack", return_value=pack):
            result = hp_.install_default_pack()
        assert "digest" in result["failed"][0]["error"]
        assert [c["id"] for c in result["created"]] == ["lc.b"]

    def test_rule_missing_from_pack_status_fails_that_rule_only(self, env):
        hp_, hive, st, _ = env
        st["rules"] = [_status("lc.b", "new", None, 1)]
        result = hp_.install_default_pack()
        assert result["failed"][0]["id"] == "lc.a"
        assert [c["id"] for c in result["created"]] == ["lc.b"]

    def test_unknown_state_fails_the_rule(self, env):
        hp_, hive, st, _ = env
        st["rules"] = [_status("lc.a", "weird"), _status("lc.b", "new", None, 1)]
        result = hp_.install_default_pack()
        assert "weird" in result["failed"][0]["error"]
        hive.set.assert_called_once()
