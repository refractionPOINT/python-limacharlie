"""AI generation SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class AI:
    """AI-powered generation of rules, queries, selectors, and playbooks."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        return self._org.client

    def generate_dr_rule(self, description: str) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/dr",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_detection(self, description: str) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/detection",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_response(self, description: str) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/response",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_lcql(self, description: str) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/lcql",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_sensor_selector(self, description: str) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/sensor_selector",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_playbook(self, description: str) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/playbook/python",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def summarize_detection(self, detection_data: dict[str, Any]) -> dict[str, Any]:
        return self.client.request("POST", f"ai/{self._org.oid}/det_summary",
                                   raw_body=json.dumps(detection_data).encode(),
                                   content_type="application/json")
