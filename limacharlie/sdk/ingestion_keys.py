"""Ingestion Keys SDK for LimaCharlie v2."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class IngestionKeys:
    def __init__(self, org: Organization) -> None:
        self._org = org

    def list(self) -> Any:
        return self._org.get_ingestion_keys()

    def create(self, name: str) -> dict[str, Any]:
        return self._org.create_ingestion_key(name)

    def delete(self, name: str) -> dict[str, Any]:
        return self._org.delete_ingestion_key(name)
