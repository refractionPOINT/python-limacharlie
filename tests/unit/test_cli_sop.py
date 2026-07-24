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
