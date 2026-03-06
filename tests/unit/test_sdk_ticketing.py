"""Tests for limacharlie.sdk.ticketing module."""

import json
from unittest.mock import MagicMock, patch, call
import pytest

from limacharlie.sdk.ticketing import Ticketing


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    org.client._jwt = "fake-jwt-token"
    return org


@pytest.fixture
def ticketing(mock_org):
    return Ticketing(mock_org)


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


class TestTicketingInit:
    def test_default_api_root(self, mock_org):
        t = Ticketing(mock_org)
        assert "ext-ticketing-api" in t._api_root

    def test_custom_api_root(self, mock_org):
        t = Ticketing(mock_org, api_root="https://custom.example.com")
        assert t._api_root == "https://custom.example.com"

    def test_env_override(self, mock_org, monkeypatch):
        monkeypatch.setenv("LC_TICKETING_API_ROOT", "https://env.example.com")
        t = Ticketing(mock_org)
        assert t._api_root == "https://env.example.com"

    def test_explicit_api_root_overrides_env(self, mock_org, monkeypatch):
        monkeypatch.setenv("LC_TICKETING_API_ROOT", "https://env.example.com")
        t = Ticketing(mock_org, api_root="https://explicit.example.com")
        assert t._api_root == "https://explicit.example.com"

    def test_oid_property(self, ticketing):
        assert ticketing.oid == "test-oid"


# ---------------------------------------------------------------------------
# Create Ticket (via extension request)
# ---------------------------------------------------------------------------


