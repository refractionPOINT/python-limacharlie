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
        """The underlying API client."""
        return self._org.client

    def generate_dr_rule(self, description: str) -> dict[str, Any]:
        """Generate a complete D&R rule from a natural language description.

        Args:
            description: Natural language description of the desired rule.
        """
        return self.client.request("POST", "ai/dr",
                                   raw_body=json.dumps({"query": description}).encode(),
                                   content_type="application/json")

    def generate_detection(self, description: str) -> dict[str, Any]:
        """Generate a detection component from a natural language description.

        Args:
            description: Natural language description of the detection logic.
        """
        return self.client.request("POST", "ai/detection",
                                   raw_body=json.dumps({"query": description}).encode(),
                                   content_type="application/json")

    def generate_response(self, description: str) -> dict[str, Any]:
        """Generate a response component from a natural language description.

        Args:
            description: Natural language description of the response action.
        """
        return self.client.request("POST", "ai/response",
                                   raw_body=json.dumps({"query": description}).encode(),
                                   content_type="application/json")

    def generate_lcql(self, description: str) -> dict[str, Any]:
        """Generate an LCQL query from a natural language description.

        Args:
            description: Natural language description of the query.
        """
        return self.client.request("POST", "ai/lcql",
                                   raw_body=json.dumps({"query": description}).encode(),
                                   content_type="application/json")

    def generate_sensor_selector(self, description: str) -> dict[str, Any]:
        """Generate a sensor selector from a natural language description.

        Args:
            description: Natural language description of the target sensors.
        """
        return self.client.request("POST", "ai/sensor_selector",
                                   raw_body=json.dumps({"query": description}).encode(),
                                   content_type="application/json")

    def generate_playbook(self, description: str) -> dict[str, Any]:
        """Generate a Python playbook from a natural language description.

        Args:
            description: Natural language description of the playbook logic.
        """
        return self.client.request("POST", "ai/playbook/python",
                                   raw_body=json.dumps({"query": description}).encode(),
                                   content_type="application/json")

    def summarize_detection(self, detection_data: dict[str, Any]) -> dict[str, Any]:
        """Generate a human-readable summary of a detection.

        Args:
            detection_data: Detection data dict to summarize.
        """
        return self.client.request("POST", "ai/det_summary",
                                   raw_body=json.dumps({"query": json.dumps(detection_data)}).encode(),
                                   content_type="application/json")
