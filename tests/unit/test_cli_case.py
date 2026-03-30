"""Tests for limacharlie case CLI commands."""

import json
import os
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_cases():
    """Patch the Cases, Organization, and Client classes used by case commands."""
    return (
        patch("limacharlie.commands.case_cmd.Client"),
        patch("limacharlie.commands.case_cmd.Organization"),
        patch("limacharlie.commands.case_cmd.Cases"),
    )


def _invoke(args, mock_cases_cls, return_value=None):
    """Invoke a CLI command with a mocked Cases instance."""
    mock_t = MagicMock()
    mock_cases_cls.return_value = mock_t
    if return_value is not None:
        # MagicMock auto-creates child mocks for attribute access.
        # Configure the default return value so any method call returns it.
        mock_t.configure_mock(**{"__class__": MagicMock})
        mock_t.return_value = return_value
        # Set specific SDK methods that our commands call.
        for name in [
            "create_case",
            "list_cases", "get_case", "export_case",
            "update_case", "add_note",
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


class TestCaseHelp:
    def test_case_group_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "--help"])
        assert result.exit_code == 0
        assert "Manage SOC cases" in result.output
        for cmd in ["create", "list", "get", "export", "update", "add-note", "merge",
                     "entity", "telemetry", "artifact", "detection", "tag",
                     "report", "dashboard", "config-get", "config-set",
                     "assignees", "bulk-update"]:
            assert cmd in result.output

    def test_entity_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "entity", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "update", "remove", "search"]:
            assert cmd in result.output

    def test_telemetry_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "telemetry", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "update", "remove"]:
            assert cmd in result.output

    def test_artifact_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "artifact", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "remove"]:
            assert cmd in result.output

    def test_detection_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "detection", "--help"])
        assert result.exit_code == 0
        for cmd in ["list", "add", "remove"]:
            assert cmd in result.output


# ---------------------------------------------------------------------------
# case create
# ---------------------------------------------------------------------------


class TestCaseCreate:
    _SAMPLE_DETECTION = json.dumps({
        "detect_id": "det-abc",
        "cat": "lateral_movement",
        "source": "dr-general",
        "routing": {"sid": "sid-123", "hostname": "ws-01"},
        "detect_mtd": {"level": "high"},
    })

    def test_create_with_detection(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "create", "--detection", self._SAMPLE_DETECTION,
                 "--summary", "Triage detection"],
                mock_t_cls,
                return_value={"created": 1, "case_number": 1},
            )
            assert result.exit_code == 0
            mock_t.create_case.assert_called_once_with(
                json.loads(self._SAMPLE_DETECTION),
                severity=None,
                summary="Triage detection",
            )

    def test_create_with_severity_override(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "create",
                 "--detection", self._SAMPLE_DETECTION,
                 "--severity", "critical",
                 "--summary", "Critical lateral movement"],
                mock_t_cls,
                return_value={"created": 1, "case_number": 1},
            )
            assert result.exit_code == 0
            mock_t.create_case.assert_called_once_with(
                json.loads(self._SAMPLE_DETECTION),
                severity="critical",
                summary="Critical lateral movement",
            )

    def test_create_without_detection(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "create", "--summary", "Manual investigation"],
                mock_t_cls,
                return_value={"created": 1, "case_number": 1},
            )
            assert result.exit_code == 0
            mock_t.create_case.assert_called_once_with(
                None,
                severity=None,
                summary="Manual investigation",
            )

    def test_create_without_detection_with_severity(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "create", "--severity", "medium",
                 "--summary", "Medium severity case"],
                mock_t_cls,
                return_value={"created": 1, "case_number": 1},
            )
            assert result.exit_code == 0
            mock_t.create_case.assert_called_once_with(
                None,
                severity="medium",
                summary="Medium severity case",
            )

    def test_create_with_summary(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "create", "--summary", "Lateral movement detected"],
                mock_t_cls,
                return_value={"created": 1, "case_number": 1},
            )
            assert result.exit_code == 0
            mock_t.create_case.assert_called_once_with(
                None,
                severity=None,
                summary="Lateral movement detected",
            )

    def test_create_without_summary_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "create",
            "--detection", self._SAMPLE_DETECTION,
        ])
        assert result.exit_code != 0

    def test_create_invalid_severity_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "create",
            "--detection", self._SAMPLE_DETECTION,
            "--severity", "extreme",
            "--summary", "Test",
        ])
        assert result.exit_code != 0

    def test_create_invalid_json_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "create", "--detection", "not-json",
            "--summary", "Test",
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case list
# ---------------------------------------------------------------------------


