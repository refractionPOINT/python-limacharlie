"""Tests for limacharlie ticket CLI commands."""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_ticketing():
    """Patch the Ticketing, Organization, and Client classes used by ticket commands."""
    return (
        patch("limacharlie.commands.ticket.Client"),
        patch("limacharlie.commands.ticket.Organization"),
        patch("limacharlie.commands.ticket.Ticketing"),
    )


def _invoke(args, mock_ticketing_cls, return_value=None):
    """Invoke a CLI command with a mocked Ticketing instance."""
    mock_t = MagicMock()
    mock_ticketing_cls.return_value = mock_t
    if return_value is not None:
        # MagicMock auto-creates child mocks for attribute access.
        # Configure the default return value so any method call returns it.
        mock_t.configure_mock(**{"__class__": MagicMock})
        mock_t.return_value = return_value
        # Set specific SDK methods that our commands call.
        for name in [
            "create_ticket",
            "list_tickets", "get_ticket", "update_ticket", "add_note",
            "bulk_update", "merge",
            "list_detections", "add_detection", "remove_detection",
            "list_entities", "add_entity", "update_entity", "remove_entity",
            "search_entities",
            "list_telemetry", "add_telemetry", "update_telemetry", "remove_telemetry",
            "list_artifacts", "add_artifact", "remove_artifact",
            "report_summary", "dashboard_counts",
            "get_config", "set_config", "list_assignees",
        ]:
            getattr(mock_t, name).return_value = return_value
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json"] + args)
    return result, mock_t


# ---------------------------------------------------------------------------
# Help / Discovery
# ---------------------------------------------------------------------------


class TestTicketHelp:
    def test_ticket_group_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "--help"])
        assert result.exit_code == 0
        assert "Manage SOC tickets" in result.output
        for cmd in ["create", "list", "get", "update", "add-note", "merge",
                     "entity", "telemetry", "artifact", "detection",
                     "report", "dashboard", "config-get", "config-set",
                     "assignees", "bulk-update"]:
            assert cmd in result.output

    def test_entity_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "entity", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "update", "remove", "search"]:
            assert cmd in result.output

    def test_telemetry_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "telemetry", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "update", "remove"]:
            assert cmd in result.output

    def test_artifact_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "artifact", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "remove"]:
            assert cmd in result.output

    def test_detection_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "detection", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "remove"]:
            assert cmd in result.output


# ---------------------------------------------------------------------------
# ticket create
# ---------------------------------------------------------------------------


class TestTicketCreate:
    def test_create_minimal(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "create", "--detection-id", "det-abc"],
                mock_t_cls,
                return_value={"created": 1, "ticket_id": "tid-new"},
            )
            assert result.exit_code == 0
            mock_t.create_ticket.assert_called_once_with(
                "det-abc",
                detection_cat=None,
                severity=None,
                detection_source=None,
                detection_priority=None,
                sensor_id=None,
                hostname=None,
            )

    def test_create_all_fields(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "create",
                 "--detection-id", "det-abc",
                 "--detection-cat", "lateral_movement",
                 "--severity", "high",
                 "--detection-source", "dr-general",
                 "--detection-priority", "7",
                 "--sensor-id", "sid-123",
                 "--hostname", "ws-01"],
                mock_t_cls,
                return_value={"created": 1, "ticket_id": "tid-new"},
            )
            assert result.exit_code == 0
            mock_t.create_ticket.assert_called_once_with(
                "det-abc",
                detection_cat="lateral_movement",
                severity="high",
                detection_source="dr-general",
                detection_priority=7,
                sensor_id="sid-123",
                hostname="ws-01",
            )

    def test_create_requires_detection_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "create"])
        assert result.exit_code != 0

    def test_create_invalid_severity_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ticket", "create", "--detection-id", "det-1", "--severity", "extreme",
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket list
# ---------------------------------------------------------------------------


