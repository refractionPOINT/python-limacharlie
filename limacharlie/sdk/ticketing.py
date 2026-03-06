"""Ticketing SDK for LimaCharlie v2.

Wraps the ext-ticketing REST API for SOC ticket lifecycle management,
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

_DEFAULT_API_ROOT = "https://ext-ticketing-api-ackbwtk5nq-uc.a.run.app"


class Ticketing:
    """Ticketing system client for LimaCharlie."""

    def __init__(self, org: Organization, api_root: str | None = None) -> None:
        self._org = org
        self._api_root = api_root or os.environ.get(
            "LC_TICKETING_API_ROOT", _DEFAULT_API_ROOT
        )

    @property
    def oid(self) -> str:
        return self._org.oid

    # ------------------------------------------------------------------
    # Extension name for ticket creation via the LC extension API.
    # ------------------------------------------------------------------

    _EXTENSION_NAME = "ext-ticketing"

    def create_ticket(
        self,
        detection: dict | None = None,
        *,
        severity: str | None = None,
    ) -> dict[str, Any]:
        """Create a new ticket via the ext-ticketing extension.

        Ticket creation goes through the LimaCharlie extension request
        mechanism (``create_ticket`` action) rather than the ticketing
        REST API.

        Args:
            detection: Optional full LC detection dict.  The backend
                extracts detect_id, cat, source, routing.sid,
                routing.hostname, and detect_mtd.level automatically.
                Omit to create an empty investigation ticket.
            severity: Optional ticket severity override
                (critical, high, medium, low).
        """
        data: dict[str, Any] = {}
        if detection is not None:
            # The extension schema declares detection as type "json",
            # which the platform validates as a JSON string (not a dict).
            data["detection"] = json.dumps(detection)
        if severity is not None:
            data["severity"] = severity
        ext = Extensions(self._org)
        return ext.request(self._EXTENSION_NAME, "create_ticket", data=data)

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
    # Tickets
    # ------------------------------------------------------------------

    def list_tickets(
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
        """List tickets with optional filtering and pagination."""
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
            qp["sensor_id"] = sensor_id
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
        return self._request("GET", "tickets", query_params=qp)

    def get_ticket(self, ticket_number: int) -> dict[str, Any]:
        """Get a single ticket with its full event timeline."""
        return self._request(
            "GET",
            f"tickets/{ticket_number}",
            query_params={"oid": self.oid},
        )

    def update_ticket(self, ticket_number: int, **fields: Any) -> dict[str, Any]:
        """Update a ticket.

        Accepted fields: status, assignee, classification,
        escalation_group, investigation_id, summary, conclusion, tags.
        """
        return self._request(
            "PATCH",
            f"tickets/{ticket_number}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def add_note(
        self,
        ticket_number: int,
        content: str,
        note_type: str | None = None,
    ) -> dict[str, Any]:
        """Add a note to a ticket."""
        body: dict[str, Any] = {"content": content}
        if note_type:
            body["note_type"] = note_type
        return self._request(
            "POST",
            f"tickets/{ticket_number}/notes",
            query_params={"oid": self.oid},
            body=body,
        )

    def bulk_update(
        self,
        ticket_numbers: list[int],
        **fields: Any,
    ) -> dict[str, Any]:
        """Bulk update up to 200 tickets."""
        body: dict[str, Any] = {
            "oid": self.oid,
            "ticket_numbers": ticket_numbers,
            "update": {k: v for k, v in fields.items() if v is not None},
        }
        return self._request("POST", "tickets/bulk-update", body=body)

    def merge(
        self,
        target_ticket_number: int,
        source_ticket_numbers: list[int],
    ) -> dict[str, Any]:
        """Merge source tickets into a target ticket."""
        return self._request(
            "POST",
            "tickets/merge",
            body={
                "oid": self.oid,
                "target_ticket_number": target_ticket_number,
                "source_ticket_numbers": source_ticket_numbers,
            },
        )

    # ------------------------------------------------------------------
    # Detections
    # ------------------------------------------------------------------

    def list_detections(self, ticket_number: int) -> dict[str, Any]:
        """List detections linked to a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_number}/detections",
            query_params={"oid": self.oid},
        )

    def add_detection(
        self,
        ticket_number: int,
        detection: dict,
    ) -> dict[str, Any]:
        """Link a detection to a ticket.

        Args:
            ticket_number: Ticket number.
            detection: Full LC detection dict.  The backend extracts
                detect_id, cat, source, routing, and detect_mtd
                automatically.
        """
        return self._request(
            "POST",
            f"tickets/{ticket_number}/detections",
            query_params={"oid": self.oid},
            body={"detection": detection},
        )

    def remove_detection(
        self,
        ticket_number: int,
        detection_id: str,
    ) -> dict[str, Any]:
        """Remove a detection link from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_number}/detections/{detection_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Entities (IOCs)
    # ------------------------------------------------------------------

    def list_entities(self, ticket_number: int) -> dict[str, Any]:
        """List entities on a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_number}/entities",
            query_params={"oid": self.oid},
        )

    def add_entity(
        self,
        ticket_number: int,
        entity_type: str,
        entity_value: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Add an entity/IOC to a ticket."""
        body: dict[str, Any] = {
            "entity_type": entity_type,
            "entity_value": entity_value,
        }
        body.update({k: v for k, v in fields.items() if v is not None})
        return self._request(
            "POST",
            f"tickets/{ticket_number}/entities",
            query_params={"oid": self.oid},
            body=body,
        )

    def update_entity(
        self,
        ticket_number: int,
        entity_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update an entity on a ticket."""
        return self._request(
            "PATCH",
            f"tickets/{ticket_number}/entities/{entity_id}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def remove_entity(
        self,
        ticket_number: int,
        entity_id: str,
    ) -> dict[str, Any]:
        """Remove an entity from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_number}/entities/{entity_id}",
            query_params={"oid": self.oid},
        )

    def search_entities(
        self,
        entity_type: str,
        entity_value: str,
    ) -> dict[str, Any]:
        """Search for entities across tickets."""
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

    def list_telemetry(self, ticket_number: int) -> dict[str, Any]:
        """List telemetry references on a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_number}/telemetry",
            query_params={"oid": self.oid},
        )

    def add_telemetry(
        self,
        ticket_number: int,
        event: dict,
        *,
        event_summary: str | None = None,
        verdict: str | None = None,
        relevance: str | None = None,
    ) -> dict[str, Any]:
        """Link a telemetry event reference to a ticket.

        Args:
            ticket_number: Ticket number.
            event: Full LC event dict.  The backend extracts
                routing.this (atom), routing.sid, and
                routing.event_type automatically.
            event_summary: Human-readable event summary.
            verdict: Verdict assessment.
            relevance: Relevance notes.
        """
        body: dict[str, Any] = {"event": event}
        if event_summary is not None:
            body["event_summary"] = event_summary
        if verdict is not None:
            body["verdict"] = verdict
        if relevance is not None:
            body["relevance"] = relevance
        return self._request(
            "POST",
            f"tickets/{ticket_number}/telemetry",
            query_params={"oid": self.oid},
            body=body,
        )

    def update_telemetry(
        self,
        ticket_number: int,
        telemetry_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update a telemetry reference on a ticket."""
        return self._request(
            "PATCH",
            f"tickets/{ticket_number}/telemetry/{telemetry_id}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def remove_telemetry(
        self,
        ticket_number: int,
        telemetry_id: str,
    ) -> dict[str, Any]:
        """Remove a telemetry reference from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_number}/telemetry/{telemetry_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self, ticket_number: int) -> dict[str, Any]:
        """List artifacts on a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_number}/artifacts",
            query_params={"oid": self.oid},
        )

    def add_artifact(
        self,
        ticket_number: int,
        artifact_type: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Add a forensic artifact reference to a ticket."""
        body: dict[str, Any] = {"artifact_type": artifact_type}
        body.update({k: v for k, v in fields.items() if v is not None})
        return self._request(
            "POST",
            f"tickets/{ticket_number}/artifacts",
            query_params={"oid": self.oid},
            body=body,
        )

    def remove_artifact(
        self,
        ticket_number: int,
        artifact_id: str,
    ) -> dict[str, Any]:
        """Remove an artifact from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_number}/artifacts/{artifact_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_ticket(self, ticket_number: int) -> dict[str, Any]:
        """Export a ticket with all its components in a single object.

        Fetches the ticket (with event timeline), detections, entities,
        telemetry, and artifacts, and returns them combined.
        """
        result = self.get_ticket(ticket_number)
        result["detections"] = self.list_detections(ticket_number)
        result["entities"] = self.list_entities(ticket_number)
        result["telemetry"] = self.list_telemetry(ticket_number)
        result["artifacts"] = self.list_artifacts(ticket_number)
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
        """Get real-time ticket counts by status/severity with SLA breaches."""
        return self._request(
            "GET",
            "dashboard/counts",
            query_params={"oids": self.oid},
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Get org ticketing configuration."""
        return self._request("GET", f"config/{self.oid}")

    def set_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update org ticketing configuration."""
        return self._request("PUT", f"config/{self.oid}", body=config)

    # ------------------------------------------------------------------
    # Assignees
    # ------------------------------------------------------------------

    def list_assignees(self) -> dict[str, Any]:
        """Get list of unique assignees across tickets."""
        return self._request(
            "GET",
            "assignees",
            query_params={"oids": self.oid},
        )
