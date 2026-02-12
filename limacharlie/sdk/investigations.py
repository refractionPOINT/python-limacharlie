"""Investigations SDK for LimaCharlie v2.

Investigations are stored as Hive records under the 'investigation' hive.
The expand endpoint enriches an investigation with full event/detection data.
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

from .hive import Hive, HiveRecord


class Investigations:
    """Investigation management via Hive and the expand API."""

    def __init__(self, org: Organization) -> None:
        self._org = org
        self._hive = Hive(org, "investigation")

    @property
    def client(self) -> Any:
        return self._org.client

    def list(self) -> dict[str, Any]:
        """List all investigations."""
        return self._hive.list()

    def get(self, name: str) -> HiveRecord:
        """Get a single investigation by name."""
        return self._hive.get(name)

    def create(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new investigation.

        Args:
            name: Investigation name.
            data: Investigation data (description, status, priority, etc.).

        Returns:
            dict: API response.
        """
        record = HiveRecord(name)
        record.data = data
        return self._hive.set(record)

    def update(self, name: str, data: dict[str, Any], etag: str | None = None) -> dict[str, Any]:
        """Update an existing investigation.

        Args:
            name: Investigation name.
            data: Updated investigation data.
            etag: Optional etag for optimistic concurrency.

        Returns:
            dict: API response.
        """
        record = HiveRecord(name)
        record.data = data
        if etag is not None:
            record.etag = etag
        return self._hive.set(record)

    def delete(self, name: str) -> dict[str, Any]:
        """Delete an investigation."""
        return self._hive.delete(name)

    def expand(self, investigation_name: str | None = None,
               investigation: dict[str, Any] | None = None) -> dict[str, Any]:
        """Expand an investigation with full event and detection data.

        Provide either investigation_name (to fetch from Hive and expand)
        or investigation (an inline investigation object to expand).

        Args:
            investigation_name: Name of investigation stored in Hive.
            investigation: Inline investigation object.

        Returns:
            dict: Expanded investigation with events and detections maps.
        """
        body: dict[str, Any] = {}
        if investigation_name is not None:
            body["investigation_name"] = investigation_name
        if investigation is not None:
            body["investigation"] = investigation
        return self.client.request(
            "POST", f"orgs/{self._org.oid}/investigation/expand",
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
        )
