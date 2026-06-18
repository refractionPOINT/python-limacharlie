"""Tests for limacharlie.sdk.cases module."""

import json
from unittest.mock import MagicMock, patch, call
import pytest

from limacharlie.sdk.cases import Cases


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.client._jwt = "fake-jwt-token"
    org.get_urls.return_value = {}
    return org


@pytest.fixture
def cases(mock_org):
    return Cases(mock_org)


def _extract_call(mock_org):
    """Extract (verb, path, kwargs) from the last client.request() call."""
    args, kwargs = mock_org.client.request.call_args
    return args, kwargs


def _extract_body(mock_org):
    """Extract parsed JSON body from the last client.request() call."""
    _, kwargs = mock_org.client.request.call_args
    return json.loads(kwargs["raw_body"])


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestCasesInit:
    def test_default_api_root(self, mock_org):
        """When no override and get_urls has no 'cases' key, falls back to default."""
        mock_org.get_urls.return_value = {}
        t = Cases(mock_org)
        assert t._api_root == "https://cases.limacharlie.io"

    def test_org_url_resolved(self, mock_org):
        """When get_urls returns a 'cases' key, use it."""
        mock_org.get_urls.return_value = {"cases": "cases.staging.limacharlie.io"}
        t = Cases(mock_org)
        assert t._api_root == "https://cases.staging.limacharlie.io"

    def test_org_url_with_scheme(self, mock_org):
        """When get_urls returns a URL with scheme, don't double-prefix."""
        mock_org.get_urls.return_value = {"cases": "https://cases.staging.limacharlie.io"}
        t = Cases(mock_org)
        assert t._api_root == "https://cases.staging.limacharlie.io"

    def test_org_url_cached(self, mock_org):
        """get_urls should only be called once."""
        mock_org.get_urls.return_value = {"cases": "cases.staging.limacharlie.io"}
        t = Cases(mock_org)
        _ = t._api_root
        _ = t._api_root
        mock_org.get_urls.assert_called_once()

    def test_org_url_error_fallback(self, mock_org):
        """When get_urls raises, fall back to default."""
        mock_org.get_urls.side_effect = Exception("network error")
        t = Cases(mock_org)
        assert t._api_root == "https://cases.limacharlie.io"

    def test_custom_api_root(self, mock_org):
        t = Cases(mock_org, api_root="https://custom.example.com")
        assert t._api_root == "https://custom.example.com"
        mock_org.get_urls.assert_not_called()

    def test_env_override(self, mock_org, monkeypatch):
        monkeypatch.setenv("LC_CASES_API_ROOT", "https://env.example.com")
        t = Cases(mock_org)
        assert t._api_root == "https://env.example.com"
        mock_org.get_urls.assert_not_called()

    def test_explicit_api_root_overrides_env(self, mock_org, monkeypatch):
        monkeypatch.setenv("LC_CASES_API_ROOT", "https://env.example.com")
        t = Cases(mock_org, api_root="https://explicit.example.com")
        assert t._api_root == "https://explicit.example.com"
        mock_org.get_urls.assert_not_called()

    def test_oid_property(self, cases):
        assert cases.oid == "test-oid"


# ---------------------------------------------------------------------------
# Create Case (via extension request)
# ---------------------------------------------------------------------------


