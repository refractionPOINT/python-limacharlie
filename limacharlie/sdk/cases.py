"""Cases SDK for LimaCharlie v2.

Wraps the ext-cases REST API for SOC case lifecycle management,
investigation tracking (entities, telemetry, artifacts), reporting,
and configuration.
"""

from __future__ import annotations

import json
import os
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

from .extensions import Extensions

_DEFAULT_API_ROOT = "https://cases.limacharlie.io"


class Cases:
    """Cases system client for LimaCharlie."""

    def __init__(self, org: Organization, api_root: str | None = None) -> None:
        self._org = org
        self._api_root = api_root or os.environ.get(
            "LC_CASES_API_ROOT", _DEFAULT_API_ROOT
        )

    @property
    def oid(self) -> str:
        return self._org.oid

    _EXTENSION_NAME = "ext-cases"

    def create_case(
        self,
        detection: dict | None = None,
        *,
        severity: str | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """Create a new case via the ext-cases extension.

        Case creation goes through the LimaCharlie extension request
        mechanism (``create_case`` action) rather than the cases
        REST API.

        Args:
            detection: Optional full LC detection dict.  The backend
                extracts detect_id, cat, source, routing.sid,
                routing.hostname, and detect_mtd.level automatically.
                Omit to create an empty investigation case.
            severity: Optional case severity override
                (critical, high, medium, low, info).
            summary: Optional case summary set at creation time
                (max 8192 chars).
        """
        data: dict[str, Any] = {}
        if detection is not None:
            # Pass the detection dict directly — the gzdata encoding
            # already JSON-serializes the full data dict, so json.dumps
            # here would double-encode it into a string that the LC
            # backend drops (schema type "json" expects an object).
            data["detection"] = detection
        if severity is not None:
            data["severity"] = severity
        if summary is not None:
            data["summary"] = summary
        ext = Extensions(self._org)
        return ext.request(self._EXTENSION_NAME, "create_case", data=data)

    def _request(
        self,
        verb: str,
        path: str,
        query_params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "alt_root": self._api_root,
            "query_params": query_params,
        }
        if body is not None:
            kwargs["raw_body"] = json.dumps(body).encode()
            kwargs["content_type"] = "application/json"
        return self._org.client.request(verb, f"api/v1/{path}", **kwargs)

    # ------------------------------------------------------------------
    # Cases
    # ------------------------------------------------------------------

    def list_cases(
        self,
        *,
        status: list[str] | None = None,
        severity: list[str] | None = None,
        classification: list[str] | None = None,
        assignee: str | None = None,
        search: str | None = None,
        sensor_id: str | None = None,
        tag: list[str] | None = None,
        sort: str | None = None,
        order: str | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List cases with optional filtering and pagination.

        Args:
            search: Full-text search across detection_cat and hostname
                on linked CaseDetection records (not case-level fields).
        """
        qp: dict[str, str] = {"oids": self.oid}
        if status:
            qp["status"] = ",".join(status)
        if severity:
            qp["severity"] = ",".join(severity)
        if classification:
            qp["classification"] = ",".join(classification)
        if assignee:
            qp["assignee"] = assignee
        if search:
            qp["search"] = search
        if sensor_id:
            qp["sid"] = sensor_id
        if tag:
            qp["tag"] = ",".join(tag)
        if sort:
            qp["sort"] = sort
        if order:
            qp["order"] = order
        if page_size is not None:
            qp["page_size"] = str(page_size)
        if page_token:
            qp["page_token"] = page_token
        return self._request("GET", "cases", query_params=qp)

    def get_case(self, case_number: int) -> dict[str, Any]:
        """Get a single case with its full event timeline."""
        return self._request(
            "GET",
            f"cases/{case_number}",
            query_params={"oid": self.oid},
        )

    def update_case(self, case_number: int, **fields: Any) -> dict[str, Any]:
        """Update a case.

        Accepted fields: status, severity, assignees, classification,
        summary, conclusion, tags.

        Note: detection-level fields (detection_id, detection_cat,
        detection_source, detection_priority, sensor_id, hostname)
        live on CaseDetection records, not on the Case itself.
        Use :meth:`add_detection` / :meth:`list_detections` to manage them.
        """
        return self._request(
            "PATCH",
            f"cases/{case_number}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def add_note(
        self,
        case_number: int,
        content: str,
        note_type: str | None = None,
    ) -> dict[str, Any]:
        """Add a note to a case."""
        body: dict[str, Any] = {"content": content}
        if note_type:
            body["note_type"] = note_type
        return self._request(
            "POST",
            f"cases/{case_number}/notes",
            query_params={"oid": self.oid},
            body=body,
        )

    def bulk_update(
        self,
        case_numbers: list[int],
        **fields: Any,
    ) -> dict[str, Any]:
        """Bulk update up to 200 cases."""
        body: dict[str, Any] = {
            "oid": self.oid,
            "case_numbers": case_numbers,
            "update": {k: v for k, v in fields.items() if v is not None},
        }
        return self._request("POST", "cases/bulk-update", body=body)

    def merge(
        self,
        target_case_number: int,
        source_case_numbers: list[int],
    ) -> dict[str, Any]:
        """Merge source cases into a target case."""
        return self._request(
            "POST",
            "cases/merge",
            body={
                "oid": self.oid,
                "target_case_number": target_case_number,
                "source_case_numbers": source_case_numbers,
            },
        )

    # ------------------------------------------------------------------
    # Detections
    # ------------------------------------------------------------------

    def list_detections(self, case_number: int) -> dict[str, Any]:
        """List detections linked to a case."""
        return self._request(
            "GET",
            f"cases/{case_number}/detections",
            query_params={"oid": self.oid},
        )

    def add_detection(
        self,
        case_number: int,
        detection: dict,
    ) -> dict[str, Any]:
        """Link a detection to a case.

        Args:
            case_number: Case number.
            detection: Full LC detection dict.  The backend extracts
                detect_id, cat, source, routing, and detect_mtd
                automatically.
        """
        return self._request(
            "POST",
            f"cases/{case_number}/detections",
            query_params={"oid": self.oid},
            body={"detection": detection},
        )

    def remove_detection(
        self,
        case_number: int,
        detection_id: str,
    ) -> dict[str, Any]:
        """Remove a detection link from a case."""
        return self._request(
            "DELETE",
            f"cases/{case_number}/detections/{detection_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Entities (IOCs)
    # ------------------------------------------------------------------

    def list_entities(self, case_number: int) -> dict[str, Any]:
        """List entities on a case."""
        return self._request(
            "GET",
            f"cases/{case_number}/entities",
            query_params={"oid": self.oid},
        )

    def add_entity(
        self,
        case_number: int,
        entity_type: str,
        entity_value: str,
        *,
        note: str | None = None,
        verdict: str | None = None,
    ) -> dict[str, Any]:
        """Add an entity/IOC to a case.

        Args:
            case_number: Case number.
            entity_type: One of ip, domain, hash, url, user, email,
                file, process, registry, other.
            entity_value: Entity value (max 1024 chars).
            note: Analyst note (max 2048 chars).
            verdict: Verdict assessment.
        """
        body: dict[str, Any] = {
            "entity_type": entity_type,
            "entity_value": entity_value,
        }
        if note is not None:
            body["note"] = note
        if verdict is not None:
            body["verdict"] = verdict
        return self._request(
            "POST",
            f"cases/{case_number}/entities",
            query_params={"oid": self.oid},
            body=body,
        )

    def update_entity(
        self,
        case_number: int,
        entity_id: str,
        *,
        note: str | None = None,
        verdict: str | None = None,
    ) -> dict[str, Any]:
        """Update an entity on a case.

        Args:
            case_number: Case number.
            entity_id: Entity ID to update.
            note: Analyst note (max 2048 chars).
            verdict: Verdict assessment.
        """
        body: dict[str, Any] = {}
        if note is not None:
            body["note"] = note
        if verdict is not None:
            body["verdict"] = verdict
        return self._request(
            "PATCH",
            f"cases/{case_number}/entities/{entity_id}",
            query_params={"oid": self.oid},
            body=body,
        )

    def remove_entity(
        self,
        case_number: int,
        entity_id: str,
    ) -> dict[str, Any]:
        """Remove an entity from a case."""
        return self._request(
            "DELETE",
            f"cases/{case_number}/entities/{entity_id}",
            query_params={"oid": self.oid},
        )

    def search_entities(
        self,
        entity_type: str,
        entity_value: str,
    ) -> dict[str, Any]:
        """Search for entities across cases."""
        return self._request(
            "GET",
            "entities/search",
            query_params={
                "oids": self.oid,
                "entity_type": entity_type,
                "entity_value": entity_value,
            },
        )

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def list_telemetry(self, case_number: int) -> dict[str, Any]:
        """List telemetry references on a case."""
        return self._request(
            "GET",
            f"cases/{case_number}/telemetry",
            query_params={"oid": self.oid},
        )

    def add_telemetry(
        self,
        case_number: int,
        event: dict,
        *,
        note: str | None = None,
        verdict: str | None = None,
    ) -> dict[str, Any]:
        """Link a telemetry event reference to a case.

        Args:
            case_number: Case number.
            event: Full LC event dict.  The backend extracts
                routing.this (atom), routing.sid, and
                routing.event_type automatically.
            note: Analyst note (max 2048 chars).
            verdict: Verdict assessment.
        """
        body: dict[str, Any] = {"event": event}
        if note is not None:
            body["note"] = note
        if verdict is not None:
            body["verdict"] = verdict
        return self._request(
            "POST",
            f"cases/{case_number}/telemetry",
            query_params={"oid": self.oid},
            body=body,
        )

    def update_telemetry(
        self,
        case_number: int,
        telemetry_id: str,
        *,
        note: str | None = None,
        verdict: str | None = None,
    ) -> dict[str, Any]:
        """Update a telemetry reference on a case.

        Args:
            case_number: Case number.
            telemetry_id: Telemetry reference ID.
            note: Analyst note (max 2048 chars).
            verdict: Verdict assessment.
        """
        body: dict[str, Any] = {}
        if note is not None:
            body["note"] = note
        if verdict is not None:
            body["verdict"] = verdict
        return self._request(
            "PATCH",
            f"cases/{case_number}/telemetry/{telemetry_id}",
            query_params={"oid": self.oid},
            body=body,
        )

    def remove_telemetry(
        self,
        case_number: int,
        telemetry_id: str,
    ) -> dict[str, Any]:
        """Remove a telemetry reference from a case."""
        return self._request(
            "DELETE",
            f"cases/{case_number}/telemetry/{telemetry_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self, case_number: int) -> dict[str, Any]:
        """List artifacts on a case."""
        return self._request(
            "GET",
            f"cases/{case_number}/artifacts",
            query_params={"oid": self.oid},
        )

    def add_artifact(
        self,
        case_number: int,
        path: str,
        source: str,
        *,
        artifact_type: str | None = None,
        note: str | None = None,
        verdict: str | None = None,
    ) -> dict[str, Any]:
        """Add a forensic artifact reference to a case.

        Args:
            case_number: Case number.
            path: Artifact path or location.
            source: Artifact source identifier.
            artifact_type: Optional artifact type (e.g., pcap, memory_dump).
            note: Analyst note (max 2048 chars).
            verdict: Verdict assessment.
        """
        body: dict[str, Any] = {"path": path, "source": source}
        if artifact_type is not None:
            body["artifact_type"] = artifact_type
        if note is not None:
            body["note"] = note
        if verdict is not None:
            body["verdict"] = verdict
        return self._request(
            "POST",
            f"cases/{case_number}/artifacts",
            query_params={"oid": self.oid},
            body=body,
        )

    def remove_artifact(
        self,
        case_number: int,
        artifact_id: str,
    ) -> dict[str, Any]:
        """Remove an artifact from a case."""
        return self._request(
            "DELETE",
            f"cases/{case_number}/artifacts/{artifact_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_case(self, case_number: int) -> dict[str, Any]:
        """Export a case with all its components in a single object.

        Fetches the case (with event timeline), detections, entities,
        telemetry, and artifacts, and returns them combined.
        """
        result = self.get_case(case_number)
        result["detections"] = self.list_detections(case_number)
        result["entities"] = self.list_entities(case_number)
        result["telemetry"] = self.list_telemetry(case_number)
        result["artifacts"] = self.list_artifacts(case_number)
        return result

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def report_summary(
        self,
        *,
        time_from: str,
        time_to: str,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive SOC report with MTTA/MTTR/TP-FP metrics."""
        qp: dict[str, str] = {
            "oids": self.oid,
            "from": time_from,
            "to": time_to,
        }
        if group_by:
            qp["group_by"] = group_by
        return self._request("GET", "reports/summary", query_params=qp)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def dashboard_counts(self) -> dict[str, Any]:
        """Get real-time case counts by status/severity with SLA breaches."""
        return self._request(
            "GET",
            "dashboard/counts",
            query_params={"oids": self.oid},
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Get org cases configuration."""
        return self._request("GET", f"config/{self.oid}")

    def set_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update org cases configuration."""
        return self._request("PUT", f"config/{self.oid}", body=config)

    # ------------------------------------------------------------------
    # Assignees
    # ------------------------------------------------------------------

    def list_assignees(self) -> dict[str, Any]:
        """Get list of unique assignees across cases."""
        return self._request(
            "GET",
            "assignees",
            query_params={"oids": self.oid},
        )