class TestCaseList:
    def test_basic_list(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list"],
                mock_t_cls,
                return_value={"cases": [{"case_id": "t1"}], "total_counts": {}},
            )
            assert result.exit_code == 0
            mock_t.list_cases.assert_called_once()
            parsed = json.loads(result.output)
            assert "cases" in parsed

    def test_list_with_filters(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list", "--status", "new", "--severity", "critical",
                 "--assignee", "alice@example.com", "--search", "mimikatz",
                 "--sort", "severity", "--order", "asc", "--limit", "20"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["status"] == ["new"]
            assert call_kwargs["severity"] == ["critical"]
            assert call_kwargs["assignee"] == "alice@example.com"
            assert call_kwargs["search"] == "mimikatz"
            assert call_kwargs["sort"] == "severity"
            assert call_kwargs["order"] == "asc"
            assert call_kwargs["page_size"] == 20

    def test_list_multiple_statuses(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list", "--status", "new", "--status", "in_progress"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["status"] == ["new", "in_progress"]

    def test_list_invalid_status_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "list", "--status", "invalid"])
        assert result.exit_code != 0

    def test_list_invalid_severity_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "list", "--severity", "extreme"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case get
# ---------------------------------------------------------------------------


class TestCaseGet:
    def test_get_by_id(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "get", "--id", "42"],
                mock_t_cls,
                return_value={"case": {"case_id": "tid-1"}, "events": []},
            )
            assert result.exit_code == 0
            mock_t.get_case.assert_called_once_with(42)

    def test_get_requires_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "get"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case export
# ---------------------------------------------------------------------------