class TestCreateTicket:
    _SAMPLE_DETECTION = {
        "detect_id": "det-1",
        "cat": "lateral_movement",
        "source": "dr-general",
        "routing": {"sid": "sid-1", "hostname": "ws-01"},
        "detect_mtd": {"level": "high"},
    }

    def test_calls_extension_request(self, ticketing, mock_org):
        with patch("limacharlie.sdk.ticketing.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1, "ticket_id": "tid-new"}
            result = ticketing.create_ticket(self._SAMPLE_DETECTION)
            MockExt.assert_called_once_with(mock_org)
            mock_ext.request.assert_called_once_with(
                "ext-ticketing", "create_ticket",
                data={"detection": json.dumps(self._SAMPLE_DETECTION)},
            )
            assert result["ticket_id"] == "tid-new"

    def test_all_optional_fields(self, ticketing, mock_org):
        with patch("limacharlie.sdk.ticketing.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            ticketing.create_ticket(self._SAMPLE_DETECTION, severity="high")
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {
                "detection": json.dumps(self._SAMPLE_DETECTION),
                "severity": "high",
            }

    def test_none_optional_fields_excluded(self, ticketing, mock_org):
        with patch("limacharlie.sdk.ticketing.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            ticketing.create_ticket(self._SAMPLE_DETECTION, severity=None)
            call_data = mock_ext.request.call_args[1]["data"]
            assert "severity" not in call_data

    def test_without_detection(self, ticketing, mock_org):
        with patch("limacharlie.sdk.ticketing.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            ticketing.create_ticket()
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {}

    def test_without_detection_with_severity(self, ticketing, mock_org):
        with patch("limacharlie.sdk.ticketing.Extensions") as MockExt:
            mock_ext = MagicMock()
            MockExt.return_value = mock_ext
            mock_ext.request.return_value = {"created": 1}
            ticketing.create_ticket(severity="medium")
            call_data = mock_ext.request.call_args[1]["data"]
            assert call_data == {"severity": "medium"}


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


class TestListTickets:
    def test_minimal(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"tickets": []}
        ticketing.list_tickets()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/tickets")
        assert kwargs["query_params"] == {"oids": "test-oid"}

    def test_all_filters(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"tickets": []}
        ticketing.list_tickets(
            status=["new", "acknowledged"],
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
        assert qp["status"] == "new,acknowledged"
        assert qp["severity"] == "critical"
        assert qp["classification"] == "pending"
        assert qp["assignee"] == "alice@example.com"
        assert qp["search"] == "mimikatz"
        assert qp["sort"] == "severity"
        assert qp["order"] == "asc"
        assert qp["page_size"] == "20"
        assert qp["page_token"] == "abc123"

    def test_empty_lists_omitted(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"tickets": []}
        ticketing.list_tickets(status=[], severity=None)
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert "status" not in qp
        assert "severity" not in qp

    def test_sensor_id_filter(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"tickets": []}
        ticketing.list_tickets(sensor_id="abc-sensor-123")
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert qp["sensor_id"] == "abc-sensor-123"

    def test_sensor_id_none_omitted(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"tickets": []}
        ticketing.list_tickets(sensor_id=None)
        _, kwargs = _extract_call(mock_org)
        qp = kwargs["query_params"]
        assert "sensor_id" not in qp


class TestGetTicket:
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"ticket": {}}
        ticketing.get_ticket(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/tickets/42")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestUpdateTicket:
    def test_patch_with_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"ticket": {}}
        ticketing.update_ticket(42, status="acknowledged", assignee="bob@example.com")
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/tickets/42")
        assert kwargs["query_params"] == {"oid": "test-oid"}
        body = json.loads(kwargs["raw_body"])
        assert body == {"status": "acknowledged", "assignee": "bob@example.com"}
        assert kwargs["content_type"] == "application/json"

    def test_none_fields_excluded(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"ticket": {}}
        ticketing.update_ticket(42, status="resolved", assignee=None, classification=None)
        body = _extract_body(mock_org)
        assert body == {"status": "resolved"}


class TestAddNote:
    def test_with_content_only(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_note(42, "Triage complete")
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/tickets/42/notes")
        assert kwargs["query_params"] == {"oid": "test-oid"}
        body = json.loads(kwargs["raw_body"])
        assert body == {"content": "Triage complete"}

    def test_with_note_type(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_note(42, "Analysis result", note_type="analysis")
        body = _extract_body(mock_org)
        assert body == {"content": "Analysis result", "note_type": "analysis"}

    def test_none_note_type_excluded(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_note(42, "Note text", note_type=None)
        body = _extract_body(mock_org)
        assert "note_type" not in body


class TestBulkUpdate:
    def test_body_structure(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.bulk_update([1, 2], status="closed", classification="false_positive")
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/tickets/bulk-update")
        body = json.loads(kwargs["raw_body"])
        assert body["oid"] == "test-oid"
        assert body["ticket_numbers"] == [1, 2]
        assert body["update"] == {"status": "closed", "classification": "false_positive"}

    def test_update_wrapper_present(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.bulk_update([1], status="resolved")
        body = _extract_body(mock_org)
        assert "update" in body
        assert body["update"] == {"status": "resolved"}

    def test_none_fields_excluded_from_update(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.bulk_update([1], status="closed", classification=None)
        body = _extract_body(mock_org)
        assert body["update"] == {"status": "closed"}


class TestMerge:
    def test_body_structure(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.merge(10, [11, 12])
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/tickets/merge")
        body = json.loads(kwargs["raw_body"])
        assert body == {
            "oid": "test-oid",
            "target_ticket_number": 10,
            "source_ticket_numbers": [11, 12],
        }


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------


class TestListDetections:
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"detections": []}
        ticketing.list_detections(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/tickets/42/detections")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddDetection:
    _SAMPLE_DETECTION = {
        "detect_id": "det-1",
        "cat": "lateral_movement",
        "source": "dr-general",
        "routing": {"sid": "sid-1", "hostname": "ws-01"},
    }

    def test_minimal(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        det = {"detect_id": "det-1"}
        ticketing.add_detection(42, det)
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/tickets/42/detections")
        body = json.loads(kwargs["raw_body"])
        assert body == {"detection": det}

    def test_with_full_detection(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_detection(42, self._SAMPLE_DETECTION)
        body = _extract_body(mock_org)
        assert body == {"detection": self._SAMPLE_DETECTION}


class TestRemoveDetection:
    def test_path_and_verb(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.remove_detection(42, "det-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/tickets/42/detections/det-1")
        assert kwargs["query_params"] == {"oid": "test-oid"}


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class TestListEntities:
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"entities": []}
        ticketing.list_entities(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/tickets/42/entities")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddEntity:
    def test_required_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_entity(42, "ip", "10.0.0.1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("POST", "api/v1/tickets/42/entities")
        body = json.loads(kwargs["raw_body"])
        assert body["entity_type"] == "ip"
        assert body["entity_value"] == "10.0.0.1"

    def test_all_optional_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_entity(
            42, "hash", "abc123",
            name="Evil hash",
            verdict="malicious",
            context="Found in startup",
            first_seen="2026-01-01T00:00:00Z",
            last_seen="2026-01-02T00:00:00Z",
        )
        body = _extract_body(mock_org)
        assert body["entity_type"] == "hash"
        assert body["entity_value"] == "abc123"
        assert body["name"] == "Evil hash"
        assert body["verdict"] == "malicious"
        assert body["context"] == "Found in startup"
        assert body["first_seen"] == "2026-01-01T00:00:00Z"
        assert body["last_seen"] == "2026-01-02T00:00:00Z"

    def test_none_optional_fields_excluded(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_entity(42, "domain", "evil.com", verdict=None, context=None)
        body = _extract_body(mock_org)
        assert "verdict" not in body
        assert "context" not in body


class TestUpdateEntity:
    def test_path_and_body(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.update_entity(42, "eid-1", verdict="malicious")
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/tickets/42/entities/eid-1")
        body = json.loads(kwargs["raw_body"])
        assert body == {"verdict": "malicious"}


class TestRemoveEntity:
    def test_path_and_verb(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.remove_entity(42, "eid-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/tickets/42/entities/eid-1")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestSearchEntities:
    def test_query_params(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"results": []}
        ticketing.search_entities("ip", "10.0.0.1")
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
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"telemetry": []}
        ticketing.list_telemetry(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/tickets/42/telemetry")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddTelemetry:
    _SAMPLE_EVENT = {
        "routing": {
            "this": "atom-uuid",
            "sid": "sid-uuid",
            "event_type": "NEW_PROCESS",
        },
    }

    def test_required_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_telemetry(42, self._SAMPLE_EVENT)
        body = _extract_body(mock_org)
        assert body == {"event": self._SAMPLE_EVENT}

    def test_with_optional_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_telemetry(
            42, self._SAMPLE_EVENT,
            event_summary="Suspicious process",
            verdict="suspicious",
            relevance="Related to C2",
        )
        body = _extract_body(mock_org)
        assert body["event"] == self._SAMPLE_EVENT
        assert body["event_summary"] == "Suspicious process"
        assert body["verdict"] == "suspicious"
        assert body["relevance"] == "Related to C2"


class TestUpdateTelemetry:
    def test_path_and_body(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.update_telemetry(42, "tel-1", verdict="malicious")
        args, kwargs = _extract_call(mock_org)
        assert args == ("PATCH", "api/v1/tickets/42/telemetry/tel-1")
        body = json.loads(kwargs["raw_body"])
        assert body == {"verdict": "malicious"}


class TestRemoveTelemetry:
    def test_path_and_verb(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.remove_telemetry(42, "tel-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/tickets/42/telemetry/tel-1")


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


class TestListArtifacts:
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        ticketing.list_artifacts(42)
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/tickets/42/artifacts")
        assert kwargs["query_params"] == {"oid": "test-oid"}


class TestAddArtifact:
    def test_required_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_artifact(42, "pcap")
        body = _extract_body(mock_org)
        assert body["artifact_type"] == "pcap"

    def test_with_optional_fields(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_artifact(
            42, "memory_dump",
            description="Process memory",
            verdict="suspicious",
        )
        body = _extract_body(mock_org)
        assert body["artifact_type"] == "memory_dump"
        assert body["description"] == "Process memory"
        assert body["verdict"] == "suspicious"


class TestRemoveArtifact:
    def test_path_and_verb(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.remove_artifact(42, "art-1")
        args, kwargs = _extract_call(mock_org)
        assert args == ("DELETE", "api/v1/tickets/42/artifacts/art-1")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExportTicket:
    def test_calls_all_endpoints(self, ticketing, mock_org):
        ticket_data = {"ticket": {"ticket_id": "tid-1"}, "events": []}
        detections_data = {"detections": [{"detection_id": "det-1"}]}
        entities_data = {"entities": [{"entity_type": "ip", "entity_value": "10.0.0.1"}]}
        telemetry_data = {"telemetry": []}
        artifacts_data = {"artifacts": []}

        mock_org.client.request.side_effect = [
            ticket_data,
            detections_data,
            entities_data,
            telemetry_data,
            artifacts_data,
        ]
        result = ticketing.export_ticket(42)

        assert mock_org.client.request.call_count == 5
        assert result["ticket"] == {"ticket_id": "tid-1"}
        assert result["events"] == []
        assert result["detections"] == detections_data
        assert result["entities"] == entities_data
        assert result["telemetry"] == telemetry_data
        assert result["artifacts"] == artifacts_data

    def test_calls_correct_paths(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.export_ticket(42)

        calls = mock_org.client.request.call_args_list
        paths = [c[0][1] for c in calls]
        assert "api/v1/tickets/42" in paths
        assert "api/v1/tickets/42/detections" in paths
        assert "api/v1/tickets/42/entities" in paths
        assert "api/v1/tickets/42/telemetry" in paths
        assert "api/v1/tickets/42/artifacts" in paths


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class TestReportSummary:
    def test_required_params(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"report": {}}
        ticketing.report_summary(
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

    def test_with_group_by(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"report": {}}
        ticketing.report_summary(
            time_from="2026-01-01T00:00:00Z",
            time_to="2026-02-01T00:00:00Z",
            group_by="severity",
        )
        _, kwargs = _extract_call(mock_org)
        assert kwargs["query_params"]["group_by"] == "severity"

    def test_no_body_sent(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.report_summary(
            time_from="2026-01-01T00:00:00Z",
            time_to="2026-02-01T00:00:00Z",
        )
        _, kwargs = _extract_call(mock_org)
        assert "raw_body" not in kwargs


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestDashboardCounts:
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"counts": {}}
        ticketing.dashboard_counts()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/dashboard/counts")
        assert kwargs["query_params"] == {"oids": "test-oid"}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_path(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"config": {}}
        ticketing.get_config()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/config/test-oid")

    def test_no_query_params(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.get_config()
        _, kwargs = _extract_call(mock_org)
        assert kwargs["query_params"] is None


class TestSetConfig:
    def test_path_and_body(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        config = {"severity_mapping": {"critical_min": 8}, "retention_days": 90}
        ticketing.set_config(config)
        args, kwargs = _extract_call(mock_org)
        assert args == ("PUT", "api/v1/config/test-oid")
        body = json.loads(kwargs["raw_body"])
        assert body == config
        assert kwargs["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# Assignees
# ---------------------------------------------------------------------------


class TestListAssignees:
    def test_path_and_query(self, ticketing, mock_org):
        mock_org.client.request.return_value = {"assignees": []}
        ticketing.list_assignees()
        args, kwargs = _extract_call(mock_org)
        assert args == ("GET", "api/v1/assignees")
        assert kwargs["query_params"] == {"oids": "test-oid"}


# ---------------------------------------------------------------------------
# _request internals
# ---------------------------------------------------------------------------


class TestRequestMethod:
    def test_alt_root_always_set(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.list_tickets()
        _, kwargs = _extract_call(mock_org)
        assert "alt_root" in kwargs
        assert "ext-ticketing-api" in kwargs["alt_root"]

    def test_get_no_raw_body(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.get_ticket(42)
        _, kwargs = _extract_call(mock_org)
        assert "raw_body" not in kwargs
        assert "content_type" not in kwargs

    def test_post_sends_json(self, ticketing, mock_org):
        mock_org.client.request.return_value = {}
        ticketing.add_note(42, "text")
        _, kwargs = _extract_call(mock_org)
        assert kwargs["content_type"] == "application/json"
        assert isinstance(kwargs["raw_body"], bytes)
        parsed = json.loads(kwargs["raw_body"])
        assert isinstance(parsed, dict)