class TestTicketList:
    def test_basic_list(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "list"],
                mock_t_cls,
                return_value={"tickets": [{"ticket_id": "t1"}], "total_counts": {}},
            )
            assert result.exit_code == 0
            mock_t.list_tickets.assert_called_once()
            parsed = json.loads(result.output)
            assert "tickets" in parsed

    def test_list_with_filters(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "list", "--status", "new", "--severity", "critical",
                 "--assignee", "alice@example.com", "--search", "mimikatz",
                 "--sort", "severity", "--order", "asc", "--limit", "20"],
                mock_t_cls,
                return_value={"tickets": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_tickets.call_args[1]
            assert call_kwargs["status"] == ["new"]
            assert call_kwargs["severity"] == ["critical"]
            assert call_kwargs["assignee"] == "alice@example.com"
            assert call_kwargs["search"] == "mimikatz"
            assert call_kwargs["sort"] == "severity"
            assert call_kwargs["order"] == "asc"
            assert call_kwargs["page_size"] == 20

    def test_list_multiple_statuses(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "list", "--status", "new", "--status", "acknowledged"],
                mock_t_cls,
                return_value={"tickets": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_tickets.call_args[1]
            assert call_kwargs["status"] == ["new", "acknowledged"]

    def test_list_invalid_status_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "list", "--status", "invalid"])
        assert result.exit_code != 0

    def test_list_invalid_severity_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "list", "--severity", "extreme"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket get
# ---------------------------------------------------------------------------


class TestTicketGet:
    def test_get_by_id(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "get", "--id", "tid-1"],
                mock_t_cls,
                return_value={"ticket": {"ticket_id": "tid-1"}, "events": []},
            )
            assert result.exit_code == 0
            mock_t.get_ticket.assert_called_once_with("tid-1")

    def test_get_requires_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "get"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket update
# ---------------------------------------------------------------------------


class TestTicketUpdate:
    def test_update_status(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "update", "--id", "tid-1", "--status", "acknowledged"],
                mock_t_cls,
                return_value={"ticket": {}},
            )
            assert result.exit_code == 0
            mock_t.update_ticket.assert_called_once_with("tid-1", status="acknowledged")

    def test_update_multiple_fields(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "update", "--id", "tid-1",
                 "--status", "resolved",
                 "--classification", "true_positive",
                 "--assignee", "bob@example.com"],
                mock_t_cls,
                return_value={"ticket": {}},
            )
            assert result.exit_code == 0
            mock_t.update_ticket.assert_called_once_with(
                "tid-1",
                status="resolved",
                classification="true_positive",
                assignee="bob@example.com",
            )

    def test_update_no_fields_error(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "update", "--id", "tid-1"],
                mock_t_cls,
            )
            assert result.exit_code != 0
            assert "at least one field" in result.output

    def test_update_invalid_status_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "update", "--id", "t1", "--status", "invalid"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket add-note
# ---------------------------------------------------------------------------