class TestCaseExport:
    def test_export_by_id(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            export_data = {
                "case": {"case_id": "tid-1", "status": "new"},
                "events": [{"type": "created"}],
                "detections": {"detections": [{"detection_id": "det-1"}]},
                "entities": {"entities": [{"entity_type": "ip"}]},
                "telemetry": {"telemetry": []},
                "artifacts": {"artifacts": []},
            }
            result, mock_t = _invoke(
                ["case", "export", "--id", "42"],
                mock_t_cls,
                return_value=export_data,
            )
            assert result.exit_code == 0
            mock_t.export_case.assert_called_once_with(42)
            parsed = json.loads(result.output)
            assert "case" in parsed

    def test_export_requires_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "export"])
        assert result.exit_code != 0

    def test_export_with_data_creates_directory(self, tmp_path):
        out_dir = str(tmp_path / "export-out")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": [{"detection_id": "det-1"}]},
            "entities": {"entities": []},
            "telemetry": {"telemetry": [{"atom": "atom-1", "sid": "sid-1"}]},
            "artifacts": {"artifacts": [{"artifact_id": "art-1"}]},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls, \
             patch("limacharlie.commands.case_cmd.Sensor") as MockSensor, \
             patch("limacharlie.commands.case_cmd.Artifacts") as MockArtifacts:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data
            mock_t._org.get_detection_by_id.return_value = {"cat": "lateral", "detect": {}}

            mock_sensor = MagicMock()
            MockSensor.return_value = mock_sensor
            mock_sensor.get_event_by_atom.return_value = {"event": {"EVENT_TYPE": "NEW_PROCESS"}}

            mock_artifacts = MagicMock()
            MockArtifacts.return_value = mock_artifacts
            mock_artifacts.get_url.return_value = {"payload": "aGVsbG8="}  # base64("hello")

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0, result.output

            # Verify directory structure.
            assert os.path.isfile(os.path.join(out_dir, "case.json"))
            assert os.path.isfile(os.path.join(out_dir, "detections", "det-1.json"))
            assert os.path.isfile(os.path.join(out_dir, "telemetry", "atom-1.json"))
            assert os.path.isfile(os.path.join(out_dir, "artifacts", "art-1.bin"))

            # Verify case.json contents.
            with open(os.path.join(out_dir, "case.json")) as f:
                case_json = json.load(f)
            assert case_json["case"]["case_id"] == "tid-1"

            # Verify detection content was fetched.
            mock_t._org.get_detection_by_id.assert_called_once_with("det-1")
            with open(os.path.join(out_dir, "detections", "det-1.json")) as f:
                det_json = json.load(f)
            assert det_json["cat"] == "lateral"

            # Verify telemetry event was fetched.
            MockSensor.assert_called_once_with(mock_t._org, "sid-1")
            mock_sensor.get_event_by_atom.assert_called_once_with("atom-1")

            # Verify artifact was downloaded (base64 inline payload).
            with open(os.path.join(out_dir, "artifacts", "art-1.bin"), "rb") as f:
                assert f.read() == b"hello"

    def test_export_with_data_skips_on_fetch_error(self, tmp_path):
        out_dir = str(tmp_path / "export-err")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": [{"detection_id": "det-bad"}]},
            "entities": {"entities": []},
            "telemetry": {"telemetry": []},
            "artifacts": {"artifacts": []},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data
            mock_t._org.get_detection_by_id.side_effect = Exception("not found")

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0
            assert os.path.isfile(os.path.join(out_dir, "case.json"))
            # Detection dir may exist but file should not.
            assert not os.path.isfile(os.path.join(out_dir, "detections", "det-bad.json"))
            assert "Warning" in result.output

    def test_export_with_data_quiet_mode(self, tmp_path):
        out_dir = str(tmp_path / "export-quiet")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": []},
            "entities": {"entities": []},
            "telemetry": {"telemetry": []},
            "artifacts": {"artifacts": []},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--quiet", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0
            assert "exported" not in result.output
            assert os.path.isfile(os.path.join(out_dir, "case.json"))

    def test_export_with_data_artifact_export_url(self, tmp_path):
        """Test artifact download via signed export URL."""
        out_dir = str(tmp_path / "export-url")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": []},
            "entities": {"entities": []},
            "telemetry": {"telemetry": []},
            "artifacts": {"artifacts": [{"artifact_id": "art-url"}]},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls, \
             patch("limacharlie.commands.case_cmd.Artifacts") as MockArtifacts, \
             patch("limacharlie.commands.case_cmd.urlopen") as mock_urlopen:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data

            mock_artifacts = MagicMock()
            MockArtifacts.return_value = mock_artifacts
            mock_artifacts.get_url.return_value = {"export": "https://signed-url.example.com/art"}

            # Mock the urlopen context manager to return binary data.
            mock_resp = MagicMock()
            mock_resp.read.side_effect = [b"artifact-binary-data", b""]
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0
            mock_urlopen.assert_called_once_with("https://signed-url.example.com/art")
            with open(os.path.join(out_dir, "artifacts", "art-url.bin"), "rb") as f:
                assert f.read() == b"artifact-binary-data"

    def test_export_with_data_telemetry_fetch_error(self, tmp_path):
        out_dir = str(tmp_path / "export-tel-err")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": []},
            "entities": {"entities": []},
            "telemetry": {"telemetry": [{"atom": "atom-bad", "sid": "sid-1"}]},
            "artifacts": {"artifacts": []},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls, \
             patch("limacharlie.commands.case_cmd.Sensor") as MockSensor:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data
            mock_sensor = MagicMock()
            MockSensor.return_value = mock_sensor
            mock_sensor.get_event_by_atom.side_effect = Exception("event expired")

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0
            assert not os.path.isfile(os.path.join(out_dir, "telemetry", "atom-bad.json"))
            assert "Warning" in result.output

    def test_export_with_data_artifact_fetch_error(self, tmp_path):
        out_dir = str(tmp_path / "export-art-err")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": []},
            "entities": {"entities": []},
            "telemetry": {"telemetry": []},
            "artifacts": {"artifacts": [{"artifact_id": "art-bad"}]},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls, \
             patch("limacharlie.commands.case_cmd.Artifacts") as MockArtifacts:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data
            mock_artifacts = MagicMock()
            MockArtifacts.return_value = mock_artifacts
            mock_artifacts.get_url.side_effect = Exception("artifact gone")

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0
            assert not os.path.isfile(os.path.join(out_dir, "artifacts", "art-bad.bin"))
            assert "Warning" in result.output

    def test_export_with_data_skips_empty_ids(self, tmp_path):
        """Entries missing detection_id/atom/sid/artifact_id are skipped."""
        out_dir = str(tmp_path / "export-empty")
        export_data = {
            "case": {"case_id": "tid-1"},
            "events": [],
            "detections": {"detections": [{"other_field": "x"}]},
            "entities": {"entities": []},
            "telemetry": {"telemetry": [{"atom": "a1"}, {"sid": "s1"}]},
            "artifacts": {"artifacts": [{}]},
        }
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t._org = MagicMock()
            mock_t.export_case.return_value = export_data

            runner = CliRunner()
            result = runner.invoke(
                cli, ["--output", "json", "case", "export", "--id", "42",
                      "--with-data", out_dir],
            )
            assert result.exit_code == 0
            # No SDK fetch methods should have been called.
            mock_t._org.get_detection_by_id.assert_not_called()


