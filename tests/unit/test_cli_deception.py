"""CLI tests for the deception group (the ext-deception extension and its config record).

The commands run through the real SDK layer; only the extension request and the
hive are mocked, so each test checks the exact request the extension receives.
"""

from __future__ import annotations

import base64
import os
import stat
import hashlib
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.discovery import get_explain
from limacharlie.errors import ApiError
from limacharlie.sdk.hive import HiveRecord


def run(args, input=None):
    return CliRunner().invoke(cli, ["--output", "json"] + args, input=input)


@pytest.fixture
def ext():
    """The extension request: ``ext.calls`` lists (action, data); ``ext.answers`` maps action -> answer."""
    with patch("limacharlie.commands.deception.Client"), \
         patch("limacharlie.commands.deception.Organization"), \
         patch("limacharlie.sdk.deception.Extensions") as ext_cls:
        state = MagicMock()
        state.calls = []
        state.answers = {}

        def request(name, action, data=None, unwrap=False):
            assert name == "ext-deception" and unwrap is True
            state.calls.append((action, data))
            answer = state.answers.get(action, {})
            return answer(data) if callable(answer) else answer

        ext_cls.return_value.request.side_effect = request
        yield state


@pytest.fixture
def hive():
    with patch("limacharlie.commands.deception.Client"), \
         patch("limacharlie.commands.deception.Organization"), \
         patch("limacharlie.sdk.deception.Hive") as hive_cls:
        mock_hive = MagicMock()
        mock_hive.set.return_value = {"success": True}
        hive_cls.return_value = mock_hive
        yield hive_cls, mock_hive


