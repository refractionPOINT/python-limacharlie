"""Exfil prevention SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Exfil:
    """Exfil prevention rule management (via replicant)."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        """List all exfil prevention rules."""
        return self._org.service_request("exfil", {"action": "list_rules"})

    def create_watch(self, name: str, event: str, value: str, operator: str, path: str | list[str],
                     tags: list[str] | None = None, platforms: list[str] | None = None) -> dict[str, Any]:
        """Create an exfil watch rule.

        Args:
            name: Rule name.
            event: Event type to watch.
            value: Value to match.
            operator: Comparison operator.
            path: Event path (string with '/' separators or list of segments).
            tags: Optional sensor tag filter.
            platforms: Optional platform filter.

        Returns:
            dict: API response.
        """
        params: dict[str, Any] = {
            "action": "add_watch",
            "name": name,
            "event": event,
            "value": value,
            "operator": operator,
            "path": path.split("/") if isinstance(path, str) else path,
        }
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        return self._org.service_request("exfil", params)

    def create_event(self, name: str, events: list[str], tags: list[str] | None = None,
                     platforms: list[str] | None = None) -> dict[str, Any]:
        """Create an exfil event rule.

        Args:
            name: Rule name.
            events: List of event types to monitor.
            tags: Optional sensor tag filter.
            platforms: Optional platform filter.

        Returns:
            dict: API response.
        """
        params: dict[str, Any] = {
            "action": "add_event_rule",
            "name": name,
            "events": events,
        }
        if tags:
            params["tags"] = tags
        if platforms:
            params["platforms"] = platforms
        return self._org.service_request("exfil", params)

    def delete_event(self, name: str) -> dict[str, Any]:
        """Delete an exfil event rule.

        Args:
            name: Rule name.

        Returns:
            dict: API response.
        """
        return self._org.service_request("exfil", {"action": "remove_event_rule", "name": name})

    def delete_watch(self, name: str) -> dict[str, Any]:
        """Delete an exfil watch rule.

        Args:
            name: Rule name.

        Returns:
            dict: API response.
        """
        return self._org.service_request("exfil", {"action": "remove_watch", "name": name})