class TestCreateCase:
    _SAMPLE_DETECTION = {
        "detect_id": "det-1",
        "cat": "lateral_movement",
        "source": "dr-general",
        "routing": {"sid": "sid-1", "hostname": "ws-01"},
        "detect_mtd": {"level": "high"},
    }

    def test_calls_extension_request(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1, "case_number": 1}
            result = cases.create_case(self._SAMPLE_DETECTION)
            MockExt.assert_called_once_with(mock_org)
            mock_ext.request.assert_called_once_with(
                "ext-cases", "create_case",
                data={"detection": self._SAMPLE_DETECTION},
            )
            assert result["case_number"] == 1

    def test_all_optional_fields(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            cases.create_case(
                self._SAMPLE_DETECTION,
                severity="high",
                summary="Test summary",
            )
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {
                "detection": self._SAMPLE_DETECTION,
                "severity": "high",
                "summary": "Test summary",
            }

    def test_none_optional_fields_excluded(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            cases.create_case(self._SAMPLE_DETECTION, severity=None)
            call_data = mock_ext.request.call_args[1]["data"]
            assert "severity" not in call_data

    def test_without_detection(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            cases.create_case()
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {}

    def test_without_detection_with_severity(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            cases.create_case(severity="medium")
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {"severity": "medium"}

    def test_with_summary(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            cases.create_case(
                self._SAMPLE_DETECTION,
                severity="high",
                summary="Lateral movement detected",
            )
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {
                "detection": self._SAMPLE_DETECTION,
                "severity": "high",
                "summary": "Lateral movement detected",
            }

    def test_summary_none_excluded(self, cases, mock_org):
        with patch("limacharlie.sdk.cases.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            cases.create_case(self._SAMPLE_DETECTION, summary=None)
            call_data = mock_ext.request.call_args[1]["data"]
            assert "summary" not in call_data


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


class TestListCases:
    def test_minimal(self, cases, mock_org):
        mock_org.client.request.return_value = {"cases": []}
        cases.list_cases()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/cases")
        assert kwargs["query_params"] == {"oids": "test-oid"}

    def test_all_filters(self, cases, mock_org):
        mock_org.client.request.return_value = {"cases": []}
        cases.list_cases(
            status=["new", "in_progress"],
            severity=["critical"],
            classification=["pending"],
            assignee="alice@example.com",
            search="mimikatz",
            sort="severity",
            order="asc",
            page_size=20,
            page_token="abc123",
        )
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert qp["oids"] == "test-oid"
        assert qp["status"] == "new,in_progress"
        assert qp["severity"] == "critical"
        assert qp["classification"] == "pending"
        assert qp["assignee"] == "alice@example.com"
        assert qp["search"] == "mimikatz"
        assert qp["sort"] == "severity"
        assert qp["order"] == "asc"
        assert qp["page_size"] == "20"
        assert qp["page_token"] == "abc123"

    def test_empty_lists_omitted(self, cases, mock_org):
        mock_org.client.request.return_value = {"cases": []}
        cases.list_cases(status=[], severity=None)
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert "status" not in qp
        assert "severity" not in qp

    def test_sensor_id_filter(self, cases, mock_org):
        mock_org.client.request.return_value = {"cases": []}
        cases.list_cases(sensor_id="abc-sensor-123")
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert qp["sid"] == "abc-sensor-123"

    def test_sensor_id_none_omitted(self, cases, mock_org):
        mock_org.client.request.return_value = {"cases": []}
        cases.list_cases(sensor_id=None)
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert "sid" not in qp


class TestGetCase:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"case": {}}
        cases.get_case(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/cases/42")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestUpdateCase:
    def test_patch_with_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {"case": {}}
        cases.update_case(42, status="in_progress", assignees=["bob@example.com"])
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/cases/42")
        assert kwargs["query_params"] == {"oid": "test-oid"}
        body = json.loads(kwargs["raw_body"])
        assert body == {"status": "in_progress", "assignees": ["bob@example.com"]}
        assert kwargs["content_type"] == "application/json"

    def test_none_fields_excluded(self, cases, mock_org):
        mock_org.client.request.return_value = {"case": {}}
        cases.update_case(42, status="resolved", assignees=None, classification=None)
        body = _extract_body(mock_org)
        assert body == {"status": "resolved"}


class TestAddNote:
    def test_with_content_only(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Triage complete")
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/cases/42/notes")
        assert kwargs["query_params"] == {"oid": "test-oid"}
        body = json.loads(kwargs["raw_body"])
        assert body == {"content": "Triage complete"}

    def test_with_note_type(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Analysis result", note_type="analysis")
        body = _extract_body(mock_org)
        assert body == {"content": "Analysis result", "note_type": "analysis"}

    def test_none_note_type_excluded(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Note text", note_type=None)
        body = _extract_body(mock_org)
        assert "note_type" not in body

    def test_with_is_public_true(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Public note", is_public=True)
        body = _extract_body(mock_org)
        assert body == {"content": "Public note", "is_public": True}

    def test_with_is_public_false(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Private note", is_public=False)
        body = _extract_body(mock_org)
        assert body == {"content": "Private note", "is_public": False}

    def test_is_public_none_excluded(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Note text", is_public=None)
        body = _extract_body(mock_org)
        assert "is_public" not in body

    def test_ai_session_id_explicit(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "AI findings", ai_session_id="sess-1")
        body = _extract_body(mock_org)
        assert body["ai_session_id"] == "sess-1"

    def test_ai_session_id_from_env(self, cases, mock_org, monkeypatch):
        monkeypatch.setenv("LC_AI_SESSION_ID", "sess-env")
        mock_org.client.request.return_value = {}
        cases.add_note(42, "AI findings")
        body = _extract_body(mock_org)
        assert body["ai_session_id"] == "sess-env"

    def test_explicit_ai_session_id_overrides_env(self, cases, mock_org, monkeypatch):
        monkeypatch.setenv("LC_AI_SESSION_ID", "sess-env")
        mock_org.client.request.return_value = {}
        cases.add_note(42, "AI findings", ai_session_id="sess-explicit")
        body = _extract_body(mock_org)
        assert body["ai_session_id"] == "sess-explicit"

    def test_no_ai_session_id_when_unset(self, cases, mock_org, monkeypatch):
        monkeypatch.delenv("LC_AI_SESSION_ID", raising=False)
        mock_org.client.request.return_value = {}
        cases.add_note(42, "Note text")
        body = _extract_body(mock_org)
        assert "ai_session_id" not in body


class TestUpdateNoteVisibility:
    def test_set_public(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.update_note_visibility(42, "evt-1", True)
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/cases/42/notes/evt-1")
        assert kwargs["query_params"] == {"oid": "test-oid"}
        body = json.loads(kwargs["raw_body"])
        assert body == {"is_public": True}

    def test_set_private(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.update_note_visibility(42, "evt-1", False)
        body = _extract_body(mock_org)
        assert body == {"is_public": False}


class TestBulkUpdate:
    def test_body_structure(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.bulk_update([1, 2], status="closed", classification="false_positive")
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/cases/bulk-update")
        body = json.loads(kwargs["raw_body"])
        assert body["oid"] == "test-oid"
        assert body["case_numbers"] == [1, 2]
        assert body["update"] == {"status": "closed", "classification": "false_positive"}

    def test_update_wrapper_present(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.bulk_update([1], status="resolved")
        body = _extract_body(mock_org)
        assert "update" in body
        assert body["update"] == {"status": "resolved"}

    def test_none_fields_excluded_from_update(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.bulk_update([1], status="closed", classification=None)
        body = _extract_body(mock_org)
        assert body["update"] == {"status": "closed"}


class TestMerge:
    def test_body_structure(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.merge(10, [11, 12])
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/cases/merge")
        body = json.loads(kwargs["raw_body"])
        assert body == {
            "oid": "test-oid",
            "target_case_number": 10,
            "source_case_numbers": [11, 12],
        }


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------


class TestListDetections:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"detections": []}
        cases.list_detections(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/cases/42/detections")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddDetection:
    _SAMPLE_DETECTION = {
        "detect_id": "det-1",
        "cat": "lateral_movement",
        "source": "dr-general",
        "routing": {"sid": "sid-1", "hostname": "ws-01"},
    }

    def test_minimal(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        det = {"detect_id": "det-1"}
        cases.add_detection(42, det)
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/cases/42/detections")
        body = json.loads(kwargs["raw_body"])
        assert body == {"detection": det}

    def test_with_full_detection(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_detection(42, self._SAMPLE_DETECTION)
        body = _extract_body(mock_org)
        assert body == {"detection": self._SAMPLE_DETECTION}


class TestRemoveDetection:
    def test_path_and_verb(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.remove_detection(42, "det-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/cases/42/detections/det-1")
        assert kwargs["query_params"] == {"oid": "test-oid"}


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class TestListEntities:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"entities": []}
        cases.list_entities(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/cases/42/entities")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddEntity:
    def test_required_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_entity(42, "ip", "10.0.0.1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/cases/42/entities")
        body = json.loads(kwargs["raw_body"])
        assert body["entity_type"] == "ip"
        assert body["entity_value"] == "10.0.0.1"

    def test_all_optional_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_entity(
            42, "hash", "abc123",
            note="Found in startup",
            verdict="malicious",
        )
        body = _extract_body(mock_org)
        assert body["entity_type"] == "hash"
        assert body["entity_value"] == "abc123"
        assert body["note"] == "Found in startup"
        assert body["verdict"] == "malicious"

    def test_none_optional_fields_excluded(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_entity(42, "domain", "evil.com", verdict=None, note=None)
        body = _extract_body(mock_org)
        assert "verdict" not in body
        assert "note" not in body


class TestUpdateEntity:
    def test_path_and_body(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.update_entity(42, "eid-1", verdict="malicious")
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/cases/42/entities/eid-1")
        body = json.loads(kwargs["raw_body"])
        assert body == {"verdict": "malicious"}


class TestRemoveEntity:
    def test_path_and_verb(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.remove_entity(42, "eid-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/cases/42/entities/eid-1")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestSearchEntities:
    def test_query_params(self, cases, mock_org):
        mock_org.client.request.return_value = {"results": []}
        cases.search_entities("ip", "10.0.0.1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/entities/search")
        assert kwargs["query_params"] == {
            "oids": "test-oid",
            "entity_type": "ip",
            "entity_value": "10.0.0.1",
        }


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TestListTelemetry:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"telemetry": []}
        cases.list_telemetry(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/cases/42/telemetry")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddTelemetry:
    _SAMPLE_EVENT = {
        "routing": {
            "this": "atom-uuid",
            "sid": "sid-uuid",
            "event_type": "NEW_PROCESS",
        },
    }

    def test_required_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_telemetry(42, self._SAMPLE_EVENT)
        body = _extract_body(mock_org)
        assert body == {"event": self._SAMPLE_EVENT}

    def test_with_optional_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_telemetry(
            42, self._SAMPLE_EVENT,
            note="Suspicious process, related to C2",
            verdict="suspicious",
        )
        body = _extract_body(mock_org)
        assert body["event"] == self._SAMPLE_EVENT
        assert body["note"] == "Suspicious process, related to C2"
        assert body["verdict"] == "suspicious"


class TestUpdateTelemetry:
    def test_path_and_body(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.update_telemetry(42, "tel-1", verdict="malicious")
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/cases/42/telemetry/tel-1")
        body = json.loads(kwargs["raw_body"])
        assert body == {"verdict": "malicious"}


class TestRemoveTelemetry:
    def test_path_and_verb(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.remove_telemetry(42, "tel-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/cases/42/telemetry/tel-1")


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


class TestListArtifacts:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        cases.list_artifacts(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/cases/42/artifacts")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddArtifact:
    def test_required_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_artifact(42, "/captures/test.pcap", "sensor-01")
        body = _extract_body(mock_org)
        assert body["path"] == "/captures/test.pcap"
        assert body["source"] == "sensor-01"

    def test_with_optional_fields(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_artifact(
            42, "/dumps/mem.dmp", "edr-collection",
            artifact_type="memory_dump",
            note="Process memory",
            verdict="suspicious",
        )
        body = _extract_body(mock_org)
        assert body["path"] == "/dumps/mem.dmp"
        assert body["source"] == "edr-collection"
        assert body["artifact_type"] == "memory_dump"
        assert body["note"] == "Process memory"
        assert body["verdict"] == "suspicious"


class TestRemoveArtifact:
    def test_path_and_verb(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.remove_artifact(42, "art-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/cases/42/artifacts/art-1")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExportCase:
    def test_calls_all_endpoints(self, cases, mock_org):
        case_data = {"case": {"case_id": "tid-1"}, "events": []}
        detections_data = {"detections": [{"detection_id": "det-1"}]}
        entities_data = {"entities": [{"entity_type": "ip", "entity_value": "10.0.0.1"}]}
        telemetry_data = {"telemetry": []}
        artifacts_data = {"artifacts": []}

        mock_org.client.request.side_effect = [
            case_data,
            detections_data,
            entities_data,
            telemetry_data,
            artifacts_data,
        ]
        result = cases.export_case(42)

        assert mock_org.client.request.call_count == 5
        assert result["case"] == {"case_id": "tid-1"}
        assert result["events"] == []
        assert result["detections"] == detections_data
        assert result["entities"] == entities_data
        assert result["telemetry"] == telemetry_data
        assert result["artifacts"] == artifacts_data

    def test_calls_correct_paths(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.export_case(42)

        calls = mock_org.client.request.call_args_list
        paths = [c[0][1] for c in calls]
        assert "api/v1/cases/42" in paths
        assert "api/v1/cases/42/detections" in paths
        assert "api/v1/cases/42/entities" in paths
        assert "api/v1/cases/42/telemetry" in paths
        assert "api/v1/cases/42/artifacts" in paths


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class TestReportSummary:
    def test_required_params(self, cases, mock_org):
        mock_org.client.request.return_value = {"report": {}}
        cases.report_summary(
            time_from="2026-01-01T00:00:00Z",
            time_to="2026-02-01T00:00:00Z",
        )
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/reports/summary")
        qp = kwargs["query_params"]
        assert qp["oids"] == "test-oid"
        assert qp["from"] == "2026-01-01T00:00:00Z"
        assert qp["to"] == "2026-02-01T00:00:00Z"
        assert "group_by" not in qp

    def test_with_group_by(self, cases, mock_org):
        mock_org.client.request.return_value = {"report": {}}
        cases.report_summary(
            time_from="2026-01-01T00:00:00Z",
            time_to="2026-02-01T00:00:00Z",
            group_by="severity",
        )
        _, kwargs = _extract_call(mock_org)
        assert kwargs["query_params"]["group_by"] == "severity"

    def test_no_body_sent(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.report_summary(
            time_from="2026-01-01T00:00:00Z",
            time_to="2026-02-01T00:00:00Z",
        )
        _, kwargs = _extract_call(mock_org)
        assert "raw_body" not in kwargs


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestDashboardCounts:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"counts": {}}
        cases.dashboard_counts()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/dashboard/counts")
        assert kwargs["query_params"] == {"oids": "test-oid"}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_path(self, cases, mock_org):
        mock_org.client.request.return_value = {"config": {}}
        cases.get_config()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/config/test-oid")

    def test_no_query_params(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.get_config()
        _, kwargs = _extract_call(mock_org)
        assert kwargs["query_params"] is None


class TestSetConfig:
    def test_path_and_body(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        config = {"severity_mapping": {"critical_min": 8}, "retention_days": 90}
        cases.set_config(config)
        args, kwargs = _extract_call(mock_org)
        assert args == ("PUT", "api/v1/config/test-oid")
        body = json.loads(kwargs["raw_body"])
        assert body == config
        assert kwargs["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# Assignees
# ---------------------------------------------------------------------------


class TestListAssignees:
    def test_path_and_query(self, cases, mock_org):
        mock_org.client.request.return_value = {"assignees": []}
        cases.list_assignees()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/assignees")
        assert kwargs["query_params"] == {"oids": "test-oid"}


# ---------------------------------------------------------------------------
# Orgs
# ---------------------------------------------------------------------------


class TestListOrgs:
    def test_path(self, cases, mock_org):
        mock_org.client.request.return_value = {"oids": ["org-1"]}
        cases.list_orgs()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/orgs")

    def test_no_query_params(self, cases, mock_org):
        mock_org.client.request.return_value = {"oids": []}
        cases.list_orgs()
        _, kwargs = _extract_call(mock_org)
        assert kwargs["query_params"] is None


# ---------------------------------------------------------------------------
# _request internals
# ---------------------------------------------------------------------------


class TestRequestMethod:
    def test_alt_root_always_set(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.list_cases()
        _, kwargs = _extract_call(mock_org)
        assert "alt_root" in kwargs
        assert kwargs["alt_root"] == "https://cases.limacharlie.io"

    def test_get_no_raw_body(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.get_case(42)
        _, kwargs = _extract_call(mock_org)
        assert "raw_body" not in kwargs
        assert "content_type" not in kwargs

    def test_post_sends_json(self, cases, mock_org):
        mock_org.client.request.return_value = {}
        cases.add_note(42, "text")
        _, kwargs = _extract_call(mock_org)
        assert kwargs["content_type"] == "application/json"
        assert isinstance(kwargs["raw_body"], bytes)
        parsed = json.loads(kwargs["raw_body"])
        assert isinstance(parsed, dict)