class TestRequests:
    def test_list_hits_maps_flags_to_the_extension_fields(self, ext):
        result = run([
            "deception", "list-hits", "--since", "1764000000", "--layer", "use",
            "--event-type", "deception_hit", "--event-type", "deception_drop_hit",
            "--auto-response-outcome", "capped", "--auto-response-outcome", "not_isolated",
            "--group", "--page-size", "50",
        ])
        assert result.exit_code == 0, result.output
        assert ext.calls == [("list_hits", {
            "since": 1764000000, "layer": "use", "group": True,
            "event_types": ["deception_hit", "deception_drop_hit"],
            "auto_response_outcome": "capped,not_isolated", "page_size": 50,
        })]

    def test_list_hits_one_event_type_uses_the_single_field(self, ext):
        assert run(["deception", "list-hits", "--event-type", "deception_coverage_warning"]).exit_code == 0
        assert ext.calls == [("list_hits", {"event_type": "deception_coverage_warning"})]

    def test_list_hits_refuses_milliseconds(self, ext):
        result = run(["deception", "list-hits", "--since", "1764000000000"])
        assert result.exit_code != 0 and "milliseconds" in result.output
        assert ext.calls == []

    def test_page_size_is_bounded_by_the_extension_limit(self, ext):
        assert run(["deception", "list", "--page-size", "501"]).exit_code != 0
        assert ext.calls == []

    def test_list_sends_states_and_flags_only_when_set(self, ext):
        result = run(["deception", "list", "--state", "failed", "--exclude-skipped", "--summary",
                      "--page-token", "t1"])
        assert result.exit_code == 0, result.output
        assert ext.calls == [("list", {
            "states": ["failed"], "exclude_skipped": True, "summary": True, "page_token": "t1",
        })]

    def test_decoy_operations_combine_scopes(self, ext):
        assert run(["deception", "rotate", "--template", "kubeconfig-backup", "--sid", "s1"]).exit_code == 0
        assert run(["deception", "verify", "--instance-id", "i1", "--instance-id", "i2"]).exit_code == 0
        assert ext.calls == [
            ("rotate", {"sid": "s1", "template": "kubeconfig-backup"}),
            ("verify", {"instance_ids": ["i1", "i2"]}),
        ]

    def test_remove_needs_confirm(self, ext):
        assert run(["deception", "remove", "--policy", "p"]).exit_code != 0
        assert ext.calls == []
        assert run(["deception", "remove", "--policy", "p", "--confirm"]).exit_code == 0
        assert ext.calls == [("remove", {"policy": "p"})]

    def test_deploy_apply_pack(self, ext):
        result = run(["deception", "deploy", "--apply-pack", "deception-alert",
                      "--apply-pack", "deception-respond"])
        assert result.exit_code == 0, result.output
        assert ext.calls == [("deploy", {"apply_pack": ["deception-alert", "deception-respond"]})]

    def test_plan_draft_reads_the_files(self, ext, tmp_path):
        policy = tmp_path / "p.yaml"
        policy.write_text("name: draft\ntargeting: {platforms: [linux]}\n")
        templates = tmp_path / "t.yaml"
        templates.write_text("- {name: kb, kind: file, spec: {}}\n")
        result = run(["deception", "plan", "--draft-policy", str(policy), "--draft-templates", str(templates)])
        assert result.exit_code == 0, result.output
        assert ext.calls == [("plan", {
            "draft_policy": {"name": "draft", "targeting": {"platforms": ["linux"]}},
            "draft_templates": [{"name": "kb", "kind": "file", "spec": {}}],
        })]

    def test_plan_draft_templates_need_a_policy_and_a_list(self, ext, tmp_path):
        templates = tmp_path / "t.yaml"
        templates.write_text("name: not-a-list\n")
        assert run(["deception", "plan", "--draft-templates", str(templates)]).exit_code != 0
        policy = tmp_path / "p.yaml"
        policy.write_text("name: draft\n")
        assert run(["deception", "plan", "--draft-policy", str(policy),
                    "--draft-templates", str(templates)]).exit_code != 0
        assert ext.calls == []

    def test_uninstall_confirm_and_flags(self, ext):
        assert run(["deception", "uninstall"]).exit_code != 0
        assert run(["deception", "uninstall", "--force", "--cancel", "--confirm"]).exit_code != 0
        assert ext.calls == []
        assert run(["deception", "uninstall", "--cancel"]).exit_code == 0
        assert run(["deception", "uninstall", "--force", "--confirm"]).exit_code == 0
        assert run(["deception", "uninstall-status"]).exit_code == 0
        assert ext.calls == [("uninstall", {"cancel": True}), ("uninstall", {"force": True}),
                             ("uninstall_status", {})]

    def test_restore_rules_exits_1_when_a_rule_was_not_restored(self, ext):
        ext.answers["restore_rules"] = {"rules": [
            {"name": "deception-alert", "restored": True, "enabled": True},
            {"name": "deception-respond", "restored": False, "code": "write_failed"},
        ]}
        result = run(["deception", "restore-rules", "--rule", "deception-alert", "--rule", "deception-respond"])
        assert result.exit_code == 1
        assert ext.calls == [("restore_rules", {"rules": ["deception-alert", "deception-respond"]})]


