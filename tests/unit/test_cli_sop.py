"""CLI tests for the sop shortcut group.

The point of these is ``sop list --brief``. The hive listing endpoint
returns whole records, so listing an org's SOPs pulls back every
procedure body in full. ``--brief`` reduces each record's data to the
fields that identify it, so a caller can decide what to fetch without
paying for all of it -- the flow every SOP-reading agent follows.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli


def _record(data):
    rec = MagicMock()
    rec.to_dict.return_value = {
        "data": data,
        "usr_mtd": {"enabled": True, "tags": ["ir"]},
        "sys_mtd": {"etag": "e1"},
    }
    return rec


class TestSopList:
    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_list_returns_full_records_by_default(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {
            "ransomware": _record({"text": "1. Isolate.", "description": "Ransomware"}),
        }
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "sop", "list"])
        assert result.exit_code == 0, result.output
        assert mock_hive_cls.call_args[0][1] == "sop"
        data = json.loads(result.output)["ransomware"]["data"]
        # Unchanged default: the body is still there for existing callers.
        assert data == {"text": "1. Isolate.", "description": "Ransomware"}

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_brief_drops_body_and_keeps_metadata(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {
            "ransomware": _record({"text": "1. Isolate." * 500, "description": "Ransomware"}),
            "after-hours": _record({"text": "Page on-call.", "description": "Escalation"}),
        }
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "sop", "list", "--brief"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)

        # Every SOP still listed, each reduced to its description.
        assert set(parsed) == {"ransomware", "after-hours"}
        assert parsed["ransomware"]["data"] == {"description": "Ransomware"}
        assert parsed["after-hours"]["data"] == {"description": "Escalation"}
        # Metadata is what tells you whether an SOP is active, so it stays.
        assert parsed["ransomware"]["usr_mtd"] == {"enabled": True, "tags": ["ir"]}
        assert parsed["ransomware"]["sys_mtd"] == {"etag": "e1"}

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_brief_tolerates_records_without_a_description(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {"bare": _record({"text": "body only"})}
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "sop", "list", "--brief"])
        assert result.exit_code == 0, result.output
        # description is optional on an SOP; the record must survive without one
        # rather than KeyError-ing or leaking the body back in.
        assert json.loads(result.output)["bare"]["data"] == {}

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_brief_fails_closed_on_a_non_object_payload(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {
            "listy": _record(["body", "parts"]),
            "stringy": _record("raw body"),
            "empty": _record(None),
        }
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "sop", "list", "--brief"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        # A payload that is not an object has none of the index fields. Passing
        # it through would hand back the very content --brief exists to drop.
        assert parsed["listy"]["data"] == {}
        assert parsed["stringy"]["data"] == {}
        # No payload at all is a different thing from a filtered one.
        assert parsed["empty"]["data"] is None

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_brief_applies_to_yaml_output(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {
            "ransomware": _record({"text": "SECRET BODY", "description": "Ransomware"}),
        }
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "yaml", "sop", "list", "--brief"])
        assert result.exit_code == 0, result.output
        # Filtering happens before rendering, so it must hold for every format.
        assert "SECRET BODY" not in result.output
        assert "Ransomware" in result.output


class TestBriefOnOtherDocumentHives:
    """org_notes and ai_skill have the same body-plus-description shape as sop.

    ai_skill is the worst case: a listing carries every SKILL.md body *and*
    every bundled supporting file.
    """

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_note_brief_keeps_description(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {
            "baseline": _record({"text": "long note body", "description": "Prod baseline"}),
        }
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "note", "list", "--brief"])
        assert result.exit_code == 0, result.output
        assert mock_hive_cls.call_args[0][1] == "org_notes"
        assert json.loads(result.output)["baseline"]["data"] == {"description": "Prod baseline"}

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_ai_skill_brief_drops_content_and_bundled_files(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.list.return_value = {
            "triage": _record({
                "name": "triage",
                "description": "Triage a detection",
                "when_to_use": "When a detection needs first-pass review",
                "content": "SKILL.md body",
                "effort": "high",
                "files": {"scripts/helper.sh": "#!/bin/sh\necho hi"},
            }),
        }
        mock_hive_cls.return_value = mock_hive

        result = CliRunner().invoke(cli, ["--output", "json", "ai-skill", "list", "--brief"])
        assert result.exit_code == 0, result.output
        assert mock_hive_cls.call_args[0][1] == "ai_skill"
        assert json.loads(result.output)["triage"]["data"] == {
            "name": "triage",
            "description": "Triage a detection",
            "when_to_use": "When a detection needs first-pass review",
        }
        # The bodies are the whole point of the flag.
        assert "SKILL.md body" not in result.output
        assert "helper.sh" not in result.output


class TestBriefIsOptIn:
    def test_hives_without_index_keys_have_no_brief_flag(self):
        # --brief only makes sense where some subset of data identifies the
        # record. secret/lookup/etc. named no index fields, so offering the
        # flag there would imply a summary the factory cannot produce.
        result = CliRunner().invoke(cli, ["secret", "list", "--brief"])
        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_sop_list_help_documents_brief(self):
        result = CliRunner().invoke(cli, ["sop", "list", "--help"])
        assert result.exit_code == 0, result.output
        assert "--brief" in result.output

    def test_every_brief_capable_hive_documents_it_in_ai_help(self):
        # register_explain is last-write-wins, so a module that registers its
        # own '<group>.list' text silently replaces anything the factory set.
        # --ai-help is the surface agents read, so a hive that offers --brief
        # and never mentions it there ships a flag nobody will find.
        from limacharlie.discovery import get_explain

        for group_name in ("sop", "note", "ai-skill"):
            result = CliRunner().invoke(cli, [group_name, "list", "--help"])
            assert "--brief" in result.output, f"{group_name} list lost the flag"
            explain = get_explain(f"{group_name}.list") or ""
            assert "--brief" in explain, f"{group_name}.list explain omits --brief"