# ---------------------------------------------------------------------------
# case update
# ---------------------------------------------------------------------------


class TestCaseUpdate:
    def test_update_status(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "update", "--id", "42", "--status", "in_progress"],
                mock_t_cls,
                return_value={"case": {}},
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(42, status="in_progress")

    def test_update_multiple_fields(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "update", "--id", "42",
                 "--status", "resolved",
                 "--classification", "true_positive",
                 "--assignees", "bob@example.com"],
                mock_t_cls,
                return_value={"case": {}},
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(
                42,
                status="resolved",
                classification="true_positive",
                assignees=["bob@example.com"],
            )

    def test_update_no_fields_error(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "update", "--id", "42"],
                mock_t_cls,
            )
            assert result.exit_code != 0
            assert "at least one field" in result.output

    def test_update_invalid_status_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "update", "--id", "1", "--status", "invalid"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case add-note
# ---------------------------------------------------------------------------


class TestCaseAddNote:
    def test_add_note_with_content(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "add-note", "--id", "42", "--content", "Triage complete"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_note.assert_called_once_with(42, "Triage complete", note_type=None)

    def test_add_note_with_type(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "add-note", "--id", "42", "--content", "Analysis", "--type", "analysis"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_note.assert_called_once_with(42, "Analysis", note_type="analysis")

    def test_add_note_from_stdin(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.add_note.return_value = {}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "add-note", "--id", "42"],
                input="Piped content\n",
            )
            assert result.exit_code == 0
            mock_t.add_note.assert_called_once_with(42, "Piped content", note_type=None)

    def test_add_note_invalid_type_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "add-note", "--id", "1", "--content", "x", "--type", "invalid",
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case bulk-update
# ---------------------------------------------------------------------------


class TestCaseBulkUpdate:
    def test_bulk_update_with_numbers(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "bulk-update", "--numbers", "1,2,3", "--status", "closed"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.bulk_update.assert_called_once_with(
                [1, 2, 3], status="closed",
            )

    def test_bulk_update_with_file(self, tmp_path):
        id_file = tmp_path / "numbers.txt"
        id_file.write_text("1\n2\n3\n")
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "bulk-update", "--input-file", str(id_file),
                 "--classification", "false_positive"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.bulk_update.assert_called_once_with(
                [1, 2, 3], classification="false_positive",
            )

    def test_bulk_update_json_array_file(self, tmp_path):
        id_file = tmp_path / "numbers.json"
        id_file.write_text('[1, 2]')
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "bulk-update", "--input-file", str(id_file), "--status", "closed"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.bulk_update.assert_called_once_with([1, 2], status="closed")

    def test_bulk_update_no_numbers_error(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["case", "bulk-update", "--status", "closed"],
                mock_t_cls,
            )
            assert result.exit_code != 0

    def test_bulk_update_no_fields_error(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["case", "bulk-update", "--numbers", "1"],
                mock_t_cls,
            )
            assert result.exit_code != 0
            assert "at least --status or --classification" in result.output


# ---------------------------------------------------------------------------
# case merge
# ---------------------------------------------------------------------------


class TestCaseMerge:
    def test_merge(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "merge", "--target", "10", "--sources", "11,12"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.merge.assert_called_once_with(10, [11, 12])

    def test_merge_requires_target(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "merge", "--sources", "1"])
        assert result.exit_code != 0

    def test_merge_requires_sources(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "merge", "--target", "1"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case entity
# ---------------------------------------------------------------------------


class TestCaseEntity:
    def test_entity_list(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "entity", "list", "--case", "42"],
                mock_t_cls,
                return_value={"entities": []},
            )
            assert result.exit_code == 0
            mock_t.list_entities.assert_called_once_with(42)

    def test_entity_add(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "entity", "add", "--case", "42",
                 "--type", "ip", "--value", "10.0.0.1", "--verdict", "malicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_entity.assert_called_once_with(
                42, "ip", "10.0.0.1",
                note=None, verdict="malicious",
            )

    def test_entity_add_invalid_type_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "entity", "add", "--case", "1",
            "--type", "invalid", "--value", "x",
        ])
        assert result.exit_code != 0

    def test_entity_update(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "entity", "update", "--case", "42",
                 "--entity-id", "eid-1", "--verdict", "benign"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.update_entity.assert_called_once_with(42, "eid-1", note=None, verdict="benign")

    def test_entity_update_no_fields_error(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["case", "entity", "update", "--case", "1", "--entity-id", "e1"],
                mock_t_cls,
            )
            assert result.exit_code != 0

    def test_entity_remove(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "entity", "remove", "--case", "42", "--entity-id", "eid-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_entity.assert_called_once_with(42, "eid-1")

    def test_entity_search(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "entity", "search", "--type", "domain", "--value", "evil.com"],
                mock_t_cls,
                return_value={"results": []},
            )
            assert result.exit_code == 0
            mock_t.search_entities.assert_called_once_with("domain", "evil.com")


# ---------------------------------------------------------------------------
# case telemetry
# ---------------------------------------------------------------------------


class TestCaseTelemetry:
    _SAMPLE_EVENT = json.dumps({
        "routing": {
            "this": "atom-1",
            "sid": "sid-1",
            "event_type": "NEW_PROCESS",
        },
    })

    def test_telemetry_list(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "telemetry", "list", "--case", "42"],
                mock_t_cls,
                return_value={"telemetry": []},
            )
            assert result.exit_code == 0
            mock_t.list_telemetry.assert_called_once_with(42)

    def test_telemetry_add(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "telemetry", "add", "--case", "42",
                 "--event", self._SAMPLE_EVENT,
                 "--verdict", "suspicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_telemetry.assert_called_once_with(
                42, json.loads(self._SAMPLE_EVENT),
                note=None, verdict="suspicious",
            )

    def test_telemetry_add_requires_event(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "telemetry", "add", "--case", "42",
        ])
        assert result.exit_code != 0

    def test_telemetry_add_invalid_json_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "telemetry", "add", "--case", "42",
            "--event", "not-json",
        ])
        assert result.exit_code != 0

    def test_telemetry_add_with_all_optional_fields(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "telemetry", "add", "--case", "42",
                 "--event", self._SAMPLE_EVENT,
                 "--note", "Process spawned, key evidence",
                 "--verdict", "malicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_telemetry.assert_called_once_with(
                42, json.loads(self._SAMPLE_EVENT),
                note="Process spawned, key evidence",
                verdict="malicious",
            )

    def test_telemetry_update(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "telemetry", "update", "--case", "42",
                 "--telemetry-id", "tel-1", "--verdict", "malicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.update_telemetry.assert_called_once_with(42, "tel-1", note=None, verdict="malicious")

    def test_telemetry_update_no_fields_error(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, _ = _invoke(
                ["case", "telemetry", "update", "--case", "1", "--telemetry-id", "tel-1"],
                mock_t_cls,
            )
            assert result.exit_code != 0

    def test_telemetry_remove(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "telemetry", "remove", "--case", "42", "--telemetry-id", "tel-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_telemetry.assert_called_once_with(42, "tel-1")


# ---------------------------------------------------------------------------
# case artifact
# ---------------------------------------------------------------------------


class TestCaseArtifact:
    def test_artifact_list(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "artifact", "list", "--case", "42"],
                mock_t_cls,
                return_value={"artifacts": []},
            )
            assert result.exit_code == 0
            mock_t.list_artifacts.assert_called_once_with(42)

    def test_artifact_add(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "artifact", "add", "--case", "42",
                 "--path", "/captures/test.pcap", "--source", "sensor-01",
                 "--type", "pcap", "--note", "Network capture",
                 "--verdict", "suspicious"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_artifact.assert_called_once_with(
                42, "/captures/test.pcap", "sensor-01",
                artifact_type="pcap", note="Network capture", verdict="suspicious",
            )

    def test_artifact_remove(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "artifact", "remove", "--case", "42", "--artifact-id", "art-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_artifact.assert_called_once_with(42, "art-1")


# ---------------------------------------------------------------------------
# case detection
# ---------------------------------------------------------------------------


class TestCaseDetection:
    _SAMPLE_DETECTION = json.dumps({
        "detect_id": "det-1",
        "cat": "lateral_movement",
        "source": "dr-general",
        "routing": {"sid": "sid-1", "hostname": "ws-01"},
        "detect_mtd": {"level": "high"},
    })

    def test_detection_list(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "detection", "list", "--case", "42"],
                mock_t_cls,
                return_value={"detections": []},
            )
            assert result.exit_code == 0
            mock_t.list_detections.assert_called_once_with(42)

    def test_detection_add(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "detection", "add", "--case", "42",
                 "--detection", self._SAMPLE_DETECTION],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.add_detection.assert_called_once_with(
                42, json.loads(self._SAMPLE_DETECTION),
            )

    def test_detection_add_requires_detection(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "detection", "add", "--case", "42",
        ])
        assert result.exit_code != 0

    def test_detection_add_invalid_json_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "case", "detection", "add", "--case", "42",
            "--detection", "not-json",
        ])
        assert result.exit_code != 0

    def test_detection_remove(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "detection", "remove", "--case", "42",
                 "--detection-id", "det-1"],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.remove_detection.assert_called_once_with(42, "det-1")


