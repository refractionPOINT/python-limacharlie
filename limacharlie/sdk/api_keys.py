"""API Keys SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class ApiKeys:
    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> dict[str, Any]:
        return self._org.get_api_keys()

    def create(self, name: str, permissions: list[str], ip_range: str | None = None) -> dict[str, Any]:
        return self._org.add_api_key(name, permissions, ip_range=ip_range)

    def delete(self, key_hash: str) -> dict[str, Any]:
        return self._org.remove_api_key(key_hash)
