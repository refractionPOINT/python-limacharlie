"""Integrity monitoring SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Integrity:
    """Integrity monitoring rule management (via replicant)."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        return self._org.service_request("integrity", {"action": "list_rules"})

    def get(self, name: str) -> dict[str, Any] | None:
        rules = self.list()
        if isinstance(rules, dict):
            for rule_name, rule_data in rules.items():
                if rule_name == name:
                    return rule_data
        return None

    def create(self, name: str, patterns: list[str], tags: list[str] | None = None,
               platforms: list[str] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"action": "add_rule", "name": name, "patterns": patterns}
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        return self._org.service_request("integrity", params)

    def delete(self, name: str) -> dict[str, Any]:
        return self._org.service_request("integrity", {"action": "remove_rule", "name": name})