# ---------------------------------------------------------------------------
# case report
# ---------------------------------------------------------------------------


class TestCaseReport:
    def test_report_summary(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "report",
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
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "report",
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
        result = runner.invoke(cli, ["case", "report", "--to", "2026-02-01T00:00:00Z"])
        assert result.exit_code != 0

    def test_report_requires_to(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "report", "--from", "2026-01-01T00:00:00Z"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# case dashboard
# ---------------------------------------------------------------------------


class TestCaseDashboard:
    def test_dashboard(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "dashboard"],
                mock_t_cls,
                return_value={"counts": {"new": 5}},
            )
            assert result.exit_code == 0
            mock_t.dashboard_counts.assert_called_once()


# ---------------------------------------------------------------------------
# case config-get / config-set
# ---------------------------------------------------------------------------


class TestCaseConfig:
    def test_config_get(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "config-get"],
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
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "config-set", "--input-file", str(config_file)],
                mock_t_cls,
                return_value={},
            )
            assert result.exit_code == 0
            mock_t.set_config.assert_called_once_with({"retention_days": 60})

    def test_config_set_from_stdin(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.set_config.return_value = {}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "config-set"],
                input='{"retention_days": 30}\n',
            )
            assert result.exit_code == 0
            mock_t.set_config.assert_called_once_with({"retention_days": 30})


