"""Investigations SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Investigations:
    """Investigation management."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        return self._org.client

    def list(self) -> dict[str, Any]:
        return self.client.request("GET", f"insight/{self._org.oid}/investigations")

    def get(self, investigation_id: str) -> dict[str, Any]:
        return self.client.request("GET", f"insight/{self._org.oid}/investigations/{investigation_id}")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.client.request("POST", f"insight/{self._org.oid}/investigations",
                                   raw_body=json.dumps(data).encode(),
                                   content_type="application/json")

    def update(self, investigation_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self.client.request("POST", f"insight/{self._org.oid}/investigations/{investigation_id}",
                                   raw_body=json.dumps(data).encode(),
                                   content_type="application/json")

    def delete(self, investigation_id: str) -> dict[str, Any]:
        return self.client.request("DELETE", f"insight/{self._org.oid}/investigations/{investigation_id}")

    def expand(self, investigation_id: str, sid: str | None = None,
               events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Expand an investigation timeline.

        Args:
            investigation_id: Investigation ID.
            sid: Optional sensor ID.
            events: Optional list of events to add.

        Returns:
            dict: API response.
        """
        data: dict[str, Any] = {}
        if sid is not None:
            data["sid"] = sid
        if events is not None:
            data["events"] = events
        return self.client.request("POST", f"insight/{self._org.oid}/investigations/{investigation_id}/expand",
                                   raw_body=json.dumps(data).encode(),
                                   content_type="application/json")
