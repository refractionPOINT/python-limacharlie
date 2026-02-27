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
        if sort:
            qp["sort"] = sort
        if order:
            qp["order"] = order
        if page_size is not None:
            qp["page_size"] = str(page_size)
        if page_token:
            qp["page_token"] = page_token
        return self._request("GET", "tickets", query_params=qp)

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Get a single ticket with its full event timeline."""
        return self._request(
            "GET",
            f"tickets/{ticket_id}",
            query_params={"oid": self.oid},
        )

    def update_ticket(self, ticket_id: str, **fields: Any) -> dict[str, Any]:
        """Update a ticket.

        Accepted fields: status, assignee, classification,
        escalation_group, investigation_id, summary, conclusion.
        """
        return self._request(
            "PATCH",
            f"tickets/{ticket_id}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def add_note(
        self,
        ticket_id: str,
        content: str,
        note_type: str | None = None,
    ) -> dict[str, Any]:
        """Add a note to a ticket."""
        body: dict[str, Any] = {"content": content}
        if note_type:
            body["note_type"] = note_type
        return self._request(
            "POST",
            f"tickets/{ticket_id}/notes",
            query_params={"oid": self.oid},
            body=body,
        )

    def bulk_update(
        self,
        ticket_ids: list[str],
        **fields: Any,
    ) -> dict[str, Any]:
        """Bulk update up to 200 tickets."""
        body: dict[str, Any] = {
            "oid": self.oid,
            "ticket_ids": ticket_ids,
            "update": {k: v for k, v in fields.items() if v is not None},
        }
        return self._request("POST", "tickets/bulk-update", body=body)

    def merge(
        self,
        target_ticket_id: str,
        source_ticket_ids: list[str],
    ) -> dict[str, Any]:
        """Merge source tickets into a target ticket."""
        return self._request(
            "POST",
            "tickets/merge",
            body={
                "oid": self.oid,
                "target_ticket_id": target_ticket_id,
                "source_ticket_ids": source_ticket_ids,
            },
        )

    # ------------------------------------------------------------------
    # Detections
    # ------------------------------------------------------------------

    def list_detections(self, ticket_id: str) -> dict[str, Any]:
        """List detections linked to a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_id}/detections",
            query_params={"oid": self.oid},
        )

    def add_detection(
        self,
        ticket_id: str,
        detection_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Link a detection to a ticket."""
        body: dict[str, Any] = {"detection_id": detection_id}
        body.update({k: v for k, v in fields.items() if v is not None})
        return self._request(
            "POST",
            f"tickets/{ticket_id}/detections",
            query_params={"oid": self.oid},
            body=body,
        )

    def remove_detection(
        self,
        ticket_id: str,
        detection_id: str,
    ) -> dict[str, Any]:
        """Remove a detection link from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_id}/detections/{detection_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Entities (IOCs)
    # ------------------------------------------------------------------

    def list_entities(self, ticket_id: str) -> dict[str, Any]:
        """List entities on a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_id}/entities",
            query_params={"oid": self.oid},
        )

    def add_entity(
        self,
        ticket_id: str,
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
            f"tickets/{ticket_id}/entities",
            query_params={"oid": self.oid},
            body=body,
        )

    def update_entity(
        self,
        ticket_id: str,
        entity_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update an entity on a ticket."""
        return self._request(
            "PATCH",
            f"tickets/{ticket_id}/entities/{entity_id}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def remove_entity(
        self,
        ticket_id: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Remove an entity from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_id}/entities/{entity_id}",
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

    def list_telemetry(self, ticket_id: str) -> dict[str, Any]:
        """List telemetry references on a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_id}/telemetry",
            query_params={"oid": self.oid},
        )

    def add_telemetry(
        self,
        ticket_id: str,
        atom: str,
        sid: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Link a telemetry event reference to a ticket."""
        body: dict[str, Any] = {"atom": atom, "sid": sid}
        body.update({k: v for k, v in fields.items() if v is not None})
        return self._request(
            "POST",
            f"tickets/{ticket_id}/telemetry",
            query_params={"oid": self.oid},
            body=body,
        )

    def update_telemetry(
        self,
        ticket_id: str,
        telemetry_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update a telemetry reference on a ticket."""
        return self._request(
            "PATCH",
            f"tickets/{ticket_id}/telemetry/{telemetry_id}",
            query_params={"oid": self.oid},
            body={k: v for k, v in fields.items() if v is not None},
        )

    def remove_telemetry(
        self,
        ticket_id: str,
        telemetry_id: str,
    ) -> dict[str, Any]:
        """Remove a telemetry reference from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_id}/telemetry/{telemetry_id}",
            query_params={"oid": self.oid},
        )

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self, ticket_id: str) -> dict[str, Any]:
        """List artifacts on a ticket."""
        return self._request(
            "GET",
            f"tickets/{ticket_id}/artifacts",
            query_params={"oid": self.oid},
        )

    def add_artifact(
        self,
        ticket_id: str,
        artifact_type: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Add a forensic artifact reference to a ticket."""
        body: dict[str, Any] = {"artifact_type": artifact_type}
        body.update({k: v for k, v in fields.items() if v is not None})
        return self._request(
            "POST",
            f"tickets/{ticket_id}/artifacts",
            query_params={"oid": self.oid},
            body=body,
        )

    def remove_artifact(
        self,
        ticket_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        """Remove an artifact from a ticket."""
        return self._request(
            "DELETE",
            f"tickets/{ticket_id}/artifacts/{artifact_id}",
            query_params={"oid": self.oid},
        )

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