class TestTicketAddNote:
    def test_add_note_with_content(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "add-note", "--id", "tid-1", "--content", "Triage complete"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_note.assert_called_once_with("tid-1", "Triage complete", note_type=None)

    def test_add_note_with_type(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "add-note", "--id", "tid-1", "--content", "Analysis", "--type", "analysis"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_note.assert_called_once_with("tid-1", "Analysis", note_type="analysis")

    def test_add_note_from_stdin(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.add_note.return_value = {}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "ticket", "add-note", "--id", "tid-1"],
                input="Piped content\n",
            )
            assert result.exit_code == 0
            mock_t.add_note.assert_called_once_with("tid-1", "Piped content", note_type=None)

    def test_add_note_invalid_type_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ticket", "add-note", "--id", "t1", "--content", "x", "--type", "invalid",
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket bulk-update
# ---------------------------------------------------------------------------


class TestTicketBulkUpdate:
    def test_bulk_update_with_ids(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "bulk-update", "--ids", "t1,t2,t3", "--status", "closed"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.bulk_update.assert_called_once_with(
                ["t1", "t2", "t3"], status="closed",
            )

    def test_bulk_update_with_file(self, tmp_path):
        id_file = tmp_path / "ids.txt"
        id_file.write_text("t1\nt2\nt3\n")
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "bulk-update", "--input-file", str(id_file),
                 "--classification", "false_positive"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.bulk_update.assert_called_once_with(
                ["t1", "t2", "t3"], classification="false_positive",
            )

    def test_bulk_update_json_array_file(self, tmp_path):
        id_file = tmp_path / "ids.json"
        id_file.write_text('["t1", "t2"]')
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "bulk-update", "--input-file", str(id_file), "--status", "closed"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.bulk_update.assert_called_once_with(["t1", "t2"], status="closed")

    def test_bulk_update_no_ids_error(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["ticket", "bulk-update", "--status", "closed"],
                mock_t_cls,
            )
            assert result.exit_code != 0

    def test_bulk_update_no_fields_error(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["ticket", "bulk-update", "--ids", "t1"],
                mock_t_cls,
            )
            assert result.exit_code != 0
            assert "at least --status or --classification" in result.output


# ---------------------------------------------------------------------------
# ticket merge
# ---------------------------------------------------------------------------


class TestTicketMerge:
    def test_merge(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "merge", "--target", "target-1", "--sources", "src-1,src-2"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.merge.assert_called_once_with("target-1", ["src-1", "src-2"])

    def test_merge_requires_target(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "merge", "--sources", "s1"])
        assert result.exit_code != 0

    def test_merge_requires_sources(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "merge", "--target", "t1"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket entity
# ---------------------------------------------------------------------------


class TestTicketEntity:
    def test_entity_list(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "entity", "list", "--ticket", "tid-1"],
                mock_t_cls,
                return_value={"entities": []},
            )
            assert result.exit_code == 0
            mock_t.list_entities.assert_called_once_with("tid-1")

    def test_entity_add(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "entity", "add", "--ticket", "tid-1",
                 "--type", "ip", "--value", "10.0.0.1", "--verdict", "malicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_entity.assert_called_once_with(
                "tid-1", "ip", "10.0.0.1",
                name=None, verdict="malicious", context=None,
                first_seen=None, last_seen=None,
            )

    def test_entity_add_invalid_type_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "ticket", "entity", "add", "--ticket", "t1",
            "--type", "invalid", "--value", "x",
        ])
        assert result.exit_code != 0

    def test_entity_update(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "entity", "update", "--ticket", "tid-1",
                 "--entity-id", "eid-1", "--verdict", "benign"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.update_entity.assert_called_once_with("tid-1", "eid-1", verdict="benign")

    def test_entity_update_no_fields_error(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["ticket", "entity", "update", "--ticket", "t1", "--entity-id", "e1"],
                mock_t_cls,
            )
            assert result.exit_code != 0

    def test_entity_remove(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "entity", "remove", "--ticket", "tid-1", "--entity-id", "eid-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_entity.assert_called_once_with("tid-1", "eid-1")

    def test_entity_search(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "entity", "search", "--type", "domain", "--value", "evil.com"],
                mock_t_cls,
                return_value={"results": []},
            )
            assert result.exit_code == 0
            mock_t.search_entities.assert_called_once_with("domain", "evil.com")


# ---------------------------------------------------------------------------
# ticket telemetry
# ---------------------------------------------------------------------------


class TestTicketTelemetry:
    def test_telemetry_list(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "telemetry", "list", "--ticket", "tid-1"],
                mock_t_cls,
                return_value={"telemetry": []},
            )
            assert result.exit_code == 0
            mock_t.list_telemetry.assert_called_once_with("tid-1")

    def test_telemetry_add(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "telemetry", "add", "--ticket", "tid-1",
                 "--atom", "atom-1", "--sid", "sid-1",
                 "--event-type", "NEW_PROCESS", "--verdict", "suspicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_telemetry.assert_called_once_with(
                "tid-1", "atom-1", "sid-1",
                event_type="NEW_PROCESS", event_summary=None,
                verdict="suspicious", relevance=None,
            )

    def test_telemetry_update(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "telemetry", "update", "--ticket", "tid-1",
                 "--telemetry-id", "tel-1", "--verdict", "malicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.update_telemetry.assert_called_once_with("tid-1", "tel-1", verdict="malicious")

    def test_telemetry_update_no_fields_error(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["ticket", "telemetry", "update", "--ticket", "t1", "--telemetry-id", "tel-1"],
                mock_t_cls,
            )
            assert result.exit_code != 0

    def test_telemetry_remove(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "telemetry", "remove", "--ticket", "tid-1", "--telemetry-id", "tel-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_telemetry.assert_called_once_with("tid-1", "tel-1")


# ---------------------------------------------------------------------------
# ticket artifact
# ---------------------------------------------------------------------------


class TestTicketArtifact:
    def test_artifact_list(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "artifact", "list", "--ticket", "tid-1"],
                mock_t_cls,
                return_value={"artifacts": []},
            )
            assert result.exit_code == 0
            mock_t.list_artifacts.assert_called_once_with("tid-1")

    def test_artifact_add(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "artifact", "add", "--ticket", "tid-1",
                 "--type", "pcap", "--description", "Network capture",
                 "--verdict", "suspicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_artifact.assert_called_once_with(
                "tid-1", "pcap",
                description="Network capture", verdict="suspicious",
            )

    def test_artifact_remove(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "artifact", "remove", "--ticket", "tid-1", "--artifact-id", "art-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_artifact.assert_called_once_with("tid-1", "art-1")


# ---------------------------------------------------------------------------
# ticket detection
# ---------------------------------------------------------------------------


class TestTicketDetection:
    def test_detection_list(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "detection", "list", "--ticket", "tid-1"],
                mock_t_cls,
                return_value={"detections": []},
            )
            assert result.exit_code == 0
            mock_t.list_detections.assert_called_once_with("tid-1")

    def test_detection_add(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "detection", "add", "--ticket", "tid-1",
                 "--detection-id", "det-1", "--detection-cat", "lateral_movement"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_detection.assert_called_once_with(
                "tid-1", "det-1",
                detection_cat="lateral_movement",
                detection_source=None,
                detection_priority=None,
                sensor_id=None,
                hostname=None,
            )

    def test_detection_remove(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "detection", "remove", "--ticket", "tid-1",
                 "--detection-id", "det-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_detection.assert_called_once_with("tid-1", "det-1")


# ---------------------------------------------------------------------------
# ticket report
# ---------------------------------------------------------------------------


class TestTicketReport:
    def test_report_summary(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "report",
                 "--from", "2026-01-01T00:00:00Z",
                 "--to", "2026-02-01T00:00:00Z"],
                mock_t_cls,
                return_value={"report": {}},
            )
            assert result.exit_code == 0
            mock_t.report_summary.assert_called_once_with(
                time_from="2026-01-01T00:00:00Z",
                time_to="2026-02-01T00:00:00Z",
                group_by=None,
            )

    def test_report_with_group_by(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "report",
                 "--from", "2026-01-01T00:00:00Z",
                 "--to", "2026-02-01T00:00:00Z",
                 "--group-by", "severity"],
                mock_t_cls,
                return_value={"report": {}},
            )
            assert result.exit_code == 0
            mock_t.report_summary.assert_called_once_with(
                time_from="2026-01-01T00:00:00Z",
                time_to="2026-02-01T00:00:00Z",
                group_by="severity",
            )

    def test_report_requires_from(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "report", "--to", "2026-02-01T00:00:00Z"])
        assert result.exit_code != 0

    def test_report_requires_to(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["ticket", "report", "--from", "2026-01-01T00:00:00Z"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# ticket dashboard
# ---------------------------------------------------------------------------


class TestTicketDashboard:
    def test_dashboard(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "dashboard"],
                mock_t_cls,
                return_value={"counts": {"new": 5}},
            )
            assert result.exit_code == 0
            mock_t.dashboard_counts.assert_called_once()


# ---------------------------------------------------------------------------
# ticket config-get / config-set
# ---------------------------------------------------------------------------


class TestTicketConfig:
    def test_config_get(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "config-get"],
                mock_t_cls,
                return_value={"retention_days": 90},
            )
            assert result.exit_code == 0
            mock_t.get_config.assert_called_once()
            parsed = json.loads(result.output)
            assert parsed["retention_days"] == 90

    def test_config_set_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"retention_days": 60}')
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "config-set", "--input-file", str(config_file)],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.set_config.assert_called_once_with({"retention_days": 60})

    def test_config_set_from_stdin(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.set_config.return_value = {}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "ticket", "config-set"],
                input='{"retention_days": 30}\n',
            )
            assert result.exit_code == 0
            mock_t.set_config.assert_called_once_with({"retention_days": 30})


# ---------------------------------------------------------------------------
# ticket assignees
# ---------------------------------------------------------------------------


class TestTicketAssignees:
    def test_assignees(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["ticket", "assignees"],
                mock_t_cls,
                return_value={"assignees": ["alice@example.com", "bob@example.com"]},
            )
            assert result.exit_code == 0
            mock_t.list_assignees.assert_called_once()


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------


class TestTicketQuietMode:
    def test_list_quiet(self):
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.list_tickets.return_value = {"tickets": []}
            runner = CliRunner()
            result = runner.invoke(cli, ["--quiet", "ticket", "list"])
            assert result.exit_code == 0
            assert result.output.strip() == ""

    def test_config_set_quiet(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"retention_days": 60}')
        p1, p2, p3 = _patch_ticketing()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.set_config.return_value = {}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--quiet", "ticket", "config-set", "--input-file", str(config_file)],
            )
            assert result.exit_code == 0
            assert "updated" not in result.output
