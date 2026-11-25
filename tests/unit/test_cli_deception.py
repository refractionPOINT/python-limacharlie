"""CLI tests for the deception group (the ext-deception extension and its config record).

The commands run through the real SDK layer; only the extension request and the
hive are mocked, so each test checks the exact request the extension receives.
"""

from __future__ import annotations

import base64
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


def _existing(enabled=True, tags=None):
    """merge_current_metadata of a stored record."""
    def merge(record):
        record.enabled = enabled
        record.tags = tags
        record.comment = "kept"
        return True
    return merge


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


class TestConfig:
    def test_new_record_is_created_enabled_and_create_only(self, hive, tmp_path):
        hive_cls, mock_hive = hive
        mock_hive.merge_current_metadata.return_value = False
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

    def test_new_record_disabled_on_request(self, hive, tmp_path):
        _, mock_hive = hive
        mock_hive.merge_current_metadata.return_value = False
        cfg = tmp_path / "c.yaml"
        cfg.write_text("schema_version: 1\n")
        assert run(["deception", "config", "set", "--input-file", str(cfg), "--disabled"]).exit_code == 0
        assert mock_hive.set.call_args[0][0].enabled is False

    def test_existing_record_keeps_its_metadata(self, hive):
        _, mock_hive = hive
        mock_hive.merge_current_metadata.side_effect = _existing(enabled=False, tags=["t"])
        result = run(["deception", "config", "set"], input="schema_version: 1\n")
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        # Data only: nothing in usr_mtd is sent, so the hive keeps the stored metadata.
        assert record.enabled is None and record.tags is None and record.comment is None
        assert record.etag is None

    def test_enabled_flag_on_existing_record_keeps_the_other_metadata(self, hive):
        _, mock_hive = hive
        mock_hive.merge_current_metadata.side_effect = _existing(enabled=False, tags=["t"])
        assert run(["deception", "config", "set", "--enabled"], input="schema_version: 1\n").exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.enabled is True and record.tags == ["t"] and record.comment == "kept"

    def test_record_input_round_trips_with_its_etag(self, hive):
        _, mock_hive = hive
        rec = HiveRecord(name="ext-deception", data={"schema_version": 1}, enabled=True,
                         tags=["iac"], etag="e1")
        mock_hive.get.return_value = rec
        got = run(["deception", "config", "get", "--output", "yaml"])
        assert got.exit_code == 0, got.output

        result = run(["deception", "config", "set"], input=got.output)
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.data == {"schema_version": 1}
        assert record.etag == "e1"
        assert record.enabled is True and record.tags == ["iac"]
        mock_hive.merge_current_metadata.assert_not_called()

    def test_no_etag_overwrites(self, hive):
        _, mock_hive = hive
        mock_hive.merge_current_metadata.side_effect = _existing()
        body = "data: {schema_version: 1}\nsys_mtd: {etag: e1}\n"
        assert run(["deception", "config", "set", "--no-etag"], input=body).exit_code == 0
        assert mock_hive.set.call_args[0][0].etag is None

    def test_etag_of_a_deleted_record_is_refused(self, hive):
        _, mock_hive = hive
        mock_hive.merge_current_metadata.return_value = False
        result = run(["deception", "config", "set", "--etag", "e1"], input="schema_version: 1\n")
        assert result.exit_code != 0
        mock_hive.set.assert_not_called()

    def test_stale_etag_is_reported(self, hive):
        _, mock_hive = hive
        mock_hive.merge_current_metadata.side_effect = _existing()
        mock_hive.set.side_effect = ApiError("ETAG_MISMATCH", status_code=409)
        result = run(["deception", "config", "set", "--etag", "old"], input="schema_version: 1\n")
        assert result.exit_code != 0

    def test_enable_writes_metadata_only(self, hive):
        _, mock_hive = hive
        mock_hive.get_metadata.return_value = HiveRecord(name="ext-deception", enabled=False, tags=["t"])
        assert run(["deception", "config", "enable"]).exit_code == 0
        record = mock_hive.set.call_args[0][0]
        assert record.data is None and record.enabled is True and record.tags == ["t"]


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