class TestDrops:
    def test_create_document_merges_file_and_flags(self, ext, tmp_path):
        doc = tmp_path / "doc.yaml"
        doc.write_text("title: From file\nauthor: Ops\n")
        result = run([
            "deception", "drops", "create", "--form", "document", "--format", "docx",
            "--label", "HR share", "--document-file", str(doc), "--title", "Salary review",
            "--line", "first", "--line", "",
        ])
        assert result.exit_code == 0, result.output
        assert ext.calls == [("create_drop", {
            "form": "document", "label": "HR share", "format": "docx",
            "document": {"title": "Salary review", "author": "Ops", "lines": ["first", ""]},
        })]

    def test_save_writes_the_verified_document(self, ext, tmp_path):
        content = b"PK\x03\x04 a docx"
        ext.answers["create_drop"] = {"drop": {"id": "d1"}, "paste": {"document": {
            "content_b64": base64.b64encode(content).decode(),
            "sha256": hashlib.sha256(content).hexdigest(),
        }}}
        out = tmp_path / "offer.docx"
        result = run(["deception", "drops", "create", "--form", "document", "--label", "x", "--save", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_bytes() == content

    def test_save_refuses_a_document_that_does_not_match_its_hash_but_prints_the_answer(self, ext, tmp_path):
        ext.answers["create_drop"] = {"drop": {"id": "d1"}, "paste": {"document": {
            "content_b64": base64.b64encode(b"abc").decode(), "sha256": "00" * 32,
        }}}
        out = tmp_path / "offer.docx"
        result = run(["deception", "drops", "create", "--form", "document", "--label", "x", "--save", str(out)])
        assert result.exit_code != 0
        assert '"d1"' in result.output  # the drop exists: its answer must still reach the operator
        assert not out.exists()

    def test_save_writes_the_qr_svg_and_refuses_a_url(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {}, "paste": {"url": "https://x", "qr_svg": "<svg/>"}}
        out = tmp_path / "qr.svg"
        assert run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(out)]).exit_code == 0
        assert out.read_text() == "<svg/>"
        ext.answers["get_drop"] = {"drop": {}, "paste": {"url": "https://x"}}
        assert run(["deception", "drops", "get", "--name", "n", "--save", str(tmp_path / "u")]).exit_code != 0

    def test_get_needs_exactly_one_selector(self, ext):
        assert run(["deception", "drops", "get"]).exit_code != 0
        assert run(["deception", "drops", "get", "--drop-id", "d", "--name", "n"]).exit_code != 0
        assert ext.calls == []

    def test_update_reads_the_version_when_not_given_and_sends_clears(self, ext):
        ext.answers["get_drop"] = {"drop": {"id": "d1", "version": 7}, "paste": {}}
        result = run(["deception", "drops", "update", "--drop-id", "d1", "--redirect-url", "",
                      "--state", "disabled"])
        assert result.exit_code == 0, result.output
        assert ext.calls == [
            ("get_drop", {"drop_id": "d1"}),
            ("update_drop", {"drop_id": "d1", "version": 7, "state": "disabled", "redirect_url": ""}),
        ]

    def test_update_reset_document(self, ext):
        assert run(["deception", "drops", "update", "--drop-id", "d1", "--version", "3",
                    "--reset-document", "--title", "t"]).exit_code != 0
        assert run(["deception", "drops", "update", "--drop-id", "d1", "--version", "3",
                    "--reset-document"]).exit_code == 0
        assert ext.calls == [("update_drop", {"drop_id": "d1", "version": 3, "document": {}})]

    def test_rotate_with_version_does_not_read(self, ext):
        assert run(["deception", "drops", "rotate", "--drop-id", "d1", "--version", "2"]).exit_code == 0
        assert ext.calls == [("rotate_drop", {"drop_id": "d1", "version": 2})]

    def test_delete_needs_confirm(self, ext):
        assert run(["deception", "drops", "delete", "--drop-id", "d1"]).exit_code != 0
        assert ext.calls == []
        assert run(["deception", "drops", "delete", "--drop-id", "d1", "--confirm"]).exit_code == 0
        assert ext.calls == [("delete_drop", {"drop_id": "d1"})]


def _missing(*_args):
    raise ApiError("not found", status_code=400,
                   response_body={"error": "lc_error_code:RECORD_NOT_FOUND - ext-deception"})


def _stored(enabled=True, tags=None, etag="e-now"):
    return HiveRecord(name="ext-deception", enabled=enabled, tags=tags, comment="kept", etag=etag)