# ---------------------------------------------------------------------------
# case assignees
# ---------------------------------------------------------------------------


class TestCaseAssignees:
    def test_assignees(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "assignees"],
                mock_t_cls,
                return_value={"assignees": ["alice@example.com", "bob@example.com"]},
            )
            assert result.exit_code == 0
            mock_t.list_assignees.assert_called_once()


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------


class TestCaseQuietMode:
    def test_list_quiet(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.list_cases.return_value = {"cases": []}
            runner = CliRunner()
            result = runner.invoke(cli, ["--quiet", "case", "list"])
            assert result.exit_code == 0
            assert result.output.strip() == ""

    def test_config_set_quiet(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"retention_days": 60}')
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.set_config.return_value = {}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--quiet", "case", "config-set", "--input-file", str(config_file)],
            )
            assert result.exit_code == 0
            assert "updated" not in result.output


# ---------------------------------------------------------------------------
# case list --tag
# ---------------------------------------------------------------------------


class TestCaseListTag:
    def test_list_with_single_tag(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list", "--tag", "phishing"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["tag"] == ["phishing"]

    def test_list_with_multiple_tags(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list", "--tag", "phishing", "--tag", "urgent"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["tag"] == ["phishing", "urgent"]

    def test_list_without_tag(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["tag"] is None


# ---------------------------------------------------------------------------
# case list --sid
# ---------------------------------------------------------------------------


class TestCaseListSid:
    def test_list_with_sid(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list", "--sid", "abc-sensor-123"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["sensor_id"] == "abc-sensor-123"

    def test_list_without_sid(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["sensor_id"] is None

    def test_list_sid_combined_with_status(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "list", "--sid", "abc-sensor-123", "--status", "new"],
                mock_t_cls,
                return_value={"cases": [], "total_counts": {}},
            )
            assert result.exit_code == 0
            call_kwargs = mock_t.list_cases.call_args[1]
            assert call_kwargs["sensor_id"] == "abc-sensor-123"
            assert call_kwargs["status"] == ["new"]


# ---------------------------------------------------------------------------
# case update --tag
# ---------------------------------------------------------------------------


class TestCaseUpdateTag:
    def test_update_with_tags(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "update", "--id", "1", "--tag", "phishing", "--tag", "urgent"],
                mock_t_cls,
                return_value={"case": {}},
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(
                1, tags=["phishing", "urgent"],
            )

    def test_update_with_tags_and_status(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "update", "--id", "1", "--status", "in_progress",
                 "--tag", "phishing"],
                mock_t_cls,
                return_value={"case": {}},
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(
                1, status="in_progress", tags=["phishing"],
            )


# ---------------------------------------------------------------------------
# case tag subcommands
# ---------------------------------------------------------------------------


class TestCaseTagSubcommands:
    def test_tag_subgroup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "tag", "--help"])
        assert result.exit_code == 0
        for cmd in ["set", "add", "remove"]:
            assert cmd in result.output

    def test_tag_set(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "tag", "set", "--id", "1", "--tag", "phishing"],
                mock_t_cls,
                return_value={"case": {}},
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(1, tags=["phishing"])

    def test_tag_set_multiple(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            result, mock_t = _invoke(
                ["case", "tag", "set", "--id", "1", "-t", "phishing", "-t", "urgent"],
                mock_t_cls,
                return_value={"case": {}},
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(1, tags=["phishing", "urgent"])

    def test_tag_add_merges_with_existing(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1, "tags": ["existing"]},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "add", "--id", "1", "--tag", "new-tag"],
            )
            assert result.exit_code == 0
            mock_t.get_case.assert_called_once_with(1)
            mock_t.update_case.assert_called_once_with(1, tags=["existing", "new-tag"])

    def test_tag_add_deduplicates(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1, "tags": ["phishing"]},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "add", "--id", "1", "--tag", "phishing"],
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(1, tags=["phishing"])

    def test_tag_add_with_no_existing_tags(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "add", "--id", "1", "--tag", "new-tag"],
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(1, tags=["new-tag"])

    def test_tag_remove(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1, "tags": ["old-tag", "keep-tag"]},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "remove", "--id", "1", "--tag", "old-tag"],
            )
            assert result.exit_code == 0
            mock_t.get_case.assert_called_once_with(1)
            mock_t.update_case.assert_called_once_with(1, tags=["keep-tag"])

    def test_tag_remove_nonexistent_tag(self):
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1, "tags": ["keep-tag"]},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "remove", "--id", "1", "--tag", "no-such-tag"],
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(1, tags=["keep-tag"])

    def test_tag_add_case_insensitive_dedup(self):
        """Adding PHISHING when 'phishing' already exists should NOT add a duplicate."""
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1, "tags": ["phishing"]},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "add", "--id", "1", "--tag", "PHISHING"],
            )
            assert result.exit_code == 0
            # The existing 'phishing' wins; no duplicate added.
            mock_t.update_case.assert_called_once_with(1, tags=["phishing"])

    def test_tag_remove_case_insensitive(self):
        """Removing PHISHING should remove existing 'Phishing' (case-insensitive)."""
        p1, p2, p3 = _patch_cases()
        with p1, p2, p3 as mock_t_cls:
            mock_t = MagicMock()
            mock_t_cls.return_value = mock_t
            mock_t.get_case.return_value = {
                "case": {"case_number": 1, "tags": ["Phishing", "keep-tag"]},
            }
            mock_t.update_case.return_value = {"case": {}}
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--output", "json", "case", "tag", "remove", "--id", "1", "--tag", "PHISHING"],
            )
            assert result.exit_code == 0
            mock_t.update_case.assert_called_once_with(1, tags=["keep-tag"])

    def test_tag_set_requires_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "tag", "set", "--tag", "x"])
        assert result.exit_code != 0

    def test_tag_set_requires_tag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["case", "tag", "set", "--id", "1"])
        assert result.exit_code != 0
