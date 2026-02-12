"""Logging rules SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class LoggingRules:
    """Log collection rule management (via replicant)."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        return self._org.service_request("logging", {"action": "list_rules"})

    def get(self, name: str) -> dict[str, Any] | None:
        rules = self.list()
        if isinstance(rules, dict):
            for rule_name, rule_data in rules.items():
                if rule_name == name:
                    return rule_data
        return None

    def create(self, name: str, patterns: list[str], tags: list[str] | None = None,
               platforms: list[str] | None = None, retention_days: int | None = None,
               delete_after: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {"action": "add_rule", "name": name, "patterns": patterns}
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        if retention_days:
            params["days_retention"] = str(retention_days)
        if delete_after:
            params["is_delete_after"] = "true"
        return self._org.service_request("logging", params)

    def delete(self, name: str) -> dict[str, Any]:
        return self._org.service_request("logging", {"action": "remove_rule", "name": name})