class TestConfig:
    def test_new_record_is_created_enabled_and_create_only(self, hive, tmp_path):
        hive_cls, mock_hive = hive
        mock_hive.get_metadata.side_effect = _missing
        cfg = tmp_path / "deception.yaml"
        cfg.write_text("schema_version: 1\npolicies: []\n")
        result = run(["deception", "config", "set", "--input-file", str(cfg)])
        assert result.exit_code == 0, result.output
        assert hive_cls.call_args[0][1] == "extension_config"
        record = mock_hive.set.call_args[0][0]
        assert record.name == "ext-deception"
        assert record.data == {"schema_version": 1, "policies": []}
        assert record.enabled is True
        assert record.etag and record.etag.startswith("create-only")

    def test_new_record_disabled_on_request(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.side_effect = _missing
        assert run(["deception", "config", "set", "--disabled"], input="schema_version: 1\n").exit_code == 0
        assert mock_hive.set.call_args[0][0].enabled is False

    def test_existing_record_keeps_its_metadata(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.return_value = _stored(enabled=False, tags=["t"])
        result = run(["deception", "config", "set"], input="schema_version: 1\n")
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        # Data only: nothing in usr_mtd is sent, so the hive keeps the stored metadata.
        assert record.enabled is None and record.tags is None and record.comment is None
        assert record.etag is None

    def test_enabled_flag_keeps_the_other_metadata_conditionally(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.return_value = _stored(enabled=False, tags=["t"], etag="e-now")
        assert run(["deception", "config", "set", "--enabled"], input="schema_version: 1\n").exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is True and record.tags == ["t"] and record.comment == "kept"
        # The metadata block replaces the stored one, so it is written only if
        # nothing changed since it was read.
        assert record.etag == "e-now"

    def test_record_input_round_trips_with_its_etag(self, hive):
        _, mock_hive = hive
        rec = HiveRecord(name="ext-deception", data={"schema_version": 1}, enabled=True,
                         tags=["iac"], etag="e1")
        mock_hive.get.return_value = rec
        mock_hive.get_metadata.return_value = _stored(etag="e1")
        got = run(["deception", "config", "get", "--output", "yaml"])
        assert got.exit_code == 0, got.output

        result = run(["deception", "config", "set"], input=got.output)
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.data == {"schema_version": 1}
        assert record.etag == "e1"
        assert record.enabled is True and record.tags == ["iac"]

    def test_round_trip_of_a_deleted_record_is_refused(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.side_effect = _missing
        body = "data: {schema_version: 1}\nusr_mtd: {enabled: true}\nsys_mtd: {etag: e1}\n"
        result = run(["deception", "config", "set"], input=body)
        assert result.exit_code != 0
        mock_hive.set.assert_not_called()

    def test_record_input_without_etag_creates_only(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.side_effect = _missing
        body = "data: {schema_version: 1}\nusr_mtd: {enabled: true}\n"
        assert run(["deception", "config", "set"], input=body).exit_code == 0
        assert mock_hive.set.call_args[0][0].etag.startswith("create-only")

    def test_no_etag_overwrites(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.return_value = _stored()
        body = "data: {schema_version: 1}\nsys_mtd: {etag: e1}\n"
        assert run(["deception", "config", "set", "--no-etag"], input=body).exit_code == 0
        assert mock_hive.set.call_args[0][0].etag is None

    def test_etag_of_a_deleted_record_is_refused(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.side_effect = _missing
        result = run(["deception", "config", "set", "--etag", "e1"], input="schema_version: 1\n")
        assert result.exit_code != 0
        mock_hive.set.assert_not_called()

    def test_metadata_read_failure_is_not_taken_for_a_missing_record(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.side_effect = ApiError("denied", status_code=403)
        assert run(["deception", "config", "set"], input="schema_version: 1\n").exit_code != 0
        mock_hive.set.assert_not_called()

    def test_enable_writes_metadata_only(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.return_value = HiveRecord(name="ext-deception", enabled=False, tags=["t"])
        assert run(["deception", "config", "enable"]).exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.data is None and record.enabled is True and record.tags == ["t"]


class TestMoreRequests:
    """Flag-to-field mapping of the commands not covered above."""

    @pytest.mark.parametrize("args, action, data", [
        (["list-hosts", "--status", "failed", "--sort", "problems", "--include-deleted", "--summary"],
         "list_hosts", {"status": "failed", "sort": "problems", "include_deleted": True, "summary": True}),
        (["list-readers", "--days", "7", "--platform", "linux", "--template", "kb"],
         "list_readers", {"days": 7, "platform": "linux", "template": "kb"}),
        (["list-test-runs", "--layer", "use", "--state", "pending"],
         "list_test_runs", {"layer": "use", "state": "pending"}),
        (["list-test-paths", "--state", "testable", "--policy", "p"],
         "list_test_paths", {"state": "testable", "policy": "p"}),
        (["coverage", "--policy", "p"], "coverage", {"policy": "p"}),
        (["test-fire", "--drop-id", "d1"], "test_fire", {"drop_id": "d1"}),
        (["kinds"], "list_kinds", {}),
        (["rollout-status"], "rollout_status", {}),
        (["drops", "list", "--form", "url", "--form", "qr", "--state", "deleted", "--managed-by", "api",
          "--last-hit", "not_since", "--last-hit-since", "2026-11-01T00:00:00Z", "--sort", "last_hit"],
         "list_drops", {"forms": ["url", "qr"], "states": ["deleted"], "managed_by": "api",
                        "last_hit": "not_since", "last_hit_since": "2026-11-01T00:00:00Z", "sort": "last_hit"}),
        (["drops", "draft-document", "--format", "svg", "--title", "t"],
         "draft_drop_document", {"format": "svg", "document": {"title": "t"}}),
    ])
    def test_mapping(self, ext, args, action, data):
        result = run(["deception"] + args)
        assert result.exit_code == 0, result.output
        assert ext.calls == [(action, data)]

    def test_restore_rules_fails_when_the_read_back_failed(self, ext):
        ext.answers["restore_rules"] = {"rules": [
            {"name": "deception-respond", "restored": True, "enabled": False, "error": "read back failed"},
        ]}
        assert run(["deception", "restore-rules", "--rule", "deception-respond"]).exit_code == 1

    def test_empty_draft_policy_is_refused(self, ext, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        assert run(["deception", "plan", "--draft-policy", str(empty)]).exit_code != 0
        assert ext.calls == []

    def test_save_with_a_url_drop_is_refused_before_creating(self, ext, tmp_path):
        result = run(["deception", "drops", "create", "--form", "url", "--label", "x",
                      "--save", str(tmp_path / "f")])
        assert result.exit_code != 0
        assert ext.calls == []

    def test_save_into_a_missing_folder_is_a_clean_error(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1"}, "paste": {"qr_svg": "<svg/>"}}
        result = run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(tmp_path / "no" / "f.svg")])
        assert result.exit_code == 1
        assert "nothing was written" in result.output and "Traceback" not in result.output


class TestFollowUps:
    @pytest.mark.parametrize("rows, code", [
        ([{"name": "a", "restored": True, "enabled": True}, {"name": "b", "restored": True, "enabled": True}], 0),
        ([{"name": "a", "restored": True, "enabled": False}], 1),
        ([{"name": "a", "restored": True, "enabled": True, "error": "read back failed"}], 1),
        ([{"name": "a", "restored": False, "enabled": True, "code": "write_failed"}], 1),
        ([], 1),
    ])
    def test_restore_rules_exit_code(self, ext, rows, code):
        ext.answers["restore_rules"] = {"rules": rows}
        assert run(["deception", "restore-rules", "--rule", "a"]).exit_code == code

    def test_rotate_save_of_a_url_drop_is_refused_before_rotating(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1", "form": "url", "version": 4}, "paste": {}}
        result = run(["deception", "drops", "rotate", "--drop-id", "d1", "--save", str(tmp_path / "f")])
        assert result.exit_code != 0
        assert [a for a, _ in ext.calls] == ["get_drop"]

    def test_rotate_save_uses_the_version_it_read(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1", "form": "qr", "version": 4}, "paste": {}}
        ext.answers["rotate_drop"] = {"drop": {"id": "d1"}, "paste": {"qr_svg": "<svg/>"}}
        out = tmp_path / "qr.svg"
        assert run(["deception", "drops", "rotate", "--drop-id", "d1", "--save", str(out)]).exit_code == 0
        assert ext.calls == [("get_drop", {"drop_id": "d1"}), ("rotate_drop", {"drop_id": "d1", "version": 4})]
        assert out.read_text() == "<svg/>"

    def test_save_writes_like_a_plain_write(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1"}, "paste": {"qr_svg": "<svg/>"}}
        new = tmp_path / "new.svg"
        old_umask = os.umask(0o022)
        try:
            assert run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(new)]).exit_code == 0
        finally:
            os.umask(old_umask)
        assert stat.S_IMODE(new.stat().st_mode) == 0o644

        # An existing file is rewritten in place: same inode, so its owner,
        # group, mode and ACLs stay as they were.
        existing = tmp_path / "shared.svg"
        existing.write_text("old")
        existing.chmod(0o660)
        inode = existing.stat().st_ino
        assert run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(existing)]).exit_code == 0
        assert existing.stat().st_ino == inode
        assert stat.S_IMODE(existing.stat().st_mode) == 0o660 and existing.read_text() == "<svg/>"

    def test_save_through_a_symlink_writes_its_target(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1"}, "paste": {"qr_svg": "<svg/>"}}
        target = tmp_path / "real.svg"
        target.write_text("old")
        link = tmp_path / "link.svg"
        link.symlink_to(target)
        assert run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(link)]).exit_code == 0
        assert link.is_symlink() and target.read_text() == "<svg/>"

    def test_a_failed_write_of_a_new_file_leaves_nothing(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1"}, "paste": {"qr_svg": "<svg/>"}}
        out = tmp_path / "qr.svg"
        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            real = real_open(path, mode, *args, **kwargs)  # the file is really created
            wrapper = MagicMock()
            wrapper.__enter__.return_value = wrapper
            wrapper.__exit__.side_effect = lambda *a: real.close()
            wrapper.write.side_effect = OSError("disk full")
            return wrapper

        with patch("limacharlie.commands.deception.open", side_effect=fake_open, create=True):
            result = run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(out)])
        assert result.exit_code == 1 and "nothing was written" in result.output
        assert not out.exists()

    def test_a_failed_rewrite_says_the_file_may_be_incomplete(self, ext, tmp_path):
        ext.answers["get_drop"] = {"drop": {"id": "d1"}, "paste": {"qr_svg": "<svg/>"}}
        out = tmp_path / "qr.svg"
        out.write_text("old")
        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            if mode == "wb":
                raise OSError("disk full")
            return real_open(path, mode, *args, **kwargs)

        with patch("limacharlie.commands.deception.open", side_effect=fake_open, create=True):
            result = run(["deception", "drops", "get", "--drop-id", "d1", "--save", str(out)])
        assert result.exit_code == 1 and "may be incomplete" in result.output
        assert "Traceback" not in result.output

class TestTableOutput:
    def test_a_list_shows_its_rows_and_the_whole_page_token(self, ext):
        token = "t" * 300
        ext.answers["list"] = {"instances": [{"id": "i1", "state": "verified"}, {"id": "i2", "state": "failed"}],
                               "next_page_token": token}
        result = CliRunner().invoke(cli, ["--output", "table", "deception", "list"])
        assert result.exit_code == 0, result.output
        assert "i2" in result.output and "[2 items]" not in result.output
        assert token in result.output

    def test_a_drop_paste_is_printed_whole(self, ext):
        url = "https://example.invalid/" + "a" * 200
        ext.answers["get_drop"] = {"drop": {"id": "d1"}, "paste": {"url": url}}
        result = CliRunner().invoke(cli, ["--output", "table", "deception", "drops", "get", "--drop-id", "d1"])
        assert result.exit_code == 0, result.output
        assert url in result.output


def _leaves(cmd, prefix):
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            yield from _leaves(sub, prefix + [name])
    else:
        yield prefix


def test_every_command_has_ai_help():
    from limacharlie.commands.deception import group

    missing = [".".join(p) for p in _leaves(group, ["deception"]) if get_explain(".".join(p)) is None]
    assert not missing, f"commands without an --ai-help text: {missing}"
