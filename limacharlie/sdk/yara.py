"""YARA SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Yara:
    """YARA scanning and rule management (via replicant)."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def scan(self, sid: str, rule: str, timeout: int | None = None) -> dict[str, Any]:
        """Run ad-hoc YARA scan on a sensor.

        Args:
            sid: Sensor ID.
            rule: YARA rule content.
            timeout: Scan timeout.

        Returns:
            dict: Scan results.
        """
        params: dict[str, Any] = {"action": "scan", "sid": str(sid), "rule": rule}
        if timeout:
            params["timeout"] = str(timeout)
        return self._org.service_request("yara", params)

    def list_rules(self) -> dict[str, Any]:
        return self._org.service_request("yara", {"action": "list_rules"})

    def add_rule(self, name: str, sources: list[str], tags: list[str] | None = None,
                 platforms: list[str] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"action": "add_rule", "name": name, "sources": json.dumps(sources)}
        if tags:
            params["tags"] = json.dumps(tags)
        if platforms:
            params["platforms"] = json.dumps(platforms)
        return self._org.service_request("yara", params)

    def delete_rule(self, name: str) -> dict[str, Any]:
        return self._org.service_request("yara", {"action": "remove_rule", "name": name})

    def list_sources(self) -> dict[str, Any]:
        return self._org.service_request("yara", {"action": "list_sources"})

    def get_source(self, name: str) -> dict[str, Any]:
        return self._org.service_request("yara", {"action": "get_source", "name": name})

    def add_source(self, name: str, source: str) -> dict[str, Any]:
        return self._org.service_request("yara", {"action": "add_source", "name": name, "source": source})

    def delete_source(self, name: str) -> dict[str, Any]:
        return self._org.service_request("yara", {"action": "remove_source", "name": name})
